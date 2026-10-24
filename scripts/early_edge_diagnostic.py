"""Non-enrolling OBSERVE throughput + same-state quote parity. No prospective DB."""

import argparse
import asyncio
from collections import Counter, OrderedDict
import json
from pathlib import Path
import sys
import tempfile
import time
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import ROOT, load_settings
from backend.app.early_edge import signal_snapshot, manifest, digest, fx_value
from backend.app.early_edge_design import risk_set
from backend.app.early_edge_parity import artifact_identity
from backend.app.early_edge_quotes import ResearchExecutionOracle
from backend.app.early_edge_telemetry import OperationalTelemetry, track_http_errors
from backend.app.early_edge_runtime import (
    ObservationCoverage,
    attach_observer,
    UsdReference,
    refresh_reference,
)


class TradeDiagnostics:
    """Observational wrapper delegates exactly once; fixed counters, bounded mint hashes."""

    def __init__(self, submit):
        self.submit = submit
        self.counts: Counter[str] = Counter()
        self.known_unit_mints: set[str] = set()

    def __call__(self, event):
        accepted = self.submit(event)
        if accepted and event.kind == "trade":
            self.counts["buy" if event.side == "buy" else "sell"] += 1
            valid = event.evidence.get("units_valid") is True
            unit = event.currency if valid and event.currency in ("SOL", "USDC") else "unknown"
            self.counts[unit] += 1
            if unit != "unknown" and len(self.known_unit_mints) < 2048:
                import hashlib

                self.known_unit_mints.add(hashlib.sha256(event.mint.encode()).hexdigest())
        return accepted


class DryObserver:
    def __init__(self, settings, plan):
        self.settings, self.plan = settings, plan
        self.coverage = ObservationCoverage(settings.max_candidates)
        self.counts: Counter = Counter()
        self.seen = OrderedDict()
        self.used_controls = OrderedDict()
        self.failed = False
        self.error = None
        self.clock = time.time
        self.universe: Callable = lambda now: []
        self.health: Callable = lambda: {}
        self.tier = lambda mint: "unknown"
        self.telemetry = None

    def observe(self, token, view, now):
        self.coverage.observe(token, view, now, self.settings, self.health(), self.tier(token.mint))
        if self.telemetry:
            self.telemetry.observe(token, now)
        s = signal_snapshot(token, view, now, self.settings)
        if s and s["action"] == "EARLY_OPPORTUNITY" and token.mint not in self.seen:
            self.seen[token.mint] = None
            if len(self.seen) > 10000:
                self.seen.popitem(last=False)
                self.counts["dedup_capacity_censoring"] += 1
            candidates = [signal_snapshot(t, v, now, self.settings) for t, v in self.universe(now)]
            available = risk_set(s, candidates, self.plan, self.used_controls)
            if self.telemetry:
                self.telemetry.early(s, available)
            if available:
                self.used_controls[available[0]["mint"]] = None
                if len(self.used_controls) > 10000:
                    self.used_controls.popitem(last=False)
                    self.counts["control_dedup_capacity_censoring"] += 1
                self.counts["matched_controls"] += 1
            self.counts["early_signals"] += 1
            self.counts["potential_controls"] += len(available)
            self.counts["unmatched_treatments"] += not available

    def created(self, event):
        self.coverage.counts["discovered"] += 1

    def migration(self, event):
        pass  # No lifecycle/candidate mutation or research enrollment.


async def diagnostic(settings, seconds, node_path, pools, max_samples, progress=None, frozen=None, run_directory=None):
    from backend.app.engine import RadarEngine
    import os

    if (
        settings.mode != "OBSERVE"
        or os.getenv("RADAR_COHORT")
        or os.getenv("PUMPPORTAL_ENABLED", "false").lower() == "true"
    ):
        raise ValueError("OBSERVE-only diagnostic; existing cohort selection forbidden")

    artifacts = artifact_identity(node_path) if node_path else []
    plan = manifest(settings, draft=True)
    if frozen:
        from backend.app.early_edge import identity

        plan = json.loads(Path(frozen).read_text())
        if plan.get("collectable") is not False or plan["identity"] != identity(settings):
            raise ValueError("Frozen clean diagnostic identity mismatch")
    from contextlib import nullcontext

    if run_directory is not None:
        Path(run_directory).mkdir(parents=True, exist_ok=False)
    directory_context = (nullcontext(str(run_directory)) if run_directory is not None else
                         tempfile.TemporaryDirectory(prefix="early-edge-throughput-"))
    with directory_context as temp:
        engine = RadarEngine(settings, Path(temp) / "diagnostic-engine.db")
        trade_diagnostic = TradeDiagnostics(engine.onchain.submit)
        engine.onchain.submit = trade_diagnostic
        evidence_samples = []
        observer = DryObserver(settings, plan)
        reference = UsdReference()
        reference_stop = asyncio.Event()
        reference_task = None
        detach = attach_observer(engine, observer)
        oracle = ResearchExecutionOracle(engine.rpc)
        records: list[dict] = []
        attempted: Counter = Counter()
        started = time.time()
        telemetry = OperationalTelemetry(settings, started)
        observer.telemetry = telemetry
        untrack = track_http_errors(engine.rpc.client, telemetry.rpc_errors)
        clean_shutdown = False
        stop_reason = None
        previous_tick = time.time()
        drift = False
        last_check = 0.0
        quote_venues: Counter[str] = Counter()
        peak_rss = 0
        peak_cpu = 0
        cpu_total = 0
        samples = 0
        import psutil

        process = psutil.Process()
        process.cpu_percent()
        from backend.app.early_edge_scheduling import SamplerBudget, quote_success

        sample_budget = SamplerBudget(started, seconds, max_samples)
        workers = []
        scheduler_stop = asyncio.Event()
        next_probe = 0.0
        current_round = -1
        round_start_index = 0
        round_interval = max(180, seconds / max(1, max_samples // 12))
        quality: list[dict] = []
        async def sample_states():
            nonlocal current_round, round_start_index, next_probe
            while not scheduler_stop.is_set():
                now = time.time()
                round_number = int((now - started) // round_interval)
                if round_number != current_round:
                    current_round = round_number
                    attempted.clear()
                    round_start_index = len(records)
                if sample_budget.available(now) and now >= next_probe and not telemetry.entry_pending(now):
                    choices = []
                    for mint, pool in pools:
                        if attempted[("PUMPSWAP", mint)] < 3:
                            choices.append((attempted[("PUMPSWAP", mint)], "PUMPSWAP", mint, pool))
                    for t in list(engine.tokens.values()):
                        if (
                            t.graduation is None
                            and t.last_curve > 0
                            and t.verified_quote_mint
                            and attempted[("PUMP", t.mint)] < 3
                        ):
                            choices.append((attempted[("PUMP", t.mint)], "PUMP", t.mint, None))
                    # Complete repeated states for the first bounded pool/mint set before expanding.
                    chosen_mints = {
                        r["mint"]
                        for r in records[round_start_index:]
                        if r["venue"] == "PUMP" and quote_success(r)
                    }
                    choices = [
                        c for c in choices if c[1] != "PUMP" or c[2] in chosen_mints or len(chosen_mints) < 2
                    ]
                    if choices:
                        _, venue, mint, pool = sorted(choices, key=lambda c: (c[1] != "PUMPSWAP", c[2]))[0]
                        assert sample_budget.claim(now)
                        attempted[(venue, mint)] += 1
                        # Probe helper minimum 2 is for full diagnostics; a single scheduled state here.
                        quote_venues[venue + ":attempts"] += 1
                        quote_started = time.time()
                        try:
                            from backend.app.early_edge_parity import sdk_compare, expected
                            from backend.app.early_edge_quotes import quote_budget, WSOL

                            obs = await oracle.observe(mint, venue, pool, diagnostic_pool=venue == "PUMPSWAP")
                            try:
                                usd = fx_value(reference.snapshot(), obs.data["quote_mint"], obs.acquired_at)
                                fx_value(reference.snapshot(), WSOL, obs.acquired_at)
                                usd_valid = True
                            except ValueError:
                                usd = 150 if obs.data["quote_mint"] == WSOL else 1
                                usd_valid = False
                            budget = quote_budget(4, usd, obs.data["quote_mint"])
                            parity = (
                                (await sdk_compare(obs.data, budget, node_path))
                                if node_path
                                else dict(python=expected(obs.data, budget), quote_valid=True)
                            )
                            telemetry.add("quote_state_acquisition_delay", obs.acquired_at - obs.requested_at)
                            quote_venues[venue + ":success"] += 1
                            records.append(
                                dict(
                                    parity,
                                    venue=venue,
                                    mint=mint,
                                    pool=pool,
                                    slot=obs.slot,
                                    commitment=obs.commitment,
                                    acquired_at=obs.acquired_at,
                                    attempt_started_at=quote_started,
                                    completed_at=time.time(),
                                    round_number=round_number,
                                    usd_reference_valid=usd_valid,
                                    quote_mint=obs.data["quote_mint"],
                                    usd_reference=reference.snapshot().get(obs.data["quote_mint"]),
                                    account_hashes=obs.account_hashes,
                                    identity_address=obs.identity_address,
                                    directions=["buy", "sell"] if venue == "PUMP" else ["sell"],
                                    notional="Diagnostic raw quote budget only; no USD fill claim",
                                )
                            )
                        except asyncio.CancelledError:
                            quote_venues[venue + ":unavailable"] += 1
                            records.append(dict(venue=venue, mint=mint, pool=pool, match=False,
                                attempt_started_at=quote_started, completed_at=time.time(),
                                round_number=round_number, error_category="CANCELLED",
                                unavailable_reason="UNAVAILABLE_INFRASTRUCTURE"))
                            raise
                        except Exception as exc:
                            quote_venues[venue + ":unavailable"] += 1
                            telemetry.add("quote_unavailable_delay", time.time() - quote_started)
                            attempted[(venue, mint)] = 3
                            records.append(
                                dict(
                                    venue=venue,
                                    mint=mint,
                                    pool=pool,
                                    match=False,
                                    error_category=type(exc).__name__,
                                    attempt_started_at=quote_started,
                                    completed_at=time.time(),
                                    round_number=round_number,
                                    unavailable_reason=getattr(exc, "reason", None),
                                )
                            )
                        next_probe = time.time() + 5
                await asyncio.sleep(0.25)

        async def entry_probes():
            while not scheduler_stop.is_set():
                await telemetry.probe_entries(oracle, reference, engine, time.time())
                await asyncio.sleep(0.1)

        try:
            await engine.start()
            workers = [asyncio.create_task(sample_states(), name="diagnostic-sampler"),
                       asyncio.create_task(entry_probes(), name="diagnostic-entry-probes")]
            reference_task = asyncio.create_task(refresh_reference(reference, reference_stop))
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                if (time.time() - previous_tick > settings.max_data_age_seconds
                        or time.time() < previous_tick):
                    telemetry.counts["observation_discontinuity_stop"] += 1
                    stop_reason = "OBSERVATION_DISCONTINUITY"
                    break
                previous_tick = time.time()
                if not engine.running or any(task.done() for task in workers):
                    telemetry.counts["operational_stop"] += 1
                    stop_reason = "STORAGE_STOP" if engine.storage_stopped else "WORKER_STOP"
                    break
                if observer.failed:
                    raise RuntimeError("Diagnostic observation failure")
                now = time.time()
                if frozen and now - last_check >= 30:
                    from backend.app.early_edge import identity

                    drift = identity(settings) != plan["identity"]
                    last_check = now
                    if drift:
                        raise ValueError("Frozen source/config drift")
                rss = process.memory_info().rss / 1024**2
                cpu = process.cpu_percent()
                peak_rss = max(peak_rss, rss)
                peak_cpu = max(peak_cpu, cpu)
                cpu_total += cpu
                samples += 1
                telemetry.sample(engine, time.time(), rss, cpu, Path(temp))
                telemetry.references(reference, time.time())
                if not quality or now - quality[-1]["ts"] >= 30:
                    statuses = Counter(engine.trade_status(t, now) for t in engine.tokens.values())
                    evidence_samples.append(
                        dict(
                            at=now,
                            counts=dict(statuses),
                            max_clean_seconds=max(
                                (engine.trade_coverage_seconds(t, now) for t in engine.tokens.values()),
                                default=0,
                            ),
                        )
                    )
                    if len(evidence_samples) > 2881:
                        evidence_samples.pop(0)
                    quality.append(
                        dict(
                            ts=now,
                            rpc=dict(engine.rpc.health),
                            recovery=json.loads(json.dumps(engine.recovery.snapshot())),
                            queue_depth=len(engine.queue.heap),
                            queue=engine.queue.snapshot(),
                            active=len(engine.tokens),
                            capacity_pressure=len(engine.tokens) >= settings.max_candidates,
                            metrics=dict(engine.metrics),
                        )
                    )
                    if progress:
                        payload = dict(
                            elapsed_seconds=now - started,
                            telemetry=telemetry.report(),
                            launches=observer.coverage.counts.get("discovered", 0),
                            early=dict(observer.counts),
                            pump=dict(engine.onchain.health),
                            rpc=dict(engine.rpc.health),
                            recovery=json.loads(json.dumps(engine.recovery.snapshot())),
                            queue_depth=len(engine.queue.heap),
                            drift=drift,
                        )
                        target = Path(progress)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        temporary = target.with_suffix(".tmp")
                        temporary.write_text(json.dumps(payload, allow_nan=False))
                        temporary.replace(target)
                    if len(quality) > 2881:
                        quality.pop(0)
                await asyncio.sleep(0.5)
            clean_shutdown = engine.running and stop_reason is None
        finally:
            scheduler_stop.set()
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            detach()
            reference_stop.set()
            if reference_task:
                reference_task.cancel()
                await asyncio.gather(reference_task, return_exceptions=True)
            await reference.close()
            for mint, row in list(telemetry.signals.items()):
                telemetry.finish_signal(mint, row, time.time())
            untrack()
            await engine.stop()
        if frozen:
            from backend.app.early_edge import identity

            drift = identity(settings) != plan["identity"]
        elapsed = time.time() - started
        counts = dict(observer.counts)
        coverage = dict(observer.coverage.counts)
        launches = coverage.get("discovered", 0)
        rejection: Counter = Counter()
        for t in engine.tokens.values():
            f = t.features.get("180", {})
            if not f.get("units_valid"):
                rejection["trade_units_unavailable"] += 1
            if t.security.get("hard_failures"):
                rejection["security_hard_failure"] += 1
            if t.graduation is not None:
                rejection["already_graduated"] += 1
            if t.state.value in ("REJECTED", "EXPIRED"):
                rejection["rejected_or_expired"] += 1
            if t.disagreement:
                rejection["provider_disagreement"] += 1
            if f.get("creator_sell_volume", 0) > 0:
                rejection["creator_selling"] += 1
        result = dict(
            namespace="EARLY_EDGE_NON_ENROLLING_DIAGNOSTIC",
            operational=telemetry.report(),
            quote_by_venue=dict(quote_venues),
            quote_consistency=dict(oracle.diagnostics),
            clean_shutdown=clean_shutdown,
            source_config_drift=drift,
            operational_stop_reason=stop_reason,
            trade_evidence_blocker_counts=dict(Counter(
                reason for token in engine.tokens.values()
                for reason, blocked in engine.trade_evidence_blockers(token, time.time()).items() if blocked)),
            manifest_proposal_hash=digest(plan),
            expiry=dict(engine.expiry_metrics),
            continuity=dict(engine.trade_continuity),
            evidence_pipeline=engine.accounting.snapshot(engine.queue),
            storage_audit=dict(engine.db.storage_audit),
            storage_stopped=engine.storage_stopped,
            database_retained=run_directory is not None,
            database_path=str(Path(temp) / "diagnostic-engine.db") if run_directory is not None else None,
            queue_drops=dict(trade=engine.queue.dropped_trades, critical=engine.queue.dropped_critical),
            live_readonly=True,
            collectable_cohort_constructed=False,
            prospective_treatment_control_outcomes_written=0,
            completed_at=time.time(),
            duration_seconds=elapsed,
            source_hash=plan["identity"]["source_hash"],
            config_hash=plan["identity"]["config_hash"],
            artifacts_verified=bool(artifacts),
            artifacts=artifacts,
            launches=launches,
            launches_per_hour=launches * 3600 / elapsed,
            **counts,
            coverage_counts=coverage,
            adequately_observed_per_hour=coverage.get("adequately_observed", 0) * 3600 / elapsed,
            early_signals_per_hour=counts.get("early_signals", 0) * 3600 / elapsed,
            controls_per_early=counts.get("potential_controls", 0) / counts["early_signals"]
            if counts.get("early_signals")
            else None,
            unmatched_rate=counts.get("unmatched_treatments", 0) / counts["early_signals"]
            if counts.get("early_signals")
            else None,
            provider_gap_samples=sum(not s["rpc"].get("connected") for s in quality),
            resource_pressure_samples=sum(s["metrics"].get("resource_pressure", False) for s in quality),
            capacity_pressure_samples=sum(s["capacity_pressure"] for s in quality),
            final_queue=engine.queue.snapshot(),
            final_pump_health=dict(engine.onchain.health),
            eligibility_rejection_categories=dict(rejection),
            observation_ready_tracked=sum(r["readiness"]["ready"] for r in observer.coverage.active.values()),
            final_usd_reference_health=dict(reference.health),
            usd_reference_preflight=reference.snapshot(),
            executable_usd_quote_successes=sum(
                r.get("usd_reference_valid", False) and r.get("quote_valid", r.get("match", False))
                for r in records
            ),
            usd_reference_unavailable_observations=sum(
                r.get("quote_valid", r.get("match", False)) and not r.get("usd_reference_valid", False)
                for r in records
            ),
            trade_acquisition=dict(trade_diagnostic.counts),
            known_unit_mint_count=len(trade_diagnostic.known_unit_mints),
            processed_buy_sell=dict(engine.trade_observations),
            evidence_samples=evidence_samples,
            final_rpc_health=dict(engine.rpc.health),
            final_recovery_health=engine.recovery.snapshot(),
            quote_attempts=len(records),
            quote_success_rate=sum(
                r.get("quote_valid", r.get("match", False)) and r.get("usd_reference_valid", False)
                for r in records
            )
            / len(records)
            if records
            else None,
            sdk_quote_success_rate=sum("official_sdk" in r for r in records) / len(records)
            if records and node_path
            else None,
            quote_sampling_round_interval_seconds=round_interval,
            estimated_hours_for_100=100 / (counts.get("early_signals", 0) * 3600 / elapsed)
            if counts.get("early_signals")
            else None,
            quote_successes=sum("python" in r for r in records),
            reference_verification_enabled=bool(node_path),
            quote_parity_failures=sum(r.get("match") is False and "official_sdk" in r for r in records)
            if node_path
            else None,
            quote_unavailable=sum("error_category" in r for r in records),
            records=records,
            quality_samples=quality,
            active_candidate_coverage=observer.coverage.active,
            peak_rss_mb=peak_rss,
            mean_cpu_pct=cpu_total / samples if samples else None,
            peak_cpu_pct=peak_cpu,
            smoke_only=seconds < 21600,
            limitation="Short runs cannot estimate N=100 reliably. SDK-only fallback budgets when USD reference missing never count as executable USD quote successes. Periodic bounded state samples are not a saturated load test. No cohort enrollment or outcomes.",
        )
        result["report_hash"] = digest(result)
        return result


def build_parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seconds", type=int, default=120)
    p.add_argument(
        "--node-path", type=Path, help="Opt-in isolated official SDK reference; omitted in normal runs"
    )
    p.add_argument(
        "--pool", action="append", default=[], help="base_mint:pool, independently verified before quotes"
    )
    p.add_argument("--max-state-samples", type=int, default=12)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--progress", type=Path)
    p.add_argument("--run-directory", type=Path, help="New durable diagnostic directory; defaults beside output")
    p.add_argument("--frozen-plan", type=Path)
    return p


def main():
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    p = build_parser()
    a = p.parse_args()
    if not 1 <= a.seconds <= 86400 or not 1 <= a.max_state_samples <= 120:
        p.error("Bounded duration/sample count required")
    settings = load_settings()
    if settings.mode != "OBSERVE":
        p.error("OBSERVE only")
    pools = [tuple(x.split(":")) for x in a.pool]
    if any(len(x) != 2 for x in pools) or len(pools) > 4:
        p.error("At most four mint:pool inputs")
    r = asyncio.run(
        diagnostic(settings, a.seconds, a.node_path, pools, a.max_state_samples, a.progress, a.frozen_plan,
                   a.run_directory or a.output.with_suffix(".run"))
    )
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open("x") as f:
        json.dump(r, f, indent=2, allow_nan=False)
    print(
        json.dumps(
            {
                k: v
                for k, v in r.items()
                if k
                not in (
                    "records",
                    "quality_samples",
                    "active_candidate_coverage",
                    "artifacts",
                    "final_queue",
                    "final_recovery_health",
                    "final_pump_health",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps(dict(error_category=type(exc).__name__, diagnostic_failed=True)), file=sys.stderr)
        raise SystemExit(1) from None

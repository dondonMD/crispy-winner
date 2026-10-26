"""Opt-in isolated descriptive pilot. Default prints a non-collectable protocol only."""

import argparse
import asyncio
from collections import Counter
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE = "bd56824676f87c52c5d507ba6c669291ee1575c0"
BRANCH = "remediation/early-edge-evidence-readiness"
HORIZONS = (15, 30, 60, 180, 300)
TOTAL = 1200
CAPTURE = 880
GRACE = 20
CLASSES = (
    "ACTIVE EMERGING BULLISH",
    "BULLISH DEVELOPING",
    "BUYING COOLING / WAIT",
    "BEARISH PRESSURE",
    "PULLBACK WATCH",
    "NEUTRAL / WAIT",
    "AVOID",
    "TOO EXTENDED",
    "INSUFFICIENT DATA",
    "STALE",
    "UNASSESSED",
)
UNRELATED = frozenset(
    (
        "backend/tests/test_endurance_harness.py",
        "scripts/validate_evidence_load.py",
        "backend/docs/per-token-evidence-investigation-20261025.md",
        "backend/tests/test_computation_profile.py",
        "backend/tests/test_consumer_trace.py",
        "scripts/consumer_trace.py",
    )
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def protocol():
    return dict(
        version=1,
        collectable=False,
        mode="OBSERVE",
        duration_seconds=TOTAL,
        first_class_measurement_cutoff_seconds=CAPTURE,
        horizons=HORIZONS,
        endpoint_delay_seconds=GRACE,
        classes=CLASSES,
        unit="first observed token/class; dependent within mint",
        measurement="gross indicative reserve-mark movement only; no execution or net returns",
        max_tokens=1000,
        max_measurements=2000,
        max_records=24000,
        max_ledger_bytes=64 * 1048576,
        hard_stop_rss_mb=500,
        hard_stop_combined_mb=640,
        min_free_bytes=512 * 1048576,
        earlier_discovery_after_cutoff="retained, not assigned outcomes",
        primary_inference="NONE; operational/descriptive pilot, no edge or approval conclusion",
        no_backfill=True,
        baseline_parent_forbidden=BASE,
        required_new_published_successor=True,
        PRE_COHORT_READY="NO",
        phase4_authorized=False,
    )


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


class PilotRefusal(ValueError):
    """Only fixed non-sensitive preflight messages may be printed by the CLI."""


def verify_source(expected):
    if not re.fullmatch("[0-9a-f]{40}", expected or "") or expected == BASE:
        raise PilotRefusal("Require explicit full successor SHA; parent baseline is forbidden")
    if git("branch", "--show-current") != BRANCH or git("rev-parse", "HEAD") != expected:
        raise PilotRefusal("Branch/HEAD does not match expected successor")
    if git("rev-parse", f"refs/remotes/origin/{BRANCH}") != expected:
        raise PilotRefusal("Expected SHA does not match fetched approved origin branch")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE, expected], cwd=ROOT, check=True, capture_output=True
    )
    changed = set(filter(None, git("diff", "--name-only", "HEAD").splitlines()))
    untracked = set(filter(None, git("ls-files", "--others", "--exclude-standard").splitlines()))
    if (changed | untracked) - UNRELATED:
        raise PilotRefusal("Unpublished source changes outside preserved unrelated allowlist")
    tracked = git("ls-files").splitlines()
    if "scripts/signal_quality_pilot.py" not in tracked:
        raise PilotRefusal("Pilot harness is not published tracked source")
    files = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in sorted(set(tracked) | ((changed | untracked) & UNRELATED))
        if (ROOT / name).is_file()
    }
    return dict(
        sha=expected,
        branch=BRANCH,
        files=files,
        private_environment_file_hash=hashlib.sha256((ROOT / ".env").read_bytes()).hexdigest()
        if (ROOT / ".env").is_file()
        else None,
        provider_environment_hash=hashlib.sha256(
            canonical(
                {
                    k: os.getenv(k)
                    for k in (
                        "HELIUS_API_KEY",
                        "SOLANA_RPC_HTTP_URL",
                        "SOLANA_RPC_WSS_URL",
                        "PUMPPORTAL_ENABLED",
                        "RADAR_MODE",
                        "RADAR_CONFIG",
                    )
                }
            ).encode()
        ).hexdigest(),
        configuration_file_hash=hashlib.sha256(
            Path(os.getenv("RADAR_CONFIG", str(ROOT / "config/conservative.yaml"))).read_bytes()
        ).hexdigest(),
        allowed_local_changes=sorted(changed | untracked),
        remote_verification="locally fetched origin ref; fetch separately before execution",
    )


def source_unchanged(source):
    try:
        return verify_source(source["sha"]) == source
    except (ValueError, OSError, subprocess.SubprocessError):
        return False


class StopPilot(RuntimeError):
    pass


class Ledger:
    """Bounded append-only hash chain; one synchronous fsync at each controller tick."""

    def __init__(self, path):
        self.path = Path(path)
        self.file = self.path.open("xb", buffering=0)
        self.sequence = 0
        self.previous = "0" * 64
        self.buffer = []
        self.buffer_bytes = 0
        self.bytes = 0
        self.failed = False

    def emit(self, kind, payload):
        if self.failed:
            raise StopPilot("LEDGER_ALREADY_FAILED")
        if self.sequence >= 24000 or len(self.buffer) >= 512:
            raise StopPilot("RECORD_CAPACITY")
        row = dict(sequence=self.sequence + 1, previous=self.previous, kind=kind, payload=payload)
        digest = hashlib.sha256(canonical(row).encode()).hexdigest()
        encoded = (canonical(dict(row, sha256=digest)) + "\n").encode()
        if len(encoded) > 16384 or self.buffer_bytes + len(encoded) > 2 * 1048576:
            raise StopPilot("BUFFER_OR_RECORD_BYTES")
        if self.bytes + self.buffer_bytes + len(encoded) > 64 * 1048576 - 4096:
            raise StopPilot("LEDGER_BYTE_LIMIT")
        self.sequence += 1
        self.previous = digest
        self.buffer.append(encoded)
        self.buffer_bytes += len(encoded)
        return self.sequence

    def flush(self):
        if self.failed:
            raise StopPilot("LEDGER_ALREADY_FAILED")
        if not self.buffer:
            return
        data = b"".join(self.buffer)
        try:
            offset = 0
            while offset < len(data):
                written = self.file.write(data[offset:])
                if not written:
                    raise OSError("short ledger write")
                offset += written
            os.fsync(self.file.fileno())
        except Exception:
            self.failed = True
            raise
        self.bytes += len(data)
        self.buffer.clear()
        self.buffer_bytes = 0

    def close(self):
        try:
            if not self.failed:
                self.flush()
        finally:
            self.file.close()


def verify_ledger(path):
    """Offline integrity reader; never repairs a partial tail or restarts collection."""
    if Path(path).stat().st_size > 64 * 1048576:
        raise ValueError("Ledger exceeds declared byte capacity")
    previous = "0" * 64
    count = 0
    last = None
    units: dict = {}
    pairs = set()
    populations: Counter = Counter()
    outcomes: Counter = Counter()
    with Path(path).open("rb") as stream:
        for line in stream:
            if count >= 24000 or len(line) > 16384 or not line.endswith(b"\n"):
                raise ValueError("Partial, oversized or over-capacity ledger")
            row = json.loads(line)
            digest = row.pop("sha256")
            if (
                row["sequence"] != count + 1
                or row["previous"] != previous
                or hashlib.sha256(canonical(row).encode()).hexdigest() != digest
            ):
                raise ValueError("Ledger sequence/hash failure")
            payload = row["payload"]
            if row["kind"] == "TRANSITION" and payload["measurement_scheduled"]:
                if len(units) >= 2000:
                    raise ValueError("Measurement capacity exceeded")
                unit = (payload["mint"], payload["classification"])
                if unit in units.values():
                    raise ValueError("Duplicate token/class measurement")
                units[row["sequence"]] = unit
                populations[payload["classification"] + "|total"] += 1
                populations[
                    payload["classification"]
                    + ("|baseline_valid" if payload["baseline"] else "|baseline_missing")
                ] += 1
            if row["kind"] == "OUTCOME":
                pair = (payload["transition_id"], payload["horizon"])
                if (
                    pair in pairs
                    or pair[0] not in units
                    or pair[1] not in HORIZONS
                    or units[pair[0]] != (payload["mint"], payload["classification"])
                ):
                    raise ValueError("Duplicate or foreign outcome")
                pairs.add(pair)
                outcomes[f"{payload['classification']}|{pair[1]}|{payload['status']}"] += 1
            previous = digest
            count += 1
            last = row["kind"]
    unresolved = len(units) * len(HORIZONS) - len(pairs)
    return dict(
        records=count,
        sha256=previous,
        complete=last == "STOP" and unresolved == 0,
        complete_scope="ledger closure and outcome accounting only; not study validity",
        stop_reason=payload.get("reason") if last == "STOP" else None,
        source_unchanged_at_stop=payload.get("source_unchanged") if last == "STOP" else None,
        unresolved_horizons=unresolved,
        populations=dict(populations),
        outcomes=dict(outcomes),
        interruption="NONE" if last == "STOP" else "UNRESOLVED_INTERRUPTION; no backfill",
    )


class Recorder:
    def __init__(self, ledger, start):
        self.ledger = ledger
        self.start = start
        self.last_time = start
        self.last = {}
        self.discovered = set()
        self.known_mints = set()
        self.seen = set()
        self.pending = {}
        self.due = []
        self.stop_reason = None
        self.integrity_interrupted = False
        self.counts: Counter = Counter()

    def emit(self, kind, payload):
        try:
            return self.ledger.emit(kind, payload)
        except Exception as exc:
            self.stop_reason = (
                type(exc).__name__
                + ":"
                + ("LIMIT_OR_IO_FAILURE" if not isinstance(exc, StopPilot) else str(exc))
            )
            return None

    def discovery(self, event, accepted, reason, now):
        if event.kind != "create":
            return
        if event.mint not in self.known_mints and len(self.known_mints) >= 1000:
            self.stop_reason = "UNIQUE_TOKEN_LIMIT"
            return
        duplicate = event.mint in self.discovered
        self.discovered.add(event.mint)
        self.known_mints.add(event.mint)
        identity = self.emit(
            "DISCOVERY",
            dict(
                mint=event.mint,
                source_ts=event.ts,
                recorded_at=now,
                admitted=bool(accepted),
                duplicate=duplicate,
                disposition=reason,
            ),
        )
        if identity is not None:
            self.counts["discovery_events"] += 1
            self.counts["duplicate_creates" if duplicate else "unique_discovered_mints"] += 1
            self.counts["admitted_creates" if accepted else "nonadmitted_creates"] += 1

    def refresh(self, engine, now):
        if self.stop_reason:
            return
        if now < self.last_time:
            self.stop_reason = "CLOCK_REGRESSION"
            return
        self.last_time = now
        prices = engine.price_research
        marks = prices.marks if prices else {}
        self.endpoints(engine, now)
        for mint, view in engine.intelligence.results.items():
            token = engine.tokens.get(mint)
            if token is None:
                continue
            if mint not in self.known_mints and len(self.known_mints) >= 1000:
                self.stop_reason = "UNIQUE_TOKEN_LIMIT"
                return
            self.known_mints.add(mint)
            early = view.get("early_market") or {}
            signal_at = early.get("observed_at", now)
            valid_time = (
                isinstance(signal_at, (int, float))
                and math.isfinite(signal_at)
                and self.start <= signal_at <= now
            )
            original_signal_at = signal_at
            if not valid_time:
                signal_at = now
            fresh = bool(early and valid_time and signal_at <= now <= early["valid_until"])
            label = (
                early.get("classification", "INSUFFICIENT DATA")
                if fresh
                else "STALE"
                if early
                else "UNASSESSED"
            )
            if not early or not valid_time:
                label = "UNASSESSED"
            if label not in CLASSES:
                self.stop_reason = "UNKNOWN_CLASSIFICATION"
                return
            key = (label, token.state.value, token.graduation is not None, bool(token.disagreement))
            if self.last.get(mint) == key:
                continue
            self.last[mint] = key
            first = (mint, label) not in self.seen
            measurable = first and valid_time and self.start <= signal_at < self.start + CAPTURE
            if measurable and self.counts["measurements"] >= 2000:
                self.stop_reason = "MEASUREMENT_LIMIT"
                return
            prior = marks.get(mint)
            baseline = (
                prior
                if prior
                and not token.disagreement
                and token.graduation is None
                and prior["acquired_at"] <= signal_at <= prior["valid_until"]
                else None
            )
            baseline = json.loads(canonical(baseline)) if baseline else None
            payload = dict(
                mint=mint,
                signal_at=signal_at,
                recorded_at=now,
                classification=label,
                raw_classification=early.get("classification"),
                assessment_observed_at=original_signal_at,
                assessment_status="AVAILABLE" if early and valid_time else "UNAVAILABLE_OR_INVALID_TIME",
                measurement_exclusion="INVALID_ASSESSMENT_TIME"
                if not valid_time
                else "CAPTURE_CLOSED"
                if signal_at >= self.start + CAPTURE
                else None,
                fresh=fresh,
                first_class=first,
                measurement_scheduled=measurable,
                lifecycle=token.state.value,
                age=signal_at - token.created,
                graduation=token.graduation,
                verified_quote_mint=getattr(token, "verified_quote_mint", None),
                disagreement=bool(token.disagreement),
                assessment=early,
                baseline=baseline,
                baseline_status="AVAILABLE_INDICATIVE" if baseline else "UNAVAILABLE",
                price_diagnostics=prices.diagnostics.first_review(mint, signal_at, baseline, prior)
                if prices
                else None,
            )
            identity = self.emit("TRANSITION", payload)
            self.counts["transitions"] += 1
            if first and identity is not None:
                self.seen.add((mint, label))
            if measurable and identity is not None:
                self.counts["measurements"] += 1
                self.pending[identity] = dict(
                    mint=mint, signal_at=signal_at, label=label, baseline=baseline, remaining=set(HORIZONS)
                )
                for h in HORIZONS:
                    heapq.heappush(self.due, (signal_at + h, identity, h))
        for mint in list(self.last):
            if mint not in engine.tokens:
                self.emit(
                    "LEFT_MONITORED_SET",
                    dict(mint=mint, recorded_at=now, last_classification=self.last[mint][0]),
                )
                del self.last[mint]

    def endpoints(self, engine, now, closing=False):
        if closing:
            self.ledger.flush()
        while self.due and (self.due[0][0] <= now or closing):
            _, identity, h = heapq.heappop(self.due)
            p = self.pending.get(identity)
            if p is None or h not in p["remaining"]:
                continue
            target = p["signal_at"] + h
            token = engine.tokens.get(p["mint"])
            mark = engine.price_research.marks.get(p["mint"]) if engine.price_research else None
            base = p["baseline"]
            valid = bool(
                mark
                and token
                and token.graduation is None
                and not token.disagreement
                and target <= mark["requested_at"] <= mark["acquired_at"] <= min(now, target + GRACE)
                and now <= mark["valid_until"]
                and (not base or mark["quote_mint"] == base["quote_mint"] and mark["slot"] >= base["slot"])
            )
            if not valid and now <= target + GRACE and not closing:
                heapq.heappush(self.due, (now + 1, identity, h))
                continue
            interrupted = closing and getattr(self, "integrity_interrupted", False)
            if interrupted:
                valid = False
            censored = not valid and closing and now <= target + GRACE
            gross = (mark["price"] / base["price"] - 1) * 100 if valid and base and mark is not None else None
            if gross is not None and not math.isfinite(gross):
                gross = None
            status = (
                "CENSORED_INTERRUPTION"
                if interrupted
                else "CENSORED_SHUTDOWN"
                if censored
                else "POSITIVE_GROSS"
                if gross is not None and gross > 0
                else "NEGATIVE_GROSS"
                if gross is not None and gross < 0
                else "FLAT_GROSS"
                if gross is not None
                else "UNAVAILABLE"
            )
            recorded = self.emit(
                "OUTCOME",
                dict(
                    transition_id=identity,
                    mint=p["mint"],
                    classification=p["label"],
                    horizon=h,
                    target_at=target,
                    recorded_at=now,
                    status=status,
                    baseline_available=base is not None,
                    endpoint_available=valid,
                    endpoint=mark if valid else None,
                    gross_change_pct=gross,
                    net_return_pct=None,
                    executable=False,
                    limitation="missing_baseline"
                    if not base
                    else "missing_or_incompatible_endpoint"
                    if not valid
                    else "indicative_only",
                ),
            )
            if recorded is None:
                heapq.heappush(self.due, (now + 1, identity, h))
                return
            self.counts[f"{p['label']}|{h}|{status}"] += 1
            if closing and len(self.ledger.buffer) >= 64:
                self.ledger.flush()
            p["remaining"].remove(h)
            if not p["remaining"]:
                del self.pending[identity]


def attach(engine, recorder, clock=time.time):
    """Wrap existing outputs only; preserve return values, provider selection and decisions."""
    process = engine.process
    refresh = engine.intelligence.refresh

    def observed(event, now=None, *, queued=False):
        result = process(event, now, queued=queued)
        try:
            recorder.discovery(event, result, getattr(engine, "_process_reason", "UNAVAILABLE"), clock())
        except Exception:
            recorder.stop_reason = "DISCOVERY_OBSERVER_FAILURE"
        return result

    def refreshed(*args, **kwargs):
        before = engine.intelligence.last_refresh
        result = refresh(*args, **kwargs)
        if engine.intelligence.last_refresh != before:
            try:
                recorder.refresh(engine, clock())
            except Exception:
                recorder.stop_reason = "CLASSIFICATION_OBSERVER_FAILURE"
        return result

    engine.process = observed
    engine.intelligence.refresh = refreshed

    def detach():
        engine.process = process
        engine.intelligence.refresh = refresh

    return detach


def discovery_snapshot(health):
    """Fixed-cardinality numeric telemetry only; never copy arbitrary health strings/maps."""
    from backend.app.discovery import FAILURE_REASONS, FAILURE_EVENTS, TRANSPORT_FAILURES

    def number(value):
        import math

        return value if isinstance(value, (int, float)) and math.isfinite(value) else None

    result = {
        key: number(health.get(key))
        for key in (
            "errors",
            "reconnects",
            "connected",
            "messages",
            "launch_events",
            "ignored_events",
            "decoding_errors",
            "last_success",
            "last_event",
        )
    }
    for key, allowed in (
        ("decode_failures_by_reason", FAILURE_REASONS),
        ("decode_failures_by_event", FAILURE_EVENTS),
        (
            "framing_failure_details",
            ("depth_mismatch", "unbalanced_finish", "unfinished_invocations", "other"),
        ),
        ("transport_failure_counts", TRANSPORT_FAILURES),
        (
            "global_reset_reasons",
            (
                "transport",
                "shutdown",
                "unknown_trade_identity",
                "invocation_framing",
                "outer_notification",
                "event_decode",
                "log_truncation",
                "truncation_recovery",
            ),
        ),
    ):
        values = health.get(key, {})
        result[key] = {name: number(values.get(name)) for name in allowed}
    return result


def operational_snapshot(engine, now, elapsed):
    queue = engine.queue
    recovery = engine.recovery.snapshot()
    return dict(
        at=now,
        elapsed_seconds=elapsed,
        candidates=len(engine.tokens),
        queue_depth=len(queue.heap),
        queue_peak=queue.peak_depth,
        dropped_trades=queue.dropped_trades,
        dropped_critical=queue.dropped_critical,
        resources=dict(engine.metrics),
        continuity=dict(engine.trade_continuity),
        rpc={k: engine.rpc.health.get(k) for k in ("requests", "errors", "rate_limits", "connected")},
        discovery=discovery_snapshot(engine.onchain.health),
        recovery={
            k: recovery.get(k)
            for k in (
                "accepted",
                "completed",
                "overflow",
                "expired",
                "pending",
                "in_flight",
                "global_gaps",
                "token_local_gaps",
            )
        },
        prices=engine.price_research.snapshot() if engine.price_research else None,
    )


def resource_reason(engine, output, elapsed):
    import shutil
    import psutil

    rss = psutil.Process().memory_info().rss / 1048576
    size = sum(p.stat().st_size for p in Path(output).iterdir() if p.is_file()) / 1048576
    if rss >= 500:
        return "PILOT_RSS_STOP"
    if size >= 640:
        return "PILOT_STORAGE_STOP"
    if shutil.disk_usage(output).free < 512 * 1048576:
        return "PILOT_DISK_FREE_STOP"
    ledger_path = Path(output) / "history.jsonl"
    if ledger_path.exists() and ledger_path.stat().st_size >= 32 * 1048576:
        return "PILOT_TRACE_SOFT_STOP"
    if engine.queue.dropped_trades or engine.queue.dropped_critical:
        return "UNACCEPTABLE_QUEUE_LOSS"
    if len(engine.queue.heap) >= 800:
        return "PILOT_QUEUE_STOP"
    if any(t.done() for t in engine.tasks):
        return "BACKGROUND_TASK_ENDED"
    if engine.storage_stopped or not engine.running:
        return "ENGINE_STOPPED"
    if engine.metrics.get("resource_pressure"):
        return "ENGINE_RESOURCE_PRESSURE"
    if elapsed >= TOTAL:
        return "SCHEDULED_COMPLETION"
    return None


async def run(expected, output):
    # All checks happen before constructing an engine or creating a database.
    from dotenv import load_dotenv
    from backend.app.config import load_settings, Settings
    import yaml

    load_dotenv(ROOT / ".env")
    source = verify_source(expected)
    if any(v for k, v in os.environ.items() if "COHORT" in k.upper()) or os.getenv(
        "PUMPPORTAL_ENABLED", "false"
    ).lower() not in ("false", "0", ""):
        raise PilotRefusal("Cohort/PumpPortal environment forbidden")
    if not (
        os.getenv("SOLANA_RPC_HTTP_URL") and os.getenv("SOLANA_RPC_WSS_URL") or os.getenv("HELIUS_API_KEY")
    ):
        raise PilotRefusal("Existing standard HTTP/WSS configuration unavailable")
    settings = load_settings()
    frozen_settings = Settings(
        **{**yaml.safe_load(git("show", f"{BASE}:config/conservative.yaml")), "mode": "OBSERVE"}
    )
    if settings.model_dump() != frozen_settings.model_dump():
        raise PilotRefusal("Effective configuration differs from frozen conservative settings")
    if settings.mode != "OBSERVE" or any(
        getattr(settings, k) != v
        for k, v in dict(
            max_candidates=250,
            max_deep=25,
            max_events=500,
            queue_size=1000,
            rss_limit_mb=700,
            db_limit_mb=1024,
        ).items()
    ):
        raise PilotRefusal("Pilot requires unchanged conservative OBSERVE capacity")
    output = Path(output).resolve()
    allowed = (ROOT / "data/early_edge").resolve()
    if output.parent != allowed or output.exists():
        raise PilotRefusal("Require new isolated output directory")
    # Linux cooperative lock plus owned-process checks. Never terminate another process.
    import fcntl
    import psutil

    lock = (allowed / ".signal-quality-pilot.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        if proc.info["pid"] == os.getpid():
            continue
        args = proc.info["cmdline"] or []
        if any(
            Path(a).name in ("uvicorn", "smoke_observe.py", "verify_observe.py", "signal_quality_pilot.py")
            or a == "backend.app.main:app"
            for a in args
        ):
            raise PilotRefusal("Competing observation process detected")
    output.mkdir(parents=True, exist_ok=False)
    from backend.app.opportunity import EARLY_MARKET_VERSION
    from backend.app.early_prices import VERSION, SCHEMA_HASH

    manifest = dict(
        interpretation_version=EARLY_MARKET_VERSION,
        price_instrument_version=VERSION,
        quote_schema_sha256=SCHEMA_HASH,
        protocol=protocol(),
        source=source,
        settings=settings.model_dump(),
        created_at=time.time(),
    )
    manifest["settings_sha256"] = hashlib.sha256(canonical(manifest["settings"]).encode()).hexdigest()
    manifest["sha256"] = hashlib.sha256(canonical(manifest).encode()).hexdigest()
    (output / "manifest.json").write_text(canonical(manifest))
    from backend.app.engine import RadarEngine

    engine = RadarEngine(settings, output / "observe.db")
    start = time.time()
    monotonic = time.monotonic()
    ledger = Ledger(output / "history.jsonl")
    recorder = Recorder(ledger, start)
    recorder.emit("START", dict(manifest_sha256=manifest["sha256"], source_sha=expected, at=start))
    ledger.flush()
    detach = attach(engine, recorder)
    reason = "UNEXPECTED_INTERRUPTION"
    error = None
    shutdown = None
    pending_tasks_after_stop = None
    next_source_check = monotonic
    next_health = monotonic
    last_controller = monotonic
    try:
        await engine.start()
        while True:
            await asyncio.sleep(1)
            current = time.monotonic()
            elapsed = current - monotonic
            if current - last_controller > 20:
                reason = "CONTROLLER_GAP"
                break
            last_controller = current
            if current >= next_health:
                recorder.emit("HEALTH", operational_snapshot(engine, time.time(), elapsed))
                next_health = current + 10
            if time.monotonic() >= next_source_check:
                if not source_unchanged(source):
                    reason = "SOURCE_DRIFT"
                    break
                next_source_check = time.monotonic() + 10
            reason = recorder.stop_reason or (
                "PILOT_RECORD_SOFT_STOP"
                if ledger.sequence >= 12000
                else resource_reason(engine, output, elapsed)
            )
            ledger.flush()
            if reason:
                break
    except BaseException as exc:
        reason = "CANCELLED" if isinstance(exc, asyncio.CancelledError) else "OBSERVER_OR_IO_FAILURE"
        error = exc
    finally:
        cutoff = time.time()
        cutoff_monotonic = time.monotonic()
        recorder.integrity_interrupted = reason in (
            "CONTROLLER_GAP",
            "SOURCE_DRIFT",
            "OBSERVER_OR_IO_FAILURE",
        ) or recorder.stop_reason in ("CLOCK_REGRESSION", "CLASSIFICATION_OBSERVER_FAILURE")
        try:
            recorder.endpoints(engine, cutoff, closing=True)
        except Exception as exc:
            reason = "OUTCOME_FINALIZATION_FAILURE"
            error = error or exc
        detach()
        try:
            await engine.stop()
            pending_tasks_after_stop = sum(
                not task.done() and task is not asyncio.current_task() for task in asyncio.all_tasks()
            )
            if pending_tasks_after_stop:
                reason = "PENDING_ASYNC_WORK_AFTER_STOP"
            import sqlite3

            # The fresh isolated DB only; never the application's original database.
            db = sqlite3.connect(f"file:{output / 'observe.db'}?mode=ro", uri=True)
            try:
                raw = db.execute(
                    "SELECT payload FROM evidence_runs WHERE session=?", (engine.session,)
                ).fetchone()
                shutdown = json.loads(raw[0]) if raw else None
                if shutdown:
                    (output / "shutdown.json").write_text(canonical(shutdown))
                integrity = db.execute("PRAGMA quick_check").fetchone()[0]
                cohorts = db.execute("SELECT count(*) FROM prospective_cohorts").fetchone()[0]
                if cohorts or engine.approved_evidence is not None:
                    reason = "COHORT_OR_APPROVAL_BOUNDARY_FAILURE"
            finally:
                db.close()
            if (
                not shutdown
                or shutdown.get("status") != "STOPPED"
                or not shutdown.get("checkpoint_complete")
                or integrity != "ok"
            ):
                reason = "SHUTDOWN_OR_DATABASE_INCOMPLETE"
        except BaseException as exc:
            reason = "SHUTDOWN_FAILED"
            error = error or exc
        try:
            if not ledger.failed:
                final_source_ok = source_unchanged(source)
                if not final_source_ok:
                    reason = "SOURCE_DRIFT"
                stop = recorder.emit(
                    "STOP",
                    dict(
                        reason=reason,
                        at=cutoff,
                        elapsed_seconds=time.monotonic() - monotonic,
                        outstanding_measurements=len(recorder.pending),
                        outstanding_horizons=sum(len(p["remaining"]) for p in recorder.pending.values()),
                        source_unchanged=final_source_ok,
                    ),
                )
                ledger.flush()
                if stop is None:
                    reason = "INCOMPLETE_LEDGER"
        except Exception as exc:
            reason = "LEDGER_IO_FAILURE"
            error = error or exc
        finally:
            ledger.file.close()
            lock.close()
        try:
            trace = verify_ledger(output / "history.jsonl")
        except (ValueError, KeyError, json.JSONDecodeError):
            trace = dict(complete=False, error="INVALID_OR_PARTIAL_LEDGER")
        report = dict(
            status="OPERATIONAL_PILOT_ONLY",
            reason=reason,
            complete=bool(
                reason == "SCHEDULED_COMPLETION"
                and trace["complete"]
                and not recorder.pending
                and shutdown
                and shutdown.get("checkpoint_complete")
            ),
            ledger_complete=trace["complete"],
            shutdown_complete=bool(
                shutdown and shutdown.get("checkpoint_complete") and not pending_tasks_after_stop
            ),
            pending_async_tasks_after_stop=pending_tasks_after_stop,
            process_exit_confirmation="operator must verify normal exit; standard asyncio executor cleanup is not bypassed",
            prospective_cohort_authorized=False,
            performance_endorsement=False,
            counts=dict(recorder.counts),
            counter_scope="observer-accepted records; verify ledger before analysis",
            elapsed_seconds=time.monotonic() - monotonic,
            observation_elapsed_seconds=cutoff_monotonic - monotonic,
            shutdown_elapsed_seconds=time.monotonic() - cutoff_monotonic,
            integrity=trace,
            PRE_COHORT_READY="NO",
            net_results="UNAVAILABLE",
        )
        (output / "report.json").write_text(canonical(report))
    if error:
        raise error
    if reason != "SCHEDULED_COMPLETION":
        raise StopPilot(reason)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--verify-ledger", type=Path)
    parser.add_argument("--expected-sha")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.verify_ledger:
        if args.run:
            parser.error("Ledger verification cannot collect observations")
        print(json.dumps(verify_ledger(args.verify_ledger), indent=2))
        return
    if not args.run:
        print(json.dumps(protocol(), indent=2))
        return
    if not args.expected_sha or args.output is None:
        parser.error("--run requires --expected-sha and --output")
    try:
        asyncio.run(run(args.expected_sha, args.output))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as exc:
        print(
            "Pilot stopped: "
            + (str(exc) if isinstance(exc, (PilotRefusal, StopPilot)) else type(exc).__name__),
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

"""Bounded operational telemetry only; no cohort, outcome, execution or scoring writes."""

from collections import Counter, deque
import asyncio
import hashlib
import math
import time

from backend.app.early_edge import fx_value
from backend.app.early_edge_quotes import quote_budget, pump_buy


class Distribution:
    edges = (0, 0.5, 1, 2, 5, 10, 20, 30, 60, 85, 120, 180, 300, 600, 1800, 3600, 21600)

    def __init__(self):
        self.n, self.total, self.minimum, self.maximum = 0, 0.0, None, None
        self.bins = [0] * (len(self.edges) + 1)

    def add(self, value):
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            return
        self.n += 1
        self.total += value
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)
        self.bins[sum(value > edge for edge in self.edges)] += 1

    def report(self):
        return dict(
            count=self.n,
            mean=self.total / self.n if self.n else None,
            min=self.minimum,
            max=self.maximum,
            upper_edges=list(self.edges) + ["INF"],
            counts=self.bins,
        )


class OperationalTelemetry:
    def __init__(self, settings, started):
        self.settings, self.started = settings, started
        self.counts: Counter[str] = Counter()
        self.distributions = {}
        self.current_seen = set()
        self.first_current = None
        self.peak_current = 0
        self.last = started
        self.resource_seconds = 0.0
        self.signals = {}  # <=64 live diagnostic markers/entry-availability probes; never outcomes.
        self.finished = []  # <=256 redacted marker summaries.
        self.entry_counts: Counter[str] = Counter()
        self.rpc_errors: Counter[str] = Counter()
        self.entry_attempts: deque[dict] = deque(maxlen=256)
        self.last_quote_probe = 0.0
        self.last_state_counts = {}
        self.reference_quality: Counter[str] = Counter()
        self.initial_storage = None
        self.peak_storage = 0
        self.peak_queue = 0

    def add(self, name, value):
        self.distributions.setdefault(name, Distribution()).add(value)

    def early(self, snapshot, controls):
        self.counts["early_unique"] += 1
        for name, key in [("signal_curve", "curve_progress"), ("signal_age", "age")]:
            self.add(name, snapshot[key])
        self.add("signal_buyers", snapshot["features"].get("estimated_independent_buyers"))
        self.add("potential_controls", len(controls))
        if not controls:
            self.counts["unmatched_no_same_quote_progress_age_security_riskset"] += 1
        if len(self.signals) < 64:
            self.signals[snapshot["mint"]] = dict(
                ts=snapshot["timestamp"], markers={}, latencies={}, last_attempt=0.0
            )
        else:
            self.counts["diagnostic_probe_capacity"] += 1

    def observe(self, token, now):
        row = self.signals.get(token.mint)
        if not row:
            return
        features = token.features.get("180", {})
        curve_ok = (
            token.curve_history
            and token.curve_history[-1] == (token.last_curve, token.curve_progress)
            and 0 <= now - token.last_curve <= 180
        )
        markers = {
            "curve85": bool(curve_ok and token.curve_progress is not None and token.curve_progress >= 85),
            "buyers": features.get("trade_evidence") == "CURRENT"
            and features.get("estimated_independent_buyers", 0) >= self.settings.min_buyers,
            "graduation": token.graduation is not None,
        }
        for name, hit in markers.items():
            if hit and name not in row["markers"]:
                row["markers"][name] = now - row["ts"]
                self.counts["crowd_" + name] += 1
                self.add("seconds_to_" + name, now - row["ts"])

    def sample(self, engine, now, rss, cpu, directory):
        if (
            engine.onchain.health.get("decode_failure_matrix", {})
            .get("TradeEvent", {})
            .get("unsupported_layout", 0)
        ):
            raise RuntimeError("UNEXPLAINED_PUMP_LAYOUT_STOP")
        self.add("rss_mb", rss)
        self.add("cpu_pct", cpu)
        dt = max(0, now - self.last)
        if engine.metrics.get("resource_pressure"):
            self.resource_seconds += dt
        self.last = now
        self.last_state_counts = dict(Counter(t.state.value for t in engine.tokens.values()))
        self.add("active", len(engine.tokens))
        deep = len(engine.deep_mints())
        self.add("deep", deep)
        self.add("background", len(engine.tokens) - deep)
        current = 0
        for token in engine.tokens.values():
            self.observe(token, now)
            if engine.trade_status(token, now) == "CURRENT":
                current += 1
                if len(self.current_seen) < 20000:
                    self.current_seen.add(hashlib.sha256(token.mint.encode()).hexdigest())
                else:
                    self.counts["current_dedup_capacity"] += 1
                if self.first_current is None:
                    self.first_current = now - self.started
                self.add("clean_coverage_current", engine.trade_coverage_seconds(token, now))
                f = token.features.get("180", {})
                for key in ("estimated_independent_buyers", "flow_ratio", "whale_share"):
                    self.add("current_" + key, f.get(key))
        self.peak_current = max(self.peak_current, current)
        self.peak_queue = max(self.peak_queue, len(engine.queue.heap))
        size = sum(p.stat().st_size for p in directory.iterdir() if p.is_file())
        self.initial_storage = size if self.initial_storage is None else self.initial_storage
        self.peak_storage = max(self.peak_storage, size)
        for task in engine.tasks:
            if task.done() and not task.cancelled() and task.exception() is not None:
                raise RuntimeError("Background provider task failed: " + type(task.exception()).__name__)
        for mint, row in list(self.signals.items()):
            if now - row["ts"] > 1800:
                self.finish_signal(mint, row, now)

    def references(self, reference, now):
        from backend.app.early_edge_quotes import WSOL, USDC

        snapshot = reference.snapshot()
        for mint, name in ((WSOL, "SOL"), (USDC, "USDC")):
            try:
                fx_value(snapshot, mint, now)
                self.reference_quality[name + ":fresh_samples"] += 1
                self.add(name + "_reference_age", now - snapshot[mint]["published_at"])
            except (ValueError, KeyError):
                self.reference_quality[name + ":unavailable_samples"] += 1

    def finish_signal(self, mint, row, now):
        for latency in (0.5, 2, 5, 10):
            if str(latency) not in row["latencies"]:
                reason = row.get("failure", "UNAVAILABLE_INFRASTRUCTURE")
                row["latencies"][str(latency)] = reason
                self.entry_counts[f"{latency}:{reason}"] += 1
        if len(self.finished) < 256:
            self.finished.append(
                dict(
                    mint_hash=hashlib.sha256(mint.encode()).hexdigest(),
                    signal_at=row["ts"],
                    markers=row["markers"],
                    latencies=row["latencies"],
                    observed_seconds=now - row["ts"],
                )
            )
        self.signals.pop(mint, None)

    def entry_pending(self, now):
        # Background work yields while any primary manual-entry window is live.
        return any("10" not in row["latencies"] and now <= row["ts"] + 20
                   for row in self.signals.values())

    def entry_unavailable(self, row, latency, reason):
        key = str(latency)
        if key not in row["latencies"]:
            row["latencies"][key] = reason
            self.entry_counts[f"{key}:{reason}"] += 1

    async def probe_entries(self, oracle, reference, engine, now):
        choices = []
        for mint, row in list(self.signals.items()):
            attempts = row.setdefault("attempts", {})
            for latency in (0.5, 2, 5, 10):
                if str(latency) not in row["latencies"] and now > row["ts"] + latency + 10:
                    self.entry_unavailable(row, latency, row.get("failure", "UNAVAILABLE_INFRASTRUCTURE"))
            due = [v for v in (0.5, 2, 5, 10) if str(v) not in row["latencies"]
                   and row["ts"] + v <= now and attempts.get(str(v), 0) < 3]
            if due and now - row.get("last_attempt", 0) >= 2:
                primary = 10 in due
                deadline = row["ts"] + (10 if primary else min(due)) + 10
                choices.append((not primary, deadline, row.get("last_attempt", 0), mint, due))
        if not choices:
            return
        _, deadline, _, mint, due = min(choices)
        row = self.signals[mint]
        row["last_attempt"] = now
        for latency in due:
            row["attempts"][str(latency)] = row["attempts"].get(str(latency), 0) + 1
        receipt = dict(signal=hashlib.sha256(mint.encode()).hexdigest()[:12],
                       signal_at=row["ts"], attempted_at=now, deadline=deadline,
                       latencies=due, outcome="UNAVAILABLE_INFRASTRUCTURE")
        self.entry_attempts.append(receipt)
        self.counts["entry_quote_attempts"] += 1
        try:
            token = engine.tokens.get(mint)
            if token is None or token.graduation is not None:
                raise ValueError("UNAVAILABLE_QUOTE")
            # A single entry worker and one background worker share the normal RPC limiter.
            obs = await asyncio.wait_for(oracle.observe(mint, "PUMP"), timeout=min(5, deadline - now))
            self.add("entry_state_acquisition_delay", obs.acquired_at - obs.requested_at)
            receipt.update(requested_at=obs.requested_at, acquired_at=obs.acquired_at)
            fx = fx_value(reference.snapshot(), obs.data["quote_mint"], obs.acquired_at)
            pump_buy(obs.data, quote_budget(4, fx, obs.data["quote_mint"]))
            receipt["outcome"] = "VALID_STATE"
            for latency in (0.5, 2, 5, 10):
                key = str(latency)
                if (key not in row["latencies"] and row["ts"] + latency <= obs.requested_at
                        <= obs.acquired_at <= row["ts"] + latency + 10):
                    row["latencies"][key] = "AVAILABLE"
                    self.entry_counts[f"{key}:AVAILABLE"] += 1
        except asyncio.CancelledError:
            row["failure"] = "UNAVAILABLE_INFRASTRUCTURE"
            receipt["outcome"] = row["failure"]
            raise
        except Exception as exc:
            self.counts["entry_quote_errors"] += 1
            self.counts["entry_" + ("QUOTE" if isinstance(exc, ValueError) else "PROVIDER")] += 1
            reason = getattr(exc, "reason", "UNAVAILABLE_QUOTE" if isinstance(exc, ValueError)
                             else "UNAVAILABLE_PROVIDER_GAP")
            allowed = ("UNAVAILABLE_QUOTE", "UNAVAILABLE_UNITS", "UNAVAILABLE_PROVIDER_GAP",
                       "UNAVAILABLE_INFRASTRUCTURE", "UNAVAILABLE_OTHER")
            row["failure"] = reason if reason in allowed else "UNAVAILABLE_OTHER"
            receipt["outcome"] = row["failure"]
        finally:
            receipt["completed_at"] = time.time()
            self.counts["entry_attempt_" + receipt["outcome"]] += 1
        for latency in due:
            if time.time() > row["ts"] + latency + 10 or row["attempts"][str(latency)] >= 3:
                self.entry_unavailable(row, latency, row.get("failure", "UNAVAILABLE_PROVIDER_GAP"))

    def report(self):
        return dict(
            entry_attempts=list(self.entry_attempts),
            counts=dict(self.counts),
            distributions={k: v.report() for k, v in self.distributions.items()},
            current_unique=len(self.current_seen),
            first_current_seconds=self.first_current,
            peak_current=self.peak_current,
            resource_pressure_seconds=self.resource_seconds,
            last_state_counts=self.last_state_counts,
            storage_growth_bytes=self.peak_storage - (self.initial_storage or 0),
            peak_storage_bytes=self.peak_storage,
            peak_queue=self.peak_queue,
            entry_availability=dict(self.entry_counts),
            marker_examples=self.finished,
            active_marker_count=len(self.signals),
            http_exception_categories=dict(self.rpc_errors),
            reference_quality=dict(self.reference_quality),
            distribution_sampling="Operational time samples; not independent research outcomes",
            cohort_created=False,
        )


def track_http_errors(client, counts):
    """Delegate every request/byte unchanged; record sanitized transport exception classes."""
    original = client.send

    def record(exc):
        import httpx

        counts[
            "ReadError"
            if isinstance(exc, httpx.ReadError)
            else "Timeout"
            if isinstance(exc, httpx.TimeoutException)
            else "OtherHTTP"
        ] += 1

    async def sent(*args, **kwargs):
        try:
            response = await original(*args, **kwargs)
        except Exception as exc:
            record(exc)
            raise
        read = response.aiter_bytes

        async def measured(*a, **kw):
            try:
                async for block in read(*a, **kw):
                    yield block
            except Exception as exc:
                record(exc)
                raise

        response.aiter_bytes = measured
        return response

    client.send = sent
    return lambda: setattr(client, "send", original)

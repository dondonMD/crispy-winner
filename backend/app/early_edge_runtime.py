"""Opt-in observational adapter and bounded quote acquisition; no core edits."""

import asyncio
import httpx
from datetime import datetime
import time
from typing import Callable

from backend.app.early_edge import canonical, fx_value, IntegrityError
from backend.app.early_edge_quotes import ResearchExecutionOracle, QuoteUnavailable, WSOL, USDC, QUOTES
from backend.app.providers import HttpProvider


class UsdReference(HttpProvider):
    """Two fixed public tickers, <=one request per product/10s; no future interpolation."""

    def __init__(self, client=None, diagnostics=None):
        super().__init__("Early research USD reference", rate=0.2, client=client)
        self.diagnostics = diagnostics
        self.cache = {}
        self.last_attempt = {}

    async def refresh(self, mints=None, max_products=2):
        products = [(WSOL, "SOL-USD"), (USDC, "USDCUSD")]
        if max_products not in (1, 2) or mints is not None and not set(mints) <= set(QUOTES):
            raise ValueError("Unsupported USD reference request")
        if mints is not None:
            products = [p for p in products if p[0] in mints]
            products.sort(key=lambda p: self.last_attempt.get(p[0], 0))
        diag = self.diagnostics
        if diag:
            for _, product in products[max_products:]:
                diag.fx_event(product, 'budget_skipped')
        for mint, product in products[:max_products]:
            now = time.time()
            if now - self.last_attempt.get(mint, 0) < 10:
                if diag:
                    diag.fx_event(product, 'interval_skipped')
                continue
            self.last_attempt[mint] = now
            before = self.health['requests']
            completed = False
            ref = None
            if diag:
                diag.fx_event(product, 'attempted')
                diag.flush()
            try:
                if mint == WSOL:
                    data = await self.request(
                        "GET",
                        f"https://api.exchange.coinbase.com/products/{product}/ticker",
                        retry_attempts=1,
                    )
                    completed = True
                    if diag:
                        diag.fx_event(product, 'http_completed')
                    price = float(data["price"])
                    published = datetime.fromisoformat(data["time"].replace("Z", "+00:00")).timestamp()
                    source = "Coinbase Exchange public ticker"
                else:
                    data = await self.request(
                        "GET",
                        "https://api.kraken.com/0/public/Trades",
                        params={"pair": "USDCUSD", "count": 1},
                        retry_attempts=1,
                    )
                    completed = True
                    if diag:
                        diag.fx_event(product, 'http_completed')
                    if (
                        data.get("error") != []
                        or set(data["result"]) != {"USDCUSD", "last"}
                        or len(data["result"]["USDCUSD"]) != 1
                    ):
                        raise ValueError("USD reference shape mismatch")
                    trade = data["result"]["USDCUSD"][0]
                    price, published = float(trade[0]), float(trade[2])
                    source = "Kraken public recent trades"
                ref = dict(
                    source=source, product=product, usd=price, published_at=published, acquired_at=time.time()
                )
                fx_value({mint: ref}, mint, ref["acquired_at"])
                self.cache[mint] = ref
                if diag:
                    diag.fx_event(product, 'usable', ref)
            except asyncio.CancelledError:
                if diag:
                    diag.fx_event(product, 'cancelled')
                raise
            except (ValueError, KeyError, IndexError, TypeError, RuntimeError, httpx.HTTPError) as exc:
                if diag:
                    from backend.app.price_diagnostics import fx_problem
                    stale = ref is not None and fx_problem({mint: ref}, mint, time.time()) == 'USD_STALE'
                    diag.fx_event(product, 'stale_rejected' if stale else 'validation_failed' if completed or getattr(exc, 'diagnostic_category', '') == 'RPC_INVALID_RESPONSE' else 'request_failed')
                pass  # Expiry is explicit; no stale substitution or fabricated USD.
            finally:
                if diag:
                    diag.fx_event(product, 'http_started', amount=self.health['requests']-before)
                    diag.flush()
        return self.snapshot()

    def snapshot(self):
        import json

        return json.loads(canonical(self.cache))


class ObservationCoverage:
    """Bounded active-candidate summaries; cumulative transition counts, no raw logs."""

    def __init__(self, limit):
        from collections import Counter

        self.limit, self.active = limit, {}
        self.counts: Counter = Counter()

    def admission(self, before, after, pressure, full, accepted):
        evicted = set(before) - set(after)
        self.counts["capacity_evictions"] += len(evicted)
        if not accepted:
            self.counts[
                "create_rejections_pressure"
                if pressure
                else "create_rejections_at_capacity"
                if full
                else "create_rejections_other"
            ] += 1
        for mint in evicted:
            if mint in self.active:
                self.active[mint]["censored_reason"] = "CAPACITY_EVICTION"
        return evicted

    def observe(self, token, view, now, settings, health=None, tier="unknown"):
        from backend.app.early_edge import signal_snapshot
        from backend.app.early_edge_design import readiness

        health = health or {}
        row = self.active.setdefault(
            token.mint,
            dict(
                first_seen=now,
                last_seen=now,
                last_curve=0,
                curve_observation_count=0,
                largest_observation_gap=0,
                coverage_seconds=0,
                eligible_monitoring_seconds=0,
                hot_seconds=0,
                background_seconds=0,
                provider_unavailable_seconds=0,
                resource_pressure_seconds=0,
                ever_eligible=False,
                ever_adequate=False,
            ),
        )
        dt = max(0, now - row["last_seen"])
        if token.last_curve > row["last_curve"]:
            if row["last_curve"]:
                row["largest_observation_gap"] = max(
                    row["largest_observation_gap"], token.last_curve - row["last_curve"]
                )
            row["curve_observation_count"] += 1
            row["last_curve"] = token.last_curve
        r = readiness(token, now, settings)
        row["coverage_seconds"] = r["coverage_seconds"]
        broad = signal_snapshot(token, view, now, settings, require_ready=False) is not None
        if broad:
            row["eligible_monitoring_seconds"] += dt if row.get("previous_eligible") else 0
            if not row["ever_eligible"]:
                self.counts["eligible_pregrad"] += 1
            row["ever_eligible"] = True
            if r["ready"] and not row["ever_adequate"]:
                self.counts["adequately_observed"] += 1
            row["ever_adequate"] |= r["ready"]
        if tier in ("hot", "background"):
            row[tier + "_seconds"] += dt
        if health.get("connected") is False:
            row["provider_unavailable_seconds"] += dt
        if health.get("backoff_level", 0) > 0 or health.get("resource_pressure", False):
            row["resource_pressure_seconds"] += dt
        row["previous_eligible"] = broad
        row["last_seen"], row["monitoring_tier"], row["readiness"] = now, tier, r
        while len(self.active) > self.limit:
            self.active.pop(next(iter(self.active)))
        return row


class EarlyEdgeObserver:
    """Synchronous passive treatment hook; risk set is projected at the same wall time."""

    def __init__(self, study, settings, reference, clock=time.time):
        self.study, self.settings, self.reference, self.clock = study, settings, reference, clock
        self.keys, self.migrations, self.crowd_pending = {}, {}, {}
        self.coverage = ObservationCoverage(settings.max_candidates)
        self.accepting, self.failed, self.error = True, False, None
        self.universe: Callable = lambda now: []
        self.health: Callable = lambda: {}
        self.tier = lambda mint: "unknown"

    def observe(self, token, opportunity, now=None):
        from backend.app.early_edge import signal_snapshot

        now = self.clock() if now is None else now
        if self.failed:
            return
        try:
            coverage = self.coverage.observe(
                token, opportunity, now, self.settings, self.health(), self.tier(token.mint)
            )
            snapshot = signal_snapshot(token, opportunity, now, self.settings, self.reference.snapshot())
            if self.accepting and snapshot and snapshot["action"] == "EARLY_OPPORTUNITY":
                key = (token.last_curve, token.last_security, snapshot["action"])
                if self.keys.get(token.mint) != key:
                    self.keys[token.mint] = key
                    while len(self.keys) > self.settings.max_candidates:
                        self.keys.pop(next(iter(self.keys)))
                    snapshot["observation_coverage"] = coverage
                    snapshot["monitoring_tier"] = self.tier(token.mint)
                    controls = [
                        signal_snapshot(t, v, now, self.settings, self.reference.snapshot())
                        for t, v in self.universe(now)
                    ]
                    for c in controls:
                        if c:
                            c["monitoring_tier"] = self.tier(c["mint"])
                            c["observation_coverage"] = self.coverage.active.get(c["mint"], {})
                    self.study.enroll(snapshot, now, controls=controls)
            early = self.study.db.execute(
                "SELECT 1 FROM ee_signals WHERE mint=? AND session=? AND arm='EARLY'",
                (token.mint, self.study.session),
            ).fetchone()
            verified_curve = (
                token.curve_history
                and token.curve_history[-1] == (token.last_curve, token.curve_progress)
                and 0 <= now - token.last_curve <= 180
            )
            markers = []
            if verified_curve and token.curve_progress is not None and token.curve_progress >= 85:
                markers.append(("CROWD_85", "CROWD_QUOTE"))
            f = token.features.get("180", {})
            if (
                token.graduation is None
                and token.flow_venue == "PUMP"
                and f.get("trade_evidence") == "CURRENT"
                and f.get("units_valid")
                and f.get("estimated_independent_buyers", 0) >= self.settings.min_buyers
            ):
                markers.append(("BUYER_CROWD", "BUYER_QUOTE"))
            for kind, quote_kind in markers:
                exists = self.study.db.execute(
                    "SELECT 1 FROM ee_lifecycle WHERE mint=? AND session=? AND kind=?",
                    (token.mint, self.study.session, kind),
                ).fetchone()
                if not exists:
                    crowd = dict(
                        ts=now,
                        progress=token.curve_progress,
                        independent_buyers=f.get("estimated_independent_buyers"),
                        observed_at=now,
                        curve_observed_at=token.last_curve,
                        fx=self.reference.snapshot(),
                        quote_mint=token.verified_quote_mint,
                        quote_kind=quote_kind,
                    )
                    self.study.record_lifecycle(token.mint, kind, now, crowd)
                    if early:
                        self.crowd_pending[(token.mint, quote_kind)] = crowd
            while len(self.crowd_pending) > self.settings.max_candidates * 2:
                (mint, kind), old = self.crowd_pending.popitem()
                self.study.benchmark(
                    mint, kind, old["ts"], dict(old, quote_status="UNAVAILABLE_INFRASTRUCTURE")
                )
        except Exception as exc:
            self.failed, self.error = True, type(exc).__name__

    def created(self, event):
        self.coverage.counts["discovered"] += 1

    def migration(self, event):
        if event.kind != "migration":
            return
        e = event.evidence
        if (
            event.source not in ("Solana WSS", "Recovered Pump instruction")
            or e.get("identity_quality") != "VERIFIED"
            or e.get("data_quality") != "VERIFIED"
            or not event.signature
            or not event.pair
        ):
            return
        if event.source == "Recovered Pump instruction" and e.get("instruction") not in (
            "migrate",
            "migrate_v2",
        ):
            return
        self.migrations[event.mint] = dict(
            mint=event.mint,
            pool=event.pair,
            signature=event.signature,
            identity_quality="VERIFIED",
            data_quality="VERIFIED",
            source=event.source,
            timestamp=event.ts,
            observed_at=self.clock(),
        )
        while len(self.migrations) > self.settings.max_candidates:
            self.migrations.pop(next(iter(self.migrations)))
        self.study.record_lifecycle(event.mint, "GRADUATION", event.ts, self.migrations[event.mint])


def attach_observer(engine, observer):
    """Only this opt-in research process wraps methods; all original calls/returns preserved."""
    observer.universe = lambda now: [
        (t, engine.intelligence.project(t, now, manual=False)) for t in engine.tokens.values()
    ]
    observer.health = lambda: (
        dict(engine.rpc.health, resource_pressure=engine.metrics.get("resource_pressure", False))
        if hasattr(engine, "rpc")
        else {}
    )
    batch_hot = None

    def tier(mint):
        if not hasattr(engine, "deep_mints"):
            return "unknown"
        hot = batch_hot if batch_hot is not None else engine.deep_mints()
        return "hot" if mint in hot else "background"

    observer.tier = tier
    original = engine.intelligence.observe
    refresh = getattr(engine.intelligence, "refresh", None)
    process = engine.process

    def refreshed(*args, **kwargs):
        nonlocal batch_hot
        # Refresh is synchronous and observational: no candidate scores/ranks mutate
        # inside its callbacks. Reuse that exact ranking only for this batch.
        batch_hot = set(engine.deep_mints()) if hasattr(engine, "deep_mints") else None
        try:
            assert refresh is not None
            return refresh(*args, **kwargs)
        finally:
            batch_hot = None

    def observed(token, now, acquisition=True):
        result = original(token, now, acquisition=acquisition)
        try:
            actual_now = observer.clock()
            view = engine.intelligence.project(token, actual_now, manual=False)
            observer.observe(token, view, actual_now)
        except Exception as exc:
            observer.failed, observer.error = True, type(exc).__name__
        return result

    def processed(event, now=None, **kwargs):
        before = set(engine.tokens) if event.kind == "create" else set()
        pressure = getattr(engine, "metrics", {}).get("resource_pressure", False)
        full = len(before) >= observer.settings.max_candidates if hasattr(observer, "settings") else False
        result = process(event, now, **kwargs)
        if event.kind == "create" and hasattr(observer, "coverage"):
            try:
                censored = observer.coverage.admission(before, engine.tokens, pressure, full, result)
                if hasattr(observer, "study"):
                    for mint in censored:
                        if mint in observer.coverage.active:
                            observer.study.db.execute(
                                "INSERT INTO ee_coverage VALUES(?,?,?) ON CONFLICT(session,mint) DO UPDATE SET payload=excluded.payload",
                                (observer.study.session, mint, canonical(observer.coverage.active[mint])),
                            )
                    observer.study.db.commit()
            except Exception as exc:
                observer.failed, observer.error = True, type(exc).__name__
        # Verify the original lifecycle actually accepted the canonical observation.
        if result and event.kind == "create" and hasattr(observer, "created"):
            observer.created(event)
        token = engine.tokens.get(event.mint)
        if (
            result
            and event.kind == "migration"
            and token
            and token.graduation == event.ts
            and token.migration_pool == event.pair
        ):
            try:
                observer.migration(event)
            except Exception as exc:
                observer.failed, observer.error = True, type(exc).__name__
        return result

    engine.intelligence.observe = observed
    if refresh is not None:
        engine.intelligence.refresh = refreshed
    engine.process = processed

    def detach():
        engine.intelligence.observe = original
        if refresh is not None:
            engine.intelligence.refresh = refresh
        engine.process = process

    return detach


async def acquire(study, engine, observer, reference, stop):
    """One research RPC at a time, shared provider limiter; bounded active signals.

    Deadline scheduling is chronological. No retrospective quote requests or
    transaction polling. Token retention/selection in the engine is untouched.
    """
    import json
    from backend.app.early_edge import quote_budget, pump_buy

    rpc = engine.rpc
    oracle = ResearchExecutionOracle(rpc)
    last_request: dict[str, float] = {}
    quality_at = 0.0
    while not stop.is_set():
        if observer.failed:
            raise IntegrityError(
                "Observational research hook failed; collection stopped: " + str(observer.error)
            )
        # USD acquisition is a separate bounded task; cached references never block fill scheduling.
        now = time.time()
        study.expire(now)
        if now - quality_at >= 30:
            study.quality(
                dict(
                    provider_health=dict(rpc.health),
                    observation_counts=dict(observer.coverage.counts),
                    queue=engine.queue.snapshot()
                    if hasattr(engine.queue, "snapshot")
                    else dict(depth=len(engine.queue.heap), drops=engine.queue.dropped),
                    recovery=dict(engine.recovery.health),
                    reference_health=dict(reference.health),
                ),
                now,
            )
            for mint, c in observer.coverage.active.items():
                study.db.execute(
                    "INSERT INTO ee_coverage VALUES(?,?,?) ON CONFLICT(session,mint) DO UPDATE SET payload=excluded.payload",
                    (study.session, mint, canonical(c)),
                )
            study.db.commit()
            quality_at = now
        pending = [
            json.loads(r["payload"])
            for r in study.db.execute("SELECT payload FROM ee_pending ORDER BY signal")
        ]
        # Required endpoint work is never put behind optional descriptive marks.
        by_mint: dict[str, tuple[int, float]] = {}
        for p in pending:
            mint = p["snapshot"]["mint"]
            ts = p["snapshot"]["timestamp"]
            endpoint = ts + p["latency_ms"] / 1000 if p["entry"] is None else ts + min(p["remaining"])
            due = (0, endpoint) if endpoint <= now else (1, last_request.get(mint, 0) + 15)
            if p["entry"] is None and endpoint > now:
                continue
            by_mint[mint] = min(by_mint.get(mint, due), due)
        for (mint, kind), crowd in list(observer.crowd_pending.items()):
            by_mint[mint] = min(by_mint.get(mint, (0, crowd["ts"])), (0, crowd["ts"]))
            if now > crowd["ts"] + 20:
                study.benchmark(
                    mint,
                    kind,
                    crowd["ts"],
                    dict(crowd, quote_status="UNAVAILABLE_QUOTE", reason="BENCHMARK_QUOTE_WINDOW_EXHAUSTED"),
                )
                observer.crowd_pending.pop((mint, kind), None)
        ready = sorted(
            (priority, due, mint)
            for mint, (priority, due) in by_mint.items()
            if due <= now and now - last_request.get(mint, 0) >= 0.5
        )
        if ready:
            _, _, mint = ready[0]
            last_request[mint] = now
            while len(last_request) > 128:
                last_request.pop(next(iter(last_request)))
            proof = observer.migrations.get(mint)
            try:
                state = await oracle.observe(
                    mint, "PUMPSWAP" if proof else "PUMP", proof["pool"] if proof else None, proof
                )
                study.observe_state(state, reference.snapshot(), time.time())
                for (m, kind), crowd in list(observer.crowd_pending.items()):
                    if (
                        m != mint
                        or not crowd["ts"] <= state.requested_at <= state.acquired_at <= crowd["ts"] + 20
                    ):
                        continue
                    try:
                        fx = fx_value(reference.snapshot(), crowd["quote_mint"], state.acquired_at)
                        buy = pump_buy(state.data, quote_budget(4, fx, crowd["quote_mint"]))
                        price = buy["quote_raw"] * fx / 10 ** QUOTES[crowd["quote_mint"]][1] / buy["quantity"]
                        payload = dict(
                            crowd,
                            quote_status="MEASURED",
                            unit_cost_usd=price,
                            quote_acquired_at=state.acquired_at,
                            slot=state.slot,
                        )
                    except QuoteUnavailable:
                        payload = dict(crowd, quote_status="UNAVAILABLE_QUOTE")
                    study.benchmark(mint, kind, crowd["ts"], payload)
                    del observer.crowd_pending[(mint, kind)]
            except QuoteUnavailable as exc:
                study.failure(mint, exc.reason)
            except Exception:
                study.failure(mint, "UNAVAILABLE_PROVIDER_GAP")
        try:
            await asyncio.wait_for(stop.wait(), 0.25)
        except asyncio.TimeoutError:
            pass


async def refresh_reference(reference, stop):
    while not stop.is_set():
        await reference.refresh()
        try:
            await asyncio.wait_for(stop.wait(), 1)
        except asyncio.TimeoutError:
            pass

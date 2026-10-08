import asyncio
import logging
import math
import time
import uuid
from collections import deque, OrderedDict

from alembic import command
from alembic.config import Config

from backend.app.config import ROOT
from backend.app.db import Database
from backend.app.domain import Deduplicator, MarketEvent, PriorityBuffer, State, Token, TRANSITIONS
from backend.app.economics import PositionSizer, TradeCostEstimator, evaluate_candidate
from backend.app.evaluation import OutcomeCollector, evaluate, strategy_version
from backend.app.features import calculate_features, score_token
from backend.app.paper import PaperAccount
from backend.app.providers import DexScreenerProvider, PumpPortalProvider, SolanaProvider
from backend.app.resources import ResourceMonitor

log = logging.getLogger(__name__)


class RadarEngine:
    def __init__(self, settings, db_path=None, offline=False):
        self.settings = settings
        self.session = str(uuid.uuid4())
        self.db = Database(db_path or ROOT / "data" / ("demo.db" if settings.mode == "DEMO" else "radar.db"))
        cfg = Config(str(ROOT / "backend/alembic.ini"))
        with self.db.engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
        self.queue = PriorityBuffer(settings.queue_size)
        self.tokens: dict[str, Token] = {}
        self.creators: OrderedDict = OrderedDict()
        self.dedup = Deduplicator()
        self.costs = TradeCostEstimator(settings)
        self.sizer = PositionSizer(settings, self.costs)
        self.paper = PaperAccount(self.db, settings, self.costs)
        self.collector = OutcomeCollector(self.db, settings, self.costs, self.session)
        self.version, self.strategy_config = strategy_version(settings)
        if not any(r.get("version") == self.version for r in self.db.rows("strategy", limit=10000)):
            self.db.add("strategy", {"version": self.version, "config": self.strategy_config})
        self.db.add(
            "session",
            {"mode": settings.mode, "version": self.version, "session_id": self.session},
            session=self.session,
        )
        self.resources = ResourceMonitor(settings, self.db)
        self.metrics = self.resources.sample()
        self.alerts: deque[dict] = deque(maxlen=100)
        self.alert_times: dict = {}
        self.tasks = []
        self.running = False
        self.processed = 0
        self.out_of_order = 0
        self.duplicates = 0
        self.rejected_payloads = 0
        self.rpc = SolanaProvider()
        self.dex = DexScreenerProvider()
        self.pump = PumpPortalProvider(settings, self.submit, self.deep_mints, require_key=not offline)
        self.lab: dict = {"holdout": {"count": 0, "status": "UNVALIDATED"}, "sample_count": 0}
        self.approved_evidence = None
        for row in reversed(self.db.rows("evidence", limit=1000)):
            if row.get("version") == self.version and (
                (row.get("mode") == "DEMO") == (settings.mode == "DEMO")
            ):
                self.approved_evidence = row["holdout"]
                break
        self.last_lab = 0.0
        self.last_maintenance = 0.0
        self.restore()
        self.db.add(
            "session_context",
            {
                "session_id": self.session,
                "mode": settings.mode,
                "settings": settings.model_dump(),
                "paper_state": self.paper.state,
                "evidence": self.approved_evidence,
                "initial_tokens": [
                    {
                        "mint": t.mint,
                        "name": t.name,
                        "symbol": t.symbol,
                        "created": t.created,
                        "creator": t.creator,
                        "state": t.state.value,
                        "graduation": t.graduation,
                        "grad_high": t.grad_high,
                        "grad_low": t.grad_low if math.isfinite(t.grad_low) else None,
                    }
                    for t in self.tokens.values()
                ],
            },
            session=self.session,
        )

    def restore(self):
        # Bounded recovery from latest compact checkpoints; recent windows re-warm after restart.
        rows = self.db.rows("snapshot", limit=5000)
        for row in reversed(rows):
            if self.settings.mode == "DEMO" and row["mint"] not in self.paper.state["positions"]:
                continue
            if row["mint"] in self.tokens or len(self.tokens) >= self.settings.max_candidates:
                continue
            if row.get("state") in ["REJECTED", "EXPIRED"]:
                continue
            token = Token(
                row["mint"],
                row.get("name", ""),
                row.get("symbol", ""),
                row["created"],
                row.get("creator", ""),
            )
            token.state = State(row["state"])
            token.graduation = row.get("graduation")
            token.grad_high = row.get("grad_high", 0)
            token.grad_low = row.get("grad_low") or math.inf
            # security and prices intentionally need refresh, not assumed current after downtime.
            token.events = deque(maxlen=self.settings.max_events)
            self.tokens[token.mint] = token

    def deep_mints(self):
        # New launches get a temporary activity audition. No holder scans for all discovery.
        eligible = [t for t in self.tokens.values() if t.state not in [State.REJECTED, State.EXPIRED]]
        eligible.sort(
            key=lambda t: (t.priority()[0], t.scores.get("maturity", 0), t.created, t.mint), reverse=True
        )
        limit = (
            self.settings.max_deep // 2 if self.metrics.get("resource_pressure") else self.settings.max_deep
        )
        protected = list(self.paper.state["positions"])
        protected += [m for m, p in self.paper.state["pending"].items() if p.get("action") == "entry"]
        ranked = protected + [t.mint for t in eligible if t.mint not in protected]
        return ranked[: max(1, limit)]

    def submit(self, event):
        token = self.tokens.get(event.mint)
        priority = token.priority()[0] if token else 5
        if event.kind in ["migration", "security"]:
            priority = 110
        return self.queue.put(event, priority)

    def alert(self, level, mint, message, now):
        key = (level, mint)
        if now - self.alert_times.get(key, -1000) < 30:
            return
        self.alert_times[key] = now
        if len(self.alert_times) > 1000:
            oldest = min(self.alert_times, key=lambda k: self.alert_times[k])
            del self.alert_times[oldest]
        self.alerts.append({"level": level, "mint": mint, "message": message, "ts": now})

    def transition(self, token, state, reason, now):
        previous = token.transition(state)
        self.db.add(
            "transition",
            {"previous": previous.value, "new": state.value, "reason": reason, "scores": token.scores},
            token.mint,
            self.session,
            now,
        )
        if state in [
            State.MATURING,
            State.NEAR_GRADUATION,
            State.GRADUATED,
            State.ENTRY_CANDIDATE,
            State.REJECTED,
        ]:
            self.alert(state.value, token.mint, reason, now)

    def admit(self, event):
        if event.kind not in ["create", "migration"]:
            return None
        if self.metrics.get("resource_pressure") or self.metrics.get("storage_full"):
            return None
        if len(self.tokens) >= self.settings.max_candidates:
            unprotected = [t for t in self.tokens.values() if t.mint not in self.paper.state["positions"]]
            if not unprotected:
                return None
            weakest = min(unprotected, key=lambda t: (t.priority(), t.created))
            incoming = 110 if event.kind == "migration" else 5
            if weakest.priority()[0] > incoming:
                return None
            if State.EXPIRED in TRANSITIONS[weakest.state]:
                self.transition(weakest, State.EXPIRED, "Evicted by stronger/newer candidate", event.ts)
            del self.tokens[weakest.mint]
        token = Token(event.mint, event.name, event.symbol, event.ts, event.creator)
        token.events = deque(maxlen=self.settings.max_events)
        self.tokens[event.mint] = token
        self.transition(token, State.SCREENING, "Discovery received", event.ts)
        self.transition(token, State.WATCHING, "Cheap activity screening", event.ts)
        return token

    def process(self, event, now=None):
        now = event.ts if now is None else now
        if event.source == "DEMO" and self.settings.mode != "DEMO":
            self.rejected_payloads += 1
            return False
        if abs(now - event.ts) > self.settings.max_data_age_seconds:
            self.rejected_payloads += 1
            return False
        if not self.dedup.accept(event.event_id):
            self.duplicates += 1
            return False
        if not self.metrics.get("storage_full") and not self.db.reserve_event(event.event_id, event.ts):
            self.duplicates += 1
            return False
        context_before = {
            "resource_pressure": self.metrics.get("resource_pressure", False),
            "storage_full": self.metrics.get("storage_full", False),
            "providers_connected": {
                "pump": self.pump.health["connected"],
                "rpc": self.rpc.health["connected"],
                "dex": self.dex.health["connected"],
            },
            "degraded": {m: True for m, t in self.tokens.items() if t.degraded},
        }
        token = self.tokens.get(event.mint) or self.admit(event)
        if token is None:
            return False
        if event.ts < token.last_event:
            token.degraded = True
            self.out_of_order += 1
            return False
        token.last_event = event.ts
        if token.creator:
            from backend.app.creator import CreatorRiskProfile

            if token.creator not in self.creators:
                self.creators[token.creator] = CreatorRiskProfile(token.creator)
            self.creators[token.creator].observe(event, token)
            self.creators.move_to_end(token.creator)
            if len(self.creators) > 250:
                self.creators.popitem(last=False)

        if event.kind == "security":
            token.security = event.evidence
            token.last_security = event.ts
            if event.evidence.get("curve_progress") is not None:
                token.curve_progress = event.evidence["curve_progress"]
            if not self.metrics.get("storage_full"):
                self.db.add("security", event.evidence, event.mint, self.session, event.ts)
        if event.kind == "trade":
            if event.source == "PumpPortal" and event.currency == "unknown":
                curve = token.security.get("bonding_curve") or {}
                pools = token.security.get("verified_pools") or []
                quote = curve.get("quote_mint") or (pools[0].get("quote_mint") if pools else None)
                event.currency = {
                    "So11111111111111111111111111111111111111112": "SOL",
                    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
                }.get(quote or "", "unknown")
            token.last_trade = event.ts
        if event.kind in ["trade", "market"]:
            token.events.append(event)
        if event.price is not None:
            token.price = event.price
            token.last_price = event.ts
            token.source_prices[event.source] = (event.ts, event.price)
            recent = [v for v in token.source_prices.values() if 0 <= event.ts - v[0] <= 20]
            token.disagreement = (
                len(recent) > 1 and max(v[1] for v in recent) / min(v[1] for v in recent) > 1.15
            )
            if token.graduation:
                token.grad_high = max(token.grad_high, event.price)
                token.grad_low = min(token.grad_low, event.price)
        if event.liquidity is not None:
            token.liquidity = event.liquidity
            token.last_liquidity = event.ts
        if event.market_cap is not None:
            token.market_cap = event.market_cap
        if event.curve_progress is not None:
            token.curve_progress = event.curve_progress
        if (
            event.kind == "migration"
            and token.graduation is None
            and token.state not in [State.REJECTED, State.EXPIRED]
        ):
            self.transition(token, State.GRADUATING, "Provider migration evidence", event.ts)
            token.graduation = event.ts
            self.db.add(
                "graduation",
                {
                    "timestamp": event.ts,
                    "source": event.source,
                    "signature": event.signature,
                    "pre_graduation_scores": token.scores,
                    "pair": event.pair,
                },
                token.mint,
                self.session,
                event.ts,
            )
            self.transition(token, State.GRADUATED, "Migration recorded", event.ts)
            self.transition(
                token,
                State.POST_GRAD_OBSERVATION,
                "Await pullback, stabilisation and renewed buying",
                event.ts,
            )
        self.analyse(token, event.ts)
        if not self.metrics.get("storage_full"):
            self.collector.observe(token, event)
        self.paper.observe(token, event.ts)
        if (
            token.price
            and event.ts - token.last_signal >= self.settings.signal_interval_seconds
            and not self.metrics.get("storage_full")
        ):
            self.collector.signal(token, event.ts, self.version)
            token.last_signal = event.ts
            self.paper.request_entry(token, event.ts, self.version)
        if not self.metrics.get("storage_full"):
            self.db.add(
                "event",
                {
                    "event": event.model_dump(),
                    "scores_after": token.scores,
                    "state_after": token.state.value,
                    "decision_after": token.decision["decision"],
                    "reasons_after": token.decision["reasons"],
                    "context_before": context_before,
                },
                token.mint,
                self.session,
                event.ts,
            )
        if event.price:
            token.history.append(
                {
                    "ts": event.ts,
                    "price": event.price,
                    "market_cap": token.market_cap,
                    "maturity": token.scores["maturity"],
                    "momentum": token.scores["momentum"],
                    "buyers": token.features["180"]["estimated_independent_buyers"],
                    "net_flow": token.features["180"]["net_flow"],
                }
            )
        self.processed += 1
        return True

    def analyse(self, token, now):
        token.features = calculate_features(token, now)
        token.scores = score_token(token, now)
        holdout = self.lab.get("holdout", {})
        # A descriptive dashboard split is not sufficient approval. Frozen prospective evidence required.
        evidence = self.approved_evidence
        edge = evidence.get("expectancy_net_pct") if evidence else None
        token.viability = self.sizer.size(
            self.paper.state["cash"], token.liquidity, edge, token.features["180"]["volatility_pct"]
        )
        healthy = self.settings.mode == "DEMO" or (
            self.pump.health["connected"] and self.rpc.health["connected"] and self.dex.health["connected"]
        )
        token.decision = evaluate_candidate(
            token,
            self.settings,
            now,
            healthy,
            self.metrics.get("resource_pressure", False) or self.metrics.get("storage_full", False),
            evidence,
        )
        token.decision["historical_evidence"] = evidence or holdout or {"count": 0, "status": "UNVALIDATED"}
        if token.decision["decision"] == "REJECT" and token.state not in [State.REJECTED, State.EXPIRED]:
            self.transition(token, State.REJECTED, "; ".join(token.decision["reasons"][:3]), now)
        elif token.state == State.WATCHING and token.scores["maturity"] >= self.settings.min_maturity:
            self.transition(token, State.MATURING, "Persistent distributed activity", now)
        elif (
            token.state == State.MATURING and token.curve_progress is not None and token.curve_progress >= 85
        ):
            self.transition(token, State.NEAR_GRADUATION, "Observed curve progress ≥85%", now)
        elif token.decision["decision"] == "ALLOW_PAPER_ENTRY" and token.state == State.POST_GRAD_OBSERVATION:
            self.transition(token, State.ENTRY_CANDIDATE, "Strict risk and economics gates passed", now)
        elif token.state == State.ENTRY_CANDIDATE and token.decision["decision"] != "ALLOW_PAPER_ENTRY":
            self.transition(token, State.POST_GRAD_OBSERVATION, "Entry gates no longer met", now)

    async def start(self):
        self.running = True
        self.tasks = [asyncio.create_task(self.run_loop(), name="monitor")]
        if self.settings.mode == "DEMO":
            self.tasks.append(asyncio.create_task(self.run_demo(), name="demo"))
        else:
            self.tasks.extend(
                [
                    asyncio.create_task(self.pump.run(), name="pumpportal"),
                    asyncio.create_task(self.run_enrichment(), name="enrichment"),
                ]
            )

    async def stop(self):
        self.running = False
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.rpc.close()
        await self.dex.close()
        self.checkpoint(time.time())
        self.db.engine.dispose()

    async def run_demo(self):
        from backend.app.demo import demo_events

        start = time.time()
        tick = 0
        while True:
            # Wall-clock paced, realistic no offline price substituted into live mode.
            for event in demo_events(start, tick, namespace=self.session[:8]):
                self.submit(event)
            tick += 1
            await asyncio.sleep(1)

    async def run_enrichment(self):
        while True:
            try:
                now = time.time()
                deep = self.deep_mints()
                graduated = [mint for mint in deep if self.tokens[mint].graduation]
                for event in await self.dex.markets(graduated):
                    self.submit(event)
                # At most one full holder/security scan per iteration, cached with TTL.
                due = [
                    self.tokens[m]
                    for m in deep
                    if (
                        self.tokens[m].graduation
                        or self.tokens[m].features.get("180", {}).get("raw_unique_buyers", 0) >= 5
                    )
                    and now - self.tokens[m].last_security
                    > (60 if self.tokens[m].priority()[0] >= 90 else self.settings.security_ttl_seconds)
                ]
                if due:
                    token = max(due, key=lambda t: t.priority())
                    token.last_security = now  # failed refresh also backs off
                    pairs = [
                        pair
                        for _, pair in self.dex.cache.values()
                        if pair and pair["baseToken"]["address"] == token.mint
                    ]
                    known = {p["pairAddress"] for p in pairs}
                    report = await self.rpc.inspect(token.mint, token.creator, known)
                    self.submit(
                        MarketEvent(
                            mint=token.mint,
                            ts=time.time(),
                            source="Solana RPC",
                            kind="security",
                            event_id=f"sec:{token.mint}:{now}",
                            evidence=report,
                        )
                    )
            except (RuntimeError, ValueError, KeyError, TypeError) as exc:
                log.warning("Enrichment degraded: %s", type(exc).__name__)
                self.alert("SYSTEM", "", "Provider enrichment unavailable; entries blocked", time.time())
            await asyncio.sleep(5)

    def checkpoint(self, now):
        if self.metrics.get("storage_full"):
            return
        for token in self.tokens.values():
            if token.creator in self.creators:
                self.db.add(
                    "creator_profile",
                    self.creators[token.creator].report(token),
                    token.mint,
                    self.session,
                    now,
                )
            self.db.add(
                "snapshot",
                {
                    "name": token.name,
                    "symbol": token.symbol,
                    "created": token.created,
                    "creator": token.creator,
                    "state": token.state.value,
                    "graduation": token.graduation,
                    "grad_high": token.grad_high,
                    "grad_low": token.grad_low if math.isfinite(token.grad_low) else None,
                    "scores": token.scores,
                },
                token.mint,
                self.session,
                now,
            )

    async def run_loop(self):
        while True:
            try:
                now = time.time()
                while self.queue.affected:
                    mint = self.queue.affected.popleft()
                    if mint in self.tokens:
                        self.tokens[mint].degraded = True
                for event in self.queue.drain(100):
                    self.process(event, now)
                for token in list(self.tokens.values()):
                    self.analyse(token, now)
                    if now - token.last_event > 300 and token.mint not in self.paper.state["positions"]:
                        from backend.app.domain import TRANSITIONS

                        if State.EXPIRED in TRANSITIONS[token.state]:
                            self.transition(token, State.EXPIRED, "Inactive candidate expired", now)
                        del self.tokens[token.mint]
                self.paper.expire_pending(now)
                if not self.metrics.get("storage_full"):
                    self.collector.expire(now)
                self.metrics = self.resources.sample()
                if self.metrics["resource_pressure"]:
                    self.alert("SYSTEM", "", "RESOURCE PRESSURE — reducing monitoring", now)
                    for token in self.tokens.values():
                        while len(token.events) > 100:
                            token.events.popleft()
                        token.degraded = True
                if now - self.last_lab > 60:
                    self.lab = await asyncio.to_thread(
                        evaluate,
                        self.db,
                        self.settings,
                        "demo" if self.settings.mode == "DEMO" else "real",
                        self.version,
                        300,
                        now,
                    )
                    self.last_lab = now
                if now - self.last_maintenance > 60:
                    await asyncio.to_thread(self.db.retention, self.settings, now)
                    self.metrics = self.resources.sample()
                    self.checkpoint(now)
                    self.last_maintenance = now
                # Detect silently ended provider tasks.
                if any(t.done() for t in self.tasks if t.get_name() != "monitor"):
                    self.metrics["resource_pressure"] = True
                    self.alert("SYSTEM", "", "Background provider stopped; entries blocked", now)
            except Exception as exc:
                log.error("Monitor failed safely: %s", type(exc).__name__)
                for token in self.tokens.values():
                    token.degraded = True
                self.alert("SYSTEM", "", "Monitor error; data degraded and entries blocked", time.time())
            await asyncio.sleep(0.25)

    def token_view(self, token, now, detail=False):
        view = {
            "mint": token.mint,
            "name": token.name,
            "symbol": token.symbol,
            "age_seconds": max(0, now - token.created),
            "state": token.state.value,
            "creator": token.creator,
            "graduation": token.graduation,
            "price": token.price,
            "market_cap": token.market_cap,
            "liquidity": token.liquidity,
            "initial_drawdown_pct": 100 * (1 - token.grad_low / token.grad_high)
            if token.grad_high and math.isfinite(token.grad_low)
            else None,
            "recovery_pct": 100 * (token.price / token.grad_low - 1)
            if token.price and math.isfinite(token.grad_low)
            else None,
            "scores": token.scores,
            "features": token.features.get("180", {}),
            "security": token.security,
            "decision": token.decision,
            "viability": token.viability,
            "data_quality": "DEGRADED"
            if token.degraded
            else ("STALE" if now - token.last_price > self.settings.max_data_age_seconds else "CURRENT"),
            "price_age_seconds": now - token.last_price if token.last_price else None,
            "source_prices": token.source_prices,
            "curve_progress": token.curve_progress,
        }
        if detail:
            view["creator_profile"] = (
                self.creators[token.creator].report(token) if token.creator in self.creators else None
            )
            view["history"] = list(token.history)
            view["transitions"] = self.db.rows("transition", mint=token.mint, limit=100)
            view["signals"] = self.db.rows("signal", mint=token.mint, limit=30)
        return view

    def snapshot(self):
        now = time.time()
        tokens = sorted(self.tokens.values(), key=lambda t: t.priority(), reverse=True)
        return {
            "name": "CRISPY WINNER — Graduation Radar",
            "mode": self.settings.mode,
            "simulated": self.settings.mode == "DEMO",
            "session": self.session,
            "strategy_version": self.version,
            "timestamp": now,
            "tokens": [self.token_view(t, now) for t in tokens],
            "paper": self.paper.summary(self.tokens),
            "lab": self.lab,
            "alerts": list(self.alerts),
            "health": {
                **self.metrics,
                "active_candidates": len(tokens),
                "deep_monitored": len(self.deep_mints()),
                "queue_size": len(self.queue.heap),
                "queue_limit": self.queue.maximum,
                "dropped_events": self.queue.dropped,
                "processed_events": self.processed,
                "duplicates": self.duplicates,
                "out_of_order": self.out_of_order,
                "pending_outcomes": len(self.collector.pending),
                "providers": {
                    "PumpPortal": self.pump.health,
                    "Solana RPC": self.rpc.health,
                    "DEX Screener": self.dex.health,
                },
            },
            "notice": "Historical or paper performance does not guarantee future results. Liquidity can disappear.",
        }

import asyncio
import logging
import math
import os
import time
import uuid
from collections import deque, OrderedDict

from alembic import command
from alembic.config import Config

from backend.app.companion import companion_view
from backend.app.config import ROOT
from backend.app.db import Database
from backend.app.discovery import DiscoveryProvider, OnchainPumpDiscovery
from backend.app.domain import Deduplicator, MarketEvent, PriorityBuffer, State, Token, TRANSITIONS
from backend.app.economics import PositionSizer, TradeCostEstimator, evaluate_candidate
from backend.app.evaluation import OutcomeCollector, evaluate, strategy_version
from backend.app.features import calculate_features, score_token
from backend.app.paper import PaperAccount
from backend.app.providers import DexScreenerProvider, PumpPortalProvider, SolanaProvider
from backend.app.resources import ResourceMonitor
from backend.app.intelligence import Intelligence

log = logging.getLogger(__name__)


class RadarEngine:
    def __init__(self, settings, db_path=None, offline=False):
        self.settings = settings
        self.offline = offline
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
        self.launch_dedup = Deduplicator()
        self.duplicate_discoveries = 0
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
        self.rpc = SolanaProvider(settings=settings)
        self.dex = DexScreenerProvider()
        self.pump = PumpPortalProvider(
            settings, self.submit, self.deep_mints, require_key=not offline,
            enabled=os.getenv("PUMPPORTAL_ENABLED", "false").lower() == "true",
        )
        self.onchain = OnchainPumpDiscovery(self.submit)
        self.discovery_providers: list[DiscoveryProvider] = [self.onchain, self.pump]
        self.lab: dict = {"holdout": {"count": 0, "status": "UNVALIDATED"}, "sample_count": 0}
        self.approved_evidence = None
        for row in reversed(self.db.rows("evidence", limit=1000)):
            if row.get("version") == self.version and (
                (row.get("mode") == "DEMO") == (settings.mode == "DEMO")
            ):
                self.approved_evidence = row["holdout"]
                break
        self.curve_metrics = {
            "curve_hot_poll_requests": 0,
            "curve_background_poll_requests": 0,
            "curve_accounts_attempted": 0,
            "curve_accounts_checked": 0,
            "curve_observations_verified": 0,
            "curve_http_requests": 0,
        }
        self.last_hot_batch = 0.0
        self.last_background_batch = 0.0
        self.expiry_metrics = {"inactive_expirations": 0, "expiry_deferred_for_poll": 0}
        self.background_backoff_until = 0.0
        self.background_backoff_level = 0
        self.rpc_errors_seen = 0
        self.last_security_scan = 0.0
        self.last_lab = 0.0
        self.last_maintenance = 0.0
        self.restore()
        self.intelligence = Intelligence(self)
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
            if token.state in [State.MATURING, State.NEAR_GRADUATION]:
                token.state = State.WATCHING  # Restored lifecycle requires new verified evidence.
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
            key=lambda t: (
                t.priority()[0],
                t.curve_progress
                if t.curve_progress is not None and t.curve_progress >= self.settings.lifecycle_maturing_pct
                else -1,
                t.created,
                t.mint,
            ),
            reverse=True,
        )
        limit = (
            self.settings.max_deep // 2 if self.metrics.get("resource_pressure") else self.settings.max_deep
        )
        protected = list(self.paper.state["positions"])
        protected += [m for m, p in self.paper.state["pending"].items() if p.get("action") == "entry"]
        protected = [m for m in protected if m in self.tokens]
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
            incoming = 110 if event.kind == "migration" else 30
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
        if event.kind == "create":
            if event.mint in self.tokens or not self.launch_dedup.accept(event.mint) or (
                not self.metrics.get("storage_full")
                and not self.db.reserve_event(f"launch:{event.mint}", event.ts)
            ):
                self.duplicates += 1
                self.duplicate_discoveries += 1
                return False
        context_before = {
            "resource_pressure": self.metrics.get("resource_pressure", False),
            "storage_full": self.metrics.get("storage_full", False),
            "providers_connected": {
                "pump": self.discovery_connected(),
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

        if event.kind == "create":
            token.launch_metadata = event.evidence.get("launch_metadata", {})
        if event.kind == "curve":
            token.curve_progress = event.evidence.get("curve_progress")
            token.last_curve = event.ts
        if event.kind == "security":
            token.security = event.evidence
            token.last_security = event.ts
            if event.evidence.get("curve_progress") is not None:
                token.curve_progress = event.evidence["curve_progress"]
            if not self.metrics.get("storage_full"):
                self.db.add("security", event.evidence, event.mint, self.session, event.ts)
        if event.kind == "security" and event.evidence.get("curve_progress") is not None:
            token.last_curve = event.ts
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
            token.market_source = event.source if event.currency == "USD" else ""
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
            token.last_market_cap = event.ts
            token.cap_source = (
                event.source
                if event.currency == "USD" and event.evidence.get("market_cap_kind") == "MARKET_CAP"
                else ""
            )
        if event.curve_progress is not None:
            token.curve_progress = event.curve_progress
        if token.curve_progress is not None:
            token.curve_peak_progress = max(token.curve_peak_progress or 0, token.curve_progress)
        # Compact research history only from already acquired, verified lifecycle observations.
        if (
            event.kind in ["curve", "security"]
            and event.evidence.get("data_quality") == "VERIFIED"
            and isinstance(event.evidence.get("curve_progress"), (int, float))
            and not isinstance(event.evidence.get("curve_progress"), bool)
            and math.isfinite(event.evidence["curve_progress"])
            and 0 <= event.evidence["curve_progress"] <= 100
            and (not token.curve_history or event.ts > token.curve_history[-1][0])
        ):
            token.curve_history.append((event.ts, token.curve_progress))
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
                    "market_cap": token.market_cap
                    if token.cap_source == "DEX Screener"
                    and 0 <= event.ts - token.last_market_cap <= self.settings.max_data_age_seconds
                    else None,
                    "maturity": token.scores["maturity"],
                    "momentum": token.scores["momentum"],
                    "buyers": token.features["180"]["estimated_independent_buyers"]
                    if self.trade_evidence_available()
                    else None,
                    "net_flow": token.features["180"]["net_flow"]
                    if self.trade_evidence_available()
                    else None,
                }
            )
        self.intelligence.observe(token, event.ts)
        self.processed += 1
        return True

    def analyse(self, token, now):
        token.last_analysis = now
        token.features = calculate_features(token, now)
        token.scores = score_token(token, now)
        holdout = self.lab.get("holdout", {})
        # A descriptive dashboard split is not sufficient approval. Frozen prospective evidence required.
        evidence = self.approved_evidence
        edge = evidence.get("expectancy_net_pct") if evidence else None
        key = (
            self.paper.state["cash"],
            token.liquidity,
            edge,
            5 / max(5, token.features["180"]["volatility_pct"]),
            token.features["180"]["volatility_pct"] if edge is not None else None,
        )
        if key != token.viability_key:
            token.viability = self.sizer.size(
                self.paper.state["cash"], token.liquidity, edge, token.features["180"]["volatility_pct"]
            )
            token.viability_key = key
        healthy = self.settings.mode == "DEMO" or (
            self.discovery_connected()
            and self.rpc.health["connected"]
            and (token.graduation is None or self.dex.health["connected"])
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
        elif (
            token.state == State.NEAR_GRADUATION
            and token.graduation is None
            and (
                not self.curve_current(token, now)
                or token.curve_progress < self.settings.lifecycle_near_exit_pct
            )
        ):
            self.transition(
                token,
                State.MATURING,
                "Curve evidence unavailable/stale"
                if not self.curve_current(token, now)
                else "Verified curve retreat below near-graduation exit threshold; lifecycle only",
                now,
            )
        elif (
            token.state == State.MATURING
            and token.graduation is None
            and (
                token.scores["maturity"] < self.settings.min_maturity
                and (
                    not self.curve_current(token, now)
                    or token.curve_progress < self.settings.lifecycle_maturing_pct
                )
            )
        ):
            self.transition(token, State.WATCHING, "Meaningful lifecycle evidence no longer current", now)
        elif token.state == State.WATCHING and (
            token.scores["maturity"] >= self.settings.min_maturity
            or (
                self.curve_current(token, now)
                and token.curve_progress >= self.settings.lifecycle_maturing_pct
            )
        ):
            self.transition(
                token,
                State.MATURING,
                "Observed lifecycle progress or persistent distributed activity; not investment quality",
                now,
            )
        elif (
            token.state == State.MATURING
            and self.curve_current(token, now)
            and token.curve_progress >= self.settings.lifecycle_near_pct
        ):
            self.transition(
                token,
                State.NEAR_GRADUATION,
                "Observed high curve progress; lifecycle only, not a buy recommendation",
                now,
            )
        elif token.decision["decision"] == "ALLOW_PAPER_ENTRY" and token.state == State.POST_GRAD_OBSERVATION:
            self.transition(token, State.ENTRY_CANDIDATE, "Strict risk and economics gates passed", now)
        elif token.state == State.ENTRY_CANDIDATE and token.decision["decision"] != "ALLOW_PAPER_ENTRY":
            self.transition(token, State.POST_GRAD_OBSERVATION, "Entry gates no longer met", now)

    def discovery_connected(self):
        return any(provider.health["connected"] for provider in self.discovery_providers)

    async def start(self):
        self.running = True
        self.tasks = [asyncio.create_task(self.run_loop(), name="monitor")]
        if self.settings.mode == "DEMO":
            self.tasks.append(asyncio.create_task(self.run_demo(), name="demo"))
        else:
            self.tasks.append(asyncio.create_task(self.run_enrichment(), name="enrichment"))
            for name, provider in zip(("onchain-discovery", "pumpportal"), self.discovery_providers):
                if provider.health["enabled"]:
                    self.tasks.append(asyncio.create_task(provider.run(), name=name))

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

    def curve_current(self, token, now):
        return token.curve_progress is not None and (
            self.settings.mode == "DEMO"
            or 0 <= now - token.last_curve <= self.settings.curve_poll_seconds * 2
        )

    def background_tokens(self, deep):
        hot = set(deep)
        return [
            t
            for t in self.tokens.values()
            if t.mint not in hot and t.graduation is None and t.state not in [State.REJECTED, State.EXPIRED]
        ]

    def candidate_expiry_deadline(self, token, hot=None, background_rank=None):
        """Current scheduling allowance, capped relative to last activity, never to now."""
        activity = token.last_event or token.created
        baseline = activity + self.settings.candidate_inactivity_seconds
        if (
            self.settings.mode == "DEMO"
            or token.graduation is not None
            or token.state in [State.REJECTED, State.EXPIRED]
        ):
            return baseline
        hot = set(self.deep_mints()) if hot is None else hot
        tier = "hot" if token.mint in hot else "background"
        interval = self.rpc.interval(
            self.settings.curve_poll_seconds
            if tier == "hot"
            else self.settings.curve_background_revisit_seconds,
            tier,
        )
        eligible = max(self.rpc.health["rate_limited_until"], self.rpc.health["next_eligible_rpc"])
        opportunity = max((token.last_curve_attempt or token.created) + interval, eligible)
        if tier == "hot":
            opportunity = max(opportunity, self.last_hot_batch + interval)
        else:
            cadence = self.rpc.interval(self.settings.curve_background_batch_seconds, tier)
            if self.rpc.health["backoff_level"] >= 3:
                eligible = max(eligible, self.rpc.health["next_eligible_rpc"] + self.rpc.interval(30, tier))
            # Same oldest-first order as the scheduler. Account for bounded batches ahead;
            # recent arrivals cannot keep moving an older token's slot to the back.
            if background_rank is None:
                background_rank = self.background_expiry_ranks(hot)
            ahead = background_rank.get(token.mint, 0)
            opportunity = max(
                opportunity, eligible, self.background_backoff_until, self.last_background_batch + cadence
            )
            opportunity += (ahead // self.settings.curve_background_batch_size) * cadence
        return min(
            activity + self.settings.candidate_expiry_max_seconds,
            max(baseline, opportunity + self.settings.candidate_expiry_grace_seconds),
        )

    def background_expiry_ranks(self, hot):
        ordered = sorted(
            self.background_tokens(hot), key=lambda t: (t.last_curve_attempt or t.created, t.created, t.mint)
        )
        return {token.mint: rank for rank, token in enumerate(ordered)}

    def expire_inactive_candidates(self, now):
        hot = set(self.deep_mints())
        background_rank = self.background_expiry_ranks(hot)
        deferred = 0
        for token in list(self.tokens.values()):
            if (
                token.mint in self.paper.state["positions"]
                or self.paper.state["pending"].get(token.mint, {}).get("action") == "entry"
                or State.EXPIRED not in TRANSITIONS[token.state]
            ):
                continue
            if now <= (token.last_event or token.created) + self.settings.candidate_inactivity_seconds:
                continue
            if now <= self.candidate_expiry_deadline(token, hot, background_rank):
                deferred += 1
                continue
            self.transition(token, State.EXPIRED, "Inactive candidate expired", now)
            del self.tokens[token.mint]
            self.expiry_metrics["inactive_expirations"] += 1
        # Current gauge, not four duplicate deferrals per second per candidate.
        self.expiry_metrics["expiry_deferred_for_poll"] = deferred

    def background_health_backoff(self, now):
        errors = self.rpc.health["errors"]
        if errors > self.rpc_errors_seen:
            self.background_backoff_level = min(3, self.background_backoff_level + 1)
            delay = min(
                300, self.settings.curve_background_backoff_seconds * 2 ** (self.background_backoff_level - 1)
            )
            self.background_backoff_until = max(
                self.background_backoff_until, now + delay, self.rpc.health["rate_limited_until"]
            )
        self.rpc_errors_seen = errors

    async def poll_curves(self, selected, tier, batch_size):
        now = time.time()
        for token in selected:
            token.last_curve_attempt = now
        self.curve_metrics[f"curve_{tier}_poll_requests"] += 1
        self.curve_metrics["curve_accounts_attempted"] += len(selected)
        requests_before = self.rpc.health["requests"]
        try:
            if tier == "background":
                reports = await self.rpc.curve_progress_batch(
                    [t.mint for t in selected], batch_size, retry_attempts=1
                )
            else:
                reports = await self.rpc.curve_progress_batch([t.mint for t in selected], batch_size)
            self.curve_metrics["curve_accounts_checked"] += len(reports)
            self.curve_metrics["curve_observations_verified"] += sum(
                r.get("curve_progress") is not None for r in reports.values()
            )
        except (RuntimeError, ValueError, KeyError, TypeError):
            reports = {t.mint: {"curve_progress": None, "data_quality": "UNKNOWN"} for t in selected}
            # Includes malformed responses even if the HTTP connection succeeded.
            self.background_backoff_until = max(
                self.background_backoff_until, time.time() + self.settings.curve_background_backoff_seconds
            )
        finally:
            self.curve_metrics["curve_http_requests"] += self.rpc.health["requests"] - requests_before
        for mint, report in reports.items():
            self.submit(
                MarketEvent(
                    mint=mint,
                    ts=time.time(),
                    source="Solana RPC",
                    kind="curve",
                    event_id=f"curve:{mint}:{now}",
                    evidence={**report, "poll_tier": tier},
                )
            )
        self.background_health_backoff(time.time())

    async def enrich_once(self):
        now = time.time()
        deep = self.deep_mints()
        due_curves = [
            self.tokens[m]
            for m in deep
            if self.tokens[m].graduation is None
            and now - self.tokens[m].last_curve_attempt
            >= self.rpc.interval(self.settings.curve_poll_seconds, "hot")
        ]
        due_curves.sort(key=lambda t: (t.last_curve_attempt, -t.priority()[0]))
        selected = due_curves[: self.settings.curve_batch_size]
        # Cooldowns do not block the loop waiting on low-priority work.
        if (
            selected
            and self.rpc.eligible("hot")
            and now - self.last_hot_batch >= self.rpc.interval(self.settings.curve_poll_seconds, "hot")
        ):
            self.last_hot_batch = now
            await self.poll_curves(selected, "hot", self.settings.curve_batch_size)
        deep = self.deep_mints()  # Membership may change while RPC was awaiting a response.
        graduated = [mint for mint in deep if self.tokens[mint].graduation is not None]
        try:
            for event in await self.dex.markets(graduated):
                self.submit(event)
        except (RuntimeError, ValueError, KeyError, TypeError):
            self.alert("SYSTEM", "", "Post-graduation market enrichment unavailable", time.time())
        deep = self.deep_mints()  # Expiry/eviction can also happen during DEX awaits.
        # One full scan per global interval, only within the bounded deep set.
        due = [
            self.tokens[m]
            for m in deep
            if (
                self.tokens[m].graduation is not None
                or (
                    self.tokens[m].curve_progress is not None
                    and 0 <= now - self.tokens[m].last_curve <= self.settings.curve_poll_seconds * 2
                    and self.tokens[m].curve_progress >= self.settings.security_min_curve_pct
                )
            )
            and now - self.tokens[m].last_security_attempt
            >= self.rpc.interval(self.settings.security_ttl_seconds, "security")
        ]
        if (
            due
            and now - self.last_security_scan
            >= self.rpc.interval(self.settings.security_scan_interval_seconds, "security")
            and self.rpc.eligible("security")
        ):
            token = max(due, key=lambda t: t.priority())
            token.last_security_attempt = self.last_security_scan = now
            known = {
                p["pairAddress"]
                for _, p in self.dex.cache.values()
                if p and p["baseToken"]["address"] == token.mint
            }
            try:
                report = await self.rpc.inspect(token.mint, token.creator, known)
            except (RuntimeError, ValueError, KeyError, TypeError):
                report = {
                    "data_quality": "UNKNOWN",
                    "risk_score": 100,
                    "hard_failures": [],
                    "warnings": ["Security refresh failed"],
                    "last_updated": time.time(),
                }
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

        now = time.time()
        self.background_health_backoff(now)
        # Strictly cheap, oldest-first sweep after hot and selective security work.
        # New arrivals cannot jump ahead of tokens awaiting their first/repeated poll.
        background = self.background_tokens(self.deep_mints())
        waiting = [
            t
            for t in background
            if not t.last_curve_attempt
            or now - t.last_curve_attempt
            >= self.rpc.interval(self.settings.curve_background_revisit_seconds, "background")
        ]
        waiting.sort(key=lambda t: (t.last_curve_attempt or t.created, t.created, t.mint))
        if (
            waiting
            and self.rpc.eligible("background")
            and not self.metrics.get("resource_pressure")
            and not self.metrics.get("storage_full")
            and now >= max(self.background_backoff_until, self.rpc.health["rate_limited_until"])
            and now - self.last_background_batch
            >= self.rpc.interval(self.settings.curve_background_batch_seconds, "background")
        ):
            self.last_background_batch = now
            errors_before = self.rpc.health["errors"]
            await self.poll_curves(
                waiting[: self.settings.curve_background_batch_size],
                "background",
                self.settings.curve_background_batch_size,
            )
            if self.rpc.health["errors"] == errors_before and time.time() >= self.background_backoff_until:
                self.background_backoff_level = max(0, self.background_backoff_level - 1)

    async def run_enrichment(self):
        while True:
            await self.enrich_once()
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
                    if now - token.last_analysis >= 1:
                        self.analyse(token, now)
                self.expire_inactive_candidates(now)
                self.intelligence.refresh(now)
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
            "companion": companion_view(
                token,
                self.settings,
                now,
                evidence=self.approved_evidence,
                healthy=self.settings.mode == "DEMO"
                or (
                    self.discovery_connected()
                    and self.rpc.health["connected"]
                    and (token.graduation is None or self.dex.health["connected"])
                ),
                resource_pressure=self.metrics.get("resource_pressure", False)
                or self.metrics.get("storage_full", False),
            ).model_dump(mode="json"),
            "mint": token.mint,
            "name": token.name,
            "symbol": token.symbol,
            "age_seconds": max(0, now - token.created),
            "state": token.state.value,
            "creator": token.creator,
            "graduation": token.graduation,
            "price": token.price,
            "market_cap": token.market_cap
            if token.cap_source == "DEX Screener"
            and 0 <= now - token.last_market_cap <= self.settings.max_data_age_seconds
            else None,
            "market_cap_observed_at": token.last_market_cap or None,
            "market_cap_quality": "CURRENT"
            if token.cap_source == "DEX Screener"
            and 0 <= now - token.last_market_cap <= self.settings.max_data_age_seconds
            else "UNAVAILABLE / STALE",
            "liquidity": token.liquidity,
            "initial_drawdown_pct": 100 * (1 - token.grad_low / token.grad_high)
            if token.grad_high and math.isfinite(token.grad_low)
            else None,
            "recovery_pct": 100 * (token.price / token.grad_low - 1)
            if token.price and math.isfinite(token.grad_low)
            else None,
            "scores": self.display_scores(token),
            "features": self.display_features(token),
            "launch_metadata": token.launch_metadata,
            "trade_evidence": "UNAVAILABLE" if not self.trade_evidence_available() else "OBSERVED_ONLY",
            "curve_observed_at": token.last_curve or None,
            "curve_peak_progress": token.curve_peak_progress,
            "curve_data_quality": "UNKNOWN"
            if token.curve_progress is None
            else "CURRENT"
            if self.curve_current(token, now)
            else "STALE",
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
            view["opportunity"] = self.intelligence.results.get(token.mint)
            view["creator_profile"] = (
                self.creators[token.creator].report(token) if token.creator in self.creators else None
            )
            view["history"] = list(token.history)
            view["transitions"] = self.db.rows("transition", mint=token.mint, limit=100)
            view["signals"] = self.db.rows("signal", mint=token.mint, limit=30)
        return view

    def intelligence_examples(self, now):
        if self.settings.mode != "DEMO":
            return {"opportunities": [], "positions": []}
        from backend.app.intelligence_demo import examples

        return examples(self.settings, self.intelligence.cfg, now)

    def companion_examples(self, now):
        if self.settings.mode != "DEMO":
            return []
        from backend.app.demo import companion_examples

        return companion_examples(self.settings, now)

    def trade_evidence_available(self):
        return self.settings.mode == "DEMO" or self.settings.trade_stream_enabled

    def display_scores(self, token):
        scores = dict(token.scores)
        scores["trade_evidence"] = "OBSERVED_ONLY" if self.trade_evidence_available() else "UNAVAILABLE"
        if not self.trade_evidence_available():
            for group in ["maturity_components", "momentum_components"]:
                scores[group] = {
                    key: value
                    if key in ["age_evidence", "volatility_penalty", "late_chase_penalty"]
                    else None
                    for key, value in scores.get(group, {}).items()
                }
        return scores

    def display_features(self, token):
        features = dict(token.features.get("180", {}))
        if not self.trade_evidence_available():
            for key in features:
                if key not in ["volatility_pct", "drawdown_pct", "price_move_pct", "vwap", "currency"]:
                    features[key] = None
            features["trade_evidence"] = "UNAVAILABLE"
        return features

    @staticmethod
    def provider_health(health):
        if "enabled" in health:
            return {**health, "status": (
                "UNAVAILABLE" if health.get("configuration_error") else
                "DISABLED" if not health["enabled"] else
                "CURRENT" if health["connected"] else
                "DEGRADED" if health.get("attempted") else "DISCONNECTED"
            ), "connection_age_seconds": max(0, time.time() - health["connected_since"])
                if health.get("connected_since") and health["connected"] else 0}
        status = (
            "RATE LIMITED"
            if health.get("rate_limited_until", 0) > time.time()
            else "BACKING OFF"
            if health.get("backoff_level", 0)
            else "NOT USED YET"
            if not health.get("attempted", False)
            else "CURRENT"
            if health["connected"]
            else "DEGRADED"
        )
        return {**health, "status": status}

    def snapshot(self):
        now = time.time()
        tokens = sorted(self.tokens.values(), key=lambda t: t.priority(), reverse=True)
        background = self.background_tokens(self.deep_mints())
        ages = [max(0, now - (t.last_curve_attempt or t.created)) for t in background]
        return {
            "name": "CRISPY WINNER — Graduation Radar",
            "mode": self.settings.mode,
            "simulated": self.settings.mode == "DEMO",
            "session": self.session,
            "strategy_version": self.version,
            "timestamp": now,
            "tokens": [self.token_view(t, now) for t in tokens],
            "companion_examples": self.companion_examples(now),
            "opportunities": self.intelligence.opportunities(),
            "manual": self.intelligence.manual_view(),
            "intelligence_examples": self.intelligence_examples(now),
            "paper": self.paper.summary(self.tokens),
            "lab": self.lab,
            "alerts": list(self.alerts),
            "health": {
                **self.metrics,
                "discovery_available": self.discovery_connected() if self.settings.mode != "DEMO" else False,
                "discovery_status": "DEMO" if self.settings.mode == "DEMO" else
                    "CURRENT" if self.discovery_connected() else "UNAVAILABLE",
                "duplicate_discoveries": self.duplicate_discoveries,
                "active_candidates": len(tokens),
                "deep_monitored": len(self.deep_mints()),
                "deep_subscriptions": len(self.pump.subscribed),
                **self.curve_metrics,
                **self.expiry_metrics,
                "background_candidates": len(background),
                "background_candidates_waiting": sum(
                    not t.last_curve_attempt
                    or now - t.last_curve_attempt
                    >= self.rpc.interval(self.settings.curve_background_revisit_seconds, "background")
                    for t in background
                ),
                "oldest_background_poll_age": round(max(ages, default=0), 1),
                "background_backoff_until": self.background_backoff_until,
                "queue_size": len(self.queue.heap),
                "queue_limit": self.queue.maximum,
                "dropped_events": self.queue.dropped,
                "processed_events": self.processed,
                "duplicates": self.duplicates,
                "out_of_order": self.out_of_order,
                "pending_outcomes": len(self.collector.pending),
                "providers": {
                    "Onchain discovery": self.provider_health(self.onchain.health),
                    "PumpPortal": self.provider_health(self.pump.health),
                    "Solana RPC": self.provider_health(
                        {
                            **self.rpc.health,
                            "effective_hot_seconds": self.rpc.interval(
                                self.settings.curve_poll_seconds, "hot"
                            ),
                            "effective_background_seconds": self.rpc.interval(
                                self.settings.curve_background_revisit_seconds, "background"
                            ),
                            "effective_security_seconds": self.rpc.interval(
                                self.settings.security_scan_interval_seconds, "security"
                            ),
                            "curve_accounts_per_request": self.rpc.health["curve_accounts"]
                            / max(1, self.rpc.health["curve_successful_requests"]),
                        }
                    ),
                    "DEX Screener": self.provider_health(self.dex.health),
                },
            },
            "notice": "Historical or paper performance does not guarantee future results. Liquidity can disappear.",
        }

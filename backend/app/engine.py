import asyncio
import logging
import math
import os
import time
import uuid
from collections import deque, OrderedDict
from typing import Any
from sqlalchemy import text

from alembic import command
from alembic.config import Config

from backend.app.companion import companion_view
from backend.app.config import ROOT
from backend.app.db import Database, StorageBudgetError
from backend.app.discovery import DiscoveryProvider, OnchainPumpDiscovery
from backend.app.domain import Deduplicator, MarketEvent, PriorityBuffer, State, Token, TRANSITIONS
from backend.app.economics import PositionSizer, TradeCostEstimator, evaluate_candidate
from backend.app.evaluation import OutcomeCollector, evaluate, strategy_version
from backend.app.features import calculate_features, score_token
from backend.app.paper import PaperAccount
from backend.app.providers import DexScreenerProvider, PumpPortalProvider, SolanaProvider
from backend.app.truncation import TruncationRecovery
from backend.app.pumpswap import PumpSwapFlow, VerifiedPool
from backend.app.resources import ResourceMonitor
from backend.app.evidence_pipeline import EventAccounting
from backend.app.intelligence import Intelligence
from backend.app.handoff import HandoffTrace
from backend.app.prospective import ProspectiveCohort, CohortIntegrityError
from backend.app.pumpswap import QUOTES

log = logging.getLogger(__name__)


class RadarEngine:
    def __init__(self, settings, db_path=None, offline=False, cohort_id=None):
        self.settings = settings
        self.offline = offline
        self.session = str(uuid.uuid4())
        self.db = Database(db_path or ROOT / "data" / ("demo.db" if settings.mode == "DEMO" else "radar.db"))
        cfg = Config(str(ROOT / "backend/alembic.ini"))
        with self.db.engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
        self.db.configure_budget(settings.db_limit_mb)
        self.storage_stopped = False
        self.prospective = None
        selected_cohort = cohort_id or (os.getenv("RADAR_COHORT") if not offline else None)
        if not selected_cohort and not offline:
            with self.db.engine.connect() as connection:
                cohort_exists = connection.execute(text("SELECT 1 FROM prospective_cohorts LIMIT 1")).first()
            if cohort_exists:
                self.db.engine.dispose()
                raise CohortIntegrityError("This research DB requires explicit cohort selection; use --cohort")
        if selected_cohort:
            try:
                self.prospective = ProspectiveCohort(self.db, settings, selected_cohort)
            except Exception:
                self.db.engine.dispose()
                raise
            self.db.record_observer = self.prospective.on_record
        self.last_audit = 0.0
        self.last_cohort_quality = 0.0
        self.cohort_started = time.time()
        self.queue = PriorityBuffer(settings.queue_size)
        self.accounting = EventAccounting()
        self.submission_filters = 0
        self.tokens: dict[str, Token] = {}
        self.creators: OrderedDict = OrderedDict()
        self.dedup = Deduplicator()
        self.launch_dedup = Deduplicator()
        self.migration_submissions = Deduplicator()
        self.duplicate_discoveries = 0
        self.costs = TradeCostEstimator(settings)
        self.sizer = PositionSizer(settings, self.costs)
        self.paper = PaperAccount(self.db, settings, self.costs)
        self.collector = OutcomeCollector(self.db, settings, self.costs, self.session)
        if self.prospective:
            self.collector.prospective = self.prospective
            self.collector.close_prospective()
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
        self.handoff = HandoffTrace()
        self.last_handoff_sample = 0.0
        self.trade_observations = {"buy": 0, "sell": 0}
        self.trade_continuity: dict[str, Any] = {"global_resets": 0, "per_token_resets": 0,
                                 "buffer_trade_evictions": 0, "buffer_expired_trade_evictions": 0,
                                 "per_token_reasons": dict.fromkeys(("decode", "stale", "queue", "buffer", "recovery", "processing", "resource"), 0)}
        self.out_of_order = 0
        self.duplicates = 0
        self.rejected_payloads = 0
        self.rpc = SolanaProvider(settings=settings)
        self.dex = DexScreenerProvider()
        self.pump = PumpPortalProvider(
            settings, self.submit, self.deep_mints, require_key=not offline,
            enabled=os.getenv("PUMPPORTAL_ENABLED", "false").lower() == "true",
        )
        self.onchain: OnchainPumpDiscovery
        self.recovery = TruncationRecovery(
            self.rpc, lambda mint: mint in self.tokens, self.invalidate_pump_token_coverage,
            lambda: self.onchain.global_gap("truncation_recovery"), self.refresh_trade_continuity,
            emit_migration=self.submit_recovered_migration,
        )
        self.onchain = OnchainPumpDiscovery(
            self.submit, tracked=lambda mint: mint in self.tokens, on_gap=self.invalidate_trade_coverage,
            on_trade_gap=self.invalidate_pump_token_coverage, on_truncation=self.recovery.submit,
            quote_for=lambda mint: self.tokens[mint].verified_quote_mint if mint in self.tokens else ""
        )
        self.pumpswap = PumpSwapFlow(self.submit, self.verified_flow_pools, self.invalidate_postgrad_coverage)
        self.discovery_providers: list[DiscoveryProvider] = [self.onchain, self.pump]
        self.lab: dict = {"holdout": {"count": 0, "status": "UNVALIDATED"}, "sample_count": 0}
        self.approved_evidence: dict | None = None
        # Persisted research rows are not an authorization capability. There is no
        # independently verified prospective approval protocol yet. Leave ALL
        # stored evidence unapproved (including legacy/flagged/DEMO rows), without
        # rewriting history. Isolated historical replay may restore its recorded
        # context explicitly; that is descriptive, never a startup approval route.
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
        self.lab_task = None
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
            token.migration_pool = row.get("migration_pool", "")
            if token.graduation and self.settings.mode != "DEMO":
                token.flow_venue = "PUMPSWAP"
                token.flow_epoch = time.time()
            token.grad_high = row.get("grad_high", 0)
            token.grad_low = row.get("grad_low") or math.inf
            # security and prices intentionally need refresh, not assumed current after downtime.
            token.events = deque(maxlen=self.settings.max_events)
            self.tokens[token.mint] = token

    def manual_mints(self):
        intelligence = getattr(self, "intelligence", None)
        if intelligence is None:
            return []
        positions = sorted(intelligence.journal.positions.values(), key=lambda p: (p["opened_at"], p["mint"]))
        return list(dict.fromkeys(p["mint"] for p in positions))

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
        protected += [m for m in self.manual_mints() if m in self.tokens and self.tokens[m].state != State.EXPIRED]
        protected = list(dict.fromkeys(m for m in protected if m in self.tokens))
        ranked = protected + [t.mint for t in eligible if t.mint not in protected]
        return ranked[: max(1, limit)]

    def submit_recovered_migration(self, event):
        if (event.mint not in self.tokens or event.event_id in self.dedup.seen
                or event.event_id in self.migration_submissions.seen):
            return "duplicate"
        return "emitted" if self.submit(event) else "queue_dropped"

    def submit(self, event):
        if event.kind == "migration" and event.signature:
            identity = f"{event.signature}:migration:{event.mint}"
            if identity in self.dedup.seen or identity in self.migration_submissions.seen:
                self.submission_filters += 1
                return False
        token = self.tokens.get(event.mint)
        priority = token.priority()[0] if token else 5
        if event.kind in ["migration", "security"]:
            priority = 110
        if event.kind == "create":
            priority = 105
        if event.kind == "trade":
            priority = min(80, priority)
        accepted = self.queue.put(event, priority)
        if accepted and event.kind == "migration" and event.signature:
            self.migration_submissions.accept(f"{event.signature}:migration:{event.mint}")
        for mint, stamp in self.queue.trade_gaps.items():
            if mint in self.tokens:
                self.invalidate_token_trade_coverage(mint, reason="queue", now=stamp)
        self.queue.trade_gaps.clear()
        return accepted

    def alert(self, level, mint, message, now, dedup_tag=None):
        key = (level, mint, dedup_tag) if dedup_tag is not None else (level, mint)
        if now - self.alert_times.get(key, -1000) < 30:
            return
        self.alert_times[key] = now
        if len(self.alert_times) > 1000:
            oldest = min(self.alert_times, key=lambda k: self.alert_times[k])
            del self.alert_times[oldest]
        self.alerts.append({"level": level, "mint": mint, "message": message, "ts": now})

    def transition(self, token, state, reason, now):
        previous = token.transition(state)
        if token.graduation:
            self.trace_handoff(token, now, "transition", reason)
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
            unprotected = [t for t in self.tokens.values() if t.mint not in self.paper.state["positions"]
                           and t.mint not in self.manual_mints()]
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
        token.trade_tracking_since = time.time() if self.settings.mode != "DEMO" else 0
        self.tokens[event.mint] = token
        self.transition(token, State.SCREENING, "Discovery received", event.ts)
        self.transition(token, State.WATCHING, "Cheap activity screening", event.ts)
        return token

    def process(self, event, now=None, *, queued=False):
        started = time.perf_counter()
        self._process_reason = "exception"
        self._event_persisted = False
        try:
            result = self._process(event, now)
            if result:
                self._process_reason = "processed"
            return result
        finally:
            if queued:
                self.accounting.finish(event.kind, self._process_reason, time.perf_counter() - started)
                self.queue.in_processing[event.kind] -= 1
                self.accounting.persisted[event.kind] += self._event_persisted

    async def drain_events(self):
        batch = self.queue.drain(100, self.settings.max_data_age_seconds)
        index = -1
        try:
            for index, event in enumerate(batch):
                try:
                    # Never reuse the time captured before the batch.
                    self.process(event, time.time(), queued=True)
                except StorageBudgetError:
                    self.storage_stopped = True
                    self.running = False
                    self.invalidate_trade_coverage()
                    raise
                except Exception:
                    if event.kind == "trade":
                        self.invalidate_token_trade_coverage(event.mint, reason="processing")
                    else:
                        self.invalidate_trade_coverage()
                    token = self.tokens.get(event.mint)
                    if token:
                        token.degraded = True
                    log.error("Event processing failed; kind=%s", event.kind)
                if index % 5 == 4:
                    await asyncio.sleep(0)
        finally:
            # Cancellation after a yield must not silently lose the detached remainder.
            for event in batch[index + 1:]:
                self.accounting.finish(event.kind, "cancelled", 0)
                self.queue.in_processing[event.kind] -= 1
                if event.kind == "trade":
                    self.invalidate_token_trade_coverage(event.mint, reason="processing")
                else:
                    self.invalidate_trade_coverage()

    def _process(self, event, now=None):
        recovered_source = event.kind == "migration" and event.source == "Recovered Pump instruction"
        now = (time.time() if recovered_source else event.ts) if now is None else now
        recovered_migration = False
        if recovered_source:
            error = self.recovery.migration_freshness_error(event, now, self.settings.max_data_age_seconds)
            if error:
                self.recovery.health[error] += 1
                self.rejected_payloads += 1
                self._process_reason = "recovery_provenance"
                return False
            recovered_migration = True
        if event.source == "DEMO" and self.settings.mode != "DEMO":
            self.rejected_payloads += 1
            self._process_reason = "demo_isolation"
            return False
        if event.kind == "trade" and event.source in ("Solana WSS", "PumpSwap WSS") and event.mint not in self.tokens:
            self._process_reason = "untracked"
            return False
        existing = self.tokens.get(event.mint)
        if event.kind == "trade" and existing:
            if existing.flow_venue == "PUMPSWAP" and event.source != "PumpSwap WSS":
                # History already stored before migration remains; late curve flow supplies no post-grad evidence.
                self._process_reason = "venue"
                return False
            if event.source == "PumpSwap WSS":
                pool = self.pumpswap.pools.get(event.evidence.get("pool"))
                if (existing.flow_venue != "PUMPSWAP" or not pool or pool.mint != existing.mint
                        or event.ts < existing.flow_epoch):
                    self._process_reason = "pool_epoch"
                    return False
        if not recovered_migration and abs(now - event.ts) > self.settings.max_data_age_seconds:
            if event.kind == "trade" and event.mint in self.tokens:
                self.invalidate_token_trade_coverage(event.mint, reason="stale", now=now)
            self.rejected_payloads += 1
            self._process_reason = "stale"
            return False
        if not self.dedup.accept(event.event_id):
            self.duplicates += 1
            self._process_reason = "duplicate_memory"
            return False
        if not self.metrics.get("storage_full") and not self.db.reserve_event(event.event_id, event.ts):
            self.duplicates += 1
            self._process_reason = "duplicate_db"
            return False
        if event.kind == "create":
            if event.mint in self.tokens or not self.launch_dedup.accept(event.mint) or (
                not self.metrics.get("storage_full")
                and not self.db.reserve_event(f"launch:{event.mint}", event.ts)
            ):
                self.duplicates += 1
                self.duplicate_discoveries += 1
                self._process_reason = "duplicate_launch"
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
            self._process_reason = "admission"
            return False
        if event.ts < token.last_event and not recovered_migration and not (event.kind == "trade" and event.source in ("Solana WSS", "PumpSwap WSS")):
            token.degraded = True
            self.out_of_order += 1
            self._process_reason = "out_of_order"
            return False
        token.last_event = max(token.last_event, event.ts)
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
            curve = event.evidence.get("bonding_curve") or {}
            if event.evidence.get("data_quality") == "VERIFIED" and curve.get("quote_mint"):
                quote = curve["quote_mint"]
                # Official BondingCurve schema: default quote mint means native SOL.
                token.verified_quote_mint = (
                    "So11111111111111111111111111111111111111112"
                    if quote == "11111111111111111111111111111111" else quote
                )
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
            token.last_trade = max(token.last_trade, event.ts)
        if event.kind in ["trade", "market"]:
            if len(token.events) == token.events.maxlen and token.events:
                oldest = token.events[0]
                if oldest.kind == "trade":
                    self.trade_continuity["buffer_trade_evictions"] += 1
                    token.buffer_loss_at = max(token.buffer_loss_at if token.buffer_loss_at is not None else 0, oldest.ts)
                    # Both processing time and the existing event-time analysis matter.
                    # Never infer deque order is timestamp order (late trades are allowed).
                    if oldest.ts >= min(now, event.ts) - 180:
                        self.invalidate_token_trade_coverage(token.mint, reason="buffer", now=now,
                                                             known_loss_at=oldest.ts)
                    else:
                        self.trade_continuity["buffer_expired_trade_evictions"] += 1
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
            if self.settings.mode != "DEMO":
                token.flow_venue = "PUMPSWAP"
                token.migration_pool = event.pair
                token.flow_epoch = max(now, event.ts)
                token.last_trade = 0
                token.postgrad_gap = token.flow_epoch
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
        evaluation_at = now if recovered_migration else event.ts
        self.analyse(token, evaluation_at)
        if token.graduation and event.kind in ("migration", "security"):
            detail = (f"{event.source}; instruction={event.evidence.get('instruction', 'visible event')}; "
                      f"slot={event.evidence.get('slot')}; signature={event.signature}" if event.kind == "migration"
                      else "Security evidence applied")
            self.trace_handoff(token, now, event.kind, detail)
        if not self.metrics.get("storage_full"):
            self.collector.observe(token, event)
        self.paper.observe(token, evaluation_at)
        if (
            token.price
            and evaluation_at - token.last_signal >= self.settings.signal_interval_seconds
            and not self.metrics.get("storage_full")
        ):
            self.collector.signal(token, evaluation_at, self.version)
            token.last_signal = evaluation_at
            self.paper.request_entry(token, evaluation_at, self.version)
        if not self.metrics.get("storage_full"):
            context_before = self.db.context_reference(context_before)
            record_id = self.db.add(
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
        if not self.metrics.get("storage_full"):
            self._event_persisted = bool(record_id)
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
                    if self.trade_status(token, event.ts) == "CURRENT"
                    else None,
                    "net_flow": token.features["180"]["net_flow"]
                    if self.trade_status(token, event.ts) == "CURRENT"
                    else None,
                }
            )
        self.intelligence.observe(token, evaluation_at)
        if recovered_migration and now - event.ts > self.settings.max_data_age_seconds:
            self.recovery.health["recovered_migration_chain_age_accepted"] += 1
        self.processed += 1
        if event.kind == "trade":
            self.trade_observations[event.side] = self.trade_observations.get(event.side, 0) + 1
        return True


    def analyse(self, token, now):
        token.last_analysis = now
        token.features = calculate_features(token, now)
        if self.settings.mode != "DEMO":
            if not token.trade_tracking_since:
                token.trade_tracking_since = now
            self.refresh_trade_continuity(token, now)
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
        self.capture_cohort_quality(time.time(), "RUNNING")
        self.running = True
        self.tasks = [asyncio.create_task(self.run_loop(), name="monitor")]
        if self.settings.mode == "DEMO":
            self.tasks.append(asyncio.create_task(self.run_demo(), name="demo"))
        else:
            self.tasks.append(asyncio.create_task(self.run_enrichment(), name="enrichment"))
            if self.pumpswap.health["enabled"]:
                self.tasks.append(asyncio.create_task(self.pumpswap.run(), name="pumpswap-flow"))
            if self.onchain.health["enabled"]:
                self.tasks.append(asyncio.create_task(self.recovery.run(), name="truncation-recovery"))
            for name, provider in zip(("onchain-discovery", "pumpportal"), self.discovery_providers):
                if provider.health["enabled"]:
                    self.tasks.append(asyncio.create_task(provider.run(), name=name))

    async def stop(self):
        self.running = False
        previous_global_resets = self.trade_continuity["global_resets"]
        try:
            # Snapshot acquisition quality before intentional socket cancellation.
            # Cancellation itself ends coverage but is not an infrastructure outage.
            self.capture_cohort_quality(time.time(), "STOPPED")
        finally:
            for task in self.tasks:
                task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
            # End coverage before clearing unknown recovery work. Preserve terminal counts,
            # not a misleading promise that an in-memory queue survives this process.
            self.onchain.health["connected"] = False
            self.pumpswap.health["connected"] = False
            if self.trade_continuity["global_resets"] == previous_global_resets:
                self.invalidate_trade_coverage()
            for token in self.tokens.values():
                if token.flow_venue == "PUMPSWAP":
                    self.invalidate_postgrad_coverage(token.mint)
            self.recovery.close_pending()
            for _, sequence, event in self.queue.heap:
                self.accounting.finish(event.kind, "shutdown_unprocessed", 0)
                self.queue.arrivals.pop(sequence, None)
            self.queue.heap.clear()
            if self.lab_task is not None:
                await asyncio.gather(self.lab_task, return_exceptions=True)
            try:
                self.collector.close_prospective()
            finally:
                # A failed client close must not bypass the other client, durable
                # shutdown accounting or database disposal. Re-raise after cleanup.
                provider_close_failures = []
                for provider in (self.rpc, self.dex):
                    try:
                        await provider.close()
                    except Exception as exc:
                        provider_close_failures.append(exc)
                checkpoint_failure = None
                try:
                    if not self.storage_stopped:
                        self.checkpoint(time.time())
                except Exception as exc:
                    checkpoint_failure = exc
                    if isinstance(exc, StorageBudgetError):
                        self.storage_stopped = True
                try:
                    self.db.evidence_run(self.session, dict(status="STORAGE_STOP" if self.storage_stopped else "STOPPED",
                        at=time.time(), accounting=self.accounting.snapshot(self.queue), continuity=self.trade_continuity,
                        recovery=self.recovery.snapshot(), queue=self.queue.snapshot(),
                        persistence_reconciliation=self.db.persistence_snapshot(),
                        checkpoint_complete=not self.storage_stopped and checkpoint_failure is None,
                        checkpoint_failure=type(checkpoint_failure).__name__ if checkpoint_failure else None,
                        provider_close_failures=[type(exc).__name__ for exc in provider_close_failures]))
                finally:
                    self.db.engine.dispose()
                if checkpoint_failure is not None:
                    # Receipt first, then preserve the caller-visible failure; never claim a clean checkpoint.
                    raise checkpoint_failure
                if provider_close_failures:
                    raise provider_close_failures[0]

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
        manual = set(self.manual_mints())
        background_rank = self.background_expiry_ranks(hot)
        deferred = 0
        for token in list(self.tokens.values()):
            if (
                token.mint in self.paper.state["positions"]
                or token.mint in manual
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
            if token.migration_pool:
                known.add(token.migration_pool)
            if token.graduation:
                self.trace_handoff(token, now, "security_attempt",
                    f"Pool hints: {len(known)}; migration hint in inspected first two: {token.migration_pool in sorted(known)[:2]}")
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
            if token.graduation:
                self.trace_handoff(token, time.time(), "security_result_queued",
                    f"quality={report.get('data_quality', 'UNKNOWN')}; verified pools returned={len(report.get('verified_pools', []))}")
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
        records = []
        for token in self.tokens.values():
            if token.creator in self.creators:
                records.append(("creator_profile", self.creators[token.creator].report(token), token.mint))
            records.append(("snapshot",
                {
                    "name": token.name,
                    "symbol": token.symbol,
                    "created": token.created,
                    "creator": token.creator,
                    "state": token.state.value,
                    "graduation": token.graduation,
                    "migration_pool": token.migration_pool,
                    "grad_high": token.grad_high,
                    "grad_low": token.grad_low if math.isfinite(token.grad_low) else None,
                    "scores": token.scores,
                }, token.mint))
        return self.db.checkpoint_records(records, self.session, now)

    def capture_cohort_quality(self, now, status="RUNNING"):
        if not self.prospective:
            return
        self.prospective.quality(self.session, {
            "started_at": self.cohort_started, "updated_at": now, "status": status,
            "recovery_overflow": self.recovery.health["overflow"],
            "recovery_expired": self.recovery.health["expired"],
            "global_trade_gaps": self.trade_continuity["global_resets"],
            "pump_reconnects": self.onchain.health["reconnects"],
            "pumpswap_reconnects": self.pumpswap.health["reconnects"],
            "rpc_errors": self.rpc.health["errors"], "rpc_429": self.rpc.health["rate_limits"],
            "stale_trade_rejections": self.trade_continuity["per_token_reasons"]["stale"],
            "queue": {k: v for k, v in self.queue.snapshot().items() if k != "depth_samples"},
            "storage_full": bool(self.metrics.get("storage_full")),
            "resource_pressure": bool(self.metrics.get("resource_pressure")),
            "providers_connected": {"pump": self.onchain.health["connected"],
                                    "pumpswap": self.pumpswap.health["connected"],
                                    "rpc": self.rpc.health["connected"]},
        })
        self.last_cohort_quality = now

    def trim_for_resource_pressure(self, token, now):
        lost = False
        while len(token.events) > 100:
            removed = token.events.popleft()
            if removed.kind == "trade":
                token.buffer_loss_at = max(token.buffer_loss_at if token.buffer_loss_at is not None else 0, removed.ts)
            lost |= removed.kind == "trade" and removed.ts >= now - 180
        token.degraded = True
        if lost:
            self.invalidate_token_trade_coverage(token.mint, reason="resource", now=now)

    def observation_tick(self, now):
        previous = self.accounting.last_tick
        gap = now - previous
        self.accounting.largest_tick_gap = max(self.accounting.largest_tick_gap, gap)
        if gap > self.settings.max_data_age_seconds or gap < 0:
            self.accounting.observation_gaps += 1
            self.accounting.gaps.append(dict(start=previous, end=now,
                reason="clock_backwards" if gap < 0 else "observation_pause"))
            self.invalidate_trade_coverage()
            for token in self.tokens.values():
                if token.flow_venue == "PUMPSWAP":
                    self.invalidate_postgrad_coverage(token.mint, now=now)
        self.accounting.last_tick = now

    async def run_loop(self):
        while True:
            try:
                now = time.time()
                while self.queue.affected:
                    mint = self.queue.affected.popleft()
                    if mint in self.tokens:
                        self.tokens[mint].degraded = True
                self.queue.sample_depth(now)
                self.observation_tick(now)
                await self.drain_events()
                now = time.time()
                for index, token in enumerate(list(self.tokens.values())):
                    application_time = time.time()
                    if application_time - token.last_analysis >= 1:
                        self.analyse(token, application_time)
                    if index % 10 == 9:
                        await asyncio.sleep(0)
                self.expire_inactive_candidates(now)
                self.intelligence.refresh(now)
                self.paper.expire_pending(now)
                if not self.metrics.get("storage_full"):
                    self.collector.expire(now)
                self.metrics = self.resources.sample()
                if now - self.last_cohort_quality >= 30:
                    self.capture_cohort_quality(now)
                if now - self.last_audit >= 30:
                    self.last_audit = now
                    self.db.evidence_run(self.session, dict(status="RUNNING", at=now,
                        accounting=self.accounting.snapshot(self.queue), continuity=self.trade_continuity,
                        persistence_reconciliation=self.db.persistence_snapshot()))
                if self.metrics["resource_pressure"]:
                    self.alert("SYSTEM", "", "RESOURCE PRESSURE — reducing monitoring", now)
                    for token in self.tokens.values():
                        self.trim_for_resource_pressure(token, now)
                if self.lab_task is not None and self.lab_task.done():
                    self.lab = self.lab_task.result()
                    self.lab_task = None
                if now - self.last_lab > 60 and self.lab_task is None:
                    # Read-only evaluation must not suspend queue consumption.
                    self.lab_task = asyncio.create_task(asyncio.to_thread(
                        evaluate, self.db, self.settings,
                        "demo" if self.settings.mode == "DEMO" else "real",
                        self.version, 300, now,
                    ))
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
            except StorageBudgetError:
                self.storage_stopped = True
                self.running = False
                self.invalidate_trade_coverage()
                self.db.evidence_run(self.session, dict(status="STORAGE_STOP", at=time.time(),
                    accounting=self.accounting.snapshot(self.queue), continuity=self.trade_continuity))
                return
            except CohortIntegrityError:
                self.running = False
                raise
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
            "trade_evidence": self.trade_status(token),
            "flow_venue": "POST-GRAD PUMPSWAP FLOW" if token.flow_venue == "PUMPSWAP" else "PRE-GRAD FLOW",
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

    def trace_handoff(self, token, now, event="snapshot", reason="", eligible=None):
        eligible = self.verified_flow_pools() if eligible is None else eligible
        pools = [p for p in eligible if p.mint == token.mint]
        selected = {p for p, record in self.pumpswap.pools.items() if record.mint == token.mint}
        acked = selected.intersection(self.pumpswap.since)
        verified = token.security.get("verified_pools", [])
        matching = [p for p in verified if p.get("base_mint") == token.mint]
        lifecycle = token.state in (State.GRADUATED, State.POST_GRAD_OBSERVATION, State.ENTRY_CANDIDATE)
        f = token.features.get("180", {})
        clean = self.trade_coverage_seconds(token, now) if token.graduation else 0
        age = now - token.last_trade if token.last_trade else None
        evidence = self.trade_status(token, now)
        if not token.graduation:
            stage = "MIGRATION_PENDING"
        elif not lifecycle:
            stage = "LIFECYCLE_INELIGIBLE"
        elif token.flow_venue != "PUMPSWAP":
            stage = "VENUE_NOT_PUMPSWAP"
        elif not pools:
            stage = ("MIGRATION_POOL_HINT_MISSING" if not token.migration_pool else
                     "SECURITY_NOT_ATTEMPTED" if not token.last_security_attempt else
                     "SECURITY_PENDING" if token.last_security < token.last_security_attempt else
                     "POOL_NOT_VERIFIED" if not matching else "POOL_IDENTITY_INCOMPLETE")
        elif not self.pumpswap.health["connected"]:
            stage = "WSS_DISCONNECTED"
        elif any(p.address not in selected for p in pools):
            desired = {p.address for p in eligible[:self.pumpswap.capacity]}
            stage = "CAPACITY_LIMITED" if any(p.address not in desired for p in pools) else "SELECTION_PENDING"
        elif any(p.address not in acked for p in pools):
            stage = "ACK_PENDING"
        elif any(p.quote_mint not in QUOTES for p in pools):
            stage = "QUOTE_UNITS_UNAVAILABLE"
        elif clean < 180:
            stage = "COVERAGE_BUILDING"
        elif f.get("samples", 0) < 3:
            stage = "SAMPLES_INSUFFICIENT"
        elif not f.get("units_valid"):
            stage = "TRADE_UNITS_UNAVAILABLE"
        elif age is None or not 0 <= age <= self.settings.max_data_age_seconds:
            stage = "TRADE_STALE"
        else:
            stage = "CURRENT" if evidence == "CURRENT" else "INCOMPLETE_EVIDENCE"
        self.handoff.observe({"mint": token.mint, "state": token.state.value, "stage": stage,
            "mode": self.settings.mode, "simulated": self.settings.mode == "DEMO",
            "migration_pool": token.migration_pool, "graduation_at": token.graduation,
            "flow_epoch": token.flow_epoch, "flow_venue": token.flow_venue,
            "security_quality": str(token.security.get("data_quality", "UNKNOWN"))[:32],
            "security_attempt_at": token.last_security_attempt, "security_applied_at": token.last_security,
            "verified_pool_count": len(verified), "matching_base_pool_count": len(matching),
            "migration_pool_verified": any(p.get("address") == token.migration_pool for p in matching),
            "eligible_pool_count": len(pools), "selected_pool_count": len(selected), "acked_pool_count": len(acked),
            "wss_connected": self.pumpswap.health["connected"], "coverage_seconds": round(clean, 2),
            "samples": f.get("samples", 0), "units_valid": bool(f.get("units_valid")),
            "last_trade_age": round(age, 2) if age is not None else None, "trade_evidence": evidence,
            "decision": token.decision.get("decision"),
            "decision_reasons": [str(r)[:240] for r in token.decision.get("reasons", [])[:8]],
            "security_failures": [str(r)[:240] for r in token.security.get("hard_failures", [])[:8]],
            "security_warnings": [str(r)[:240] for r in token.security.get("warnings", [])[:8]]}, now, event, reason)

    def handoff_snapshot(self, now):
        if now - self.last_handoff_sample >= 1:
            eligible = self.verified_flow_pools()
            if not self.handoff.records:
                candidates = sorted((t for t in self.tokens.values() if t.graduation),
                                    key=lambda t: t.priority(), reverse=True)[:self.handoff.maximum]
            else:
                candidates = [self.tokens[mint] for mint in self.handoff.records if mint in self.tokens]
            for token in candidates:
                self.trace_handoff(token, now, eligible=eligible)
            self.last_handoff_sample = now
        return self.handoff.snapshot(self.tokens, now)

    def verified_flow_pools(self):
        result = []
        for token in sorted(self.tokens.values(), key=lambda t: t.priority(), reverse=True):
            if (not token.graduation or token.flow_venue != "PUMPSWAP" or token.state not in
                    (State.GRADUATED, State.POST_GRAD_OBSERVATION, State.ENTRY_CANDIDATE)):
                continue
            for pool in sorted(token.security.get("verified_pools", []), key=lambda p: p.get("address", "")):
                if pool.get("base_mint") == token.mint and pool.get("address") and pool.get("quote_mint"):
                    result.append(VerifiedPool(pool["address"], token.mint, pool["quote_mint"]))
        return result

    def invalidate_pump_token_coverage(self, mint, reason="decode", now=None):
        token = self.tokens.get(mint)
        if token and token.flow_venue != "PUMPSWAP":
            self.invalidate_token_trade_coverage(mint, reason, now)

    def invalidate_postgrad_coverage(self, mint, now=None):
        token = self.tokens.get(mint)
        if token and token.flow_venue == "PUMPSWAP":
            self.invalidate_token_trade_coverage(mint, now=now)

    def invalidate_token_trade_coverage(self, mint, reason="decode", now=None, known_loss_at=None):
        token = self.tokens.get(mint)
        if token is None:
            return
        if (reason == "buffer" and type(known_loss_at) in (int, float)
                and math.isfinite(known_loss_at) and known_loss_at >= 0):
            token.buffer_loss_at = max(token.buffer_loss_at if token.buffer_loss_at is not None else 0, known_loss_at)
        elif token.flow_venue == "PUMPSWAP":
            token.postgrad_gap = max(token.postgrad_gap, time.time() if now is None else now)
        else:
            token.trade_gap = max(token.trade_gap, time.time() if now is None else now)
        self.trade_continuity["per_token_resets"] += 1
        reason = reason if reason in self.trade_continuity["per_token_reasons"] else "decode"
        self.trade_continuity["per_token_reasons"][reason] += 1
        for features in token.features.values():
            features["continuity_valid"] = False
            features["trade_evidence"] = "PARTIAL" if features.get("samples") else "UNAVAILABLE"

    def invalidate_trade_coverage(self):
        # Only transport or unassignable event loss reaches this callback.
        self.trade_continuity["global_resets"] += 1
        for token in self.tokens.values():
            if token.flow_venue == "PUMPSWAP":
                continue
            token.trade_gap = time.time()
            for features in token.features.values():
                features["continuity_valid"] = False
                features["trade_evidence"] = "PARTIAL" if features.get("samples") else "UNAVAILABLE"

    def refresh_trade_continuity(self, token=None, now=None):
        now = time.time() if now is None else now
        for candidate in ([token] if token is not None else self.tokens.values()):
            clean = self.trade_coverage_seconds(candidate, now)
            for seconds, features in candidate.features.items():
                pending = candidate.flow_venue != "PUMPSWAP" and self.recovery.overlaps(candidate, now, int(seconds))
                features["coverage_seconds"] = clean
                features["coverage_state"] = "PENDING RECOVERY" if pending else "OBSERVING"
                if candidate.flow_venue == "PUMPSWAP" and not self.pumpswap.coverage(candidate.mint, now):
                    selected = any(p.mint == candidate.mint for p in self.pumpswap.pools.values())
                    eligible = any(p.mint == candidate.mint for p in self.verified_flow_pools())
                    features["coverage_state"] = ("AWAITING ACK" if selected else "CAPACITY LIMITED" if eligible
                                                  else "VERIFIED POOL UNAVAILABLE")
                features["continuity_valid"] = (clean >= int(seconds) and not pending
                    and (candidate.buffer_loss_at is None or now - candidate.buffer_loss_at > int(seconds)))
            if "180" in candidate.features:
                candidate.features["180"]["trade_evidence"] = self.trade_status(candidate, now)

    def trade_coverage_seconds(self, token, now):
        if token.flow_venue == "PUMPSWAP":
            verified = {p.address: p for p in self.verified_flow_pools() if p.mint == token.mint}
            if not verified or any(self.pumpswap.pools.get(p) != record or p not in self.pumpswap.since
                                   for p, record in verified.items()):
                return 0
            return min(self.pumpswap.coverage(token.mint, now), max(0, now - max(
                token.flow_epoch, token.postgrad_gap, token.buffer_loss_at or 0)))
        health = self.onchain.health
        start = max(health["connected_since"], health["last_decode_gap"], token.trade_tracking_since,
                    token.trade_gap, token.buffer_loss_at or 0)
        return max(0, now - start) if health["connected"] else 0

    def trade_status(self, token, now=None):
        now = time.time() if now is None else now
        f = token.features.get("180", {})
        if self.settings.mode == "DEMO":
            return "CURRENT"
        if not f.get("samples") or not f.get("units_valid"):
            return "UNAVAILABLE"
        ready = (self.trade_coverage_seconds(token, now) >= 180 if token.flow_venue == "PUMPSWAP"
                 else not self.recovery.overlaps(token, now) and self.onchain.health["connected"])
        if (ready and f.get("continuity_valid") and f.get("samples", 0) >= 3
                and (token.buffer_loss_at is None or now - token.buffer_loss_at > 180)
                and 0 <= now - token.last_trade <= self.settings.max_data_age_seconds):
            return "CURRENT"
        return "PARTIAL"

    def trade_evidence_blockers(self, token, now):
        f = token.features.get("180", {})
        return dict(no_samples=not f.get("samples"), unknown_or_mixed_units=not f.get("units_valid"),
                    insufficient_samples=f.get("samples", 0) < 3,
                    incomplete_window=not f.get("continuity_valid"),
                    transport_or_pool_unavailable=(not self.pumpswap.coverage(token.mint, now)
                        if token.flow_venue == "PUMPSWAP" else not self.onchain.health["connected"]),
                    stale_trade=not (0 <= now - token.last_trade <= self.settings.max_data_age_seconds),
                    pending_recovery=(token.flow_venue != "PUMPSWAP" and self.recovery.overlaps(token, now)))

    def trade_evidence_available(self):
        return self.settings.mode == "DEMO" or self.settings.trade_stream_enabled or self.onchain.health["enabled"]

    def display_scores(self, token):
        scores = dict(token.scores)
        scores["trade_evidence"] = self.trade_status(token)
        if self.trade_status(token) != "CURRENT":
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
        features["trade_evidence"] = self.trade_status(token)
        if self.trade_status(token) != "CURRENT":
            for key in features:
                if key not in ["volatility_pct", "drawdown_pct", "price_move_pct", "vwap", "currency",
                               "coverage_state", "coverage_seconds", "continuity_valid"]:
                    features[key] = None
            features["trade_evidence"] = self.trade_status(token)
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
            "evidence_pipeline": dict(self.accounting.snapshot(self.queue),
                submission_filters={"migration_duplicate": self.submission_filters},
                storage=dict(self.db.storage_audit), storage_stopped=self.storage_stopped,
                persistence_reconciliation=self.db.persistence_snapshot()),
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
                "queue_lag": self.queue.snapshot(now),
                "truncation_recovery": self.recovery.snapshot(),
                "postgrad_handoff": self.handoff_snapshot(now),
                "dropped_events": self.queue.dropped,
                "trade_observations": self.trade_observations,
                "processed_trade_rate": sum(self.trade_observations.values()) / max(1, now - self.queue.created),
                "trade_continuity": self.trade_continuity,
                "dropped_trade_events": self.queue.dropped_trades,
                "dropped_critical_events": self.queue.dropped_critical,
                "clean_wss_coverage_seconds": max(0, time.time() - max(self.onchain.health["connected_since"], self.onchain.health["last_decode_gap"]))
                    if self.onchain.health["connected"] else 0,
                "trade_evidence_counts": {status: sum(self.trade_status(t) == status for t in self.tokens.values())
                    for status in ("CURRENT", "PARTIAL", "UNAVAILABLE")},
                "processed_events": self.processed,
                "duplicates": self.duplicates,
                "out_of_order": self.out_of_order,
                "pending_outcomes": len(self.collector.pending),
                "pumpswap_flow": {**self.pumpswap.health, "evidence_counts": {
                    status: sum(t.flow_venue == "PUMPSWAP" and self.trade_status(t) == status for t in self.tokens.values())
                    for status in ("CURRENT", "PARTIAL", "UNAVAILABLE")}},
                "providers": {
                    "PumpSwap flow": self.provider_health(self.pumpswap.health),
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

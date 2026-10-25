"""Bounded local orchestration over already acquired observations; zero provider calls."""

import time

from backend.app.domain import Token
from backend.app.exit_intelligence import exit_view
from backend.app.manual import ManualJournal
from backend.app.opportunity import load_intelligence_settings, opportunity_view, provider_market
from backend.app.opportunity_research import OpportunityResearch


class Intelligence:
    def __init__(self, engine):
        self.engine = engine
        self.cfg = load_intelligence_settings()
        self.journal = ManualJournal(engine.db, engine.settings, self.cfg)
        self.research = OpportunityResearch(engine.db, engine.settings, self.cfg, engine.session)
        self.results: dict = {}
        self.exit_results: dict = {}
        self.exit_actions: dict = {}
        self.last_refresh = 0.0

    def project(self, token, now, manual=True):
        market = provider_market(token, self.engine.settings, now)
        if manual:
            observed = self.journal.market_view(token.mint, now)
            if observed and (observed["status"] == "CURRENT" or market["status"] != "CURRENT"):
                market = observed
        return opportunity_view(token, self.engine.settings, now, self.cfg, market)

    def observe(self, token, now, acquisition=True):
        if (
            self.engine.offline
            or self.engine.settings.mode == "DEMO"
            or self.engine.metrics.get("storage_full")
        ):
            return
        if acquisition:
            self.research.observe(token, now)
        # Research uses only provider context; manual market input never changes research classification.
        result = self.project(token, now, manual=False)
        previous = self.research.actions.get(token.mint)
        self.research.transition(token, result, now, self.engine.version)
        if previous and previous != result.action.value and result.action.value == "EARLY_OPPORTUNITY":
            self.engine.alert(
                "OPPORTUNITY", token.mint, "EARLY OPPORTUNITY — unvalidated manual research", now
            )

    def refresh(self, now, force=False):
        if not force and now - self.last_refresh < 1:
            return
        self.last_refresh = now
        self.results = {
            mint: self.project(token, now).model_dump(mode="json")
            for mint, token in self.engine.tokens.items()
        }
        if (
            not self.engine.offline
            and self.engine.settings.mode != "DEMO"
            and not self.engine.metrics.get("storage_full")
        ):
            for token in self.engine.tokens.values():
                self.observe(token, now, acquisition=False)
            self.research.expire(now)
        active = set(self.engine.tokens)
        self.research.actions = {
            mint: action for mint, action in self.research.actions.items() if mint in active
        }
        self.refresh_positions(now)

    def refresh_positions(self, now):
        self.exit_results = {}
        hot = set(self.engine.deep_mints())
        for identity, position in self.journal.positions.items():
            token = self.engine.tokens.get(position["mint"])
            observed = self.journal.market_view(position["mint"], now)
            provider = provider_market(token, self.engine.settings, now) if token else None
            for market in [provider, observed]:
                if market and not self.engine.metrics.get("storage_full"):
                    self.journal.update_mark(position, market, now)
            # An evicted token receives no extra scans and cannot be called healthy.
            projection = self.project(token or Token(position["mint"], "", "", now), now)
            result = exit_view(position, token, projection, self.engine.settings, self.cfg, now).model_dump(
                mode="json"
            )
            previous = self.exit_actions.get(identity)
            if (previous != result["action"] and result["action"] in [
                "PROTECT_PROFIT", "EXIT_RISK", "THESIS_INVALIDATED", "MOMENTUM_DETERIORATING", "DATA_STALE"
            ]):
                self.engine.alert(
                    "MANUAL_POSITION",
                    position["mint"],
                    "Manual position: " + result["action"] + " — review externally",
                    now,
                    dedup_tag=identity + ":" + result["action"],
                )
            self.exit_actions[identity] = result["action"]
            missing = []
            if token is None:
                missing.append("Token is not actively tracked; no automatic readmission or historical backfill")
            else:
                if token.mint not in hot:
                    missing.append("Outside current deep-monitoring capacity")
                if not self.engine.discovery_connected() or not self.engine.rpc.health["connected"]:
                    missing.append("Discovery or account provider unavailable")
                if projection.security_quality != "CURRENT":
                    missing.append("Current verified security unavailable")
                if projection.trade_evidence != "CURRENT":
                    missing.append("Current continuous buyer-flow evidence unavailable")
                if token.graduation is None and projection.dynamics.freshness != "CURRENT":
                    missing.append("Current verified curve unavailable")
                if token.graduation is not None and (not provider or provider["status"] != "CURRENT"):
                    missing.append("Current post-migration market mark unavailable")
            if result["mark"] is None:
                missing.append("Current position price/mark unavailable")
            if self.engine.metrics.get("resource_pressure") or self.engine.metrics.get("storage_full"):
                missing.append("Resource/storage pressure reduces evidence coverage")
            self.exit_results[identity] = {**position, "exit": result, "monitoring": {
                "status": "MONITORING DEGRADED" if missing else "OBSERVING",
                "reasons": missing, "observed_at": now,
                "valid_until": now + self.engine.settings.max_data_age_seconds,
            }}
        self.exit_actions = {
            key: value for key, value in self.exit_actions.items() if key in self.journal.positions
        }

    def opportunities(self):
        ranked = [
            {
                "mint": mint,
                "name": self.engine.tokens[mint].name,
                "symbol": self.engine.tokens[mint].symbol,
                **result,
            }
            for mint, result in self.results.items()
            if mint in self.engine.tokens
        ]
        ranked.sort(key=lambda value: (-value["ranking_score"], value["mint"]))
        return {
            "status": "UNVALIDATED RESEARCH SIGNALS",
            "items": ranked,
            "counts": {
                action: sum(row["action"] == action for row in ranked)
                for action in [
                    "EARLY_OPPORTUNITY",
                    "DEVELOPING",
                    "PULLBACK_WATCH",
                    "TOO_EXTENDED",
                    "AVOID",
                    "DATA_LIMITED",
                ]
            },
            "signals_this_session": self.research.signal_count,
            "outcomes_this_session": self.research.outcome_count,
            "pending_research": len(self.research.pending),
            "validated_edge": False,
            "research_version": self.cfg.version,
        }

    def manual_view(self):
        return {
            "cash_usd": self.journal.cash,
            "max_open": self.cfg.manual_max_open,
            "open": list(self.exit_results.values()),
            "manual_execution_only": True,
        }

    def open_position(self, value, now=None):
        now = time.time() if now is None else now
        token = self.engine.tokens.get(value.mint)
        projection = self.project(token or Token(value.mint, "", "", now), now).model_dump(mode="json")
        thesis = {
            **projection,
            "recorded_at": now,
            "core_version": self.engine.version,
            "name": token.name if token else "",
            "entry_liquidity_usd": token.liquidity
            if token and 0 <= now - token.last_liquidity <= self.engine.settings.max_data_age_seconds
            else None,
            "snapshot_kind": "ENTRY-TIME OBSERVATION; NOT HISTORICAL RECONSTRUCTION",
        }
        # Backdated entries cannot acquire a future-looking thesis retroactively.
        if value.opened_at is not None and now - value.opened_at > 5:
            thesis = {
                "recorded_at": now,
                "core_version": self.engine.version,
                "snapshot_kind": "UNAVAILABLE — ENTRY WAS BACKDATED",
                "dynamics": {},
            }
        position = self.journal.open(value, thesis, now)
        self.refresh_positions(now)
        return self.exit_results[position["position_id"]]

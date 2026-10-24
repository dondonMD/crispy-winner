"""Prospective research namespaces; no approved evidence or strict paper integration."""

import json
import math
from collections import defaultdict, OrderedDict
from backend.app.economics import TradeCostEstimator
from backend.app.config import Settings
from backend.app.opportunity import current
from sqlalchemy import select
from backend.app.db import OpportunityPendingRow, Record
from backend.app.opportunity import provider_market


class OpportunityResearch:
    LIMIT = 1000

    def __init__(self, db, settings, cfg, session):
        self.db, self.settings, self.cfg, self.session = db, settings, cfg, session
        with db.sessions() as sql:
            rows = sql.scalars(select(OpportunityPendingRow).limit(self.LIMIT)).all()
            self.pending = {row.id: json.loads(row.payload) for row in rows}
            self.committed_pending = OrderedDict((row.id, row.payload) for row in rows)
        if settings.mode == "DEMO":
            self.pending = {}
            self.committed_pending.clear()
        self.by_mint: dict[str, set[int]] = defaultdict(set)
        for identity, payload in self.pending.items():
            self.by_mint[payload["mint"]].add(identity)
        self.actions = {}
        self.signal_count = 0
        self.outcome_count = 0

    def save_pending(self, identity, payload):
        # Only committed, byte-identical state may skip a write. Never cache mutable payloads.
        encoded = json.dumps(payload, allow_nan=False) if payload is not None else None
        if encoded is not None and self.committed_pending.get(identity) == encoded:
            return
        with self.db.sessions.begin() as sql:
            if payload is None:
                row = sql.get(OpportunityPendingRow, identity)
                if row:
                    sql.delete(row)
            else:
                sql.merge(OpportunityPendingRow(id=identity, payload=encoded))
        if encoded is None:
            self.committed_pending.pop(identity, None)
        else:
            self.committed_pending[identity] = encoded
            self.committed_pending.move_to_end(identity)
            while len(self.committed_pending) > self.LIMIT:
                self.committed_pending.popitem(last=False)

    def transition(self, token, projection, now, core_version):
        if self.settings.mode == "DEMO":
            return
        action = projection.action.value
        if self.actions.get(token.mint) == action:
            return
        self.actions[token.mint] = action
        while len(self.actions) > self.settings.max_candidates:
            self.actions.pop(next(iter(self.actions)))
        provider = provider_market(token, self.settings, now)
        snapshot = projection.model_dump(mode="json")
        # User observations never enter provider-derived signal baselines/outcomes.
        snapshot["market_context"] = provider
        identity = self.db.add(
            "opportunity_signal",
            {
                "observed_at": now,
                "projection": snapshot,
                "mode": "REAL",
                "core_version": core_version,
                "research_version": self.cfg.version,
                "baseline_curve": projection.dynamics.current,
                "provider_price_usd": provider["price_usd"],
                "provider_cap_usd": provider["market_cap_usd"],
                "validated_edge": False,
            },
            token.mint,
            self.session,
            now,
        )
        self.signal_count += 1
        if len(self.pending) >= self.LIMIT:
            oldest = next(iter(self.pending))
            old = self.pending.pop(oldest)
            self.by_mint[old["mint"]].discard(oldest)
            if not self.by_mint[old["mint"]]:
                del self.by_mint[old["mint"]]
            for horizon in list(old["remaining"]):
                self.write_outcome(oldest, old, horizon, now, "UNAVAILABLE_CAPACITY")
            self.save_pending(oldest, None)
        payload = {
            "mint": token.mint,
            "signal_ts": now,
            "session": self.session,
            "core_version": core_version,
            "research_version": self.cfg.version,
            "cost_settings": self.settings.model_dump(
                include={
                    "fee_pct_per_side",
                    "platform_fee_pct",
                    "network_usd_per_side",
                    "priority_usd_per_side",
                    "failed_tx_reserve_usd",
                    "slippage_pct",
                    "fee_verified",
                }
            ),
            "remaining": list(self.cfg.horizons),
            "entry_liquidity": token.liquidity
            if current(token.last_liquidity, now, self.settings.max_data_age_seconds)
            else None,
            "latest_liquidity": None,
            "latest_liquidity_ts": None,
            "research_notional_usd": self.settings.account_usd * self.settings.max_position_fraction,
            "baseline_curve": projection.dynamics.current,
            "baseline_price": provider["price_usd"],
            "baseline_cap": provider["market_cap_usd"],
            "curve_max": projection.dynamics.current,
            "curve_min": projection.dynamics.current,
            "price_max": provider["price_usd"],
            "price_min": provider["price_usd"],
            "cap_max": provider["market_cap_usd"],
            "cap_min": provider["market_cap_usd"],
            "migration_ts": None,
            "latest_curve": None,
            "latest_price": None,
            "latest_cap": None,
            "latest_curve_ts": None,
            "latest_market_ts": None,
            "latest_price_ts": None,
            "latest_cap_ts": None,
        }
        self.pending[identity] = payload
        self.by_mint[token.mint].add(identity)
        self.save_pending(identity, payload)

    def write_outcome(self, identity, payload, horizon, now, status="OBSERVED"):
        end = payload["signal_ts"] + horizon

        def change(value, baseline):
            result = 100 * (value / baseline - 1) if value is not None and baseline else None
            return result if result is not None and math.isfinite(result) else None

        baseline = payload["baseline_curve"]
        price_valid = current(payload.get("latest_price_ts") or 0, end, self.settings.max_data_age_seconds)
        curve_valid = current(payload["latest_curve_ts"] or 0, end, self.cfg.curve_fresh_seconds)
        forward = change(payload["latest_price"], payload["baseline_price"]) if price_valid else None
        costs = None
        if (
            forward is not None
            and forward > -100
            and payload.get("entry_liquidity")
            and payload.get("latest_liquidity")
            and current(payload.get("latest_liquidity_ts") or 0, end, self.settings.max_data_age_seconds)
        ):
            costs = TradeCostEstimator(Settings(**payload.get("cost_settings", {}))).estimate(
                payload["research_notional_usd"],
                min(payload["entry_liquidity"], payload["latest_liquidity"]),
                forward,
            )
        outcome = {
            "signal_id": identity,
            "core_version": payload.get("core_version"),
            "research_version": payload.get("research_version"),
            "horizon": horizon,
            "signal_ts": payload["signal_ts"],
            "due_at": end,
            "recorded_at": now,
            "status": status,
            "endpoint_curve": payload["latest_curve"] if curve_valid else None,
            "curve_observed_at": payload["latest_curve_ts"],
            "max_subsequent_curve": payload["curve_max"] if payload["latest_curve_ts"] else None,
            "min_subsequent_curve": payload["curve_min"] if payload["latest_curve_ts"] else None,
            "max_curve_regression_pp": baseline - payload["curve_min"]
            if baseline is not None and payload["curve_min"] is not None and payload["latest_curve_ts"]
            else None,
            "migration_ts": payload["migration_ts"],
            "time_to_migration": payload["migration_ts"] - payload["signal_ts"]
            if payload["migration_ts"]
            else None,
            "forward_return_pct": forward,
            "estimated_after_cost_return_pct": costs["net_return_pct"] if costs else None,
            "price_endpoint_status": "CURRENT AT HORIZON" if price_valid else "UNAVAILABLE / STALE",
            "maximum_favourable_excursion_pct": change(payload["price_max"], payload["baseline_price"])
            if payload.get("latest_price_ts")
            else None,
            "maximum_adverse_excursion_pct": change(payload["price_min"], payload["baseline_price"])
            if payload.get("latest_price_ts")
            else None,
            "market_cap_change_pct": change(payload["latest_cap"], payload["baseline_cap"])
            if current(payload.get("latest_cap_ts") or 0, end, self.settings.max_data_age_seconds)
            else None,
            "source": "PROVIDER OBSERVATIONS ONLY",
            "price_returns": "GROSS RESEARCH MEASUREMENT, NOT AFTER-COST EDGE",
            "validated_edge": False,
        }
        remaining = [value for value in payload["remaining"] if value != horizon]
        with self.db.sessions.begin() as sql:
            row = sql.get(OpportunityPendingRow, identity)
            if row is None:
                payload["remaining"] = []
                return
            sql.add(
                Record(
                    kind="opportunity_outcome",
                    mint=payload["mint"],
                    ts=now,
                    session=payload["session"],
                    payload=json.dumps(outcome, allow_nan=False),
                )
            )
            if remaining:
                row.payload = json.dumps({**payload, "remaining": remaining}, allow_nan=False)
            else:
                sql.delete(row)
        payload["remaining"] = remaining
        self.outcome_count += 1

    def observe(self, token, now):
        if self.settings.mode == "DEMO":
            return
        market = provider_market(token, self.settings, now)
        for identity in list(self.by_mint.get(token.mint, set())):
            payload = self.pending[identity]
            if now <= payload["signal_ts"]:
                continue
            # Freeze horizons before adding any observation from after their deadline.
            self.settle(identity, payload, now)
            if identity not in self.pending:
                continue
            if current(token.last_liquidity, now, self.settings.max_data_age_seconds):
                payload["latest_liquidity"] = token.liquidity
                payload["latest_liquidity_ts"] = token.last_liquidity
            values = {
                "curve": token.curve_progress
                if token.curve_history and token.last_curve == token.curve_history[-1][0]
                else None,
                "price": market["price_usd"],
                "cap": market["market_cap_usd"],
            }
            for metric, value in values.items():
                if value is not None:
                    payload[f"latest_{metric}"] = value
                    payload[f"{metric}_max"] = (
                        max(value, payload[f"{metric}_max"])
                        if payload[f"{metric}_max"] is not None
                        else value
                    )
                    payload[f"{metric}_min"] = (
                        min(value, payload[f"{metric}_min"])
                        if payload[f"{metric}_min"] is not None
                        else value
                    )
            if values["curve"] is not None:
                payload["latest_curve_ts"] = token.last_curve
            if values["price"] is not None:
                payload["latest_price_ts"] = market["price_observed_at"]
            if values["cap"] is not None:
                payload["latest_cap_ts"] = market["cap_observed_at"]
            if values["price"] is not None or values["cap"] is not None:
                payload["latest_market_ts"] = market["observed_at"]
            if token.graduation and token.graduation >= payload["signal_ts"]:
                payload["migration_ts"] = token.graduation
            self.save_pending(identity, payload)

    def settle(self, identity, payload, now):
        for horizon in list(payload["remaining"]):
            due = payload["signal_ts"] + horizon
            if now <= due:
                continue
            covered = (
                current(payload["latest_curve_ts"] or 0, due, self.cfg.curve_fresh_seconds)
                or current(payload.get("latest_price_ts") or 0, due, self.settings.max_data_age_seconds)
                or current(payload.get("latest_cap_ts") or 0, due, self.settings.max_data_age_seconds)
                or payload["migration_ts"] is not None
            )
            status = "OBSERVED" if covered else "UNAVAILABLE_GAP"
            self.write_outcome(identity, payload, horizon, now, status)
        if not payload["remaining"]:
            self.pending.pop(identity, None)
            self.by_mint[payload["mint"]].discard(identity)
            if not self.by_mint[payload["mint"]]:
                del self.by_mint[payload["mint"]]
            self.save_pending(identity, None)

    def expire(self, now):
        for identity, payload in list(self.pending.items()):
            self.settle(identity, payload, now)

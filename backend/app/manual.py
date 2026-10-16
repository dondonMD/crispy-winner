"""Local manual observations and journal. No wallet, order or execution integration."""

from collections import OrderedDict
import json
import uuid

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator, model_validator
from solders.pubkey import Pubkey
from sqlalchemy import select

from backend.app.db import ManualPositionRow, Record
from backend.app.economics import TradeCostEstimator
from backend.app.opportunity import current


class ManualInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class MintInput(ManualInput):
    mint: str = Field(min_length=32, max_length=44)

    @field_validator("mint")
    @classmethod
    def valid_mint(cls, value):
        try:
            return str(Pubkey.from_string(value))
        except ValueError:
            raise ValueError("A valid Solana mint address is required") from None


class MarketInput(MintInput):
    price_usd: FiniteFloat | None = Field(default=None, gt=0, le=1e12)
    market_cap_usd: FiniteFloat | None = Field(default=None, gt=0, le=1e15)

    @model_validator(mode="after")
    def has_observation(self):
        if self.price_usd is None and self.market_cap_usd is None:
            raise ValueError("Enter a price or market cap observation")
        return self


class OpenPositionInput(MarketInput):
    amount_usd: FiniteFloat = Field(gt=0, le=1e6)
    opened_at: FiniteFloat | None = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=1000)
    confirm: bool


class ClosePositionInput(ManualInput):
    confirm: bool
    notes: str = Field(default="", max_length=1000)


class CashInput(ManualInput):
    cash_usd: FiniteFloat = Field(ge=0, le=1e6)


class EconomicsInput(MintInput):
    amount_usd: FiniteFloat = Field(gt=0, le=1e6)


def manual_economics(settings, cash, amount, token, now):
    liquidity = (
        token.liquidity
        if token and current(token.last_liquidity, now, settings.max_data_age_seconds)
        else None
    )
    estimator = TradeCostEstimator(settings)
    costs = estimator.estimate(amount, liquidity)
    return {
        "available_cash_usd": cash,
        "position_usd": amount,
        "account_fraction_pct": amount / cash * 100 if cash else None,
        "remaining_cash_usd": cash - amount if cash is not None else None,
        "costs": costs,
        "break_even_pct": estimator.break_even(amount, liquidity),
        "status": "ESTIMATED" if costs else "UNKNOWN — CURRENT LIQUIDITY UNAVAILABLE",
        "affordable": cash is not None and costs is not None and amount + costs["entry_cost_usd"] <= cash,
        "economically_viable": False,
        "reason": "Unvalidated; costs do not establish an edge",
        "remaining_cash_after_entry_cost_usd": cash - amount - costs["entry_cost_usd"]
        if cash is not None and costs
        else None,
    }


class ManualJournal:
    def __init__(self, db, settings, cfg):
        self.db, self.settings, self.cfg = db, settings, cfg
        self.mode = "DEMO" if settings.mode == "DEMO" else "REAL"
        self.market: OrderedDict[str, dict] = OrderedDict()
        for row in db.rows("manual_market_context", session=self.mode, limit=250):
            self.market[row["mint"]] = {k: v for k, v in row.items() if k not in ["id", "session", "ts"]}
        saved = db.rows("manual_account", session=self.mode, limit=1)
        self.cash = saved[-1]["cash_usd"] if saved else None
        with db.sessions() as session:
            rows = session.scalars(
                select(ManualPositionRow)
                .where(ManualPositionRow.status == "OPEN", ManualPositionRow.mode == self.mode)
                .limit(11)
            ).all()
            self.positions = {row.id: json.loads(row.payload) for row in rows}

    def set_cash(self, value, now):
        self.cash = value.cash_usd
        self.db.add("manual_account", {"cash_usd": self.cash}, session=self.mode, ts=now)
        return {"cash_usd": self.cash, "source": "MANUAL USER SETTING"}

    def market_view(self, mint, now):
        saved = self.market.get(mint)
        if not saved:
            return None
        return {
            **saved,
            "status": "CURRENT"
            if current(saved["observed_at"], now, self.cfg.manual_fresh_seconds)
            else "STALE",
            "age_seconds": max(0, now - saved["observed_at"]),
            "verified": False,
        }

    def observe_market(self, value, now):
        observation = {
            **value.model_dump(),
            "observed_at": now,
            "source": "MANUAL USER OBSERVATION",
            "verified": False,
        }
        self.db.add("manual_market_context", observation, value.mint, self.mode, now)
        self.market[value.mint] = observation
        self.market.move_to_end(value.mint)
        while len(self.market) > 250:
            self.market.popitem(last=False)
        return self.market_view(value.mint, now)

    def persist(self, position, kind, now):
        # Current state and immutable journal event are committed together.
        with self.db.sessions.begin() as session:
            session.merge(
                ManualPositionRow(
                    id=position["position_id"],
                    mode=self.mode,
                    status=position["status"],
                    updated_at=now,
                    payload=json.dumps(position, allow_nan=False),
                )
            )
            session.add(
                Record(
                    kind=kind,
                    mint=position["mint"],
                    ts=now,
                    session=self.mode,
                    payload=json.dumps(
                        {
                            "position_id": position["position_id"],
                            "marks": position["marks"],
                            "peaks": position["peaks"],
                        }
                        if kind == "manual_position_mark"
                        else position,
                        allow_nan=False,
                    ),
                )
            )

    def open(self, value, thesis, now):
        if not value.confirm:
            raise ValueError("Explicit confirmation is required; this records an external manual entry only")
        if len(self.positions) >= self.cfg.manual_max_open:
            raise ValueError(f"At most {self.cfg.manual_max_open} manual positions may be open")
        if value.opened_at is not None and not 0 <= now - value.opened_at <= 86400 * 30:
            raise ValueError("Entry timestamp must be within the last 30 days, not in the future")
        position = {
            "position_id": str(uuid.uuid4()),
            "mint": value.mint,
            "status": "OPEN",
            "amount_usd": value.amount_usd,
            "opened_at": value.opened_at or now,
            "entry_price_usd": value.price_usd,
            "entry_market_cap_usd": value.market_cap_usd,
            "notes": value.notes,
            "thesis": thesis,
            "manual_execution_only": True,
            "marks": {},
            "peaks": {},
            "mode": self.mode,
        }
        self.persist(position, "manual_position", now)
        self.positions[position["position_id"]] = position
        return position

    def close(self, identity, value, now):
        if not value.confirm:
            raise ValueError("Confirm closing this journal record; no transaction will be sent")
        position = self.positions.get(identity)
        if not position:
            raise KeyError(identity)
        position = {**position, "status": "CLOSED", "closed_at": now, "close_notes": value.notes}
        self.persist(position, "manual_position_close", now)
        del self.positions[identity]
        return position

    def closed(self):
        with self.db.sessions() as session:
            rows = session.scalars(
                select(ManualPositionRow)
                .where(ManualPositionRow.status == "CLOSED", ManualPositionRow.mode == self.mode)
                .order_by(ManualPositionRow.updated_at.desc())
                .limit(100)
            ).all()
            return [json.loads(row.payload) for row in rows]

    def update_mark(self, position, market, now):
        if market.get("status") != "CURRENT":
            return
        source = market["source"]
        for metric in ["price_usd", "market_cap_usd"]:
            value = market.get(metric)
            if value is None:
                continue
            # USD price is the only basis for actual return estimates. Cap changes are proxy only.
            key = source + ":" + metric
            stamp = (
                market.get("price_observed_at" if metric == "price_usd" else "cap_observed_at")
                or market["observed_at"]
            )
            if stamp < position["opened_at"]:
                continue
            old = position["marks"].get(key)
            if old and stamp <= old["observed_at"]:
                continue
            position["marks"][key] = {
                "value": value,
                "observed_at": stamp,
                "source": source,
                "metric": metric,
            }
            position["peaks"][key] = max(value, position["peaks"].get(key, value))
            self.persist(position, "manual_position_mark", now)

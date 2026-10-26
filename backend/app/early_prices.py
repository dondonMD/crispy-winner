"""Verified indicative Pump reserve marks and descriptive V2.1 follow-up. Never fills."""

import hashlib
import json
import math
import time
from decimal import Decimal

from solders.pubkey import Pubkey
from backend.app.early_edge_quotes import (
    decode_account,
    mint_info,
    pda,
    PUMP_PROGRAM,
    TOKEN_PROGRAM,
    WSOL,
    QUOTES,
    ZERO,
    QuoteUnavailable,
    SOURCES_PATH,
)
from backend.app.early_edge import fx_value
from backend.app.db import Record
from sqlalchemy import select, func

HORIZONS = (15, 30, 60, 180, 300)
VERSION = "v21-reserve-marks-1"

SCHEMA_HASH = hashlib.sha256(SOURCES_PATH.read_bytes()).hexdigest()
MAX_AGE = 20


def reserve_state(mint, address, curve_account, mint_account, quote_accounts, slot, requested, acquired):
    """Only same getMultipleAccounts context; unknown account versions fail closed."""
    if address != pda([b"bonding-curve", bytes(Pubkey.from_string(mint))], PUMP_PROGRAM):
        raise QuoteUnavailable("MINT_IDENTITY")
    if type(slot) is not int or slot <= 0 or not 0 <= acquired - requested <= 5:
        raise QuoteUnavailable("STATE_CONTEXT")
    try:
        curve = decode_account(curve_account, PUMP_PROGRAM, "BondingCurve")
    except QuoteUnavailable:
        raise QuoteUnavailable("CURVE_ACCOUNT_LAYOUT") from None
    quote = WSOL if curve["quote_mint"] == ZERO else curve["quote_mint"]
    if quote not in QUOTES:
        failure = QuoteUnavailable("UNSUPPORTED_QUOTE")
        setattr(failure, "_reserve_rejection", (0, 3))  # Numeric telemetry: unsupported identity, no address.
        raise failure
    try:
        supply, decimals, _ = mint_info(mint_account)
    except QuoteUnavailable:
        raise QuoteUnavailable("MINT_METADATA") from None
    try:
        qa = quote_accounts[quote]
        _, qdecimals, _ = mint_info(qa)
    except (QuoteUnavailable, KeyError):
        raise QuoteUnavailable("QUOTE_METADATA") from None
    if qa["owner"] != TOKEN_PROGRAM or qdecimals != QUOTES[quote][1] or not 0 <= decimals <= 18:
        raise QuoteUnavailable("UNVERIFIED_DECIMALS")
    if (
        supply != curve["token_total_supply"]
        or curve["complete"]
        or curve["is_mayhem_mode"]
        or any(curve[k] for k in ("depth", "post_complete_base_out", "post_complete_quote_in"))
    ):
        failure = QuoteUnavailable("UNSUPPORTED_CURVE_STATE")
        try:
            from backend.app.reserve_rejection_diagnostics import condition_mask

            mask = condition_mask(curve, supply)
            if type(mask) is not int or not 0 <= mask < 64:
                raise ValueError("Invalid reserve diagnostic mask")
            setattr(failure, "_reserve_rejection", (mask, 1 if quote == WSOL else 2))
        except Exception:
            # Only optional telemetry is isolated; the original rejection is never replaced.
            setattr(failure, "_reserve_rejection", (0, 1 if quote == WSOL else 2))
            setattr(failure, "_reserve_rejection_failed", True)
        raise failure
    base, q = curve["virtual_token_reserves"], curve["virtual_quote_reserves"]
    if (
        min(base, q, curve["real_token_reserves"], supply) <= 0
        or curve["real_token_reserves"] > min(base, supply)
        or curve["real_quote_reserves"] > q
    ):
        raise QuoteUnavailable("INVALID_RESERVES")

    def digest(a):
        return hashlib.sha256(json.dumps(a, sort_keys=True).encode()).hexdigest()

    return dict(
        mint=mint,
        venue="PUMP",
        quote_mint=quote,
        base_decimals=decimals,
        quote_decimals=qdecimals,
        base_raw=base,
        quote_raw=q,
        slot=slot,
        identity_address=address,
        requested_at=requested,
        acquired_at=acquired,
        account_hashes=[digest(a) for a in (curve_account, mint_account, qa)],
        commitment="confirmed",
    )


def usd_mark(state, refs, now, disagreement=False):
    if disagreement:
        raise QuoteUnavailable("PROVIDER_DISAGREEMENT")
    if not 0 <= now - state["acquired_at"] <= MAX_AGE:
        raise QuoteUnavailable("STALE_STATE")
    quote = state["quote_mint"]
    try:
        fx = fx_value(refs, quote, now)
    except QuoteUnavailable:
        from backend.app.price_diagnostics import fx_problem

        raise QuoteUnavailable(fx_problem(refs, quote, now)) from None
    # Marginal synthetic reserve ratio; no protocol fee/impact/fill guarantee.
    price = (
        Decimal(state["quote_raw"])
        / Decimal(state["base_raw"])
        * Decimal(10) ** (state["base_decimals"] - state["quote_decimals"])
    )
    usd = float(price * Decimal(str(fx)))
    if not math.isfinite(usd) or usd <= 0:
        raise QuoteUnavailable("INVALID_PRICE")
    ref = refs[quote]
    return dict(
        **{
            **state,
            "state_acquired_at": state["acquired_at"],
            "acquired_at": max(state["acquired_at"], ref["acquired_at"]),
        },
        price_quote=str(price),
        price=usd,
        currency="USD",
        source="Verified Pump reserve ratio + independent USD reference",
        source_schema_sha256=SCHEMA_HASH,
        formula="marginal_virtual_quote_per_base_unit_v1",
        version=VERSION,
        observed_at=max(state["acquired_at"], ref["acquired_at"]),
        valid_until=min(
            state["acquired_at"] + MAX_AGE, ref["published_at"] + MAX_AGE, ref["acquired_at"] + MAX_AGE
        ),
        usd_reference=dict(ref),
        verification="VERIFIED_SNAPSHOT_INPUTS",
        evidence_level="INDICATIVE_MARGINAL_MARK_NOT_EXECUTABLE",
        provider_expiry=None,
        freshness_policy_seconds=MAX_AGE,
        fees=None,
        liquidity_usd=None,
        net_return_pct=None,
    )


class PriceResearch:
    """Bounded one first review/mint/session, all five horizons retained, no cohort."""

    LIMIT = 250

    def __init__(self, db, session):
        self.db, self.session = db, session
        self.marks: dict = {}
        self.pending: dict = {}
        self.seen: set = set()
        self.capacity_omitted = 0
        self.rejected = 0
        from backend.app.price_diagnostics import PriceDiagnostics

        self.diagnostics = PriceDiagnostics(db, session)
        self.expired_marks: set = set()
        # Interrupted sessions cannot be completed using new observations.
        with db.sessions() as sql:
            rows = sql.scalars(
                select(Record)
                .where(Record.kind == "v21_price_signal")
                .order_by(Record.id.desc())
                .limit(self.LIMIT)
            ).all()
            old = [(r.id, r.mint, r.session, json.loads(r.payload)) for r in rows]
        for identity, mint, session_id, row in old:
            if session_id == session:
                self.seen.add(mint)
            completed = {
                x["horizon"]
                for x in db.rows("v21_price_outcome", mint, session_id, limit=1250)
                if x["signal_id"] == identity
            }
            for horizon in HORIZONS:
                if horizon not in completed:
                    self._write(identity, mint, session_id, horizon, "UNAVAILABLE_RESTART", None)

    def _write(self, identity, mint, session, horizon, status, value, endpoint=None):
        # Single serial writer: retry after an uncertain commit must not duplicate a horizon.
        with self.db.sessions() as sql:
            exists = sql.scalar(
                select(Record.id)
                .where(
                    Record.kind == "v21_price_outcome",
                    Record.session == session,
                    Record.mint == mint,
                    func.json_extract(Record.payload, "$.signal_id") == identity,
                    func.json_extract(Record.payload, "$.horizon") == horizon,
                )
                .limit(1)
            )
        if exists is not None:
            return
        self.db.add(
            "v21_price_outcome",
            dict(
                signal_id=identity,
                horizon=horizon,
                status=status,
                measurement=value,
                endpoint=endpoint,
                endpoint_status="OBSERVED_INDICATIVE_MARK" if endpoint else "UNAVAILABLE",
                net_return_pct=None,
                executable=False,
                version=VERSION,
            ),
            mint,
            session,
            time.time(),
        )

    def accept(self, mark, now, persist=False):
        try:
            mint = mark["mint"]
            valid = (
                mark["version"] == VERSION
                and mark["currency"] == "USD"
                and mark["venue"] == "PUMP"
                and mark["quote_mint"] in QUOTES
                and mark["quote_decimals"] == QUOTES[mark["quote_mint"]][1]
                and mark["verification"] == "VERIFIED_SNAPSHOT_INPUTS"
                and mark["source_schema_sha256"] == SCHEMA_HASH
                and type(mark["slot"]) is int
                and mark["slot"] > 0
                and math.isfinite(mark["price"])
                and mark["price"] > 0
                and mark["requested_at"] <= mark["state_acquired_at"] <= mark["acquired_at"]
                and mark["observed_at"] == mark["acquired_at"]
                and 0 <= now - mark["state_acquired_at"] <= MAX_AGE
            )
        except (KeyError, TypeError, ValueError):
            valid = False
        if valid:
            try:
                expected = usd_mark(
                    {
                        **{
                            k: mark[k]
                            for k in (
                                "mint",
                                "venue",
                                "quote_mint",
                                "base_decimals",
                                "quote_decimals",
                                "base_raw",
                                "quote_raw",
                                "slot",
                                "identity_address",
                                "requested_at",
                                "account_hashes",
                                "commitment",
                            )
                        },
                        "acquired_at": mark["state_acquired_at"],
                    },
                    {mark["quote_mint"]: mark["usd_reference"]},
                    now,
                )
                valid = (
                    mark["price"] == expected["price"]
                    and mark["valid_until"] == expected["valid_until"]
                    and mark["identity_address"]
                    == pda([b"bonding-curve", bytes(Pubkey.from_string(mint))], PUMP_PROGRAM)
                )
            except (KeyError, TypeError, ValueError, ArithmeticError):
                valid = False
        if not valid:
            self.rejected += 1
            self.diagnostics.note(mark.get("mint", "UNAVAILABLE"), "MARK_REJECTED", now)
            return False
        # Own immutable-at-enrollment copies, never caller-owned mutable dictionaries.
        mark = json.loads(json.dumps(mark, allow_nan=False))
        old = self.marks.get(mint)
        if old and (mark["slot"] < old["slot"] or mark["acquired_at"] <= old["acquired_at"]):
            self.rejected += 1
            self.diagnostics.note(mark.get("mint", "UNAVAILABLE"), "MARK_REJECTED", now)
            return False
        if not mark["observed_at"] <= now <= mark["valid_until"]:
            self.rejected += 1
            self.diagnostics.note(mark.get("mint", "UNAVAILABLE"), "MARK_REJECTED", now)
            return False
        if persist:
            # Do not expose an observation before its evidence receipt commits.
            self.diagnostics.note(mint, "SUBMITTED", now)
            try:
                self.db.add("v21_price_mark", mark, mint, self.session, mark["acquired_at"])
            except Exception:
                code = "PERSISTENCE_UNACKNOWLEDGED"
                try:
                    rows = self.db.rows("v21_price_mark", mint, self.session, limit=1)
                    found = bool(rows and all(rows[0].get(k) == v for k, v in mark.items()))
                    code = "PERSISTED_UNACKNOWLEDGED" if found else "NOT_PERSISTED"
                except Exception:
                    pass
                self.diagnostics.note(mint, code, now)
                self.diagnostics.flush()
                raise
            self.diagnostics.note(mint, "PERSISTED", now)
        self.expired_marks.discard(mint)
        self.marks[mint] = mark
        while len(self.marks) > self.LIMIT:
            oldest = next(iter(self.marks))
            self.marks.pop(oldest)
            self.expired_marks.discard(oldest)
        return True

    def tick(self, tokens, projections, now):
        for mint, mark in self.marks.items():
            if now > mark["valid_until"] and mint not in self.expired_marks:
                self.diagnostics.note(mint, "EXPIRED", now)
                self.expired_marks.add(mint)
        for identity, p in list(self.pending.items()):
            for horizon in list(p["remaining"]):
                due = p["signal_ts"] + horizon
                if now < due:
                    continue
                token = tokens.get(p["mint"])
                mark = self.marks.get(p["mint"])
                valid = (
                    mark
                    and token
                    and token.graduation is None
                    and not token.disagreement
                    and due <= mark["requested_at"] <= mark["acquired_at"] <= min(now, due + MAX_AGE)
                    and now <= mark["valid_until"]
                )
                if not valid and now <= due + MAX_AGE:
                    continue
                base = p["baseline"]
                if valid and base and mark is not None:
                    valid = mark["quote_mint"] == base["quote_mint"] and mark["slot"] >= base["slot"]
                value = (
                    dict(
                        baseline_signal_id=identity,
                        baseline_price_usd=base["price"],
                        observed_delay_seconds=mark["acquired_at"] - due,
                        gross_price_change_pct=(mark["price"] / base["price"] - 1) * 100,
                    )
                    if valid and base and mark is not None
                    else None
                )
                status = (
                    "OBSERVED_GROSS_MARK"
                    if value
                    else "UNAVAILABLE_BASELINE"
                    if not base
                    else "UNAVAILABLE_PRICE"
                )
                self._write(
                    identity, p["mint"], self.session, horizon, status, value, mark if valid else None
                )
                p["remaining"].remove(horizon)
            if not p["remaining"]:
                del self.pending[identity]
        for mint, projection in projections.items():
            early = projection.get("early_market") or {}
            if not early.get("speculative_review") or not early.get("version", "").startswith(
                "early-market-v2.1-"
            ):
                continue
            if mint in self.seen:
                continue
            saved = self.db.rows("v21_price_signal", mint, self.session, limit=1)
            if saved:
                # Recover a committed signal whose acknowledgement failed; never take a new baseline.
                row = saved[0]
                self.diagnostics.review(
                    mint,
                    row["signal_ts"],
                    row["baseline"],
                    None,
                    frozen=self.diagnostics.historical_review(
                        row.get(
                            "first_review_price_diagnostics",
                            dict(mint=mint, signal_at=row["signal_ts"], baseline_status=row["status"]),
                        )
                    ),
                )
                self.seen.add(mint)
                completed = {
                    x["horizon"]
                    for x in self.db.rows("v21_price_outcome", mint, self.session, limit=5)
                    if x["signal_id"] == row["id"]
                }
                remaining = [h for h in HORIZONS if h not in completed]
                if remaining:
                    self.pending[row["id"]] = dict(
                        mint=mint, signal_ts=row["signal_ts"], baseline=row["baseline"], remaining=remaining
                    )
                continue
            if len(self.seen) >= self.LIMIT:
                self.capacity_omitted += 1
                continue
            token = tokens[mint]
            if not (early["observed_at"] <= now <= early["valid_until"]) or token.graduation is not None:
                continue
            mark = self.marks.get(mint)
            baseline = (
                mark
                if mark and not token.disagreement and mark["acquired_at"] <= now <= mark["valid_until"]
                else None
            )
            baseline = json.loads(json.dumps(baseline)) if baseline else None
            first_review = self.diagnostics.first_review(mint, now, baseline, mark)
            payload = dict(
                first_review_price_diagnostics=first_review,
                version=VERSION,
                signal_ts=now,
                assessment=early,
                baseline=baseline,
                status="BASELINE_OBSERVED" if baseline else "UNAVAILABLE_BASELINE",
                horizons=HORIZONS,
            )
            identity = self.db.add("v21_price_signal", payload, mint, self.session, now)
            self.diagnostics.review(mint, now, baseline, mark, frozen=first_review)
            self.diagnostics.flush()
            self.seen.add(mint)
            self.pending[identity] = dict(
                mint=mint, signal_ts=now, baseline=baseline, remaining=list(HORIZONS)
            )

    def snapshot(self):
        return dict(
            signals=len(self.seen),
            pending=len(self.pending),
            capacity_omitted_assessments=self.capacity_omitted,
            rejected_marks=self.rejected,
            retained_marks=len(self.marks),
            executable=False,
            acquisition_diagnostics=self.diagnostics.summary(),
        )

    def stop(self):
        self.diagnostics.status = "STOPPED"
        self.diagnostics.flush()
        for identity, p in list(self.pending.items()):
            for horizon in p["remaining"]:
                self._write(identity, p["mint"], self.session, horizon, "UNAVAILABLE_SHUTDOWN", None)
            del self.pending[identity]

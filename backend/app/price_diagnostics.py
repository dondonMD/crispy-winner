"""Local bounded operational receipts only; never inputs to pricing or eligibility."""

from collections import Counter, OrderedDict
import hashlib
import json
import math
import time
from backend.app.db import EvidenceRun

CODES = frozenset(
    """ATTEMPTED RPC_COMPLETED RPC_UNAVAILABLE RPC_TIMEOUT RPC_RATE_LIMITED RPC_CANCELLED
RPC_INVALID_RESPONSE ACQUISITION_CANCELLED NO_VERIFIED_CURVE CURVE_ACCOUNT_LAYOUT MINT_IDENTITY MINT_METADATA QUOTE_METADATA
UNVERIFIED_DECIMALS UNSUPPORTED_QUOTE UNSUPPORTED_CURVE_STATE INVALID_RESERVES STATE_CONTEXT
STATE_VALIDATED USD_UNAVAILABLE USD_STALE USD_TIME_INVALID PROVIDER_DISAGREEMENT STALE_STATE INVALID_PRICE
CALCULATION_REJECTED CONSTRUCTED SUBMITTED PERSISTED NOT_PERSISTED PERSISTED_UNACKNOWLEDGED PERSISTENCE_UNACKNOWLEDGED MARK_REJECTED TOKEN_INELIGIBLE
NOT_SELECTED BACKGROUND_ONLY NOT_PREGRAD NOT_DUE RPC_INELIGIBLE EXPIRED UNKNOWN_OTHER""".split()
)
TERMINAL = CODES - {
    "ATTEMPTED",
    "RPC_COMPLETED",
    "STATE_VALIDATED",
    "CONSTRUCTED",
    "SUBMITTED",
    "NOT_SELECTED",
    "BACKGROUND_ONLY",
    "NOT_PREGRAD",
    "NOT_DUE",
    "RPC_INELIGIBLE",
    "EXPIRED",
}
FX_CODES = frozenset(
    "attempted http_started http_completed request_failed validation_failed stale_rejected cancelled usable interval_skipped budget_skipped".split()
)


def fx_problem(refs, quote, now):
    """Diagnostic explanation only; acceptance still exclusively uses fx_value()."""
    ref = refs.get(quote)
    if not isinstance(ref, dict):
        return "USD_UNAVAILABLE"
    stamps = [ref.get(k) for k in ("published_at", "acquired_at")]
    if all(isinstance(t, (int, float)) and math.isfinite(t) for t in stamps):
        if any(now - t > 20 for t in stamps):
            return "USD_STALE"
        if any(now - t < 0 for t in stamps):
            return "USD_TIME_INVALID"
    return "USD_UNAVAILABLE"


class PriceDiagnostics:
    TOKEN_LIMIT = 32
    REVIEW_LIMIT = 24
    BYTE_LIMIT = 48000

    def __init__(self, db, session):
        self.db = db
        self.key = "px:" + hashlib.sha256(session.encode()).hexdigest()[:32]
        self.counts: Counter = Counter()
        self.tokens: OrderedDict = OrderedDict()
        self.reviews: OrderedDict = OrderedDict()
        self.inflight: dict = {}
        self.fx: dict = {
            p: dict(counts={}, reference=None, cache_present=False) for p in ("SOL-USD", "USDCUSD")
        }
        self.token_omissions = self.review_omissions = self.durable_failures = 0
        self.sequence = 0
        self.status = "RUNNING"
        # Reusing a session must not erase a previous durable diagnostic checkpoint.
        with db.sessions() as sql:
            row = sql.get(EvidenceRun, self.key)
            old = json.loads(row.payload) if row else None
        if old:
            self.counts.update(old["counts"])
            self.tokens.update((r["mint"], r) for r in old["tokens"])
            self.reviews.update((r["mint"], r) for r in old["reviews"])
            self.fx = old["fx"]
            for row in self.fx.values():
                row["cache_present"] = False
                c = row["counts"]
                terminal = sum(
                    c.get(k, 0)
                    for k in ("usable", "request_failed", "validation_failed", "stale_rejected", "cancelled")
                )
                row["checkpoint_unresolved"] = max(0, c.get("attempted", 0) - terminal)
            self.sequence = old["sequence"]
            self.token_omissions = old["token_omissions"]
            self.review_omissions = old["review_omissions"]
            self.counts["unresolved_at_previous_checkpoint"] += old["in_progress"]
            # This is an unknown checkpoint tail, NOT proof that requests failed.

    def note(self, mint, code, now=None):
        from solders.pubkey import Pubkey

        try:
            mint = (
                str(Pubkey.from_string(mint)) if isinstance(mint, str) and len(mint) <= 44 else "UNAVAILABLE"
            )
        except ValueError:
            mint = "UNAVAILABLE"
        code = code if code in CODES else "UNKNOWN_OTHER"
        recorded_at = time.time()
        now = recorded_at if now is None else now
        self.counts[code] += 1
        selection = code in {"NOT_SELECTED", "BACKGROUND_ONLY", "NOT_PREGRAD", "NOT_DUE", "RPC_INELIGIBLE"}
        if selection and mint not in self.tokens:
            if mint in self.reviews:
                self.reviews[mint]["selection_status"] = code
            return
        row = self.tokens.setdefault(mint, dict(mint=mint, attempts=0))
        if not selection:
            previous = (row.get("at"), row.get("recorded_at"))
            valid_times = all(isinstance(t, (int, float)) and math.isfinite(t) for t in (now, recorded_at))
            row["time_order_ambiguous"] = bool(
                row.get("time_order_ambiguous")
                or not valid_times
                or previous[0] is not None
                and now < previous[0]
                or previous[1] is not None
                and recorded_at < previous[1]
            )
            row["recorded_at"] = recorded_at
        if code in TERMINAL and code != "PERSISTED":
            row.update(
                last_failure=code,
                last_failure_at=now,
                last_failure_recorded_at=recorded_at,
                failure_time_ambiguous=row.get("time_order_ambiguous", False),
            )
        row.update(
            **(
                {"selection_status": code, "selection_at": now}
                if selection
                else {"last_status": code, "at": now}
            )
        )
        self.tokens.move_to_end(mint)
        if code == "ATTEMPTED":
            row["attempts"] += 1
            if mint in self.inflight:
                self.counts["overlapping_attempt_diagnostic"] += 1
            if mint in self.inflight or len(self.inflight) < 25:
                self.inflight[mint] = code
            else:
                self.counts["inflight_omissions"] += 1
        elif code in TERMINAL:
            if mint in self.inflight:
                self.counts["finished_attempts"] += 1
            self.inflight.pop(mint, None)
        elif mint in self.inflight:
            self.inflight[mint] = code
        if code == "PERSISTED":
            row["last_persisted_at"] = now
        if mint in self.reviews and not selection:
            review = self.reviews[mint]
            review.update(last_status=code, last_status_at=now, last_status_recorded_at=recorded_at)
            if code in TERMINAL and code != "PERSISTED":
                review.update(last_failure=code, last_failure_at=now, last_failure_recorded_at=recorded_at)
            if code == "PERSISTED" and review["baseline_status"] != "VALID_SIGNAL_BASELINE":
                review["later_mark_not_backfilled"] = now >= review["signal_at"]
        while len(self.tokens) > self.TOKEN_LIMIT:
            self.tokens.popitem(last=False)
            self.token_omissions += 1

    def review(self, mint, signal_at, baseline, prior, frozen=None):
        if mint in self.reviews:
            return
        if len(self.reviews) >= self.REVIEW_LIMIT:
            self.review_omissions += 1
            return
        self.reviews[mint] = json.loads(
            json.dumps(frozen if frozen is not None else self.first_review(mint, signal_at, baseline, prior))
        )
        # Historical snapshot may have been frozen before a DB callback; latest state stays operational.
        current = self.tokens.get(mint, {})
        mapping = {
            "last_status": "last_status",
            "last_status_at": "at",
            "last_status_recorded_at": "recorded_at",
            "last_failure": "last_failure",
            "last_failure_at": "last_failure_at",
            "last_failure_recorded_at": "last_failure_recorded_at",
        }
        for dest, source in mapping.items():
            if source in current:
                self.reviews[mint][dest] = current[source]

    @staticmethod
    def _temporal_reason(event_at, recorded_at, signal_at, ambiguous):
        if event_at is None or recorded_at is None:
            return "MISSING_OBSERVATION_TIMESTAMP"
        if not all(
            isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t)
            for t in (event_at, recorded_at, signal_at)
        ):
            return "INVALID_TIMESTAMP"
        if ambiguous:
            return "NON_MONOTONIC_DIAGNOSTIC_CLOCK"
        if event_at > signal_at or recorded_at > signal_at:
            return "NOT_AVAILABLE_AT_SIGNAL"
        if event_at == signal_at or recorded_at == signal_at:
            return "EQUAL_TIMESTAMP_AMBIGUOUS"
        if event_at > recorded_at:
            return "EVENT_AFTER_PROCESSING_TIMESTAMP"
        return None

    @staticmethod
    def historical_review(review):
        # Never derive legacy first-review facts from mutable latest-state fields.
        result = dict(review)
        if "acquisition_status_at_signal" not in result:
            result.update(
                acquisition_status_at_signal="UNKNOWN",
                rejection_reason_at_signal="UNKNOWN",
                rejection_observed_at_signal=None,
                rejection_event_at_signal=None,
                acquisition_status_unknown_reason="LEGACY_SIGNAL_PROVENANCE_UNAVAILABLE",
                rejection_reason_unknown_reason="LEGACY_SIGNAL_PROVENANCE_UNAVAILABLE",
            )
        return result

    def first_review(self, mint, signal_at, baseline, prior):
        captured_at = time.time()
        token = self.tokens.get(mint, {})
        status_unknown = self._temporal_reason(
            token.get("at"), token.get("recorded_at"), signal_at, token.get("time_order_ambiguous", False)
        )
        failure_unknown = (
            self._temporal_reason(
                token.get("last_failure_at"),
                token.get("last_failure_recorded_at"),
                signal_at,
                token.get("failure_time_ambiguous", False) or token.get("time_order_ambiguous", False),
            )
            if token.get("last_failure")
            else "NO_REJECTION_RECORDED"
            if not self.token_omissions
            else "DIAGNOSTIC_HISTORY_NOT_RETAINED"
        )
        if isinstance(signal_at, (int, float)) and math.isfinite(signal_at) and signal_at > captured_at:
            status_unknown = failure_unknown = "SIGNAL_TIMESTAMP_AFTER_CAPTURE"
        reason = (
            "VALID_SIGNAL_BASELINE"
            if baseline
            else "EARLIER_MARK_EXPIRED"
            if prior and prior["valid_until"] < signal_at
            else "VALID_MARK_UNAVAILABLE_AT_SIGNAL"
            if prior
            else "ATTEMPT_RECORDED_NO_MARK"
            if token.get("attempts")
            else "UNKNOWN_DIAGNOSTIC_EVICTED"
            if self.token_omissions
            else "NO_ACQUISITION_ATTEMPTED"
        )
        return dict(
            captured_at=captured_at,
            acquisition_status_at_signal=token.get("last_status", "UNKNOWN")
            if not status_unknown
            else "UNKNOWN",
            rejection_reason_at_signal=token["last_failure"] if not failure_unknown else "UNKNOWN",
            rejection_observed_at_signal=token["last_failure_recorded_at"] if not failure_unknown else None,
            rejection_event_at_signal=token["last_failure_at"] if not failure_unknown else None,
            acquisition_status_unknown_reason=status_unknown,
            rejection_reason_unknown_reason=failure_unknown,
            mint=mint,
            signal_at=signal_at,
            baseline_status=reason,
            last_status=token.get("last_status", "UNAVAILABLE"),
            last_status_at=token.get("at"),
            attempts_at_signal=token.get("attempts"),
            last_failure=token.get("last_failure"),
            later_mark_not_backfilled=False,
        )

    def fx_event(self, product, code, reference=None, amount=1):
        if product not in self.fx or code not in FX_CODES:
            self.counts["unknown_fx_diagnostic"] += 1
            return
        row = self.fx[product]
        row["counts"][code] = row["counts"].get(code, 0) + amount
        if code in {"usable", "request_failed", "validation_failed", "stale_rejected", "cancelled"}:
            row["last_result"] = code
            row["last_result_at"] = time.time()
        if reference is not None:
            row["cache_present"] = True
            # No provider payload or exception text survives this whitelist.
            row["reference"] = {
                k: reference[k] for k in ("published_at", "acquired_at", "source", "product", "usd")
            }

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        fx = json.loads(json.dumps(self.fx))
        for row in fx.values():
            ref = row["reference"]
            c = row["counts"]
            terminal = sum(
                c.get(k, 0)
                for k in ("usable", "request_failed", "validation_failed", "stale_rejected", "cancelled")
            )
            row["in_progress"] = c.get("attempted", 0) - terminal - row.get("checkpoint_unresolved", 0)
            row["counter_consistent"] = row["in_progress"] >= 0
            row["usable_in_current_cache"] = bool(
                row.get("cache_present")
                and ref
                and all(0 <= now - ref[k] <= 20 for k in ("published_at", "acquired_at"))
            )
            row["publication_age_seconds"] = now - ref["published_at"] if ref else None
            row["acquisition_age_seconds"] = now - ref["acquired_at"] if ref else None
            row["freshness"] = (
                "FRESH"
                if ref and all(0 <= now - ref[k] <= 20 for k in ("published_at", "acquired_at"))
                else "STALE"
                if ref
                else "UNAVAILABLE"
            )
        result = dict(
            version=2,
            at=now,
            sequence=self.sequence,
            status=self.status,
            counts=dict(self.counts),
            in_progress=len(self.inflight),
            attempt_reconciled=(
                self.counts["ATTEMPTED"]
                == self.counts["finished_attempts"]
                + len(self.inflight)
                + self.counts["unresolved_at_previous_checkpoint"]
                and not self.counts["overlapping_attempt_diagnostic"]
                and not self.counts["inflight_omissions"]
            ),
            tokens=list(self.tokens.values()),
            reviews=[self.historical_review(r) for r in self.reviews.values()],
            fx=fx,
            token_omissions=self.token_omissions,
            review_omissions=self.review_omissions,
            durable_failures=self.durable_failures,
            scope="sampled tokens; counters count stages, not independent signals",
        )
        return result

    def summary(self):
        s = self.snapshot()
        return {
            k: s[k]
            for k in (
                "status",
                "counts",
                "in_progress",
                "attempt_reconciled",
                "fx",
                "token_omissions",
                "review_omissions",
                "durable_failures",
            )
        } | {"receipt_key": self.key}

    def flush(self):
        self.sequence += 1
        payload = self.snapshot()
        while len(json.dumps(payload).encode()) > self.BYTE_LIMIT and (
            payload["tokens"] or payload["reviews"]
        ):
            key = "tokens" if payload["tokens"] else "reviews"
            payload[key].pop()
            count_key = "byte_omitted_" + key
            payload[count_key] = payload.get(count_key, 0) + 1
            payload["byte_omissions"] = payload.get("byte_omissions", 0) + 1
        try:
            self.db.evidence_run(self.key, payload)
        except Exception:
            # Never swallow cancellation (BaseException), change market evidence or report a durable success.
            self.durable_failures += 1

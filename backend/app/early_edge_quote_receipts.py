"""Offline structural contract, not provider authentication, a fill or approval.

Trusted expectations must come from a reviewed adapter and independent canonical
identity inspection. A caller-supplied flag cannot authenticate a provider quote.
No prices, profits, SDK fills, transactions or cohort outcomes are produced here.
"""

from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, ValidationError, field_validator
from solders.pubkey import Pubkey

from backend.app.early_edge_quotes import QUOTES
from backend.app.providers import PUMP_PROGRAM

VERSION = "route-receipt-v1"
COSTS = ("protocol", "creator", "lp", "platform", "network", "priority", "transfer", "rent")
SAFE_ID = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
DIGEST = r"^[a-f0-9]{64}$"
U64 = 2**64 - 1


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class Context(ContractModel):
    """Separately verified venue/mints plus the predeclared request intent.

    This is an input trust boundary, not a claim verified by this offline module.
    Evidence hashes must resolve to reviewed private identity/source receipts.
    """

    provider: str = Field(pattern=SAFE_ID)
    source_version: str = Field(pattern=SAFE_ID)
    quote_version: str = Field(pattern=SAFE_ID)
    adapter_evidence_sha256: str = Field(pattern=DIGEST)
    identity_evidence_sha256: str = Field(pattern=DIGEST)
    signal_at: FiniteFloat = Field(gt=0)
    direction: Literal["BUY", "SELL"]
    horizon_seconds: Literal[60, 180, 300, 600, 1800] = 300
    base_mint: str
    quote_mint: str
    base_decimals: int = Field(ge=0, le=18)
    quote_decimals: int = Field(ge=0, le=18)
    input_amount_raw: int = Field(gt=0, le=U64)
    venue: Literal["PUMP", "PUMPSWAP"]
    venue_address: str
    lifecycle: Literal["PRE_GRAD", "MIGRATED"]
    migration_evidence_sha256: str | None = Field(default=None, pattern=DIGEST)
    # Frozen request policy, never selected after observing the quote.
    max_slippage_bps: int = Field(ge=0, le=10000)
    cost_policy_sha256: str = Field(pattern=DIGEST)
    usd_reference_sha256: str = Field(pattern=DIGEST)
    position_usd: Literal[4] = 4
    verified_context_slot: int | None = Field(default=None, ge=0)
    verified_context_acquired_at: FiniteFloat | None = Field(default=None, gt=0)
    verified_context_sha256: str | None = Field(default=None, pattern=DIGEST)

    @field_validator("base_mint", "quote_mint", "venue_address")
    @classmethod
    def key(cls, value):
        if str(Pubkey.from_string(value)) != value or value == str(Pubkey.default()):
            raise ValueError("Invalid identity")
        return value


class Fee(ContractModel):
    component: Literal["protocol", "creator", "lp", "platform", "network", "priority", "transfer", "rent"]
    treatment: Literal["EMBEDDED", "EXTERNAL", "RECOVERABLE_LOCKUP", "NOT_APPLICABLE", "UNAVAILABLE"]
    amount_raw: int | None = Field(ge=0, le=U64)
    mint: str | None = Field(max_length=44)
    decimals: int | None = Field(ge=0, le=18)
    evidence_sha256: str | None = Field(pattern=DIGEST)
    unavailable_reason: Literal["NOT_PROVIDED", "UNSUPPORTED", "UNVERIFIED"] | None

    @field_validator("mint")
    @classmethod
    def fee_key(cls, value):
        return Context.key(value) if value is not None else None


class Receipt(ContractModel):
    evidence_kind: Literal["PROVIDER_ROUTE_QUOTE"]
    provider: str = Field(pattern=SAFE_ID)
    source_version: str = Field(pattern=SAFE_ID)
    quote_version: str = Field(pattern=SAFE_ID)
    quote_sha256: str = Field(pattern=DIGEST)
    response_evidence_sha256: str = Field(pattern=DIGEST)
    requested_at: FiniteFloat = Field(gt=0)
    responded_at: FiniteFloat = Field(gt=0)
    provider_quoted_at: FiniteFloat | None = Field(default=None, gt=0)
    context_slot: int | None = Field(default=None, ge=0)
    context_evidence_sha256: str | None = Field(default=None, pattern=DIGEST)
    # Minimal v1 supports authoritative TIME expiry only. No guessed slot expiry.
    expires_at: FiniteFloat = Field(gt=0)
    expiry_evidence_sha256: str = Field(pattern=DIGEST)
    direction: Literal["BUY", "SELL"]
    venue: Literal["PUMP", "PUMPSWAP"]
    venue_address: str = Field(min_length=32, max_length=44)
    base_mint: str = Field(min_length=32, max_length=44)
    quote_mint: str = Field(min_length=32, max_length=44)
    base_decimals: int = Field(ge=0, le=18)
    quote_decimals: int = Field(ge=0, le=18)
    input_amount_raw: int = Field(gt=0, le=U64)
    output_amount_raw: int = Field(gt=0, le=U64)
    minimum_output_raw: int = Field(gt=0, le=U64)
    amount_semantics: Literal["EXACT_IN_RAW_NET_OUTPUT"]
    route_available: bool
    route_evidence_sha256: str = Field(pattern=DIGEST)
    # Only this restrictive, documented execution profile is supported in v1.
    execution_conditions: Literal["CLASSIC_SPL_NO_FREEZE_HOOK_TRANSFER_FEE_OR_RESTRICTIONS"]
    conditions_evidence_sha256: str = Field(pattern=DIGEST)
    fees: tuple[Fee, ...] = Field(min_length=8, max_length=8)

    @field_validator("base_mint", "quote_mint", "venue_address")
    @classmethod
    def receipt_key(cls, value):
        return Context.key(value)

    @field_validator("fees", mode="before")
    @classmethod
    def fee_array(cls, value):
        if isinstance(value, list) and len(value) == 8:
            return tuple(value)
        return value


class Result(ContractModel):
    accepted: bool
    route_valid: bool = False
    status: Literal["QUOTE_ACCEPTED", "QUOTE_NOT_SELECTED", "UNAVAILABLE_QUOTE", "UNAVAILABLE_UNITS", "UNAVAILABLE_PROVIDER_GAP"]
    reason: str
    receipt_sha256: str | None = None
    context_sha256: str
    # Even accepted receipts are not measured returns or authenticated fills.
    outcome_authorized: Literal[False] = False


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_receipt(payload, context: Context, now: float) -> Result:
    """Pure, bounded validation. Never stores raw payload/errors or calls a provider."""
    context_hash = digest(context.model_dump(mode="json"))
    receipt_hash = None

    def reject(reason, status="UNAVAILABLE_QUOTE", route_valid=False):
        return Result(accepted=False, route_valid=route_valid, status=status, reason=reason,
                      context_sha256=context_hash, receipt_sha256=receipt_hash)

    # No arbitrary object conversion, unbounded raw JSON or unrestricted strings.
    if not isinstance(payload, dict) or len(payload) > 40:
        return reject("INCOMPLETE_RECEIPT")
    try:
        r = Receipt.model_validate(payload)
    except ValidationError:
        return reject("INCOMPLETE_OR_UNSUPPORTED_RECEIPT")
    receipt_hash = digest(r.model_dump(mode="json"))
    if type(now) not in (float, int) or not 0 < now < float("inf"):
        return reject("INVALID_TIME")
    if any(getattr(r, k) != getattr(context, k) for k in ("provider", "source_version", "quote_version")):
        return reject("SOURCE_MISMATCH")
    if any(getattr(r, k) != getattr(context, k) for k in (
        "base_mint", "quote_mint", "base_decimals", "quote_decimals", "input_amount_raw")):
        return reject("UNITS_OR_AMOUNT_MISMATCH", "UNAVAILABLE_UNITS")
    if context.base_mint == context.quote_mint or context.quote_mint not in QUOTES:
        return reject("UNSUPPORTED_UNITS", "UNAVAILABLE_UNITS")
    if QUOTES[context.quote_mint][1] != context.quote_decimals:
        return reject("UNSUPPORTED_UNITS", "UNAVAILABLE_UNITS")
    if (r.direction, r.venue, r.venue_address) != (context.direction, context.venue, context.venue_address):
        return reject("IDENTITY_OR_DIRECTION_MISMATCH")
    if context.lifecycle == "PRE_GRAD":
        curve = Pubkey.find_program_address(
            [b"bonding-curve", bytes(Pubkey.from_string(context.base_mint))], Pubkey.from_string(PUMP_PROGRAM),
        )[0]
        if context.venue != "PUMP" or context.venue_address != str(curve):
            return reject("VENUE_INCOMPATIBLE")
    elif (context.direction == "BUY" or context.venue != "PUMPSWAP"
          or context.migration_evidence_sha256 is None):
        return reject("MIGRATION_EVIDENCE_REQUIRED")
    boundary = context.signal_at + (10 if context.direction == "BUY" else context.horizon_seconds)
    delay = 10 if context.direction == "BUY" else 20
    if not boundary <= r.requested_at <= r.responded_at <= now <= boundary + delay:
        return reject("LATE_OR_OUT_OF_WINDOW", "UNAVAILABLE_PROVIDER_GAP")
    if r.provider_quoted_at is not None:
        if not r.requested_at <= r.provider_quoted_at <= r.responded_at:
            return reject("STALE_OR_FUTURE_PROVIDER_QUOTE")
    if r.provider_quoted_at is None or r.context_slot is not None or r.context_evidence_sha256 is not None:
        if (r.context_slot is None or r.context_evidence_sha256 is None
                or context.verified_context_slot != r.context_slot
                or context.verified_context_sha256 != r.context_evidence_sha256
                or context.verified_context_acquired_at is None
                or not r.requested_at <= context.verified_context_acquired_at <= r.responded_at):
            return reject("MISSING_PROVIDER_TIME_OR_CONTEXT")
    if r.expires_at <= now or r.expires_at <= r.responded_at:
        return reject("EXPIRED_QUOTE")
    if not r.route_available:
        return reject("NO_ROUTE")
    minimum = r.output_amount_raw * (10000 - context.max_slippage_bps) // 10000
    if not max(1, minimum) <= r.minimum_output_raw <= r.output_amount_raw:
        return reject("INCONSISTENT_SLIPPAGE_OR_OUTPUT")
    if {f.component for f in r.fees} != set(COSTS):
        return reject("INCOMPLETE_COST_LEDGER", route_valid=True)
    for f in r.fees:
        if f.treatment == "UNAVAILABLE":
            return reject("COST_COMPONENT_UNAVAILABLE", route_valid=True)
        if f.unavailable_reason is not None or f.evidence_sha256 is None:
            return reject("UNVERIFIED_COST_COMPONENT", route_valid=True)
        if (f.mint not in QUOTES or f.decimals != QUOTES[f.mint][1] or f.amount_raw is None):
            return reject("COST_UNITS_UNAVAILABLE", "UNAVAILABLE_UNITS", True)
        if f.treatment == "NOT_APPLICABLE" and f.amount_raw != 0:
            return reject("INCONSISTENT_COST_COMPONENT", route_valid=True)
        if f.treatment == "RECOVERABLE_LOCKUP" and f.component != "rent":
            return reject("INCONSISTENT_COST_COMPONENT", route_valid=True)
    return Result(accepted=True, route_valid=True, status="QUOTE_ACCEPTED", reason="VALID_RECEIPT",
                  receipt_sha256=digest(r.model_dump(mode="json")), context_sha256=context_hash)

"""Synthetic exact SDK 4.2.0 layout and diagnostic/security isolation regressions."""

import base64
import hashlib
from pathlib import Path

import pytest

from backend.app.discovery import decode_event, DecodeFailure, FIELDS, SCHEMA
from backend.tests.test_onchain_trades import wire, payload
from backend.app.discovery import OnchainPumpDiscovery
from scripts.pump_trade_forensics import inspect_payload, scoped_events


@pytest.mark.parametrize("is_buy", [True, False])
def test_official_420_exact_extension(is_buy):
    encoded = wire(is_buy=is_buy, quote_transfer_fee=123)
    name, fields = decode_event(encoded)
    assert name == "TradeEvent" and fields["quote_transfer_fee"] == 123
    assert fields["is_buy"] == is_buy
    assert len(FIELDS["TradeEvent"]) == 36
    old = FIELDS["TradeEvent"][:-1]
    metadata, _ = inspect_payload(encoded, old)
    assert metadata["category"] == "KNOWN_DISCRIMINATOR_TRAILING_BYTES"
    assert metadata["remaining"] == 8 and metadata["u64"] == [123]
    assert metadata["parsed_fields"] == 35
    assert metadata["final_documented_field"] == "creator_fee_unclaimed"
    assert metadata["trailing_sha256"] == hashlib.sha256((123).to_bytes(8, "little")).hexdigest()


@pytest.mark.parametrize("extra", [b"x", b"\0" * 8, b"\0" * 16])
def test_no_opaque_tail(extra):
    encoded = base64.b64encode(base64.b64decode(wire()) + extra).decode()
    with pytest.raises(DecodeFailure):
        decode_event(encoded)


@pytest.mark.parametrize("remove", [1, 8, 9, 32, 300])
def test_truncation_and_documented_old_layout_fail_closed(remove):
    encoded = base64.b64encode(base64.b64decode(wire())[:-remove]).decode()
    with pytest.raises(DecodeFailure):
        decode_event(encoded)
    metadata, _ = inspect_payload(encoded)
    assert metadata["category"] == "FIELD_BOUNDARY_FAILURE"


def test_new_schema_provenance_keeps_other_events():
    p = SCHEMA["trade_event_source"]
    assert p["version"] == "4.2.0" and p["npm_registry_signature_verified"]
    assert p["idl_sha256"] == "c53b8f5d39887afd27cc40a256527a421c2d91b64a9014dc4952a261f4f36a01"
    assert "639b87fb" in SCHEMA["source"]
    assert FIELDS["TradeEvent"][-1] == dict(name="quote_transfer_fee", type="u64")


def test_units_dedup_and_unknown_quote_unchanged():
    from solders.pubkey import Pubkey

    events = []
    p = OnchainPumpDiscovery(events.append, tracked=lambda mint: True)
    n = payload(wire(quote_mint=str(Pubkey.new_unique()), quote_transfer_fee=99))
    p.receive(n)
    p.receive(n)
    assert len(events) == 1 and not events[0].evidence["units_valid"]
    assert events[0].currency == "unknown"
    assert p.health["duplicate_trades"] == 1


def test_diagnostic_failure_metadata_has_no_wallet_or_payload():
    meta, _ = inspect_payload(wire(), FIELDS["TradeEvent"][:-1])
    assert not {"user", "wallet", "mint", "raw", "payload"}.intersection(meta)
    assert inspect_payload("A" * 16385)[0]["detail"] == "ENCODED_STRING_TOO_LARGE"
    assert inspect_payload(base64.b64encode(b"abc").decode())[0]["category"] == "RAW_TOO_SHORT"


def test_failed_scopes_and_truncation_not_valid_evidence():
    from backend.app.providers import PUMP_PROGRAM

    logs = [
        f"Program {PUMP_PROGRAM} invoke [1]",
        "Program data: " + wire(),
        f"Program {PUMP_PROGRAM} failed: custom error",
    ]
    assert scoped_events(logs) == ([], False)
    assert scoped_events(logs[:-1] + ["Log truncated"])[1]


def test_no_engine_database_or_execution_in_forensics():
    for path in ("scripts/pump_trade_forensics.py", "scripts/pump_authority_audit.py"):
        s = Path(path).read_text()
        assert "import RadarEngine" not in s and "import sqlite" not in s
        assert "sendTransaction" not in s and "Keypair" not in s


def test_diagnostic_exact_invalid_categories():
    assert inspect_payload(wire(timestamp=2**62))[0]["category"] == "INVALID_TIMESTAMP"
    raw = bytearray(base64.b64decode(wire()))
    raw[56] = 2
    assert inspect_payload(base64.b64encode(raw).decode())[0]["category"] == "INVALID_BOOL"
    raw = bytearray(base64.b64decode(wire()))
    offset = raw.index(b"\x06\x00\x00\x00buy_v3")
    raw[offset : offset + 4] = (2049).to_bytes(4, "little")
    assert inspect_payload(base64.b64encode(raw).decode())[0]["category"] == "INVALID_STRING"
    assert (
        inspect_payload(wire(), [{"name": "unsupported", "type": "u256"}])[0]["category"]
        == "FIELD_TYPE_UNSUPPORTED"
    )


def test_cross_slot_gate_requires_diverse_complete_finalized_examples():
    from scripts.pump_cross_slot import sufficient

    samples = [
        dict(
            slot=i // 3,
            mint_hash=str(i % 4),
            direction="BUY" if i % 2 else "SELL",
            parsed_fields=36,
            remaining=0,
            quote_account_matches=True,
        )
        for i in range(12)
    ]
    assert sufficient(samples)
    assert not sufficient([dict(s, slot=1) for s in samples])
    assert not sufficient([dict(s, remaining=8) for s in samples])


def test_cross_slot_named_instruction_identity():
    from scripts.pump_cross_slot import match_instruction
    from backend.app.truncation import INSTRUCTIONS, BASE58
    from backend.app.providers import PUMP_PROGRAM

    definition = next(v for v in INSTRUCTIONS.values() if v["name"] == "buy")
    value = int.from_bytes(bytes(definition["discriminator"]), "big")
    encoded = ""
    while value:
        value, digit = divmod(value, 58)
        encoded = BASE58[digit] + encoded
    accounts = [a["name"] for a in definition["accounts"]]
    instruction = dict(programId=PUMP_PROGRAM, data=encoded, accounts=accounts)
    fields = dict(mint="mint", user="user", is_buy=True, ix_name="buy")
    assert len(match_instruction(fields, [instruction])) == 1
    assert not match_instruction(dict(fields, user="FOREIGN"), [instruction])
    assert not match_instruction(dict(fields, is_buy=False), [instruction])

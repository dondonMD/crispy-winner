import base64
import hashlib
import struct
import pytest
from solders.pubkey import Pubkey
from backend.app.onchain import parse_curve, parse_pool, parse_global, curve_progress, PUMP_SWAP_PROGRAM
from backend.app.providers import PUMP_PROGRAM


def encoded(raw, program):
    return {"owner": program, "data": [base64.b64encode(raw).decode(), "base64"]}


def test_curve_and_dynamic_baseline():
    raw = (
        hashlib.sha256(b"account:BondingCurve").digest()[:8]
        + struct.pack("<QQQQQ", 300, 100, 20, 80, 1000)
        + b"\x00"
    )
    curve = parse_curve(encoded(raw, PUMP_PROGRAM))
    global_raw = (
        hashlib.sha256(b"account:Global").digest()[:8]
        + b"\x00" * 65
        + struct.pack("<QQQQ", 400, 30, 120, 1000)
    )
    global_config = parse_global(encoded(global_raw, PUMP_PROGRAM))
    assert curve_progress(curve, global_config) == pytest.approx(83.33)
    global_config["initial_real_token_reserves"] = 125
    assert curve_progress(curve, global_config) is None
    with pytest.raises(ValueError):
        parse_curve(encoded(raw, "unknown"))
    with pytest.raises(ValueError):
        parse_curve(encoded(b"garbage", PUMP_PROGRAM))


def test_pool_mint_and_virtual_reserves():
    mint = Pubkey.new_unique()
    raw = bytearray(261)
    raw[:8] = hashlib.sha256(b"account:Pool").digest()[:8]
    raw[43:75] = bytes(mint)
    raw[245:261] = (100).to_bytes(16, "little", signed=True)
    pool = parse_pool(encoded(raw, PUMP_SWAP_PROGRAM), str(mint))
    assert pool["virtual_quote_reserves"] == 100
    with pytest.raises(ValueError):
        parse_pool(encoded(raw, PUMP_SWAP_PROGRAM), str(Pubkey.new_unique()))

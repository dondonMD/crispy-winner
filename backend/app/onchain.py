"""Validated stable prefixes from official Pump IDLs, verified 2026-10-08.

Unknown layouts/program owners are rejected. Appended fields do not shift prefixes.
Never treat curve completion alone as a migrated pool.
"""

import base64
import hashlib
import struct
from solders.pubkey import Pubkey
from backend.app.providers import PUMP_PROGRAM

PUMP_SWAP_PROGRAM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"


def binary_account(account, program, name, minimum):
    if not account or account.get("owner") != program:
        raise ValueError("Unexpected account program")
    data = account.get("data")
    if not isinstance(data, list) or len(data) != 2 or data[1] != "base64":
        raise ValueError("Unsupported account encoding")
    raw = base64.b64decode(data[0], validate=True)
    if len(raw) < minimum or raw[:8] != hashlib.sha256(f"account:{name}".encode()).digest()[:8]:
        raise ValueError("Unknown account layout/discriminator")
    return raw


def parse_pool(account, mint):
    raw = binary_account(account, PUMP_SWAP_PROGRAM, "Pool", 243)

    def key(offset):
        return str(Pubkey.from_bytes(raw[offset : offset + 32]))

    if key(43) != mint:
        raise ValueError("Pool base mint mismatch")
    return {
        "base_mint": key(43),
        "quote_mint": key(75),
        "base_account": key(139),
        "quote_account": key(171),
        "creator_fee_recipient": key(211),
        "virtual_quote_reserves": int.from_bytes(raw[245:261], "little", signed=True)
        if len(raw) >= 261
        else 0,
    }


def parse_curve(account):
    raw = binary_account(account, PUMP_PROGRAM, "BondingCurve", 49)
    virtual_token, virtual_quote, real_token, real_quote, supply = struct.unpack_from("<QQQQQ", raw, 8)
    complete = raw[48]
    if complete not in [0, 1] or not virtual_token or not supply:
        raise ValueError("Invalid curve values")
    return {
        "virtual_token_reserves": virtual_token,
        "virtual_quote_reserves": virtual_quote,
        "real_token_reserves": real_token,
        "real_quote_reserves": real_quote,
        "token_total_supply": supply,
        "complete": bool(complete),
        "quote_mint": str(Pubkey.from_bytes(raw[83:115]))
        if len(raw) >= 115
        else ("So11111111111111111111111111111111111111112" if len(raw) <= 83 else None),
    }


def parse_global(account):
    raw = binary_account(account, PUMP_PROGRAM, "Global", 105)
    virtual_token, virtual_quote, real_token, supply = struct.unpack_from("<QQQQ", raw, 73)
    if not real_token or virtual_token < real_token or not supply:
        raise ValueError("Invalid global reserves")
    return {
        "initial_virtual_token_reserves": virtual_token,
        "initial_virtual_quote_reserves": virtual_quote,
        "initial_real_token_reserves": real_token,
        "token_total_supply": supply,
    }


def curve_progress(curve, global_config):
    # Only apply current global baseline when curve supply and invariant offset match.
    if (
        curve["token_total_supply"] != global_config["token_total_supply"]
        or curve["virtual_token_reserves"] - curve["real_token_reserves"]
        != global_config["initial_virtual_token_reserves"] - global_config["initial_real_token_reserves"]
    ):
        return None
    fraction = 1 - curve["real_token_reserves"] / global_config["initial_real_token_reserves"]
    return round(max(0, min(100, fraction * 100)), 2)

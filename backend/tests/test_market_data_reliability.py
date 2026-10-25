"""Isolated market-data identity checks. No live RPC, engine, cohort or trades."""

import base64
import hashlib

import pytest
from solders.pubkey import Pubkey

from backend.app.onchain import PUMP_SWAP_PROGRAM, parse_pool

MINT = str(Pubkey.new_unique())
POOL = str(Pubkey.new_unique())
WSOL = "So11111111111111111111111111111111111111112"


def pool_account(default_offset=None, quote=WSOL):
    raw = bytearray(243)
    raw[:8] = hashlib.sha256(b"account:Pool").digest()[:8]
    for offset, value in ((43, MINT), (75, quote), (139, str(Pubkey.new_unique())),
                          (171, str(Pubkey.new_unique()))):
        raw[offset:offset + 32] = bytes(Pubkey.from_string(value))
    if default_offset is not None:
        raw[default_offset:default_offset + 32] = bytes(Pubkey.default())
    return {"owner": PUMP_SWAP_PROGRAM, "data": [base64.b64encode(raw).decode(), "base64"]}


@pytest.mark.parametrize("offset", [43, 75, 139, 171])
def test_default_pool_identity_never_verifies(offset):
    mint = str(Pubkey.default()) if offset == 43 else MINT
    with pytest.raises(ValueError):
        parse_pool(pool_account(offset), mint)


def test_unknown_nondefault_quote_stays_identity_only_and_optional_creator_may_be_default():
    quote = str(Pubkey.new_unique())
    parsed = parse_pool(pool_account(quote=quote), MINT)
    assert parsed["base_mint"] == MINT and parsed["quote_mint"] == quote
    assert parsed["creator_fee_recipient"] == str(Pubkey.default())
    # Identity verification must not invent supported units or reject all unfamiliar quotes.
    from backend.app.pumpswap import QUOTES
    assert quote not in QUOTES


@pytest.mark.parametrize("offset", [43, 75, 139, 171])
async def test_malformed_pool_cannot_enter_security_verified_registry(offset):
    from backend.app.providers import SolanaProvider, TOKEN_PROGRAM

    rpc = SolanaProvider()
    calls = []

    async def fixture_rpc(method, params, **kwargs):
        calls.append(method)
        if method == "getAccountInfo":
            if params[0] == POOL:
                return {"value": pool_account(offset)}
            if params[0] == MINT:
                return {"value": {"owner": TOKEN_PROGRAM, "data": {"parsed": {
                    "type": "mint", "info": {"mintAuthority": None, "freezeAuthority": None}}}}}
            return {"value": None}  # Missing curve stays unavailable, never guessed.
        if method == "getTokenSupply":
            return {"value": {"amount": "1000"}}
        assert method == "getTokenLargestAccounts"
        return {"value": []}

    rpc.rpc = fixture_rpc
    try:
        report = await rpc.inspect(MINT, known_accounts={POOL})
        assert report["verified_pools"] == []
        assert report["bonding_curve"] is None
        assert calls.count("getAccountInfo") == 3
    finally:
        await rpc.close()

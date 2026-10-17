"""Synthetic compiled transactions: no recorded transactions, wallets or endpoints."""
import copy
import time

import httpx
import pytest
from solders.pubkey import Pubkey

from backend.app.truncation import (
    CLASSIFICATIONS, EVENT_AUTHORITY, EVENT_CPI, EVENTS, INSTRUCTIONS, PUMP_PROGRAM,
    TRADE_NAMES, decode_base58, transaction_impact,
)
from backend.tests.test_onchain_trades import payload, wire
from backend.tests.test_trade_gap_scoping import tracked_engine as tracked_engine


def b58(raw):
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = int.from_bytes(raw, "big")
    result = ""
    while number:
        number, digit = divmod(number, 58)
        result = alphabet[digit] + result
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + result


def transaction(mints=(), name="buy", inner=False, loaded=False):
    notification = payload(wire())
    signature = notification["params"]["result"]["value"]["signature"]
    definition = next(i for i in INSTRUCTIONS.values() if i["name"] == name)
    keys = [PUMP_PROGRAM] + [str(Pubkey.new_unique()) for _ in definition["accounts"]]
    names = [a["name"] for a in definition["accounts"]]
    position = names.index("mint" if "mint" in names else "base_mint")
    instructions = []
    for mint in mints or [str(Pubkey.new_unique())]:
        keys.append(mint)
        accounts = list(range(1, len(names) + 1))
        accounts[position] = len(keys) - 1
        instructions.append({"programIdIndex": 0, "accounts": accounts,
                             "data": b58(bytes(definition["discriminator"]) + bytes(18))})
    meta = {"err": None, "innerInstructions": [], "loadedAddresses": {"writable": [], "readonly": []},
            "logMessages": ["Log truncated"]}  # Never consulted by the classifier.
    message = {"accountKeys": keys, "instructions": instructions}
    if loaded:
        meta["loadedAddresses"]["writable"] = [keys.pop()]
        message["addressTableLookups"] = [{"accountKey": str(Pubkey.new_unique()),
                                          "writableIndexes": [7], "readonlyIndexes": []}]
    if inner:
        message["instructions"] = [{"programIdIndex": 1, "accounts": [], "data": ""}]
        meta["innerInstructions"] = [{"index": 0, "instructions": instructions}]
    return {"slot": 123, "version": 0 if loaded else "legacy", "meta": meta,
            "transaction": {"signatures": [signature], "message": message}}, signature


def impact(tx, signature, mints):
    return transaction_impact(tx, signature, 123, lambda mint: mint in mints)


@pytest.mark.parametrize("name", sorted(TRADE_NAMES))
@pytest.mark.parametrize("inner,loaded", [(False, False), (True, False), (False, True), (True, True)])
def test_canonical_trade_mint_layout_outer_inner_and_v0(name, inner, loaded):
    mint = str(Pubkey.new_unique())
    tx, sig = transaction([mint], name, inner, loaded)
    assert impact(tx, sig, {mint}) == ("TRACKED_AFFECTED", {mint})
    assert impact(tx, sig, set()) == ("UNTRACKED_CONFIRMED", set())


def test_multiple_tracked_mints_and_no_log_dependency():
    mints = {str(Pubkey.new_unique()), str(Pubkey.new_unique())}
    tx, sig = transaction(mints)
    del tx["meta"]["logMessages"]
    assert impact(tx, sig, mints) == ("TRACKED_AFFECTED", mints)


@pytest.mark.parametrize("mutation,expected", [
    (lambda tx: tx["meta"].update(err={"InstructionError": [0, "failed"]}), "TRANSACTION_FAILED"),
    (lambda tx: tx["meta"].update(innerInstructions=None), "MALFORMED"),
    (lambda tx: tx.update(version=2), "MALFORMED"),
    (lambda tx: tx.update(slot=124), "MALFORMED"),
    (lambda tx: tx["transaction"].update(signatures=["wrong"]), "MALFORMED"),
    (lambda tx: tx["transaction"]["message"]["instructions"][0].update(data="11111111"), "UNSUPPORTED_PUMP_TRADE"),
    (lambda tx: tx["transaction"]["message"]["instructions"][0].update(accounts=[]), "MALFORMED"),
    (lambda tx: tx["transaction"]["message"]["instructions"][0].update(programIdIndex=True), "MALFORMED"),
    (lambda tx: tx["transaction"]["message"]["instructions"][0].update(data="@"), "MALFORMED"),
])
def test_untrusted_transaction_fails_closed(mutation, expected):
    tx, sig = transaction()
    mutation(tx)
    assert impact(tx, sig, set()) == (expected, set())


def test_missing_loaded_addresses_fails_closed():
    tx, sig = transaction(loaded=True)
    tx["meta"]["loadedAddresses"]["writable"] = []
    assert impact(tx, sig, set())[0] == "MALFORMED"


def test_canonical_event_cpi_is_not_a_trade():
    tx, sig = transaction(inner=True)
    keys = tx["transaction"]["message"]["accountKeys"]
    keys.append(EVENT_AUTHORITY)
    instruction = {"programIdIndex": 0, "accounts": [len(keys) - 1],
                   "data": b58(EVENT_CPI + next(iter(EVENTS)) + bytes(32))}
    tx["meta"]["innerInstructions"][0]["instructions"].append(instruction)
    assert impact(tx, sig, set())[0] == "UNTRACKED_CONFIRMED"
    instruction["accounts"] = [1]
    assert impact(tx, sig, set())[0] == "UNSUPPORTED_PUMP_TRADE"


def truncated():
    notification = payload(wire(mint=str(Pubkey.new_unique())))
    notification["params"]["result"]["value"]["logs"].append("Log truncated")
    return notification


async def mock_rpc(engine, result, status=200):
    await engine.rpc.client.aclose()
    def handler(request):
        assert request.method == "POST"
        import json
        body = json.loads(request.content)
        assert body["method"] == "getTransaction"
        assert body["params"][1] == {"encoding": "json", "commitment": "confirmed", "maxSupportedTransactionVersion": 1}
        return httpx.Response(status, json={"jsonrpc": "2.0", "id": 1, "result": result})
    engine.rpc.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    engine.rpc.limiter.interval = 0


async def test_normal_notification_never_requests_recovery(tracked_engine):
    e = tracked_engine
    e.onchain.receive(payload(wire()))
    await e.recovery.step()
    assert not e.recovery.pending and e.rpc.health["requests"] == 0


async def test_duplicate_explicit_truncation_one_request_untracked_preserves_clean_start(tracked_engine):
    e = tracked_engine
    starts = {m: (t.trade_tracking_since, t.trade_gap) for m, t in e.tokens.items()}
    tx, _ = transaction()
    await mock_rpc(e, tx)
    n = truncated()
    e.onchain.receive(n)
    e.onchain.receive(copy.deepcopy(n))
    assert len(e.recovery.pending) == 1
    assert all(e.trade_status(t) == "PARTIAL" and t.features["180"]["trade_evidence"] == "PARTIAL" for t in e.tokens.values())
    assert all(t.features["180"]["coverage_state"] == "PENDING RECOVERY" for t in e.tokens.values())
    assert e.trade_continuity["global_resets"] == 0
    await e.recovery.step()
    assert not e.recovery.pending
    assert all(e.trade_status(t) == "CURRENT" for t in e.tokens.values())
    assert starts == {m: (t.trade_tracking_since, t.trade_gap) for m, t in e.tokens.items()}
    e.onchain.receive(n)
    await e.recovery.step()
    h = e.recovery.snapshot()
    assert h["requests"] == h["successful_requests"] == 1
    assert h["deduplicated"] == 2
    assert h["classifications"]["UNTRACKED_CONFIRMED"] == 1
    assert e.rpc.health["requests"] == 1


@pytest.mark.parametrize("multiple", [False, True])
async def test_recovered_tracked_impact_local_only_at_observation_time(tracked_engine, multiple):
    e = tracked_engine
    mints = list(e.tokens)[:2 if multiple else 1]
    tx, _ = transaction(mints, inner=True, loaded=True)
    await mock_rpc(e, tx)
    e.onchain.receive(truncated())
    observed = next(iter(e.recovery.pending.values())).observed
    await e.recovery.step()
    for mint, token in e.tokens.items():
        assert token.trade_gap == (observed if mint in mints else 0)
        assert e.trade_status(token) == ("PARTIAL" if mint in mints else "CURRENT")
    assert e.trade_continuity["global_resets"] == 0
    assert e.recovery.snapshot()["token_local_gaps"] == len(mints)


async def test_pending_blocks_threshold_crossing_and_untracked_resolution_restores_window(tracked_engine):
    e = tracked_engine
    token = next(iter(e.tokens.values()))
    now = time.time()
    token.trade_tracking_since = now - 179
    e.onchain.receive(truncated())
    e.refresh_trade_continuity(token, now + 2)
    token.last_trade = now + 2
    assert e.trade_coverage_seconds(token, now + 2) >= 180
    assert e.trade_status(token, now + 2) != "CURRENT"
    tx, _ = transaction()
    await mock_rpc(e, tx)
    await e.recovery.step()
    e.refresh_trade_continuity(token, now + 2)
    assert e.trade_status(token, now + 2) == "CURRENT"


async def test_unavailable_exhausts_bounded_attempts_then_global(tracked_engine):
    e = tracked_engine
    await mock_rpc(e, None)
    e.onchain.receive(truncated())
    for _ in range(e.recovery.MAX_ATTEMPTS):
        next(iter(e.recovery.pending.values())).next_attempt = 0
        await e.recovery.step()
    assert not e.recovery.pending
    assert e.recovery.snapshot()["requests"] == 3
    assert e.recovery.snapshot()["classifications"]["TRANSACTION_UNAVAILABLE"] == 1
    assert e.trade_continuity["global_resets"] == 1
    assert all(e.trade_status(t) != "CURRENT" for t in e.tokens.values())


async def test_recovery_429_uses_shared_backoff_and_no_storm(tracked_engine):
    e = tracked_engine
    await mock_rpc(e, None, 429)
    e.onchain.receive(truncated())
    await e.recovery.step()
    for _ in range(10):
        await e.recovery.step()
    h = e.recovery.snapshot()
    assert h["requests"] == h["rate_limits"] == h["errors"] == 1
    assert e.rpc.health["backoff_level"] > 0
    assert len(e.recovery.pending) == 1


async def test_pending_expires_while_rpc_cooling_down(tracked_engine):
    e = tracked_engine
    e.onchain.receive(truncated())
    next(iter(e.recovery.pending.values())).observed -= e.recovery.MAX_AGE + 1
    e.rpc.health["next_eligible_rpc"] = time.time() + 100
    await e.recovery.step()
    assert not e.recovery.pending and e.rpc.health["requests"] == 0
    assert e.trade_continuity["global_resets"] == 1


def test_recovery_overflow_fails_global_and_state_is_bounded(tracked_engine):
    e = tracked_engine
    from solders.signature import Signature
    for _ in range(50):
        e.recovery.submit(str(Signature.new_unique()), 123, time.time())
    assert len(e.recovery.pending) == e.recovery.MAX_PENDING
    assert e.recovery.health["overflow"] == 50 - e.recovery.MAX_PENDING
    assert len(e.recovery.seen.seen) <= e.recovery.seen.maximum
    assert set(e.recovery.health["classifications"]) == set(CLASSIFICATIONS)
    assert e.trade_continuity["global_resets"] > 0


@pytest.mark.parametrize("balanced", [True, False])
async def test_truncation_framing_defers_global_reset_until_recovery(tracked_engine, balanced):
    e = tracked_engine
    n = truncated()
    if not balanced:
        del n["params"]["result"]["value"]["logs"][-2]
    e.onchain.receive(n)
    assert len(e.recovery.pending) == 1 and e.trade_continuity["global_resets"] == 0
    tx, _ = transaction()
    await mock_rpc(e, tx)
    await e.recovery.step()
    assert all(e.trade_status(t) == "CURRENT" for t in e.tokens.values())


def test_queue_age_metrics_are_bounded_and_do_not_change_freshness(monkeypatch):
    from backend.app.domain import MarketEvent, PriorityBuffer
    clock = [1000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    queue = PriorityBuffer(2)
    event = MarketEvent(mint="synthetic", ts=1000, kind="trade", side="buy", source="test", event_id="t")
    queue.put(event, 1)
    clock[0] += 21
    assert queue.snapshot()["oldest_trade_age"] == 21
    queue.drain(max_age=20)
    assert queue.snapshot()["trades_stale_while_queued"] == 1
    assert not queue.arrivals
    # Already stale on arrival is rejected by the engine but not blamed on queue residence.
    queue.put(event, 1)
    queue.drain(max_age=20)
    assert queue.stale_while_queued == 1
    for i in range(1000):
        queue.sample_depth(1100 + i)
    assert len(queue.depth_samples) == 300 and queue.peak_depth == 1


def test_base58_bounds_and_zero_prefix():
    for data in (bytes(8), bytes(range(255)), b"\0\0abc"):
        assert decode_base58(b58(data)) == data
    with pytest.raises(ValueError):
        decode_base58("x" * 16385)


@pytest.mark.parametrize("classification", ["UNSUPPORTED_PUMP_TRADE", "MALFORMED", "TRANSACTION_FAILED"])
async def test_unresolved_classifications_reset_all(tracked_engine, classification):
    e = tracked_engine
    tx, _ = transaction()
    if classification == "UNSUPPORTED_PUMP_TRADE":
        tx["transaction"]["message"]["instructions"][0]["data"] = "11111111"
    elif classification == "MALFORMED":
        tx["meta"]["innerInstructions"] = None
    else:
        tx["meta"]["err"] = {"InstructionError": [0, "failed"]}
    await mock_rpc(e, tx)
    e.onchain.receive(truncated())
    await e.recovery.step()
    assert e.recovery.snapshot()["classifications"][classification] == 1
    assert e.trade_continuity["global_resets"] == 1
    assert all(t.trade_gap > 0 and e.trade_status(t) != "CURRENT" for t in e.tokens.values())


async def test_transport_gap_during_pending_cannot_be_erased_by_untracked_resolution(tracked_engine):
    e = tracked_engine
    e.onchain.receive(truncated())
    e.onchain.global_gap("transport")
    gaps = {m: t.trade_gap for m, t in e.tokens.items()}
    tx, _ = transaction()
    await mock_rpc(e, tx)
    await e.recovery.step()
    assert gaps == {m: t.trade_gap for m, t in e.tokens.items()}
    assert all(e.trade_status(t) != "CURRENT" for t in e.tokens.values())


def test_official_mint_positions_and_unchanged_evidence_limits(tracked_engine):
    e = tracked_engine
    assert e.settings.max_data_age_seconds == 20
    for definition in INSTRUCTIONS.values():
        if definition["name"] in TRADE_NAMES:
            position = 1 if "_v2" in definition["name"] or "_v3" in definition["name"] else 2
            assert definition["accounts"][position]["name"] in ("mint", "base_mint")
    token = next(iter(e.tokens.values()))
    now = time.time()
    token.trade_tracking_since = now - 179.9
    e.refresh_trade_continuity(token, now)
    assert e.trade_status(token, now) != "CURRENT"
    token.trade_tracking_since = now - 180
    e.refresh_trade_continuity(token, now)
    assert e.trade_status(token, now) == "CURRENT"
    token.last_trade = now - 20.1
    assert e.trade_status(token, now) != "CURRENT"


@pytest.mark.parametrize("name", sorted(TRADE_NAMES))
@pytest.mark.parametrize("inner", [False, True])
def test_current_standard_v1_inline_instructions(name, inner):
    mint = str(Pubkey.new_unique())
    tx, sig = transaction([mint], name=name, inner=inner)
    tx["version"] = 1
    tx["transaction"]["message"]["transactionConfig"] = {
        "priorityFee": None, "computeUnitLimit": 300000,
        "loadedAccountsDataSizeLimit": 64000000, "heapSize": None}
    assert impact(tx, sig, {mint}) == ("TRACKED_AFFECTED", {mint})
    assert impact(tx, sig, set()) == ("UNTRACKED_CONFIRMED", set())
    tx["transaction"]["message"]["addressTableLookups"] = []
    assert impact(tx, sig, set())[0] == "MALFORMED"


@pytest.mark.parametrize("field,value", [("priorityFee", -1), ("computeUnitLimit", True),
    ("heapSize", 2**32), ("unknownFutureField", 1)])
def test_unknown_or_invalid_v1_config_fails_closed(field, value):
    tx, sig = transaction()
    tx["version"] = 1
    tx["transaction"]["message"]["transactionConfig"] = {
        "priorityFee": None, "computeUnitLimit": 300000,
        "loadedAccountsDataSizeLimit": 64000000, "heapSize": None, field: value}
    assert impact(tx, sig, set())[0] == "MALFORMED"


def test_v0_combines_loaded_writable_then_readonly_with_loaded_program_id():
    mint = str(Pubkey.new_unique())
    tx, sig = transaction([mint], loaded=True)
    message, meta = tx["transaction"]["message"], tx["meta"]
    original = message["accountKeys"] + [mint]
    message["accountKeys"] = message["accountKeys"][1:]
    meta["loadedAddresses"] = {"writable": [PUMP_PROGRAM], "readonly": [mint]}
    message["addressTableLookups"][0]["readonlyIndexes"] = [8]
    resolved = message["accountKeys"] + [PUMP_PROGRAM, mint]
    instruction = message["instructions"][0]
    instruction["programIdIndex"] = resolved.index(PUMP_PROGRAM)
    instruction["accounts"] = [resolved.index(original[i]) for i in instruction["accounts"]]
    assert impact(tx, sig, {mint}) == ("TRACKED_AFFECTED", {mint})


def test_canonical_but_unsupported_multi_hop_fails_closed():
    tx, sig = transaction()
    definition = next(i for i in INSTRUCTIONS.values() if i["name"] == "multi_hop_curve_swap")
    tx["transaction"]["message"]["instructions"][0]["data"] = b58(bytes(definition["discriminator"]) + bytes(8))
    assert impact(tx, sig, set()) == ("UNSUPPORTED_PUMP_TRADE", set())


async def test_failed_truncated_notification_does_not_schedule_recovery(tracked_engine):
    e = tracked_engine
    n = truncated()
    n["params"]["result"]["value"]["err"] = {"InstructionError": [0, "failed"]}
    e.onchain.receive(n)
    await e.recovery.step()
    assert not e.recovery.pending and e.rpc.health["requests"] == 0
    assert all(e.trade_status(t) == "CURRENT" for t in e.tokens.values())

"""Canonical, synthetic identity-only routes; no executed amounts or live fixtures."""
import copy
import struct

import pytest
from solders.pubkey import Pubkey

from backend.app import pump_amm_recovery as route
from backend.app.truncation import INSTRUCTIONS, transaction_impact
from backend.tests.test_truncation_recovery import b58, transaction, mock_rpc, truncated
from backend.tests.test_trade_gap_scoping import tracked_engine as tracked_engine

PUMP = route.PUMP
CALL = next(i for i in INSTRUCTIONS.values() if i["name"] == "multi_hop_curve_swap")
WSOL = "So11111111111111111111111111111111111111112"


def unique():
    return str(Pubkey.new_unique())


def curve(mint):
    return str(Pubkey.find_program_address([b"bonding-curve", bytes(Pubkey.from_string(mint))],
                                         Pubkey.from_string(PUMP))[0])


def build(hop_routes, version="legacy", inner_route=False, heights=True):
    tx, signature = transaction()
    message = tx["transaction"]["message"]
    message.update(accountKeys=[], instructions=[])
    keys = message["accountKeys"]
    tx["meta"]["innerInstructions"] = []
    def key(value):
        if value not in keys:
            keys.append(value)
        return keys.index(value)
    for hops in hop_routes:
        fixed = {d["name"]: d.get("address", unique()) for d in route.SCHEMA["instruction"]["accounts"]}
        fixed["global_config"] = route.GLOBAL_CONFIG
        fixed["pump_global"] = str(Pubkey.find_program_address([b"global"], Pubkey.from_string(PUMP))[0])
        fixed["pump_fee_config"] = "8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt"
        fixed["pump_event_authority"] = str(Pubkey.find_program_address([b"__event_authority"], Pubkey.from_string(PUMP))[0])
        accounts = [key(fixed[name]) for name in route.ROUTE_NAMES]
        quote = WSOL
        for base, is_curve in hops:
            accounts.extend(key(value) for value in (base, quote, curve(base) if is_curve else unique(), unique(), unique()))
            quote = base
        instruction = {"programIdIndex": key(route.PROGRAM), "accounts": accounts,
                       "data": b58(route.DISCRIMINATOR + bytes(16))}
        call_values = {a["name"]: unique() for a in CALL["accounts"]}
        call_values["global"] = fixed["pump_global"]
        call_values.update(fee_config=fixed["pump_fee_config"], pump_amm_global_config=fixed["global_config"],
                           user=fixed["user"], event_authority=fixed["pump_event_authority"], program=PUMP)
        call = {"programIdIndex": key(PUMP), "accounts": [key(call_values[a["name"]]) for a in CALL["accounts"]],
                "data": b58(bytes(CALL["discriminator"]) + bytes(12))}
        root = len(message["instructions"])
        if inner_route:
            message["instructions"].append({"programIdIndex": key(unique()), "accounts": [], "data": ""})
            instruction["stackHeight"] = 2 if heights else None
            call["stackHeight"] = 3 if heights else None
            inner = [instruction, call]
        else:
            message["instructions"].append(instruction)
            call["stackHeight"] = 2 if heights else None
            inner = [call]
        tx["meta"]["innerInstructions"].append({"index": root, "instructions": inner})
    tx["version"] = version
    if version == 1:
        message["transactionConfig"] = {"priorityFee": None, "computeUnitLimit": 300000,
                                          "loadedAccountsDataSizeLimit": 64000000, "heapSize": None}
    if version == 0:
        original = list(keys)
        static, writable, readonly = original[:3], original[3::2], original[4::2]
        resolved = static + writable + readonly
        message["accountKeys"] = static
        tx["meta"]["loadedAddresses"] = {"writable": writable, "readonly": readonly}
        message["addressTableLookups"] = [{"accountKey": unique(), "writableIndexes": list(range(len(writable))),
                                          "readonlyIndexes": list(range(len(writable), len(writable) + len(readonly)))}]
        for i in message["instructions"] + [i for g in tx["meta"]["innerInstructions"] for i in g["instructions"]]:
            i["programIdIndex"] = resolved.index(original[i["programIdIndex"]])
            i["accounts"] = [resolved.index(original[index]) for index in i["accounts"]]
    return tx, signature


def impact(tx, sig, tracked):
    metrics = route.diagnostics()
    classification, affected = transaction_impact(tx, sig, 123, tracked.__contains__, metrics)
    return classification, affected, metrics


@pytest.mark.parametrize("version", ["legacy", 0, 1])
@pytest.mark.parametrize("inner", [False, True])
@pytest.mark.parametrize("kinds,tracked_positions", [([False, True], [0, 1]), ([True, True], [1]),
    ([True, True], [0, 1]), ([True, True], []), ([False, False], [0, 1])])
def test_canonical_routes_exact_curve_impact(version, inner, kinds, tracked_positions):
    mints = [unique(), unique()]
    tx, sig = build([list(zip(mints, kinds))], version, inner)
    tracked = {mints[i] for i in tracked_positions}
    expected = {mint for mint, is_curve in zip(mints, kinds) if is_curve and mint in tracked}
    classification, affected, metrics = impact(tx, sig, tracked)
    assert classification == ("TRACKED_AFFECTED" if expected else "UNTRACKED_CONFIRMED")
    assert affected == expected
    assert metrics["multi_hop_curve_swap_observed"] == metrics["multi_hop_routes_resolved"] == 1
    assert metrics["multi_hop_tracked_affected" if expected else "multi_hop_untracked_confirmed"] == 1
    assert sum(metrics["unsupported_instruction_counts"].values()) == 0


def test_schema_exact_pinned_provenance_and_layout():
    assert route.SCHEMA["source"]["commit"] == "639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22"
    assert route.SCHEMA["source"]["path"] == "idl/pump_amm.json"
    assert route.SCHEMA["remaining_accounts_source"]["path"] == "docs/instructions/MULTI_HOP_SWAP.md"
    assert list(route.DISCRIMINATOR) == [43, 100, 73, 19, 233, 246, 111, 148]
    assert route.FIXED_COUNT == 16 and route.GROUP_SIZE == 5
    assert route.SCHEMA["hop_accounts"] == ["base_mint", "quote_mint", "venue", "base_vault", "quote_vault"]


@pytest.mark.parametrize("heights", [False, True])
def test_outer_parent_group_proves_multiple_calls_without_guessing(heights):
    mint = unique()
    tx, sig = build([[(mint, True)]], heights=heights)
    calls = tx["meta"]["innerInstructions"][0]["instructions"]
    calls.append(copy.deepcopy(calls[0]))
    classification, affected, metrics = impact(tx, sig, {mint})
    assert (classification, affected) == ("TRACKED_AFFECTED", {mint})
    assert metrics["multi_hop_curve_swap_observed"] == 2 and metrics["multi_hop_routes_resolved"] == 1


@pytest.mark.parametrize("inner", [False, True])
def test_multiple_routes_proven_by_separate_outer_groups(inner):
    mints = [unique(), unique()]
    tx, sig = build([[(mints[0], True)], [(mints[1], True)]], inner_route=inner)
    classification, affected, metrics = impact(tx, sig, set(mints))
    assert (classification, affected) == ("TRACKED_AFFECTED", set(mints))
    assert metrics["multi_hop_routes_resolved"] == 2


@pytest.mark.parametrize("heights", [False, True])
def test_multiple_inner_routes_in_one_group_need_proven_ancestry(heights):
    mints = [unique(), unique()]
    tx, sig = build([[(mints[0], True)], [(mints[1], True)]], inner_route=True, heights=heights)
    tx["transaction"]["message"]["instructions"] = tx["transaction"]["message"]["instructions"][:1]
    groups = tx["meta"]["innerInstructions"]
    groups[0]["instructions"].extend(groups.pop()["instructions"])
    classification, affected, metrics = impact(tx, sig, set(mints))
    assert classification == ("TRACKED_AFFECTED" if heights else "UNSUPPORTED_PUMP_TRADE")
    assert affected == (set(mints) if heights else set())
    assert metrics["multi_hop_ambiguous"] == (0 if heights else 2)


def test_sole_inner_route_without_ancestry_stays_unsupported():
    mint = unique()
    tx, sig = build([[(mint, True)]], inner_route=True, heights=False)
    classification, affected, metrics = impact(tx, sig, {mint})
    assert classification == "UNSUPPORTED_PUMP_TRADE" and not affected
    assert metrics["multi_hop_ambiguous"] == 1


def test_sibling_route_is_not_parent_even_in_same_group():
    mint = unique()
    tx, sig = build([[(mint, True)]], inner_route=True)
    tx["meta"]["innerInstructions"][0]["instructions"][1]["stackHeight"] = 2
    classification, affected, metrics = impact(tx, sig, {mint})
    assert classification == "UNSUPPORTED_PUMP_TRADE" and not affected
    assert metrics["multi_hop_unresolved"] == 1 and metrics["multi_hop_ambiguous"] == 0


def test_route_in_other_outer_group_cannot_resolve_call():
    mint = unique()
    tx, sig = build([[(mint, True)]])
    tx["transaction"]["message"]["instructions"].append({"programIdIndex": 0, "accounts": [], "data": ""})
    tx["meta"]["innerInstructions"][0]["index"] = 1
    assert impact(tx, sig, {mint})[:2] == ("UNSUPPORTED_PUMP_TRADE", set())


def test_missing_route_preserves_unsupported_subtype():
    tx, sig = build([[(unique(), True)]])
    tx["transaction"]["message"]["instructions"][0]["programIdIndex"] = 0
    result = impact(tx, sig, set())
    assert result[0] == "UNSUPPORTED_PUMP_TRADE"
    assert result[2]["unsupported_instruction_counts"]["multi_hop_curve_swap"] == 1


@pytest.mark.parametrize("change", ["short_fixed", "zero_hops", "short_group", "extra_group_account", "invalid_pubkey",
    "wrong_program", "wrong_global_config", "short_data", "trailing_data", "short_call", "bad_byte_vector"])
def test_malformed_route_or_call_never_clears(change):
    mint = unique()
    tx, sig = build([[(mint, True)]])
    instruction = tx["transaction"]["message"]["instructions"][0]
    call = tx["meta"]["innerInstructions"][0]["instructions"][0]
    keys = tx["transaction"]["message"]["accountKeys"]
    if change == "short_fixed":
        instruction["accounts"] = instruction["accounts"][:15]
    elif change == "zero_hops":
        instruction["accounts"] = instruction["accounts"][:16]
    elif change == "short_group":
        instruction["accounts"].pop()
    elif change == "extra_group_account":
        instruction["accounts"].append(instruction["accounts"][-1])
    elif change == "invalid_pubkey":
        keys[instruction["accounts"][16]] = "not-a-pubkey"
    elif change == "wrong_program":
        instruction["accounts"][12] = instruction["accounts"][0]
    elif change == "wrong_global_config":
        instruction["accounts"][3] = instruction["accounts"][0]
    elif change == "short_data":
        instruction["data"] = b58(route.DISCRIMINATOR)
    elif change == "trailing_data":
        instruction["data"] = b58(route.DISCRIMINATOR + bytes(17))
    elif change == "short_call":
        call["accounts"] = call["accounts"][:2]
    else:
        call["data"] = b58(bytes(CALL["discriminator"]) + bytes(8) + struct.pack("<I", 50))
    assert impact(tx, sig, {mint})[:2] == ("MALFORMED", set())


def test_route_and_call_binding_mismatch_fails_closed():
    mint = unique()
    tx, sig = build([[(mint, True)]])
    call = tx["meta"]["innerInstructions"][0]["instructions"][0]
    call["accounts"][3] = call["accounts"][4]  # user cannot be borrowed from another call.
    classification, affected, metrics = impact(tx, sig, {mint})
    assert classification == "UNSUPPORTED_PUMP_TRADE" and not affected
    assert metrics["multi_hop_unresolved"] == 1


def test_unrelated_unknown_pump_instruction_still_forces_global_classification():
    mint = unique()
    tx, sig = build([[(mint, True)]])
    inner = tx["meta"]["innerInstructions"][0]["instructions"]
    unknown = copy.deepcopy(inner[0])
    unknown["data"] = b58(bytes(8))
    inner.append(unknown)
    classification, affected, metrics = impact(tx, sig, {mint})
    assert classification == "UNSUPPORTED_PUMP_TRADE" and not affected
    assert metrics["multi_hop_routes_resolved"] == 1
    assert metrics["unsupported_instruction_counts"] == {"multi_hop_curve_swap": 0, "unknown_discriminator": 1, "other": 0}


def test_unsupported_diagnostics_have_fixed_cardinality():
    tx, sig = transaction()
    metrics = route.diagnostics()
    instruction = tx["transaction"]["message"]["instructions"][0]
    for i in range(1000):
        instruction["data"] = b58(i.to_bytes(8, "little"))
        assert transaction_impact(tx, sig, 123, lambda mint: False, metrics)[0] == "UNSUPPORTED_PUMP_TRADE"
    assert len(metrics["unsupported_instruction_counts"]) == 3
    assert metrics["unsupported_instruction_counts"]["unknown_discriminator"] == 1000
    assert len(metrics) == 7


@pytest.mark.parametrize("is_curve", [False, True])
async def test_engine_recovery_is_identity_only_and_locally_scoped(tracked_engine, is_curve):
    e = tracked_engine
    mint = next(iter(e.tokens))
    other = next(m for m in e.tokens if m != mint)
    tx, _ = build([[(mint, is_curve)]], version=1, inner_route=True)
    before = {m: list(t.events) for m, t in e.tokens.items()}
    await mock_rpc(e, tx)
    e.onchain.receive(truncated())
    await e.recovery.step()
    assert e.trade_status(e.tokens[mint]) == ("PARTIAL" if is_curve else "CURRENT")
    assert e.trade_status(e.tokens[other]) == "CURRENT"
    assert e.trade_continuity["global_resets"] == 0
    assert before == {m: list(t.events) for m, t in e.tokens.items()}
    assert not e.queue.heap and e.trade_observations == {"buy": 0, "sell": 0}
    assert e.rpc.truncation_metrics["requests"] == e.rpc.health["requests"] == 1


def test_transport_timing_diagnostics_are_bounded():
    from backend.app.discovery import OnchainPumpDiscovery
    p = OnchainPumpDiscovery(lambda event: False)
    for _ in range(100):
        p.record_transport_transition("CONNECTED")
        p.record_transport_transition("DISCONNECTED")
    assert len(p.health["transport_transitions"]) == 32
    assert {i["state"] for i in p.health["transport_transitions"]} == {"CONNECTED", "DISCONNECTED"}


def test_impossible_cpi_height_jump_cannot_clear_recovery():
    tx, sig = build([[(unique(), True)]])
    tx["meta"]["innerInstructions"][0]["instructions"][0]["stackHeight"] = 3
    assert impact(tx, sig, set())[:2] == ("MALFORMED", set())

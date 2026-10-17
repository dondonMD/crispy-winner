"""Identity-only PumpSwap route inspection for explicit Pump log truncations."""
from dataclasses import dataclass
import json
from pathlib import Path

from solders.pubkey import Pubkey

SCHEMA = json.loads(Path(__file__).with_suffix(".json").read_text())
PROGRAM = SCHEMA["program"]
DISCRIMINATOR = bytes(SCHEMA["instruction"]["discriminator"])
FIXED_COUNT = SCHEMA["fixed_account_count"]
GROUP_SIZE = len(SCHEMA["hop_accounts"])
PUMP = SCHEMA["curve_pda_program"]
ROUTE_NAMES = [a["name"] for a in SCHEMA["instruction"]["accounts"]]
GLOBAL_CONFIG = str(Pubkey.find_program_address([b"global_config"], Pubkey.from_string(PROGRAM))[0])


def diagnostics():
    # Fixed cardinality: never key dictionaries by untrusted data/discriminator.
    return {"unsupported_instruction_counts": dict.fromkeys(
        ("multi_hop_curve_swap", "unknown_discriminator", "other"), 0),
        **dict.fromkeys(("multi_hop_curve_swap_observed", "multi_hop_routes_resolved",
                        "multi_hop_untracked_confirmed", "multi_hop_tracked_affected",
                        "multi_hop_unresolved", "multi_hop_ambiguous"), 0)}


def count(metrics, name, amount=1, subtype=None):
    if metrics is not None:
        if subtype is None:
            metrics[name] += amount
        else:
            metrics[name][subtype] += amount


@dataclass(slots=True)
class Invocation:
    instruction: dict
    root: int
    parents: tuple[int, ...] | None
    inner: bool


def invocations(outer, groups):
    """Keep RPC outer-index grouping; use stackHeight only when ancestry is proven."""
    result = [Invocation(i, index, (), False) for index, i in enumerate(outer)]
    for group in groups:
        root = group["index"]
        stack = [root]
        for instruction in group["instructions"]:
            height = instruction.get("stackHeight")
            if height is not None and (type(height) is not int or not 2 <= height <= 64):
                raise ValueError("invalid CPI stack height")
            if height == 2:
                stack = [root]
            if height is not None and stack and height > len(stack) + 1:
                raise ValueError("missing CPI stack frame")
            if height is None or height > len(stack) + 1:
                parents = None
                stack = []
            else:
                stack = stack[:height - 1]
                parents = tuple(stack) if len(stack) == height - 1 else None
            identity = len(result)
            result.append(Invocation(instruction, root, parents, True))
            if parents is not None:
                stack.append(identity)
    return result


def route_mints(instruction, keys, data):
    accounts = instruction["accounts"]
    remaining = len(accounts) - FIXED_COUNT
    if remaining <= 0 or remaining % GROUP_SIZE or len(data) != 24:
        raise ValueError("invalid canonical route shape")
    fixed = {name: keys[accounts[index]] for index, name in enumerate(ROUTE_NAMES)}
    for index, definition in enumerate(SCHEMA["instruction"]["accounts"]):
        if definition.get("address") and keys[accounts[index]] != definition["address"]:
            raise ValueError("route program account mismatch")
    if fixed["global_config"] != GLOBAL_CONFIG:
        raise ValueError("route global config mismatch")
    mints = set()
    for start in range(FIXED_COUNT, len(accounts), GROUP_SIZE):
        base, quote, venue, base_vault, quote_vault = (keys[index] for index in accounts[start:start + GROUP_SIZE])
        for key in (base, quote, venue, base_vault, quote_vault):
            Pubkey.from_string(key)
        if base == str(Pubkey.default()) or quote == str(Pubkey.default()):
            raise ValueError("invalid route mint")
        expected = str(Pubkey.find_program_address(
            [b"bonding-curve", bytes(Pubkey.from_string(base))], Pubkey.from_string(PUMP))[0])
        if venue == expected:
            mints.add(base)
    return fixed, mints


def resolve(calls, routes, contexts, keys, tracked, pump_definition, metrics):
    """Associate every Pump curve call, or leave the whole transaction unsupported.

    Route IDs/context parent IDs refer to the same bounded invocation array.
    Outer-index grouping proves ancestry of a sole outer route even when older
    metadata lacks stackHeight. Inner routes require recorded ancestry.
    """
    affected: set[str] = set()
    resolved_routes = set()
    unsupported = False
    names = [a["name"] for a in pump_definition["accounts"]]
    for identity, data in calls:
        context = contexts[identity]
        same_group = [i for i in routes if contexts[i].root == context.root]
        ancestors = [] if context.parents is None else [i for i in context.parents if i in routes]
        parent = ancestors[-1] if ancestors else None
        # A sole outer route contains every CPI in its own metadata group. Do not
        # use this fallback if any inner route could be a different parent.
        if context.inner and parent is None and same_group == [context.root]:
            parent = context.root
        if not context.inner or parent is None:
            count(metrics, "unsupported_instruction_counts", subtype="multi_hop_curve_swap")
            count(metrics, "multi_hop_unresolved")
            if context.parents is None and (len(same_group) > 1 or any(contexts[i].inner for i in same_group)):
                count(metrics, "multi_hop_ambiguous")
            unsupported = True
            continue
        instruction = context.instruction
        if len(instruction["accounts"]) < len(names) or len(data) < 20:
            raise ValueError("invalid curve-call shape")
        if int.from_bytes(data[16:20], "little") != len(data) - 20:
            raise ValueError("invalid curve-call byte vector")
        accounts = {name: keys[instruction["accounts"][index]] for index, name in enumerate(names)}
        fixed, mints = routes[parent]
        # Bind fields shared by the two canonical IDLs. No source/vault offsets
        # or amounts are inferred from the curve instruction's remaining data.
        bindings = {"pump_amm_global_config": "global_config", "user": "user",
                    "global": "pump_global", "fee_config": "pump_fee_config",
                    "event_authority": "pump_event_authority", "program": "pump_program"}
        if any(accounts[call_name] != fixed[route_name] for call_name, route_name in bindings.items()):
            count(metrics, "unsupported_instruction_counts", subtype="multi_hop_curve_swap")
            count(metrics, "multi_hop_unresolved")
            unsupported = True
            continue
        resolved_routes.add(parent)
        affected.update(mint for mint in mints if tracked(mint))
    count(metrics, "multi_hop_routes_resolved", len(resolved_routes))
    return unsupported, affected

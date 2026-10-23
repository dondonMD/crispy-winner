"""Read-only research quotes, ported from pinned official SDK math. No execution APIs."""

import base64
from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
import hashlib
import json
from pathlib import Path
import time

from solders.pubkey import Pubkey

from backend.app.providers import PUMP_PROGRAM, TOKEN_PROGRAM, TOKEN_2022

SOURCES_PATH = Path(__file__).with_name("early_edge_sources.json")
SOURCES = json.loads(SOURCES_PATH.read_text())
ZERO = str(Pubkey.default())
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
QUOTES = {WSOL: ("SOL", 9), USDC: ("USDC", 6)}
AMM = SOURCES["programs"]["pump_amm"]
FEE_PROGRAM = SOURCES["programs"]["pump_fees"]
SUPPLY = 10**15


class QuoteUnavailable(ValueError):
    def __init__(self, reason="UNAVAILABLE_QUOTE"):
        super().__init__(reason)
        self.reason = reason


def ceildiv(a, b):
    if type(a) is not int or type(b) is not int or a < 0 or b <= 0:
        raise QuoteUnavailable()
    return (a + b - 1) // b


def fee(amount, bps):
    return ceildiv(amount * bps, 10000)


def tier(config, quote, cap):
    if quote not in QUOTES:
        raise QuoteUnavailable("UNAVAILABLE_UNITS")
    tiers = config["stable_fee_tiers"] or config["fee_tiers"] if quote == USDC else config["fee_tiers"]
    if not tiers or len(tiers) > 128:
        raise QuoteUnavailable()
    thresholds = [t["market_cap_lamports_threshold"] for t in tiers]
    if thresholds != sorted(set(thresholds)):
        raise QuoteUnavailable()
    selected = tiers[0]
    for t in tiers:
        if t["market_cap_lamports_threshold"] <= cap:
            selected = t
    return dict(selected["fees"])


def rates(state, side):
    base, quote = state["base_reserve"], state["effective_quote"]
    if min(base, quote, state["mint_supply"]) <= 0:
        raise QuoteUnavailable()
    supply = state["mint_supply"]
    if state["venue"] == "PUMP" and side == "sell" and not state["is_mayhem_mode"]:
        supply = SUPPLY  # Pump SDK getFee() differs deliberately from its buy budget helper.
    if state["venue"] == "PUMPSWAP" and state["is_mayhem_mode"]:
        supply = SUPPLY
    result = tier(state["fee_config"], state["quote_mint"], quote * supply // base)
    if state["venue"] == "PUMPSWAP" and not state["canonical_pool"]:
        result = dict(state["fee_config"]["flat_fees"])
    if state["creator_fee_configurable"] and state["creator_fee_bps"]:
        result["creator_fee_bps"] = state["creator_fee_bps"]
    if not state["has_creator"]:
        result["creator_fee_bps"] = 0
    if any(type(v) is not int or not 0 <= v <= 10000 for v in result.values()):
        raise QuoteUnavailable()
    return result


def pump_buy(state, budget):
    if state["venue"] != "PUMP" or state["complete"] or type(budget) is not int or budget <= 1:
        raise QuoteUnavailable()
    r = rates(state, "buy")
    amount = (budget - 1) * 10000 // (10000 + r["protocol_fee_bps"] + r["creator_fee_bps"])
    quantity = min(
        amount * state["base_reserve"] // (state["effective_quote"] + amount), state["real_token_reserves"]
    )
    if quantity <= 0 or quantity >= state["base_reserve"]:
        raise QuoteUnavailable()
    # SDK getBuySolAmountFromTokenAmount + getFee: actual exact-out cost for that quoted quantity.
    principal = quantity * state["effective_quote"] // (state["base_reserve"] - quantity) + 1
    sell_rates = rates(state, "sell")
    fees = fee(principal, sell_rates["protocol_fee_bps"]) + fee(principal, sell_rates["creator_fee_bps"])
    if principal + fees > budget:
        raise QuoteUnavailable()  # Never claim a fill exceeding the research cash budget.
    return {
        "quantity": quantity,
        "quote_raw": principal + fees,
        "protocol_fees_raw": fees,
        "principal_raw": principal,
        "fee_decomposition_raw": dict(
            protocol=fee(principal, sell_rates["protocol_fee_bps"]),
            creator=fee(principal, sell_rates["creator_fee_bps"]),
            lp=0,
        ),
    }


def sell(state, quantity):
    if type(quantity) is not int or quantity <= 0 or state["complete"]:
        raise QuoteUnavailable()
    r = rates(state, "sell")
    gross = quantity * state["effective_quote"] // (state["base_reserve"] + quantity)
    lp = fee(gross, r["lp_fee_bps"]) if state["venue"] == "PUMPSWAP" else 0
    other = fee(gross, r["protocol_fee_bps"]) + fee(gross, r["creator_fee_bps"])
    if state["venue"] == "PUMPSWAP" and gross - lp > state["real_quote_reserves"]:
        raise QuoteUnavailable()  # Insufficient real reserves is not proof of a permanently zero exit.
    if state["venue"] == "PUMP" and gross > state["real_quote_reserves"]:
        raise QuoteUnavailable()
    if gross - lp - other <= 0:
        raise QuoteUnavailable()
    return {
        "gross_quote_raw": gross,
        "quote_raw": gross - lp - other,
        "protocol_fees_raw": lp + other,
        "economic_zero": gross - lp - other == 0,
        "fee_decomposition_raw": dict(
            lp=lp, protocol=fee(gross, r["protocol_fee_bps"]), creator=fee(gross, r["creator_fee_bps"])
        ),
    }


def pda(seeds, owner):
    return str(Pubkey.find_program_address(seeds, Pubkey.from_string(owner))[0])


def decode_account(account, owner, name):
    if not account or account.get("owner") != owner or account.get("executable") is not False:
        raise QuoteUnavailable()
    try:
        encoded, encoding = account["data"]
        if encoding != "base64" or len(encoded) > 65536:
            raise QuoteUnavailable()
        raw = base64.b64decode(encoded, validate=True)
        # Only SDK-documented account versions. This never applies to event payloads.
        historical = {
            "BondingCurve": ({49, 81, 82, 83, 115, 124, 125, 141, 151}, 166),
            "Global": ({1045, 1054}, 1088),
            "Pool": ({211, 243, 244, 245, 261, 270, 271}, 287),
            "GlobalConfig": ({907, 940}, 949),
        }
        if name in historical:
            old, size = historical[name]
            if len(raw) in old:
                raw += bytes(size - len(raw))
        if name == "FeeConfig":
            if len(raw) < 2512:
                raise QuoteUnavailable()

            def vector_end(start):
                if start + 4 > len(raw):
                    raise QuoteUnavailable()
                count = int.from_bytes(raw[start : start + 4], "little")
                end = start + 4 + 40 * count
                if count > 50 or end > len(raw):
                    raise QuoteUnavailable()
                return end

            end = vector_end(65)
            if len(raw) >= 4073:
                end = vector_end(end)
            if len(raw) >= 4097:
                end += 24
                if end > len(raw):
                    raise QuoteUnavailable()
            # Official deserialize_versioned: allocated stale tail is not part of that version.
            raw = raw[:end] + bytes(28)
        schema = SOURCES["account_schemas"][name]
        if raw[:8] != bytes(schema["discriminator"]):
            raise QuoteUnavailable()
        offset = 8

        def take(n):
            nonlocal offset
            if offset + n > len(raw):
                raise QuoteUnavailable()
            result = raw[offset : offset + n]
            offset += n
            return result

        def struct(kind):
            return {f["name"]: read(f["type"]) for f in SOURCES["account_schemas"][kind]["fields"]}

        def read(kind):
            if isinstance(kind, dict):
                if "defined" in kind:
                    return struct(kind["defined"]["name"])
                if "array" in kind:
                    item, count = kind["array"]
                elif "vec" in kind:
                    item, count = kind["vec"], int.from_bytes(take(4), "little")
                else:
                    raise QuoteUnavailable()
                if not 0 <= count <= 128:
                    raise QuoteUnavailable()
                return [read(item) for _ in range(count)]
            if kind == "pubkey":
                return str(Pubkey.from_bytes(take(32)))
            if kind == "bool":
                value = take(1)[0]
                if value not in (0, 1):
                    raise QuoteUnavailable()
                return bool(value)
            sizes = {"u8": 1, "u16": 2, "u32": 4, "u64": 8, "u128": 16, "i128": 16}
            return int.from_bytes(take(sizes[kind]), "little", signed=kind.startswith("i"))

        result = struct(name)
        # Known allocated account padding only. Undocumented nonzero account extensions fail closed.
        if any(raw[offset:]):
            raise QuoteUnavailable()
        return result
    except (ValueError, KeyError, TypeError, IndexError):
        raise QuoteUnavailable() from None


def mint_info(account):
    if (
        not account
        or account.get("owner") not in (TOKEN_PROGRAM, TOKEN_2022)
        or account.get("executable") is not False
        or not isinstance(account.get("data"), list)
        or len(account["data"]) != 2
        or account["data"][1] != "base64"
        or len(account["data"][0]) > 65536
    ):
        raise QuoteUnavailable()
    raw = base64.b64decode(account["data"][0], validate=True)
    if len(raw) < 82 or raw[45] != 1:
        raise QuoteUnavailable()
    if len(raw) > 82:
        # Metadata-only mint extensions; transfer fees/hooks/confidential/default-state remain unsupported.
        if account["owner"] != TOKEN_2022 or len(raw) < 166 or raw[165] != 1:
            raise QuoteUnavailable()
        offset = 166
        while offset < len(raw):
            if not any(raw[offset:]):
                break
            tag = int.from_bytes(raw[offset : offset + 2], "little")
            size = int.from_bytes(raw[offset + 2 : offset + 4], "little")
            if tag not in (18, 19) or offset + 4 + size > len(raw):
                raise QuoteUnavailable()
            offset += 4 + size
    return int.from_bytes(raw[36:44], "little"), raw[44], 170 if account["owner"] == TOKEN_2022 else 165


def vault_amount(account, mint, authority):
    if (
        not account
        or account.get("owner") not in (TOKEN_PROGRAM, TOKEN_2022)
        or account.get("executable") is not False
        or not isinstance(account.get("data"), list)
        or len(account["data"]) != 2
        or account["data"][1] != "base64"
        or len(account["data"][0]) > 65536
    ):
        raise QuoteUnavailable()
    raw = base64.b64decode(account["data"][0], validate=True)
    if account["owner"] == TOKEN_2022:
        if len(raw) != 170 or raw[165] != 2 or raw[166:170] != b"\x07\x00\x00\x00":
            raise QuoteUnavailable()
    elif len(raw) != 165:
        raise QuoteUnavailable()
    if (
        len(raw) < 165
        or str(Pubkey.from_bytes(raw[:32])) != mint
        or str(Pubkey.from_bytes(raw[32:64])) != authority
        or raw[108] != 1
    ):
        raise QuoteUnavailable()
    return int.from_bytes(raw[64:72], "little")


@dataclass(frozen=True)
class StateObservation:
    mint: str
    requested_at: float
    acquired_at: float
    slot: int
    data_json: str
    rent_lamports: int
    account_hashes: tuple
    commitment: str = "confirmed"
    identity_address: str = ""
    account_addresses: tuple = ()
    identity_context_slot: int = 0

    @property
    def data(self):
        return json.loads(self.data_json)


class ResearchExecutionOracle:
    """Verified account snapshots only; never imports a trade event decoder."""

    def __init__(self, rpc):
        self.rpc = rpc
        self.rents = {}
        self.diagnostics = dict(
            slot_consistency_rejections=0, account_shape_rejections=0, acquisition_delay_rejections=0
        )
        self.slots: OrderedDict[str, int] = OrderedDict()

    async def observe(self, mint, venue="PUMP", pool=None, migration=None, min_slot=0, diagnostic_pool=False):
        if str(Pubkey.from_string(mint)) == ZERO:
            raise QuoteUnavailable()
        owner = PUMP_PROGRAM if venue == "PUMP" else AMM
        if venue not in ("PUMP", "PUMPSWAP"):
            raise QuoteUnavailable()
        address = (
            pda([b"bonding-curve", bytes(Pubkey.from_string(mint))], PUMP_PROGRAM)
            if venue == "PUMP"
            else pool
        )
        if (
            venue == "PUMPSWAP"
            and not diagnostic_pool
            and (
                not migration
                or migration.get("identity_quality") != "VERIFIED"
                or migration.get("data_quality") != "VERIFIED"
                or migration.get("source") not in ("Solana WSS", "Recovered Pump instruction")
                or not migration.get("signature")
                or migration.get("pool") != pool
                or migration.get("mint") != mint
            )
        ):
            raise QuoteUnavailable()
        min_slot = max(min_slot, self.slots.get(address, 0))
        # Identity discovery read is never the fill. The final batch revalidates every identity.
        first = await self.rpc.rpc(
            "getAccountInfo",
            [address, {"encoding": "base64", "commitment": "confirmed", "minContextSlot": min_slot}],
        )
        if first["context"]["slot"] < min_slot:
            self.diagnostics["slot_consistency_rejections"] += 1
            raise QuoteUnavailable("UNAVAILABLE_PROVIDER_GAP")
        account_name = "BondingCurve" if venue == "PUMP" else "Pool"
        initial = decode_account(first["value"], owner, account_name)
        quote = initial["quote_mint"]
        quote = WSOL if quote == ZERO and venue == "PUMP" else quote
        if quote not in QUOTES:
            raise QuoteUnavailable("UNAVAILABLE_UNITS")
        global_address = pda([b"global" if venue == "PUMP" else b"global_config"], owner)
        fee_address = pda([b"fee_config", bytes(Pubkey.from_string(owner))], FEE_PROGRAM)
        addresses = [address, mint, quote, global_address, fee_address]
        if venue == "PUMPSWAP":
            addresses += [initial["pool_base_token_account"], initial["pool_quote_token_account"]]
        request = time.time()
        result = await self.rpc.rpc(
            "getMultipleAccounts",
            [
                addresses,
                {
                    "encoding": "base64",
                    "commitment": "confirmed",
                    "minContextSlot": max(min_slot, first["context"]["slot"]),
                },
            ],
        )
        acquired = time.time()
        if acquired - request > 5:
            self.diagnostics["acquisition_delay_rejections"] += 1
            raise QuoteUnavailable("UNAVAILABLE_PROVIDER_GAP")
        accounts = result["value"]
        if len(accounts) != len(addresses) or result["context"]["slot"] < max(
            min_slot, first["context"]["slot"]
        ):
            self.diagnostics[
                "slot_consistency_rejections"
                if result["context"]["slot"] < max(min_slot, first["context"]["slot"])
                else "account_shape_rejections"
            ] += 1
            raise QuoteUnavailable()
        curve = decode_account(accounts[0], owner, account_name)
        if venue == "PUMPSWAP":
            from backend.app.onchain import parse_pool

            try:
                verified = parse_pool(accounts[0], mint)
            except ValueError:
                raise QuoteUnavailable() from None
            if verified["quote_mint"] != quote or any(
                curve[k] == ZERO
                for k in ("base_mint", "quote_mint", "pool_base_token_account", "pool_quote_token_account")
            ):
                raise QuoteUnavailable()
        _, quote_decimals, _ = mint_info(accounts[2])
        supply, decimals, rent_size = mint_info(accounts[1])
        if quote_decimals != QUOTES[quote][1] or accounts[2]["owner"] != TOKEN_PROGRAM:
            raise QuoteUnavailable("UNAVAILABLE_UNITS")
        global_state = decode_account(accounts[3], owner, "Global" if venue == "PUMP" else "GlobalConfig")
        fees = decode_account(accounts[4], FEE_PROGRAM, "FeeConfig")
        actual_quote = WSOL if venue == "PUMP" and curve["quote_mint"] == ZERO else curve["quote_mint"]
        if actual_quote != quote or (
            venue == "PUMPSWAP"
            and (
                curve["base_mint"] != mint
                or any(
                    curve[k] != initial[k] for k in ("pool_base_token_account", "pool_quote_token_account")
                )
            )
        ):
            raise QuoteUnavailable()
        if venue == "PUMP":
            state = dict(
                base_reserve=curve["virtual_token_reserves"],
                effective_quote=curve["virtual_quote_reserves"],
                real_token_reserves=curve["real_token_reserves"],
                real_quote_reserves=curve["real_quote_reserves"],
                complete=curve["complete"],
                canonical_pool=True,
                has_creator=curve["creator"] != ZERO,
            )
            if curve["depth"] or curve["post_complete_base_out"] or curve["post_complete_quote_in"]:
                raise QuoteUnavailable()  # Synthetic-migration/depth quote routing is outside this study.
        else:
            if global_state["disable_flags"] & (1 << 4):
                raise QuoteUnavailable()
            base = vault_amount(accounts[5], mint, pool)
            q = vault_amount(accounts[6], quote, pool)
            state = dict(
                base_reserve=base,
                effective_quote=q + curve["virtual_quote_reserves"],
                real_quote_reserves=q - curve["protocol_fees"] - curve["creator_fees"],
                real_token_reserves=base,
                complete=False,
                canonical_pool=curve["creator"]
                == pda([b"pool-authority", bytes(Pubkey.from_string(mint))], PUMP_PROGRAM),
                has_creator=curve["coin_creator"] != ZERO,
            )
        state.update(
            diagnostic_identity_only=bool(diagnostic_pool),
            venue=venue,
            quote_mint=quote,
            mint_supply=supply,
            base_decimals=decimals,
            is_mayhem_mode=curve["is_mayhem_mode"],
            creator_fee_bps=curve["creator_fee_bps"],
            creator_fee_configurable=global_state["creator_fee_configurable"],
            fee_config=fees,
            base_mint=mint,
            creator=curve["creator"],
            coin_creator=curve["creator"] if venue == "PUMP" else curve["coin_creator"],
            quote_vault_reserve=curve["virtual_quote_reserves"] if venue == "PUMP" else q,
            virtual_quote_reserves=0 if venue == "PUMP" else curve["virtual_quote_reserves"],
            fee_buckets_total=0 if venue == "PUMP" else curve["protocol_fees"] + curve["creator_fees"],
        )
        if rent_size not in self.rents:
            self.rents[rent_size] = await self.rpc.rpc(
                "getMinimumBalanceForRentExemption", [rent_size, {"commitment": "confirmed"}]
            )
        if type(self.rents[rent_size]) is not int or self.rents[rent_size] <= 0:
            raise QuoteUnavailable()
        self.slots[address] = result["context"]["slot"]
        self.slots.move_to_end(address)
        while len(self.slots) > 128:
            self.slots.popitem(last=False)
        return StateObservation(
            mint,
            request,
            acquired,
            result["context"]["slot"],
            json.dumps(state, sort_keys=True),
            self.rents[rent_size],
            tuple(hashlib.sha256(json.dumps(a, sort_keys=True).encode()).hexdigest() for a in accounts),
            "confirmed",
            address,
            tuple(addresses),
            first["context"]["slot"],
        )


def quote_budget(usd, fx, quote):
    if quote not in QUOTES or Decimal(str(fx)) <= 0:
        raise QuoteUnavailable("UNAVAILABLE_UNITS")
    return int(
        (Decimal(str(usd)) * 10 ** QUOTES[quote][1] / Decimal(str(fx))).to_integral_value(rounding=ROUND_DOWN)
    )

"""Bounded identity-only recovery of explicit logsSubscribe truncations.

Never reads transaction logs or interprets requested amounts as executed flow.
"""
import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import json
import hashlib
import math
from pathlib import Path
import time
from typing import Any

from solders.pubkey import Pubkey

from backend.app.discovery import PUMP_PROGRAM
from backend.app.domain import Deduplicator, MarketEvent
from backend.app import pump_amm_recovery as multi_hop
from backend.app.recovery_metrics import RecoveryMetrics

SCHEMA = json.loads(Path(__file__).with_name("pump_instructions.json").read_text())
INSTRUCTIONS = {bytes(i["discriminator"]): i for i in SCHEMA["instructions"]}
EVENTS = {bytes(d) for d in SCHEMA["event_discriminators"]}
# Official Anchor 14cec14617f372b69403c6fe0c904e46a723ca3f
# lang/src/event.rs: Sha256(anchor:event)[..8], little endian.
EVENT_CPI = bytes.fromhex("e445a52e51cb9a1d")
EVENT_AUTHORITY = str(Pubkey.find_program_address([b"__event_authority"], Pubkey.from_string(PUMP_PROGRAM))[0])
BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TRADE_NAMES = {"buy", "buy_exact_sol_in", "buy_v2", "buy_v3", "buy_exact_quote_in_v2",
               "buy_exact_quote_in_v3", "sell", "sell_v2", "sell_v3"}
CLASSIFICATIONS = ("UNTRACKED_CONFIRMED", "TRACKED_AFFECTED", "UNSUPPORTED_PUMP_TRADE",
                   "TRANSACTION_UNAVAILABLE", "TRANSACTION_FAILED", "MALFORMED")


def decode_base58(value):
    if not isinstance(value, str) or len(value) > 16384:
        raise ValueError("instruction data bound")
    number = 0
    for char in value:
        number = number * 58 + BASE58.index(char)
    return b"\0" * (len(value) - len(value.lstrip("1"))) + number.to_bytes((number.bit_length() + 7) // 8, "big")


MIGRATION_NAMES = {"migrate", "migrate_v2"}
WSOL = "So11111111111111111111111111111111111111112"
MIGRATION_COUNTERS = ("recovered_migrate_instruction", "recovered_migrate_v2_instruction",
    "recovered_migration_tracked_mint", "recovered_migration_untracked_mint", "recovered_migration_emitted",
    "recovered_migration_duplicate", "recovered_migration_invalid_layout", "recovered_migration_queue_dropped",
    "recovered_migration_invalid_time", "recovered_migration_unproven_cpi")


def migration_identity(definition, accounts, keys, data, ordinal):
    # Account names/layout come exclusively from the existing pinned official IDL.
    if len(data) != 8 or len(accounts) < len(definition["accounts"]):
        raise ValueError("migration layout")
    named = {a["name"]: keys[accounts[i]] for i, a in enumerate(definition["accounts"])}
    mint = named["mint" if definition["name"] == "migrate" else "base_mint"]
    quote = named["wsol_mint"] if definition["name"] == "migrate" else named["quote_mint"]
    for address in (mint, quote, named["pool"]):
        if Pubkey.from_string(address) == Pubkey.default():
            raise ValueError("default migration key")
    curve = str(Pubkey.find_program_address([b"bonding-curve", bytes(Pubkey.from_string(mint))],
                                           Pubkey.from_string(PUMP_PROGRAM))[0])
    if (named["bonding_curve"] != curve or named["pump_amm"] != multi_hop.PROGRAM
            or definition["name"] == "migrate" and quote != WSOL):
        raise ValueError("migration identity")
    return {"mint": mint, "pool": named["pool"], "quote_mint": quote,
            "instruction": definition["name"], "instruction_ordinal": ordinal}


def transaction_impact(result, signature, slot, tracked, diagnostics=None, migrations=None):
    """Validate legacy/v0/v1 compiled instruction identities, including complete CPI data."""
    try:
        if result["slot"] != slot or type(result["slot"]) is not int:
            raise ValueError("slot mismatch")
        version = result.get("version", "legacy")
        if version != "legacy" and not (type(version) is int and version in (0, 1)):
            raise ValueError("unsupported version")
        meta = result["meta"]
        if meta["err"] is not None:
            return "TRANSACTION_FAILED", set()
        tx = result["transaction"]
        if not isinstance(tx["signatures"], list) or not tx["signatures"] or tx["signatures"][0] != signature:
            raise ValueError("signature mismatch")
        message = tx["message"]
        if version == 1:
            config = message["transactionConfig"]
            fields = {"priorityFee": 64, "computeUnitLimit": 32,
                      "loadedAccountsDataSizeLimit": 32, "heapSize": 32}
            if not isinstance(config, dict) or set(config) != set(fields):
                raise ValueError("unsupported v1 configuration")
            for field, bits in fields.items():
                value = config[field]
                if value is not None and (type(value) is not int or not 0 <= value < 2**bits):
                    raise ValueError("invalid v1 configuration")
            if "addressTableLookups" in message:
                raise ValueError("v1 cannot use lookup tables")
        elif "transactionConfig" in message:
            raise ValueError("configuration on older message")
        keys = list(message["accountKeys"])
        if not 1 <= len(keys) <= 256:
            raise ValueError("account bounds")
        lookups = message.get("addressTableLookups", [])
        if not isinstance(lookups, list) or len(lookups) > 256:
            raise ValueError("lookup bounds")
        if version == "legacy" and lookups:
            raise ValueError("legacy address lookups")
        loaded = meta.get("loadedAddresses", {"writable": [], "readonly": []})
        for kind, indexes in (("writable", "writableIndexes"), ("readonly", "readonlyIndexes")):
            addresses = loaded[kind]
            if not isinstance(addresses, list) or len(addresses) > 256:
                raise ValueError("loaded bounds")
            count = 0
            for lookup in lookups:
                Pubkey.from_string(lookup["accountKey"])
                indices = lookup[indexes]
                if not isinstance(indices, list) or any(type(i) is not int or not 0 <= i <= 255 for i in indices):
                    raise ValueError("lookup index")
                count += len(indices)
            if count != len(addresses):
                raise ValueError("missing loaded addresses")
            keys.extend(addresses)
        if len(keys) > 256:
            raise ValueError("resolved account bounds")
        for key in keys:
            Pubkey.from_string(key)
        outer = message["instructions"]
        inner = meta["innerInstructions"]  # null/missing means CPI coverage cannot be established.
        if not isinstance(outer, list) or not isinstance(inner, list) or len(outer) > 256 or len(inner) > len(outer):
            raise ValueError("instruction bounds")
        groups = set()
        for group in inner:
            index = group["index"]
            if type(index) is not int or not 0 <= index < len(outer) or index in groups:
                raise ValueError("inner group index")
            groups.add(index)
            if not isinstance(group["instructions"], list) or len(group["instructions"]) > 1024:
                raise ValueError("inner bounds")
        if len(outer) + sum(len(g["instructions"]) for g in inner) > 2048:
            raise ValueError("total instructions")
        contexts = multi_hop.invocations(outer, inner)
        staged_migrations = []
        staged_histogram: dict[str, int] = {}
        calls = []
        routes = {}
        affected = set()
        unsupported = False
        for identity, context in enumerate(contexts):
            instruction, is_inner = context.instruction, context.inner
            program = instruction["programIdIndex"]
            accounts = instruction["accounts"]
            if (type(program) is not int or not 0 <= program < len(keys) or not isinstance(accounts, list)
                    or len(accounts) > 256 or any(type(i) is not int or not 0 <= i < len(keys) for i in accounts)):
                raise ValueError("compiled account index")
            if keys[program] not in (PUMP_PROGRAM, multi_hop.PROGRAM):
                continue
            data = decode_base58(instruction["data"])
            if keys[program] == multi_hop.PROGRAM:
                if data[:8] == multi_hop.DISCRIMINATOR:
                    routes[identity] = multi_hop.route_mints(instruction, keys, data)
                continue
            if (data[:8] == EVENT_CPI and is_inner and len(accounts) == 1
                    and keys[accounts[0]] == EVENT_AUTHORITY and len(data) >= 16 and data[8:16] in EVENTS):
                continue  # Canonical Anchor event emission, not a trade invocation.
            definition = INSTRUCTIONS.get(data[:8])
            if definition is None:
                multi_hop.count(diagnostics, "unsupported_instruction_counts",
                                subtype="other" if data[:8] == EVENT_CPI else "unknown_discriminator")
                unsupported = True
                continue
            name = definition["name"]
            staged_histogram[name] = staged_histogram.get(name, 0) + 1
            if name in MIGRATION_NAMES:
                if diagnostics is not None:
                    diagnostics[f"recovered_{name}_instruction"] = diagnostics.get(f"recovered_{name}_instruction", 0) + 1
                try:
                    migration = migration_identity(definition, accounts, keys, data, identity)
                except (ValueError, KeyError, IndexError):
                    if diagnostics is not None:
                        diagnostics["recovered_migration_invalid_layout"] = diagnostics.get("recovered_migration_invalid_layout", 0) + 1
                    raise
                migration["inner"] = is_inner
                staged_migrations.append(migration)
            if definition["name"] == "multi_hop_curve_swap":
                multi_hop.count(diagnostics, "multi_hop_curve_swap_observed")
                calls.append((identity, data))
                continue
            required = sum(not a.get("optional", False) for a in definition["accounts"])
            if len(accounts) < required:
                raise ValueError("canonical account layout")
            if definition["name"] in TRADE_NAMES:
                if len(data) < 24:
                    raise ValueError("truncated trade arguments")
                names = [a["name"] for a in definition["accounts"]]
                position = names.index("mint" if "mint" in names else "base_mint")
                mint = keys[accounts[position]]
                if mint == str(Pubkey.default()):
                    raise ValueError("default mint")
                if tracked(mint):
                    affected.add(mint)
        if calls:
            definition = next(i for i in INSTRUCTIONS.values() if i["name"] == "multi_hop_curve_swap")
            unresolved, curve_mints = multi_hop.resolve(calls, routes, contexts, keys, tracked, definition, diagnostics)
            unsupported |= unresolved
            affected.update(curve_mints)
        if diagnostics is not None:
            histogram = diagnostics.get("instruction_counts")
            if histogram is not None:
                for name, count in staged_histogram.items():
                    histogram[name] += count
                diagnostics["instruction_histogram_transactions"] += 1
        if migrations is not None:
            migrations.extend(staged_migrations)
        if unsupported:
            return "UNSUPPORTED_PUMP_TRADE", set()
        if calls:
            multi_hop.count(diagnostics, "multi_hop_tracked_affected" if affected else "multi_hop_untracked_confirmed")
        return ("TRACKED_AFFECTED" if affected else "UNTRACKED_CONFIRMED"), affected
    except (ValueError, KeyError, TypeError, IndexError, AttributeError):
        return "MALFORMED", set()


@dataclass
class Recovery:
    signature: str
    slot: int
    observed: float
    attempts: int = 0
    next_attempt: float = 0
    first_rpc: bool = False


MIGRATION_AGE_COUNTERS = ("recovered_migration_chain_age_accepted",
    "recovered_migration_recovery_freshness_rejected", "recovered_migration_recovery_window_rejected",
    "recovered_migration_missing_freshness_provenance")


def migration_digest(event):
    return hashlib.sha256(json.dumps(event.model_dump(), sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).digest()


class TruncationRecovery:
    MAX_RECOVERY_IN_FLIGHT = 2
    MAX_PENDING = 32
    MAX_ATTEMPTS = 3
    MAX_AGE = 45

    def __init__(self, rpc, tracked, local_gap, global_gap, changed, emit_migration=None):
        self.emit_migration = emit_migration
        self.migration_seen = Deduplicator(10000)
        self.verified_migrations: OrderedDict[str, bytes] = OrderedDict()
        self.rpc, self.tracked = rpc, tracked
        self.local_gap, self.global_gap, self.changed = local_gap, global_gap, changed
        self.pending: OrderedDict[str, Recovery] = OrderedDict()
        self.seen = Deduplicator(10000)
        self.metrics = RecoveryMetrics()
        self.rpc.recovery_observer = self
        self.in_flight = 0
        self.claimed: set[str] = set()
        self.rpc_in_flight = 0
        self.health: dict[str, Any] = {"requests": 0, "successful_requests": 0, "errors": 0, "rate_limits": 0,
                       "submitted": 0, "accepted": 0, "expired": 0, "completed": 0, "shutdown_unresolved": 0,
                       "maximum_in_flight": 0, "maximum_rpc_in_flight": 0, "first_attempt_successes": 0, "monitoring_requests_with_backlog": 0,
                       "recovery_requests_with_backlog": 0, "attempts_distribution": dict.fromkeys((0, 1, 2, 3), 0),
                       "deduplicated": 0, "peak_pending": 0, "overflow": 0, "global_gaps": 0,
                       "token_local_gaps": 0, "classifications": dict.fromkeys(CLASSIFICATIONS, 0),
                       **multi_hop.diagnostics(), **dict.fromkeys(MIGRATION_COUNTERS + MIGRATION_AGE_COUNTERS, 0),
                       "recovered_migration_last_ages": {},
                       "instruction_counts": dict.fromkeys((i["name"] for i in INSTRUCTIONS.values()), 0),
                       "instruction_histogram_transactions": 0}

    def submit(self, signature, slot, observed):
        self.health["submitted"] += 1
        self.metrics.tick("arrivals")
        if not self.seen.accept(signature):
            self.health["deduplicated"] += 1
            return
        if len(self.pending) >= self.MAX_PENDING:
            self.health["overflow"] += 1
            self.health["global_gaps"] += 1
            self.global_gap()
            return
        self.health["accepted"] += 1
        self.pending[signature] = Recovery(signature, slot, observed)
        self.health["peak_pending"] = max(self.health["peak_pending"], len(self.pending))
        self.changed()

    def rpc_started(self, signature):
        recovery = self.pending.get(signature)
        if recovery is not None and not recovery.first_rpc:
            recovery.first_rpc = True
            self.metrics.sample("queue_wait", time.time() - recovery.observed)

    def overlaps(self, token, now, seconds=180):
        return any(r.observed >= max(now - seconds, token.trade_tracking_since) for r in self.pending.values())

    def snapshot(self):
        return {**self.health, **self.rpc.truncation_metrics, "scheduling": self.metrics.snapshot(),
                "in_flight": self.in_flight, "pending": len(self.pending),
                "accepted_reconciled": self.health["accepted"] == (
                    self.health["completed"] + self.health["shutdown_unresolved"] + len(self.pending)),
                "oldest_pending_age": max((time.time() - r.observed for r in self.pending.values()), default=0),
                "coverage_state": "PENDING RECOVERY" if self.pending else (
                    "STOPPED INCOMPLETE" if self.health["shutdown_unresolved"] else "RESOLVED")}

    def close_pending(self):
        """Only after worker cancellation. Unresolved shutdown work is never a success."""
        if self.claimed or self.in_flight or self.rpc_in_flight:
            raise RuntimeError("Recovery workers must stop before closing pending work")
        self.health["shutdown_unresolved"] += len(self.pending)
        self.pending.clear()
        self.changed()

    def resolve(self, recovery: Recovery, classification, affected=()):
        if self.pending.get(recovery.signature) is not recovery:
            return
        self.health["completed"] += 1
        self.health["attempts_distribution"][recovery.attempts] += 1
        self.metrics.tick("completions")
        self.metrics.sample("total_latency", time.time() - recovery.observed)
        self.health["classifications"][classification] += 1
        if classification == "TRACKED_AFFECTED":
            for mint in affected:
                self.local_gap(mint, reason="recovery", now=recovery.observed)
                self.health["token_local_gaps"] += 1
        elif classification != "UNTRACKED_CONFIRMED":
            self.health["global_gaps"] += 1
            self.global_gap()
        self.pending.pop(recovery.signature, None)
        self.changed()

    def migration_freshness_error(self, event, now, max_age):
        """Session-bound proof; flags/source strings alone cannot grant lifecycle replay."""
        missing = "recovered_migration_missing_freshness_provenance"
        window = "recovered_migration_recovery_window_rejected"
        stale = "recovered_migration_recovery_freshness_rejected"
        e = event.evidence
        if (event.kind != "migration" or event.source != "Recovered Pump instruction"
                or e.get("identity_quality") != "VERIFIED" or e.get("data_quality") != "VERIFIED"
                or e.get("instruction") not in MIGRATION_NAMES or e.get("program") != PUMP_PROGRAM
                or e.get("schema_source") != SCHEMA["source"] or e.get("commitment") != "confirmed"
                or e.get("mint") != event.mint or e.get("pool") != event.pair or e.get("inner") is not False):
            return missing
        observed, verified = e.get("truncation_observed_at"), e.get("recovery_verified_at")
        if any(type(t) not in (int, float) or not math.isfinite(t) or t < 1_500_000_000
               for t in (event.ts, observed, verified)):
            return missing
        self.health["recovered_migration_last_ages"] = {
            "chain_age_seconds_at_process": round(now - event.ts, 3),
            "recovery_age_seconds_at_process": round(now - verified, 3),
            "recovery_duration_seconds": round(verified - observed, 3)}
        if observed > now or event.ts > now or verified < observed or event.ts > verified or verified - observed > self.MAX_AGE:
            return window
        if verified > now or now - verified > max_age:
            return stale
        try:
            if self.verified_migrations.get(event.event_id) != migration_digest(event):
                return missing
        except (ValueError, TypeError):
            return missing
        return None

    def emit_migrations(self, recovery, result, migrations):
        for identity in migrations:
            # A successful transaction does not prove a caught inner CPI succeeded.
            # Without complete execution status we may count its instruction, never invent its lifecycle.
            if identity["inner"]:
                self.health["recovered_migration_unproven_cpi"] += 1
                continue
            mint = identity["mint"]
            if not self.tracked(mint):
                self.health["recovered_migration_untracked_mint"] += 1
                continue
            self.health["recovered_migration_tracked_mint"] += 1
            block_time = result.get("blockTime")
            if block_time is None:
                # Confirmed notification observation is an upper bound, never a claim of exact chain time.
                stamp, basis = recovery.observed, "confirmed_notification_observed_upper_bound"
            else:
                stamp, basis = block_time, "getTransaction.blockTime"
            if (type(stamp) not in (int, float) or not 1_500_000_000 <= stamp <= time.time() + 20
                    or stamp > recovery.observed + 20):
                self.health["recovered_migration_invalid_time"] += 1
                continue
            event_id = f"{recovery.signature}:migration:{mint}"
            if not self.migration_seen.accept(event_id):
                self.health["recovered_migration_duplicate"] += 1
                continue
            event = MarketEvent(mint=mint, kind="migration", ts=stamp, source="Recovered Pump instruction",
                event_id=event_id, signature=recovery.signature, pair=identity["pool"],
                evidence={**identity, "data_quality": "VERIFIED", "identity_quality": "VERIFIED",
                    "slot": recovery.slot, "commitment": "confirmed", "program": PUMP_PROGRAM,
                    "schema_source": SCHEMA["source"], "time_basis": basis,
                    "truncation_observed_at": recovery.observed})
            # Canonical transaction/layout/status/identity and MarketEvent validation have completed.
            event.evidence["recovery_verified_at"] = time.time()
            self.verified_migrations[event_id] = migration_digest(event)
            while len(self.verified_migrations) > self.migration_seen.maximum:
                self.verified_migrations.popitem(last=False)
            outcome = self.emit_migration(event) if self.emit_migration else "queue_dropped"
            self.health[f"recovered_migration_{outcome}"] += 1

    async def step(self):
        # Claims are made without an await; pending includes claimed work.
        now = time.time()
        for expired in list(self.pending.values()):
            if expired.signature not in self.claimed and now - expired.observed >= self.MAX_AGE:
                self.health["expired"] += 1
                self.resolve(expired, "TRANSACTION_UNAVAILABLE")
        if len(self.claimed) >= self.MAX_RECOVERY_IN_FLIGHT or not self.rpc.eligible():
            return
        recovery = next((r for r in self.pending.values()
                         if r.signature not in self.claimed and r.next_attempt <= now), None)
        if recovery is None:
            return
        if recovery.attempts >= self.MAX_ATTEMPTS:
            self.resolve(recovery, "TRANSACTION_UNAVAILABLE")
            return
        self.claimed.add(recovery.signature)
        recovery.attempts += 1
        started = time.monotonic()
        self.in_flight += 1
        self.health["maximum_in_flight"] = max(self.health["maximum_in_flight"], self.in_flight)
        try:
            try:
                result = await self.rpc.rpc("getTransaction", [recovery.signature,
                    {"encoding": "json", "commitment": "confirmed", "maxSupportedTransactionVersion": 1}],
                    purpose="truncation")
            except (RuntimeError, ValueError, OSError):
                result = None
            if time.time() - recovery.observed >= self.MAX_AGE:
                self.health["expired"] += 1
                self.resolve(recovery, "TRANSACTION_UNAVAILABLE")
            elif result is not None:
                if recovery.attempts == 1:
                    self.health["first_attempt_successes"] += 1
                migrations: list[dict] = []
                classification, affected = transaction_impact(result, recovery.signature, recovery.slot,
                                                               self.tracked, self.health, migrations)
                self.emit_migrations(recovery, result, migrations)
                self.resolve(recovery, classification, affected)
            elif recovery.attempts >= self.MAX_ATTEMPTS:
                self.resolve(recovery, "TRANSACTION_UNAVAILABLE")
            else:
                recovery.next_attempt = time.time() + 2 ** recovery.attempts
        finally:
            self.claimed.discard(recovery.signature)
            self.in_flight -= 1
            self.metrics.sample("rpc_latency", time.monotonic() - started)

    async def _worker(self):
        while True:
            await self.step()
            await asyncio.sleep(0.1)

    async def run(self):
        # Two long-lived tasks, never one task per signature. The provider's shared
        # FIFO semaphore, start limiter and cooldown remain authoritative.
        workers = [asyncio.create_task(self._worker()) for _ in range(self.MAX_RECOVERY_IN_FLIGHT)]
        try:
            await asyncio.gather(*workers)
        finally:
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

"""Synthetic canonical migration transactions, isolated from real research."""
import copy
import time

import pytest
from solders.pubkey import Pubkey

from backend.app.config import Settings
from backend.app.domain import MarketEvent, State, Token
from backend.app.engine import RadarEngine
from backend.app.truncation import INSTRUCTIONS, PUMP_PROGRAM, Recovery, WSOL, transaction_impact
from backend.app.pump_amm_recovery import PROGRAM
from backend.tests.test_truncation_recovery import transaction, b58


def fixture(name="migrate", loaded=False, inner=False, version="legacy"):
    mint = str(Pubkey.new_unique())
    tx, sig = transaction([mint], name, inner=inner, loaded=loaded)
    definition = next(i for i in INSTRUCTIONS.values() if i["name"] == name)
    keys = tx["transaction"]["message"]["accountKeys"]
    instructions = (tx["meta"]["innerInstructions"][0]["instructions"] if inner
                    else tx["transaction"]["message"]["instructions"])
    ix = instructions[0]
    named = {a["name"]: ix["accounts"][i] for i, a in enumerate(definition["accounts"])}
    curve = str(Pubkey.find_program_address([b"bonding-curve", bytes(Pubkey.from_string(mint))], Pubkey.from_string(PUMP_PROGRAM))[0])
    keys[named["bonding_curve"]] = curve
    keys[named["pump_amm"]] = PROGRAM
    if name == "migrate":
        keys[named["wsol_mint"]] = WSOL
    ix["data"] = b58(bytes(definition["discriminator"]))
    tx["blockTime"] = int(time.time())
    if version == 1:
        tx["version"] = 1
        tx["transaction"]["message"]["transactionConfig"] = dict.fromkeys(
            ("priorityFee", "computeUnitLimit", "loadedAccountsDataSizeLimit", "heapSize"))
    return tx, sig, mint, named, ix


@pytest.mark.parametrize("name", ["migrate", "migrate_v2"])
@pytest.mark.parametrize("loaded,inner,version", [(False, False, "legacy"), (True, False, 0), (True, True, 0), (False, False, 1)])
def test_canonical_migration_identity(name, loaded, inner, version):
    tx, sig, mint, named, _ = fixture(name, loaded, inner, version)
    migrations = []
    assert transaction_impact(tx, sig, 123, lambda m: True, migrations=migrations) == ("UNTRACKED_CONFIRMED", set())
    assert len(migrations) == 1 and migrations[0]["mint"] == mint
    keys = tx["transaction"]["message"]["accountKeys"]
    assert migrations[0]["pool"] == keys[named["pool"]]
    assert migrations[0]["quote_mint"] == (WSOL if name == "migrate" else keys[named["quote_mint"]])


@pytest.mark.parametrize("mutation", ["curve", "program", "pool", "mint", "quote", "short", "args", "failed"])
def test_invalid_migration_fails_closed(mutation):
    tx, sig, _, named, ix = fixture("migrate_v2")
    keys = tx["transaction"]["message"]["accountKeys"]
    field = {"curve": "bonding_curve", "program": "pump_amm", "pool": "pool", "mint": "base_mint", "quote": "quote_mint"}.get(mutation)
    if field:
        keys[named[field]] = str(Pubkey.default())
    elif mutation == "short":
        ix["accounts"].pop()
    elif mutation == "args":
        ix["data"] = b58(bytes(next(i["discriminator"] for i in INSTRUCTIONS.values() if i["name"] == "migrate_v2")) + b"x")
    else:
        tx["meta"]["err"] = {"InstructionError": [0, "failed"]}
    migrations = []
    assert transaction_impact(tx, sig, 123, lambda m: True, migrations=migrations)[0] in ("MALFORMED", "TRANSACTION_FAILED")
    assert not migrations


def engine(tmp_path):
    return RadarEngine(Settings(mode="OBSERVE", trade_stream_enabled=False), tmp_path / "migration.db", offline=True)


@pytest.mark.parametrize("visible_first", [True, False])
async def test_recovered_existing_lifecycle_and_visible_dedup(tmp_path, visible_first):
    tx, sig, mint, _, _ = fixture("migrate_v2")
    e = engine(tmp_path)
    t = Token(mint, "Synthetic", "TEST", time.time() - 100, state=State.WATCHING)
    e.tokens[mint] = t
    async def rpc(*args, **kwargs):
        return tx
    e.rpc.rpc = rpc
    e.rpc.eligible = lambda *a: True
    migrations = []
    transaction_impact(tx, sig, 123, lambda m: True, migrations=migrations)
    visible = MarketEvent(mint=mint, ts=tx["blockTime"], source="Onchain Pump", kind="migration",
                          event_id=f"{sig}:migration:{mint}", signature=sig, pair=migrations[0]["pool"])
    if visible_first:
        assert e.submit(visible)
    e.recovery.submit(sig, 123, time.time())
    await e.recovery.step()
    if not visible_first:
        assert not e.submit(visible)
    for event in e.queue.drain():
        assert e.process(event, time.time())
    assert t.graduation and t.flow_venue == "PUMPSWAP" and t.flow_epoch
    assert t.migration_pool == migrations[0]["pool"]
    assert t.state == State.POST_GRAD_OBSERVATION
    assert len(e.db.rows("graduation")) == 1
    assert e.recovery.health["recovered_migrate_v2_instruction"] == 1
    assert e.recovery.health["recovered_migration_duplicate" if visible_first else "recovered_migration_emitted"] == 1
    e.db.engine.dispose()


def test_untracked_no_admission_and_time_fallback(tmp_path):
    tx, sig, mint, _, _ = fixture()
    e = engine(tmp_path)
    migrations = []
    transaction_impact(tx, sig, 123, lambda m: False, e.recovery.health, migrations)
    recovery = Recovery(sig, 123, time.time())
    e.recovery.emit_migrations(recovery, tx, migrations)
    assert not e.tokens and not e.queue.heap
    assert e.recovery.health["recovered_migration_untracked_mint"] == 1
    e.tokens[mint] = Token(mint, "Synthetic", "TEST", time.time())
    tx.pop("blockTime")
    e.recovery.emit_migrations(recovery, tx, migrations)
    event = e.queue.drain()[0]
    assert event.ts == recovery.observed
    assert event.evidence["time_basis"] == "confirmed_notification_observed_upper_bound"
    assert event.evidence["data_quality"] == "VERIFIED"
    e.db.engine.dispose()


def test_multiple_mints_and_bounded_diagnostics(tmp_path):
    e = engine(tmp_path)
    tx, sig, mint, _, ix = fixture()
    other, _, mint2, _, ix2 = fixture()
    keys = tx["transaction"]["message"]["accountKeys"]
    offset = len(keys)
    keys.extend(other["transaction"]["message"]["accountKeys"])
    second = copy.deepcopy(ix2)
    second["programIdIndex"] += offset
    second["accounts"] = [a + offset for a in second["accounts"]]
    tx["transaction"]["message"]["instructions"].append(second)
    migrations = []
    transaction_impact(tx, sig, 123, lambda m: True, e.recovery.health, migrations)
    assert {m["mint"] for m in migrations} == {mint, mint2}
    assert e.recovery.health["instruction_counts"]["migrate"] == 2
    assert len(e.recovery.health["instruction_counts"]) == len(INSTRUCTIONS)
    assert e.rpc.health["requests"] == 0
    e.db.engine.dispose()


def test_inner_migration_not_invented_when_cpi_success_unproven(tmp_path):
    tx, sig, mint, _, _ = fixture(inner=True)
    e = engine(tmp_path)
    e.tokens[mint] = Token(mint, "Synthetic", "TEST", time.time())
    migrations = []
    transaction_impact(tx, sig, 123, lambda m: True, e.recovery.health, migrations)
    e.recovery.emit_migrations(Recovery(sig, 123, time.time()), tx, migrations)
    assert not e.queue.heap and e.recovery.health["recovered_migration_unproven_cpi"] == 1
    assert e.recovery.health["recovered_migrate_instruction"] == 1
    e.db.engine.dispose()


@pytest.mark.parametrize("age,accepted", [(2, True), (21, True)])
def test_recovered_migration_can_follow_newer_observation_with_fresh_acquisition(tmp_path, age, accepted):
    tx, sig, mint, _, _ = fixture()
    now = time.time()
    tx["blockTime"] = now - age
    e = engine(tmp_path)
    t = Token(mint, "Synthetic", "TEST", now - 100, state=State.WATCHING)
    t.last_event = now
    e.tokens[mint] = t
    migrations = []
    transaction_impact(tx, sig, 123, lambda m: True, migrations=migrations)
    e.recovery.emit_migrations(Recovery(sig, 123, now), tx, migrations)
    event = e.queue.drain()[0]
    assert e.process(event, max(now, event.evidence["recovery_verified_at"])) is accepted
    assert bool(t.graduation) is accepted
    assert t.last_event == now
    assert e.settings.max_data_age_seconds == 20
    e.db.engine.dispose()

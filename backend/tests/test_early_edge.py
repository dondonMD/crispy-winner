"""Explicitly synthetic research fixtures; never production enrollment."""

import base64
from collections import deque
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest
from solders.pubkey import Pubkey

from backend.app.config import Settings
from backend.app.domain import Token, State, MarketEvent
from backend.app.early_edge import (
    Study,
    IntegrityError,
    manifest,
    signal_snapshot,
    canonical,
    fx_value,
    HORIZONS,
    MAX_PENDING,
    result_costs,
)
from backend.app.early_edge_quotes import (
    WSOL,
    USDC,
    ZERO,
    AMM,
    FEE_PROGRAM,
    SOURCES,
    StateObservation,
    QuoteUnavailable,
    ResearchExecutionOracle,
    pump_buy,
    sell,
    quote_budget,
    decode_account,
    mint_info,
    vault_amount,
    pda,
)
from backend.app.early_edge_report import report, bootstraps, contrast, evidence_status, summary
from backend.app.early_edge_runtime import EarlyEdgeObserver, attach_observer, UsdReference
from backend.app.providers import PUMP_PROGRAM, TOKEN_PROGRAM
from backend.app.opportunity import load_intelligence_settings

NOW = 10000.0
VECTORS = json.loads(Path(__file__).with_name("fixtures").joinpath("early_edge/sdk_quotes.json").read_text())[
    "vectors"
]


def refs(now=NOW):
    return {
        m: dict(
            source="Coinbase Exchange public ticker" if m == WSOL else "Kraken public recent trades",
            product=p,
            usd=v,
            published_at=now,
            acquired_at=now,
        )
        for m, p, v in ((WSOL, "SOL-USD", 150), (USDC, "USDCUSD", 1))
    }


def token(now=NOW):
    t = Token(str(Pubkey.new_unique()), "Synthetic research", "SYNTH", now - 240)
    t.state = State.MATURING
    t.curve_history = deque([(now - 180, 30), (now - 120, 36), (now - 60, 42), (now, 48)], maxlen=32)
    t.last_curve, t.curve_progress = now, 48
    t.verified_quote_mint = WSOL
    t.security = dict(data_quality="VERIFIED", hard_failures=[])
    t.last_security = now
    t.features = {"180": dict(units_valid=True, currency="SOL", creator_sell_volume=0)}
    t.events.append(
        MarketEvent(
            mint=t.mint,
            ts=now,
            source="Solana WSS",
            kind="trade",
            event_id="synthetic",
            currency="SOL",
            side="buy",
            volume=0.1,
            evidence=dict(units_valid=True, quote_mint=WSOL, canonical_trade={}),
        )
    )
    return t


def view(action="EARLY_OPPORTUNITY"):
    return dict(
        action=action,
        research_version=load_intelligence_settings().version,
        dynamics={"freshness": "CURRENT"},
    )


def snap(t=None, now=NOW, action="EARLY_OPPORTUNITY"):
    return signal_snapshot(t or token(now), view(action), now, Settings(mode="OBSERVE"), refs(now))


def state(mint, at, venue="PUMP", requested=None):
    data = deepcopy(next(v["state"] for v in VECTORS if v["state"]["venue"] == venue))
    return StateObservation(
        mint,
        at if requested is None else requested,
        at,
        123,
        canonical(data),
        2039280,
        tuple(hashlib.sha256(f"synthetic-{i}".encode()).hexdigest() for i in range(7)),
    )


@pytest.fixture
def study(tmp_path):
    settings = Settings(mode="OBSERVE")
    p = manifest(settings, now=NOW - 2, draft=False, synthetic=True)
    s = Study(tmp_path / "early-synthetic.db", settings, p, synthetic=True)
    s.begin(NOW - 1)
    yield s
    try:
        s.db.close()
    except sqlite3.ProgrammingError:
        pass


@pytest.mark.parametrize("v", VECTORS, ids=[f"sdk-{i}" for i in range(len(VECTORS))])
def test_authoritative_sdk_golden(v):
    if v["state"]["venue"] == "PUMP":
        buy = pump_buy(v["state"], v["budget"])
        assert buy["quantity"] == int(v["quantity"])
        assert buy["quote_raw"] == int(v["entry_cost"])
    result = sell(v["state"], int(v["quantity"]))
    assert result["quote_raw"] == int(v["exit"])


@pytest.mark.parametrize(
    "change",
    [
        {"graduation": NOW - 1},
        {"state": State.REJECTED},
        {"state": State.EXPIRED},
        {"flow_venue": "PUMPSWAP"},
        {"curve_progress": 85},
        {"last_curve": NOW - 181},
        {"security": {"hard_failures": ["CONCENTRATION"]}},
        {"disagreement": True},
        {"features": {"180": {"units_valid": False, "currency": "SOL"}}},
        {"features": {"180": {"units_valid": True, "currency": "USDC"}}},
        {"features": {"180": {"units_valid": True, "currency": "SOL", "creator_sell_volume": 1}}},
        {"verified_quote_mint": str(Pubkey.new_unique())},
    ],
)
def test_signal_safeguards_unchanged(change):
    t = token()
    for k, v in change.items():
        setattr(t, k, v)
    assert snap(t) is None


def test_snapshot_is_pure_immutable_and_control_same_window(study):
    t = token()
    original = deepcopy(t)
    s = snap(t)
    assert t == original
    sid = study.enroll(s, NOW)
    s["features"]["currency"] = "changed"
    t.features["180"]["currency"] = "changed"
    stored = json.loads(study.db.execute("SELECT snapshot FROM ee_signals WHERE id=?", (sid,)).fetchone()[0])
    assert stored["features"]["currency"] == "SOL"
    assert snap(token(), action="DEVELOPING") is not None
    with pytest.raises(IntegrityError):
        study.enroll(snap(token(), action="DEVELOPING"), NOW)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        study.db.execute("UPDATE ee_signals SET ts=0")


@pytest.mark.parametrize(
    "field,value",
    [
        ("timestamp", NOW - 3),
        ("timestamp", NOW + 11),
        ("opportunity_version", "wrong"),
        ("mode", "DEMO"),
        ("graduation", NOW - 1),
    ],
)
def test_historical_drift_and_fake_signals_refused(study, field, value):
    s = snap()
    s[field] = value
    with pytest.raises(IntegrityError):
        study.enroll(s, NOW)
    assert study.db.execute("SELECT count(*) FROM ee_signals").fetchone()[0] == 0


def test_manifest_integrity_and_copy(study):
    p = study.plan
    p["primary_horizon"] = 60
    assert study.plan["primary_horizon"] == 300
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        study.db.execute("UPDATE ee_manifest SET payload='{}'")
    study.settings = study.settings.model_copy(update={"slippage_pct": 1.234})
    with pytest.raises(IntegrityError, match="drift"):
        study.enroll(snap(), NOW)


def test_earliest_per_token_session_arm_no_pseudo_replication(study):
    t = token()
    first = study.enroll(snap(t), NOW)
    assert study.enroll(snap(t, now=NOW + 11), NOW + 11) is None
    other = token(NOW + 2)
    assert study.enroll(
        snap(other, now=NOW + 2), NOW + 2, controls=[snap(t, now=NOW + 2, action="DEVELOPING")]
    )
    rows = study.db.execute("SELECT id,arm,ts FROM ee_signals ORDER BY id").fetchall()
    assert len(rows) == 3 and rows[0]["id"] == first and rows[0]["ts"] == NOW
    assert study.db.execute("SELECT sum(n) FROM ee_repeats").fetchone()[0] == 1
    with pytest.raises(IntegrityError):
        study.enroll(dict(snap(t), timestamp=NOW - 0.1), NOW + 2)


def test_first_state_after_latency_entry_receipt_never_rewritten(study):
    s = snap()
    study.enroll(s, NOW)
    # Response after boundary cannot rescue a request initiated before boundary.
    study.observe_state(state(s["mint"], NOW + 10.1, requested=NOW + 9.99), refs(NOW + 10.1), NOW + 10.1)
    assert study.db.execute("SELECT count(*) FROM ee_entries").fetchone()[0] == 0
    study.observe_state(state(s["mint"], NOW + 10.2, requested=NOW + 10), refs(NOW + 10.2), NOW + 10.2)
    receipt = study.db.execute("SELECT payload FROM ee_entries").fetchone()[0]
    assert json.loads(receipt)["state"]["requested_at"] == NOW + 10
    study.observe_state(state(s["mint"], NOW + 11), refs(NOW + 11), NOW + 11)
    assert study.db.execute("SELECT payload FROM ee_entries").fetchone()[0] == receipt
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        study.db.execute("UPDATE ee_entries SET payload='{}'")


def test_horizon_first_observable_not_preboundary_or_future_best(study):
    s = snap()
    study.enroll(s, NOW)
    study.observe_state(state(s["mint"], NOW + 11), refs(NOW + 11), NOW + 11)
    study.observe_state(state(s["mint"], NOW + 300.1, requested=NOW + 299.9), refs(NOW + 300.1), NOW + 300.1)
    assert study.db.execute("SELECT count(*) FROM ee_outcomes WHERE horizon=300").fetchone()[0] == 0
    study.observe_state(state(s["mint"], NOW + 300.3), refs(NOW + 300.3), NOW + 300.3)
    outcome = json.loads(study.db.execute("SELECT payload FROM ee_outcomes WHERE horizon=300").fetchone()[0])
    assert outcome["status"] == "MEASURED"
    assert outcome["exit_state"]["requested_at"] == NOW + 300.3
    assert outcome["venue_at_entry"] == "PUMP"
    assert outcome["entry_state"]["acquired_at"] == NOW + 11
    assert (outcome["gross_return_pct"] - outcome["net_return_pct"]) * 4 / 100 == pytest.approx(
        outcome["total_cost_usd"]
    )
    assert outcome["entry_cost_usd"] + outcome["exit_cost_usd"] == pytest.approx(outcome["total_cost_usd"])


def test_postgrad_account_quotes_do_not_use_trade_logs(study):
    s = snap()
    study.enroll(s, NOW)
    study.observe_state(state(s["mint"], NOW + 11), refs(NOW + 11), NOW + 11)
    study.observe_state(state(s["mint"], NOW + 300, venue="PUMPSWAP"), refs(NOW + 300), NOW + 300)
    o = json.loads(study.db.execute("SELECT payload FROM ee_outcomes WHERE horizon=300").fetchone()[0])
    assert o["venue_at_exit"] == "PUMPSWAP"
    assert o["token_quantity"] > 0


@pytest.mark.parametrize("kind", ["request_before", "future", "stale", "missing_hashes"])
def test_invalid_states_fail_closed(study, kind):
    s = snap()
    study.enroll(s, NOW)
    obs = state(s["mint"], NOW + 11)
    if kind == "request_before":
        obs = replace(obs, requested_at=NOW + 2)
    elif kind == "future":
        obs = replace(obs, acquired_at=NOW + 2)
    elif kind == "stale":
        obs = replace(obs, acquired_at=NOW - 21, requested_at=NOW - 22)
    else:
        obs = replace(obs, account_hashes=())
    with pytest.raises(IntegrityError):
        study.observe_state(obs, refs(), NOW + 11)


def test_restart_no_backfill_and_missing_in_denominator(study):
    study.enroll(snap(), NOW)
    path = study.path
    settings = study.settings
    study.db.close()  # abrupt interruption, no close finalization
    resumed = Study(path, settings, synthetic=True)
    resumed.begin(NOW + 2)
    rows = resumed.db.execute("SELECT status,payload FROM ee_outcomes").fetchall()
    assert len(rows) == len(HORIZONS)
    assert all(
        r["status"] == "UNAVAILABLE_INFRASTRUCTURE"
        and json.loads(r["payload"])["reason"] == "PROCESS_INTERRUPTION"
        for r in rows
    )
    resumed.close(NOW + 3)
    result = report(path)
    assert result == report(path)
    assert result["primary_accounting_fraction"] == 1
    assert result["primary_outcome_coverage"] == 0 and result["primary_unavailable"] == 1
    assert result["status"] == "INTERIM_OPERATIONAL_ONLY"
    assert result["horizons"] is None


def test_capacity_enrolls_then_accounts_every_signal(study):
    # Capacity patch is synthetic only; production manifest remains 64.
    assert MAX_PENDING == 64
    for _ in range(MAX_PENDING + 1):
        study.enroll(snap(), NOW)
    assert study.db.execute("SELECT count(*) FROM ee_signals").fetchone()[0] == 65
    assert study.db.execute("SELECT count(*) FROM ee_pending").fetchone()[0] == 64 * 4
    assert (
        study.db.execute(
            "SELECT count(*) FROM ee_outcomes WHERE status='UNAVAILABLE_INFRASTRUCTURE'"
        ).fetchone()[0]
        == 5
    )


@pytest.mark.parametrize("failure", ["UNAVAILABLE_UNITS", "UNAVAILABLE_PROVIDER_GAP", "UNAVAILABLE_QUOTE"])
def test_expiry_explicit_not_zero(study, failure):
    s = snap()
    study.enroll(s, NOW)
    study.failure(s["mint"], failure)
    study.expire(NOW + 21)
    assert {r[0] for r in study.db.execute("SELECT status FROM ee_outcomes")} == {failure}
    with pytest.raises(IntegrityError):
        study.outcome(1, 300, dict(status="ECONOMIC_ZERO_EXIT"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("usd", 0),
        ("usd", float("nan")),
        ("acquired_at", NOW + 0.01),
        ("published_at", NOW - 21),
        ("product", "wrong"),
        ("source", "guess"),
    ],
)
def test_usd_reference_fails_closed(field, value):
    r = refs()
    r[WSOL][field] = value
    with pytest.raises(QuoteUnavailable):
        fx_value(r, WSOL, NOW)


def test_units_budget_and_cost_exactly_once(study):
    assert quote_budget(4, 150, WSOL) == 26666666
    assert quote_budget(4, 0.99, USDC) == 4040404
    with pytest.raises(QuoteUnavailable):
        quote_budget(4, 1, ZERO)
    s = snap()
    obs = state(s["mint"], NOW + 11)
    e = pump_buy(obs.data, quote_budget(4, 150, WSOL))
    e.update(unit_usd=150 / 1e9, cash_left_usd=4 - e["quote_raw"] * 150 / 1e9, rent_usd=0.3, state={})
    x = sell(obs.data, e["quantity"])
    result = result_costs(study.plan, e, x, 150 / 1e9, obs)
    assert result["recoverable_rent_capital_usd"] == 0.3
    assert result["external_entry_cost_usd"] < 0.3
    assert result["gross_return_pct"] - result["net_return_pct"] == pytest.approx(
        result["total_cost_usd"] / 4 * 100
    )


def test_crowd_immutable_first_not_survivor_condition(study):
    s = snap()
    study.enroll(s, NOW)
    study.record_lifecycle(s["mint"], "CROWD_85", NOW + 10, dict(observed_at=NOW + 10, progress=85))
    study.record_lifecycle(s["mint"], "CROWD_85", NOW + 20, dict(observed_at=NOW + 20, progress=90))
    assert study.db.execute("SELECT ts FROM ee_benchmarks WHERE kind='CROWD_85'").fetchone()[0] == NOW + 10
    assert study.db.execute("SELECT count(*) FROM ee_signals").fetchone()[0] == 1
    with pytest.raises(IntegrityError):
        study.record_lifecycle(s["mint"], "GRADUATION", NOW + 1, dict(observed_at=NOW - 100))


def test_statistics_deterministic_clustered_and_no_unlock():
    rows = [
        dict(mint=str(i), arm=a, stratum="same", value=v)
        for i in range(4)
        for a, v in [("EARLY", i + 1), ("CONTROL", i - 1)]
    ]
    assert contrast(rows) == 2
    b = bootstraps(rows, resamples=10000)
    assert b == bootstraps(rows, resamples=10000) and b["mint_clusters"] == 4
    assert b["contrast_ci95"] == [2, 2]
    plan = dict(min_primary_samples=100, synthetic=False, bootstrap_resamples=10000)
    assert evidence_status(plan, 99, 1, 0, 1, 1, b, True, True, True) == "INSUFFICIENT_SAMPLE"
    crossing = dict(b, primary_ci95=[-1, 4])
    assert evidence_status(plan, 100, 1, 0, 1, 1, crossing, True, True, True) == "PROMISING_NOT_PROVEN"
    assert evidence_status(plan, 100, 1, 1, 1, 1, b, True, True, True) == "PROMISING_NOT_PROVEN"
    assert evidence_status(plan, 100, 1, 0, 1, 1, b, True, True, True) == "EARLY_EDGE_SUPPORTED"
    assert (
        evidence_status(dict(plan, synthetic=True), 100, 1, 0, 1, 1, b, True, True, True)
        != "EARLY_EDGE_SUPPORTED"
    )
    assert summary([-10, 12])["normal_ci95"][0] < 0


def test_old_database_not_touched(tmp_path):
    old = tmp_path / "old.db"
    c = sqlite3.connect(old)
    c.execute("CREATE TABLE old_manifest(x)")
    c.commit()
    c.close()
    before = old.read_bytes()
    with pytest.raises(IntegrityError, match="Foreign"):
        Study(old, Settings(mode="OBSERVE"))
    assert old.read_bytes() == before


def encode_account(name, values, owner):
    def enc(kind, v):
        if isinstance(kind, dict):
            if "defined" in kind:
                return struct(kind["defined"]["name"], v)
            if "array" in kind:
                item, _ = kind["array"]
                return b"".join(enc(item, x) for x in v)
            return len(v).to_bytes(4, "little") + b"".join(enc(kind["vec"], x) for x in v)
        if kind == "pubkey":
            return bytes(Pubkey.from_string(v))
        if kind == "bool":
            return bytes([int(v)])
        return int(v).to_bytes(
            {"u8": 1, "u16": 2, "u32": 4, "u64": 8, "u128": 16, "i128": 16}[kind],
            "little",
            signed=kind.startswith("i"),
        )

    def default(kind):
        if isinstance(kind, dict):
            if "defined" in kind:
                return {}
            if "vec" in kind:
                return []
            return [default(kind["array"][0]) for _ in range(kind["array"][1])]
        return ZERO if kind == "pubkey" else False if kind == "bool" else 0

    def struct(n, v):
        return b"".join(
            enc(f["type"], v.get(f["name"], default(f["type"])))
            for f in SOURCES["account_schemas"][n]["fields"]
        )

    raw = bytes(SOURCES["account_schemas"][name]["discriminator"]) + struct(name, values)
    if name == "FeeConfig":
        raw += bytes(4097 - len(raw))
    return dict(owner=owner, executable=False, data=[base64.b64encode(raw).decode(), "base64"])


def mint_account(decimals=6, supply=10**15):
    raw = bytearray(82)
    raw[36:44] = supply.to_bytes(8, "little")
    raw[44] = decimals
    raw[45] = 1
    return dict(owner=TOKEN_PROGRAM, executable=False, data=[base64.b64encode(raw).decode(), "base64"])


def vault(mint, pool, amount):
    raw = bytearray(165)
    raw[:32] = bytes(Pubkey.from_string(mint))
    raw[32:64] = bytes(Pubkey.from_string(pool))
    raw[64:72] = amount.to_bytes(8, "little")
    raw[108] = 1
    return dict(owner=TOKEN_PROGRAM, executable=False, data=[base64.b64encode(raw).decode(), "base64"])


@pytest.mark.parametrize("venue", ["PUMP", "PUMPSWAP"])
async def test_oracle_independent_complete_accounts_no_trade_events(venue):
    mint, pool = str(Pubkey.new_unique()), str(Pubkey.new_unique())
    fixture = next(v["state"] for v in VECTORS if v["state"]["venue"] == venue)
    if venue == "PUMP":
        owner = PUMP_PROGRAM
        a = encode_account(
            "BondingCurve",
            dict(
                virtual_token_reserves=fixture["base_reserve"],
                virtual_quote_reserves=fixture["effective_quote"],
                real_token_reserves=fixture["real_token_reserves"],
                real_quote_reserves=fixture["real_quote_reserves"],
                creator=str(Pubkey.new_unique()),
                quote_mint=ZERO,
            ),
            owner,
        )
        g = encode_account("Global", dict(creator_fee_configurable=True), owner)
    else:
        owner = AMM
        a = encode_account(
            "Pool",
            dict(
                base_mint=mint,
                quote_mint=WSOL,
                pool_base_token_account=str(Pubkey.new_unique()),
                pool_quote_token_account=str(Pubkey.new_unique()),
                creator=pda([b"pool-authority", bytes(Pubkey.from_string(mint))], PUMP_PROGRAM),
                coin_creator=str(Pubkey.new_unique()),
            ),
            owner,
        )
        g = encode_account("GlobalConfig", dict(creator_fee_configurable=True), owner)
    accounts = [
        a,
        mint_account(),
        mint_account(9),
        g,
        encode_account("FeeConfig", fixture["fee_config"], FEE_PROGRAM),
    ]
    if venue == "PUMPSWAP":
        accounts += [vault(mint, pool, 800000000000000), vault(WSOL, pool, 65000000000)]

    class Rpc:
        calls = []

        async def rpc(self, method, params):
            self.calls.append((method, params))
            if method == "getAccountInfo":
                return dict(context={"slot": 100}, value=a)
            if method == "getMultipleAccounts":
                return dict(context={"slot": 101}, value=accounts)
            if method == "getMinimumBalanceForRentExemption":
                return 2039280
            raise AssertionError("No transaction / trading RPC permitted")

    rpc = Rpc()
    oracle = ResearchExecutionOracle(rpc)
    proof = dict(
        identity_quality="VERIFIED",
        data_quality="VERIFIED",
        mint=mint,
        pool=pool,
        signature="canonical",
        source="Solana WSS",
    )
    obs = await oracle.observe(mint, venue, pool, proof)
    assert obs.data["venue"] == venue and obs.data["quote_mint"] == WSOL
    assert len(obs.account_hashes) == len(accounts)
    assert obs.requested_at <= obs.acquired_at and obs.slot == 101
    assert len(rpc.calls) == 3
    accounts[0] = dict(a, owner=ZERO)
    with pytest.raises(QuoteUnavailable):
        await oracle.observe(mint, venue, pool, proof)


@pytest.mark.parametrize("kind", ["owner", "truncated", "discriminator", "tail"])
def test_account_parser_fail_closed(kind):
    a = encode_account("BondingCurve", {}, PUMP_PROGRAM)
    raw = base64.b64decode(a["data"][0])
    if kind == "owner":
        a["owner"] = ZERO
    if kind == "truncated":
        raw = raw[:-1]
    if kind == "discriminator":
        raw = b"wrong!!!" + raw[8:]
    if kind == "tail":
        raw += b"\x01"
    a["data"][0] = base64.b64encode(raw).decode()
    with pytest.raises(QuoteUnavailable):
        decode_account(a, PUMP_PROGRAM, "BondingCurve")


def test_mint_vault_identity_units():
    m, p = str(Pubkey.new_unique()), str(Pubkey.new_unique())
    assert mint_info(mint_account())[1] == 6
    a = vault(m, p, 123)
    assert vault_amount(a, m, p) == 123
    with pytest.raises(QuoteUnavailable):
        vault_amount(a, m, str(Pubkey.new_unique()))
    a["owner"] = ZERO
    with pytest.raises(QuoteUnavailable):
        vault_amount(a, m, p)


async def test_oracle_unverified_pool_no_rpc():
    class Rpc:
        async def rpc(self, *args):
            raise AssertionError("Must reject before network")

    with pytest.raises(QuoteUnavailable):
        await ResearchExecutionOracle(Rpc()).observe(
            str(Pubkey.new_unique()), "PUMPSWAP", str(Pubkey.new_unique()), {}
        )


def test_observer_preserves_core_return_state_and_handles_failure(study):
    t = token()
    enum = SimpleNamespace(value="EARLY_OPPORTUNITY")
    opportunity = SimpleNamespace(action=enum)
    opportunity.model_dump = lambda **_: view()
    ref = SimpleNamespace(snapshot=lambda: refs())
    observer = EarlyEdgeObserver(study, study.settings, ref, clock=lambda: NOW)
    calls = []
    intelligence = SimpleNamespace(
        observe=lambda *a, **kw: calls.append("core") or 123, project=lambda *a, **kw: opportunity
    )
    engine = SimpleNamespace(intelligence=intelligence, process=lambda *a, **kw: 456, tokens={t.mint: t})
    before = deepcopy(t)
    detach = attach_observer(engine, observer)
    assert engine.intelligence.observe(t, NOW) == 123
    assert t == before and calls == ["core"]
    assert study.db.execute("SELECT count(*) FROM ee_signals").fetchone()[0] == 1
    observer.keys.clear()
    study.enroll = lambda *a, **kw: (_ for _ in ()).throw(ValueError("synthetic failure"))
    assert engine.intelligence.observe(t, NOW) == 123 and observer.failed
    assert t == before
    detach()
    assert engine.intelligence.observe(t, NOW) == 123


async def test_usd_bounded_cache_without_future_backfill(monkeypatch):
    import backend.app.early_edge_runtime as runtime

    clock = [NOW]
    monkeypatch.setattr(runtime.time, "time", lambda: clock[0])
    ref = UsdReference()
    calls = []

    async def request(method, url, **kw):
        calls.append(url)
        if "SOL-USD" in url:
            return dict(price="150", time="1970-01-01T02:46:40+00:00")
        return dict(error=[], result={"USDCUSD": [[".999", "1", NOW, "b", "l", "", 123]], "last": "123"})

    ref.request = request
    await ref.refresh()
    await ref.refresh()
    assert len(calls) == 2
    assert fx_value(ref.snapshot(), USDC, NOW) == 0.999
    clock[0] += 21
    with pytest.raises(QuoteUnavailable):
        fx_value(ref.snapshot(), WSOL, clock[0])
    await ref.close()


def test_namespace_no_execution_imports():
    for p in (
        Path("backend/app/early_edge_quotes.py"),
        Path("backend/app/early_edge.py"),
        Path("backend/app/early_edge_report.py"),
    ):
        content = p.read_text()
        assert "from backend.app.engine" not in content
        assert "sendTransaction" not in content and "Keypair" not in content


def test_only_canonical_pump_units_qualify():
    t = token()
    t.events.clear()
    assert snap(t) is None
    t.events.append(
        MarketEvent(
            mint=t.mint,
            ts=NOW,
            kind="trade",
            source="PumpPortal",
            event_id="synthetic",
            currency="SOL",
            side="buy",
            volume=1,
        )
    )
    assert snap(t) is None


@pytest.mark.parametrize("length", [49, 81, 82, 83, 115, 124, 125, 141, 151])
def test_documented_historical_curve_account_versions(length):
    a = encode_account("BondingCurve", {}, PUMP_PROGRAM)
    raw = base64.b64decode(a["data"][0])[:length]
    a["data"][0] = base64.b64encode(raw).decode()
    decoded = decode_account(a, PUMP_PROGRAM, "BondingCurve")
    assert decoded["depth"] == 0 and decoded["creator_fee_bps"] == 0


@pytest.mark.parametrize("length", [2512, 4073, 4097])
def test_official_versioned_fee_config_reader(length):
    fees = VECTORS[0]["state"]["fee_config"]
    a = encode_account("FeeConfig", fees, FEE_PROGRAM)
    raw = bytearray(base64.b64decode(a["data"][0])[:length])
    # Bytes outside the canonical length-selected layout are stale allocation,
    # explicitly not fields according to both pinned official SDK readers.
    read_end = 65 + 4 + 40 * len(fees["fee_tiers"])
    if length >= 4073:
        read_end += 4
    if length >= 4097:
        read_end += 24
    raw[read_end:] = b"\xff" * (len(raw) - read_end)
    a["data"][0] = base64.b64encode(raw).decode()
    decoded = decode_account(a, FEE_PROGRAM, "FeeConfig")
    assert decoded["fee_tiers"] == fees["fee_tiers"]
    assert decoded["stable_fee_tiers"] == []


def test_zero_or_insufficient_quote_is_not_economic_zero():
    s = deepcopy(VECTORS[0]["state"])
    s["real_quote_reserves"] = 0
    with pytest.raises(QuoteUnavailable):
        sell(s, 1000)
    s["real_quote_reserves"] = 40000000000
    with pytest.raises(QuoteUnavailable):
        sell(s, 1)


async def test_real_engine_observational_equivalence(tmp_path, study, monkeypatch):
    from backend.app.engine import RadarEngine
    from dataclasses import asdict

    monkeypatch.setattr("backend.app.engine.time.time", lambda: NOW)
    settings = Settings(mode="OBSERVE")
    plain = RadarEngine(settings, tmp_path / "plain.db", offline=True)
    hooked = RadarEngine(settings, tmp_path / "hooked.db", offline=True)
    observer = EarlyEdgeObserver(study, settings, SimpleNamespace(snapshot=lambda: refs()), clock=lambda: NOW)
    detach = attach_observer(hooked, observer)
    mint = str(Pubkey.new_unique())
    events = [
        MarketEvent(mint=mint, kind="create", ts=NOW - 10, source="Solana WSS", event_id="synthetic-create"),
        MarketEvent(
            mint=mint,
            kind="curve",
            ts=NOW,
            source="Solana RPC",
            event_id="synthetic-curve",
            curve_progress=40,
            evidence={"data_quality": "VERIFIED"},
        ),
    ]
    for e in events:
        assert plain.process(e, e.ts) == hooked.process(e, e.ts)
    assert asdict(plain.tokens[mint]) == asdict(hooked.tokens[mint])
    assert plain.paper.state == hooked.paper.state
    assert plain.version == hooked.version
    assert not observer.failed
    detach()
    await plain.stop()
    await hooked.stop()


def test_less_than_two_mint_clusters_has_no_supporting_ci():
    rows = [dict(mint="one", arm=a, stratum="s", value=v) for a, v in [("EARLY", 2), ("CONTROL", 1)]]
    b = bootstraps(rows, resamples=10000)
    assert b["primary_ci95"] == [None, None]


def test_synthetic_smoke_is_offline_and_no_live_state():
    from scripts.early_edge_smoke import smoke

    result = smoke()
    assert result["synthetic"] and not result["live_cohort_created"]
    assert result["network_requests"] == 0 and not result["engine_created"]
    assert result["historical_enrollments"] == 0 and result["pre_latency_entries"] == 0
    assert result["interruption_explicit"] and result["report_deterministic"]


def test_risk_set_exact_time_and_deterministic_ties(study):
    from backend.app.early_edge_design import risk_set

    t = snap()
    a = snap(action="DEVELOPING")
    b = snap(action="DEVELOPING")
    expected = min(a["mint"], b["mint"])
    assert risk_set(t, [b, a], study.plan)[0]["mint"] == expected
    assert risk_set(t, [dict(a, timestamp=NOW - 0.001)], study.plan) == []
    assert risk_set(t, [dict(a, security_verified=False)], study.plan) == []
    tid = study.enroll(t, NOW, controls=[b, a])
    row = study.db.execute("SELECT * FROM ee_pairs WHERE treatment=?", (tid,)).fetchone()
    selected = study.db.execute("SELECT mint,ts FROM ee_signals WHERE id=?", (row["control"],)).fetchone()
    assert selected["mint"] == expected and selected["ts"] == t["timestamp"]


def test_readiness_same_floor_no_momentum_matching(study):
    from backend.app.early_edge_design import readiness

    t = token()
    t.curve_history = deque([(NOW - 180, 55), (NOW - 120, 50), (NOW - 60, 49), (NOW, 48)], maxlen=32)
    assert readiness(t, NOW, study.settings)["ready"]
    assert snap(t, action="DEVELOPING") is not None  # Negative momentum is not a readiness exclusion.
    t.curve_history = deque([(NOW - 20, 47), (NOW, 48)], maxlen=32)
    assert snap(t) is None and snap(t, action="DEVELOPING") is None
    t = token()
    t.security = {"data_quality": "UNKNOWN", "hard_failures": []}
    t.curve_history = deque([(NOW - 60, 40), (NOW - 30, 44), (NOW, 48)], maxlen=32)
    assert snap(t) is None and snap(t, action="DEVELOPING") is None


def test_control_later_early_keeps_original_pair(study):
    c = token()
    a = snap()
    control = snap(c, action="DEVELOPING")
    tid = study.enroll(a, NOW, controls=[control])
    before = tuple(study.db.execute("SELECT * FROM ee_pairs WHERE treatment=?", (tid,)).fetchone())
    later = study.enroll(snap(c, now=NOW + 1), NOW + 1)
    assert (
        later
        and tuple(study.db.execute("SELECT * FROM ee_pairs WHERE treatment=?", (tid,)).fetchone()) == before
    )
    assert study.db.execute("SELECT count(*) FROM ee_signals WHERE mint=?", (c.mint,)).fetchone()[0] == 2


def test_all_latency_variants_share_captured_stream(study):
    s = snap()
    study.enroll(s, NOW)
    for dt in (0.49, 0.5, 2, 5, 9.999, 10):
        study.observe_state(state(s["mint"], NOW + dt), refs(NOW + dt), NOW + dt)
    assert study.db.execute("SELECT count(*) FROM ee_entries").fetchone()[0] == 1
    secondary = study.db.execute(
        "SELECT latency_ms,payload FROM ee_secondary_entries ORDER BY latency_ms"
    ).fetchall()
    assert [r["latency_ms"] for r in secondary] == [500, 2000, 5000]
    assert [json.loads(r["payload"])["state"]["acquired_at"] - NOW for r in secondary] == [0.5, 2, 5]
    primary = json.loads(study.db.execute("SELECT payload FROM ee_entries").fetchone()[0])
    assert primary["state"]["acquired_at"] == NOW + 10 and primary["latency_boundary"] == NOW + 10


def test_first_100_treatments_close_permanently(study):
    for i in range(100):
        study.enroll(snap(), NOW)
    closed = study.enrollment_state(NOW)
    assert closed["closed"] and closed["reason"] == "TARGET_N" and closed["treatments"] == 100
    assert study.enroll(snap(), NOW + 1) is None
    assert study.db.execute("SELECT count(*) FROM ee_signals WHERE arm='EARLY'").fetchone()[0] == 100
    assert report(study.path)["status"] == "INTERIM_OPERATIONAL_ONLY"


def test_30_calendar_days_close_even_if_results_unavailable(study):
    study.enroll(snap(), NOW)
    end = study.plan["created_at"] + 30 * 86400
    assert not study.enrollment_state(end - 0.001)["closed"]
    assert study.enrollment_state(end)["reason"] == "CALENDAR_LIMIT"
    study.expire(end)
    r = report(study.path)
    assert r["finalized"] and r["status"] == "INSUFFICIENT_SAMPLE"


def test_interim_hides_all_outcome_statistics(study):
    s = snap()
    study.enroll(s, NOW)
    study.observe_state(state(s["mint"], NOW + 10), refs(NOW + 10), NOW + 10)
    study.observe_state(state(s["mint"], NOW + 300), refs(NOW + 300), NOW + 300)
    r = report(study.path)
    assert (
        r["status"] == "INTERIM_OPERATIONAL_ONLY" and r["horizons"] is None and r["primary_bootstrap"] is None
    )
    assert "secondary_latencies" not in r


def test_mint_pair_bootstrap_preserves_crossovers():
    from backend.app.early_edge_report import paired_bootstrap

    rows = [
        dict(id=1, mint="a", arm="EARLY", stratum="s", value=2),
        dict(id=2, mint="b", arm="CONTROL", stratum="s", value=1),
        dict(id=3, mint="b", arm="EARLY", stratum="s", value=3),
        dict(id=4, mint="c", arm="CONTROL", stratum="s", value=2),
        dict(id=5, mint="d", arm="EARLY", stratum="s", value=4),
        dict(id=6, mint="e", arm="CONTROL", stratum="s", value=3),
    ]
    pairs = [dict(treatment=1, control=2), dict(treatment=3, control=4), dict(treatment=5, control=6)]
    a = paired_bootstrap(rows, pairs, resamples=100)
    assert a == paired_bootstrap(rows, pairs, resamples=100)
    assert a["independent_mint_pair_components"] == 2 and a["complete_pairs"] == 3
    assert a["contrast_ci95"] == [1, 1]
    assert paired_bootstrap(rows[:4], pairs[:2], resamples=100)["contrast_ci95"] == [None, None]


def test_economic_zero_automatic_proof_disabled(study):
    with pytest.raises(IntegrityError, match="disabled"):
        study.outcome(
            1,
            300,
            dict(
                status="ECONOMIC_ZERO_EXIT",
                zero_exit_evidence=dict(
                    kind="VERIFIED_NO_EXECUTABLE_EXIT", canonical_rule="guessed", account_hashes=["x"] * 7
                ),
            ),
        )


@pytest.mark.parametrize(
    "change", [{"commitment": "processed"}, {"requested_at": NOW - 10, "acquired_at": NOW + 1}]
)
def test_quote_consistency_receipt_rejected(study, change):
    s = snap()
    study.enroll(s, NOW)
    with pytest.raises(IntegrityError):
        study.observe_state(replace(state(s["mint"], NOW + 1), **change), refs(NOW + 1), NOW + 1)


def test_diagnostic_pool_receipts_cannot_enter_outcomes(study):
    s = snap()
    study.enroll(s, NOW)
    obs = state(s["mint"], NOW + 10)
    data = dict(obs.data, diagnostic_identity_only=True)
    with pytest.raises(IntegrityError, match="Diagnostic"):
        study.observe_state(replace(obs, data_json=canonical(data)), refs(NOW + 10), NOW + 10)


def test_non_enrolling_diagnostic_never_constructs_study(study, monkeypatch):
    from scripts.early_edge_diagnostic import DryObserver

    monkeypatch.setattr(Study, "__init__", lambda *a, **k: (_ for _ in ()).throw(AssertionError("No cohort")))
    observer = DryObserver(study.settings, study.plan)
    t = token()
    v = SimpleNamespace(model_dump=lambda **_: view())
    observer.observe(t, v, NOW)
    assert observer.counts["early_signals"] == 1
    assert study.db.execute("SELECT count(*) FROM ee_signals").fetchone()[0] == 0


def test_buyer_crowd_first_observation_not_backdated(study):
    t = token()
    ref = SimpleNamespace(snapshot=lambda: refs())
    observer = EarlyEdgeObserver(study, study.settings, ref)
    v = SimpleNamespace(model_dump=lambda **_: view())
    observer.observe(t, v, NOW)
    t.features["180"].update(trade_evidence="CURRENT", estimated_independent_buyers=study.settings.min_buyers)
    observer.observe(t, v, NOW + 1)
    observer.observe(t, v, NOW + 2)
    row = study.db.execute("SELECT * FROM ee_benchmarks WHERE kind='BUYER_CROWD'").fetchone()
    assert row["ts"] == NOW + 1
    assert (t.mint, "BUYER_QUOTE") in observer.crowd_pending


def test_manifest_hardening_fields(study):
    p = study.plan
    assert (p["primary_position_usd"], p["primary_latency_seconds"], p["primary_horizon_seconds"]) == (
        4,
        10,
        300,
    )
    assert p["target_treatment_samples"] == 100 and p["max_enrollment_days"] == 30
    assert p["secondary_latency_seconds"] == [0.5, 2, 5] and p["no_optional_stopping"]
    assert p["cost_model"]["rent_policy"] == "RECOVERABLE_CAPITAL_LOCKUP"


async def test_sdk_live_reference_parity_on_fixed_state():
    from backend.app.early_edge_parity import sdk_compare, artifact_identity, string_ints

    path = Path("/tmp/crispy-early-quote-ref/node_modules")
    if __import__("os").getenv("EARLY_EDGE_SDK_REFERENCE") != "1" or not path.exists():
        pytest.skip("Opt-in isolated official SDK reference only; ordinary tests use pinned goldens")
    artifact_identity(path)
    assert string_ints(2**100) == str(2**100)
    for venue in ("PUMP", "PUMPSWAP"):
        vector = next(v for v in VECTORS if v["state"]["venue"] == venue)
        result = await sdk_compare(vector["state"], vector.get("budget", 26666666), path)
        assert result["match"]


def test_manual_budget_uses_entry_reference_not_preentry_sol_move(study):
    s = snap()
    study.enroll(s, NOW)
    r = refs(NOW + 10)
    r[WSOL]["usd"] = 200
    study.observe_state(state(s["mint"], NOW + 10), r, NOW + 10)
    entry = json.loads(study.db.execute("SELECT payload FROM ee_entries").fetchone()[0])
    assert entry["unit_usd"] == 200 / 1e9 and entry["quote_raw"] <= 20000000
    assert entry["entry_usd_reference"]["acquired_at"] == NOW + 10
    assert entry["quote_raw"] * entry["unit_usd"] + entry["cash_left_usd"] == pytest.approx(4)


def test_rent_ledger_excludes_lockup_and_charges_close_fee(study):
    s = snap()
    obs = state(s["mint"], NOW + 10)
    e = pump_buy(obs.data, quote_budget(4, 150, WSOL))
    e.update(unit_usd=150 / 1e9, cash_left_usd=4 - e["quote_raw"] * 150 / 1e9, rent_usd=0.3, state={})
    x = sell(obs.data, e["quantity"])
    o = result_costs(study.plan, e, x, 150 / 1e9, obs)
    ledger = {r["component"]: r for r in o["cost_ledger"]}
    assert ledger["base_ata_rent"]["classification"] == "RECOVERABLE_CAPITAL_LOCKUP"
    assert ledger["network_entry_exit_close"]["usd"] == 0.015
    assert o["net_return_pct"] - o["non_recovery_sensitivity_net_return_pct"] == pytest.approx(7.5)
    assert sum(
        row["usd"] or 0 for row in o["cost_ledger"] if row["classification"] != "RECOVERABLE_CAPITAL_LOCKUP"
    ) == pytest.approx(o["total_cost_usd"])
    assert study.plan["cost_model"]["additional_slippage_pct"] == 1


async def test_oracle_rejects_regressing_context_and_slow_batch(monkeypatch):
    # The first verified identity read cannot be combined with an older final bank.
    import backend.app.early_edge_quotes as quotes

    mint = str(Pubkey.new_unique())
    a = encode_account("BondingCurve", dict(quote_mint=ZERO), PUMP_PROGRAM)

    class Rpc:
        async def rpc(self, method, params):
            if method == "getAccountInfo":
                return dict(context={"slot": 100}, value=a)
            return dict(context={"slot": 99}, value=[None] * 5)

    with pytest.raises(QuoteUnavailable):
        await ResearchExecutionOracle(Rpc()).observe(mint)
    clock = iter([NOW, NOW + 5.001])
    monkeypatch.setattr(quotes.time, "time", lambda: next(clock))
    with pytest.raises(QuoteUnavailable, match="PROVIDER_GAP"):
        await ResearchExecutionOracle(Rpc()).observe(mint)


def test_attestation_rejects_mismatch_drift_missing_states(study):
    from backend.app.early_edge_parity import validate_attestation

    records = [
        dict(venue=v, mint=str(i), pool="pool" + str(i) if v == "PUMPSWAP" else None, match=True)
        for v in ("PUMP", "PUMPSWAP")
        for i in range(2)
        for _ in range(2)
    ]
    for i, r in enumerate(records):
        r.update(
            slot=100 + i,
            commitment="confirmed",
            acquired_at=NOW,
            account_hashes=["0" * 64] * 7,
            identity_address="diagnostic",
            python={"exit": "1"},
            official_sdk={"exit": "1"},
        )
    body = dict(
        records=records,
        usd_reference_preflight=refs(),
        source_hash=study.plan["identity"]["source_hash"],
        config_hash=study.plan["identity"]["config_hash"],
        completed_at=NOW,
        artifacts_verified=True,
        live_readonly=True,
    )
    from backend.app.early_edge import digest

    def signed(b):
        return dict(b, report_hash=digest(b))

    assert validate_attestation(study.plan, signed(body), NOW)
    bad = deepcopy(body)
    bad["records"][0]["match"] = False
    with pytest.raises(IntegrityError):
        validate_attestation(study.plan, signed(bad), NOW)
    with pytest.raises(IntegrityError):
        validate_attestation(study.plan, signed(dict(body, source_hash="drift")), NOW)
    with pytest.raises(IntegrityError):
        validate_attestation(study.plan, signed(body), NOW + 86401)


async def test_diagnostic_refuses_old_cohort_selection(monkeypatch):
    from scripts.early_edge_diagnostic import diagnostic

    monkeypatch.setenv("RADAR_COHORT", "prospective-20261019-2c58b1a49cc8")
    with pytest.raises(ValueError, match="selection forbidden"):
        await diagnostic(Settings(mode="OBSERVE"), 1, Path("/missing"), [], 1)

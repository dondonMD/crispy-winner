"""Synthetic risk sets and mocked quote providers; no market/cohort evidence."""
import asyncio
from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest
from solders.pubkey import Pubkey

from backend.app.config import Settings
from backend.app.early_edge import IntegrityError, canonical
from backend.app.early_edge_design import risk_set
from backend.app.early_edge_report import report
from backend.app.early_edge_telemetry import OperationalTelemetry
from backend.app.providers import SolanaProvider
from backend.tests.test_early_edge import (
    NOW, refs, snap, state, token, study as study,
)


def fixed_snapshot(label, action="EARLY_OPPORTUNITY"):
    fixture = token()
    fixture.mint = str(Pubkey.from_bytes(hashlib.sha256(label.encode()).digest()))
    for event in fixture.events:
        event.mint = fixture.mint
    return snap(fixture, action=action)


@pytest.mark.parametrize("early_factor,control_factor,sign", [(2, .5, 1), (.5, 2, -1)])
def test_matched_quotes_and_after_cost_comparison_preserve_winners_and_losers(
    study, early_factor, control_factor, sign, record_property
):
    cases = []
    for i in range(2):
        treatment = fixed_snapshot(f"synthetic-treatment:{i}")
        control = fixed_snapshot(f"synthetic-control:{i}", "DEVELOPING")
        assert risk_set(treatment, [control], study.plan) == [control]
        sid = study.enroll(treatment, NOW, controls=[control])
        pair = study.db.execute("SELECT * FROM ee_pairs WHERE treatment=?", (sid,)).fetchone()
        assert pair["control"] is not None and pair["reason"] == "MATCHED"
        cases.extend(((treatment, early_factor), (control, control_factor)))
    for snapshot, _ in cases:
        study.observe_state(state(snapshot["mint"], NOW + 10), refs(NOW + 10), NOW + 10)
    for snapshot, multiplier in cases:
        observed = state(snapshot["mint"], NOW + 300)
        data = observed.data
        data["effective_quote"] = int(data["effective_quote"] * multiplier)
        # Explicit synthetic quote state, not an inferred real transaction.
        study.observe_state(replace(observed, data_json=canonical(data)), refs(NOW + 300), NOW + 300)
    rows = [json.loads(r[0]) for r in study.db.execute("SELECT payload FROM ee_outcomes WHERE horizon=300")]
    assert len(rows) == 4 and all(r["status"] == "MEASURED" for r in rows)
    assert all(r["total_cost_usd"] > 0 for r in rows)
    assert any(r["net_return_pct"] < 0 for r in rows)
    study.expire(study.plan["created_at"] + 30 * 86400)
    result = report(study.path)
    assert result["matched_controls"] == 2 and result["primary_outcome_coverage"] == 1
    assert result["status"] == "INSUFFICIENT_SAMPLE"
    assert result["primary_bootstrap"]["paired_difference"] * sign > 0
    record_property("paired_difference", result["primary_bootstrap"]["paired_difference"])
    record_property("early_mean", result["horizons"]["300"]["early"]["mean"])
    record_property("control_mean", result["horizons"]["300"]["control"]["mean"])
    assert result == report(study.path)


def test_control_quote_missingness_remains_in_comparison_denominator(study):
    treatment = fixed_snapshot("synthetic-treatment")
    control = fixed_snapshot("synthetic-control", "DEVELOPING")
    study.enroll(treatment, NOW, controls=[control])
    study.observe_state(state(treatment["mint"], NOW + 10), refs(NOW + 10), NOW + 10)
    study.failure(control["mint"], "UNAVAILABLE_PROVIDER_GAP", NOW + 20)
    study.observe_state(state(treatment["mint"], NOW + 300), refs(NOW + 300), NOW + 300)
    study.expire(study.plan["created_at"] + 30 * 86400)
    result = report(study.path)
    assert result["primary_accounting_fraction"] == 1
    assert result["primary_outcome_coverage"] == .5
    assert result["primary_unavailable"] == 1
    assert result["horizons"]["300"]["control"]["n"] == 0
    assert result["primary_status_counts"]["UNAVAILABLE_PROVIDER_GAP"] == 1
    assert result["status"] != "EARLY_EDGE_SUPPORTED"


@pytest.mark.parametrize("bad", ["timestamp", "readiness", "units", "creator"])
def test_unfair_or_unsafe_control_cannot_be_enrolled(study, bad):
    treatment = fixed_snapshot("synthetic-treatment")
    control = fixed_snapshot("synthetic-control", "DEVELOPING")
    if bad == "timestamp":
        control["timestamp"] -= 1
        assert risk_set(treatment, [control], study.plan) == []
        with pytest.raises(IntegrityError):
            study.enroll(treatment, NOW, controls=[control])
        assert study.db.execute("SELECT count(*) FROM ee_pairs").fetchone()[0] == 0
        return
    if bad == "readiness":
        control["observation_readiness"]["ready"] = False
    if bad == "units":
        control["canonical_units_known"] = False
    if bad == "creator":
        control["features"]["creator_sell_volume"] = 1
    with pytest.raises(IntegrityError):
        study.enroll(treatment, NOW, controls=[control])
    assert study.db.execute("SELECT count(*) FROM ee_signals").fetchone()[0] == 0


async def test_primary_entry_progresses_after_background_occupies_shared_slots(monkeypatch):
    now = [NOW + 9]
    monkeypatch.setattr("backend.app.early_edge_telemetry.time.time", lambda: now[0])
    entered, release = asyncio.Event(), asyncio.Event()
    requests = []

    async def transport(request):
        requests.append(json.loads(request.content)["method"])
        entered.set()
        await release.wait()
        return httpx.Response(200, json={"result": 123})

    provider = SolanaProvider(client=httpx.AsyncClient(transport=httpx.MockTransport(transport)))
    provider.url = "https://synthetic.invalid"
    telemetry = OperationalTelemetry(Settings(), NOW)
    telemetry.signals["synthetic"] = dict(ts=NOW, markers={}, latencies={}, last_attempt=0)
    engine = SimpleNamespace(tokens={"synthetic": SimpleNamespace(graduation=None)})

    class Oracle:
        async def observe(self, mint, venue):
            requested = now[0]
            await provider.rpc("getSlot", [])
            return state(mint, now[0], requested=requested)

    reference = SimpleNamespace(snapshot=lambda: refs(now[0]))
    background = [asyncio.create_task(provider.rpc("getSlot", [])) for _ in range(2)]
    await entered.wait()
    now[0] = NOW + 10
    primary = asyncio.create_task(telemetry.probe_entries(Oracle(), reference, engine, now[0]))
    await asyncio.sleep(.05)
    assert telemetry.entry_pending(now[0])  # Scheduler prevents NEW background work.
    now[0] = NOW + 12
    release.set()
    await asyncio.gather(*background, primary)
    assert telemetry.signals["synthetic"]["latencies"]["10"] == "AVAILABLE"
    assert len(requests) == 3  # No unrestricted client or retry multiplication.
    assert telemetry.entry_attempts[-1]["requested_at"] >= NOW + 10
    assert telemetry.entry_attempts[-1]["acquired_at"] <= NOW + 20
    await provider.close()


@pytest.mark.parametrize("status", [429, 500])
async def test_failed_and_rate_limited_provider_keeps_unavailable_not_economic_zero(monkeypatch, status):
    now = [NOW + 10]
    monkeypatch.setattr("backend.app.early_edge_telemetry.time.time", lambda: now[0])
    requests = []

    def transport(request):
        requests.append(1)
        return httpx.Response(status, headers={"Retry-After": "2"})

    provider = SolanaProvider(client=httpx.AsyncClient(transport=httpx.MockTransport(transport)))
    provider.url = "https://synthetic.invalid"
    telemetry = OperationalTelemetry(Settings(), NOW)
    telemetry.signals["synthetic"] = dict(ts=NOW, markers={}, latencies={}, last_attempt=0)
    engine = SimpleNamespace(tokens={"synthetic": SimpleNamespace(graduation=None)})

    class Oracle:
        async def observe(self, *args):
            await provider.rpc("getSlot", [])
            pytest.fail("No state can be returned by this provider")

    for offset in (10, 12, 14, 21):
        now[0] = NOW + offset
        await telemetry.probe_entries(Oracle(), None, engine, now[0])
        if offset == 10:
            assert not provider.eligible()
    assert telemetry.signals["synthetic"]["latencies"]["10"] == "UNAVAILABLE_PROVIDER_GAP"
    assert len(requests) <= 3 and provider.health["errors"] >= 1
    if status == 429:
        assert provider.health["rate_limits"] >= 1
    assert all("net_return_pct" not in receipt and receipt["outcome"] != "ECONOMIC_ZERO_EXIT"
               for receipt in telemetry.entry_attempts)
    await provider.close()


async def test_quote_timeout_cancels_acquisition_and_keeps_missed_deadline_unavailable(monkeypatch):
    now = [NOW + 10]
    monkeypatch.setattr("backend.app.early_edge_telemetry.time.time", lambda: now[0])
    telemetry = OperationalTelemetry(Settings(), NOW)
    telemetry.signals["synthetic"] = dict(ts=NOW, markers={}, latencies={}, last_attempt=0)
    engine = SimpleNamespace(tokens={"synthetic": SimpleNamespace(graduation=None)})
    cancelled = []

    class Oracle:
        async def observe(self, *args):
            now[0] = NOW + 21
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)

    await telemetry.probe_entries(Oracle(), None, engine, NOW + 10)
    assert cancelled == [True]
    assert telemetry.signals["synthetic"]["latencies"]["10"] == "UNAVAILABLE_PROVIDER_GAP"
    assert telemetry.entry_attempts[-1]["outcome"] == "UNAVAILABLE_PROVIDER_GAP"
    assert "net_return_pct" not in telemetry.entry_attempts[-1]

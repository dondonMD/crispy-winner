"""Synthetic quote scheduling; no cohort and no network."""
from types import SimpleNamespace

import pytest

from backend.app.config import Settings
from backend.app.early_edge_scheduling import SamplerBudget, quote_success
from backend.app.early_edge_telemetry import OperationalTelemetry
from backend.app.early_edge_quotes import QuoteUnavailable


def test_python_success_and_reference_failure_predicates():
    assert quote_success({"quote_valid": True})
    assert quote_success({"match": True})
    assert not quote_success({"match": False})


def test_sampler_is_spread_across_rounds_and_never_exceeds_global_budget():
    budget = SamplerBudget(100, 21600, 120)
    assert budget.claim(100)
    assert not budget.claim(101)
    for second in range(101, 21700):
        budget.claim(second)
    assert budget.total == 120 and budget.per_round == 12
    assert budget.rounds == 10
    assert not budget.claim(999999)


def telemetry():
    t = OperationalTelemetry(Settings(), 100)
    t.signals["synthetic"] = dict(ts=100, markers={}, latencies={}, last_attempt=0)
    engine = SimpleNamespace(tokens={"synthetic": SimpleNamespace(graduation=None)})
    return t, engine


async def test_expired_entry_never_spends_http_and_stays_unavailable():
    t, engine = telemetry()

    class Oracle:
        async def observe(self, *args):
            pytest.fail("Expired work must not make a request")

    await t.probe_entries(Oracle(), None, engine, 121)
    assert t.signals["synthetic"]["latencies"]["10"] == "UNAVAILABLE_INFRASTRUCTURE"


async def test_unknown_units_keep_typed_reason_and_retries_bounded(monkeypatch):
    t, engine = telemetry()
    now = [110]
    monkeypatch.setattr("backend.app.early_edge_telemetry.time.time", lambda: now[0])
    calls = []

    class Oracle:
        async def observe(self, *args):
            calls.append(1)
            raise QuoteUnavailable("UNAVAILABLE_UNITS")

    for at in (110, 112, 114, 116):
        now[0] = at
        await t.probe_entries(Oracle(), None, engine, at)
    assert len(calls) == 3
    assert t.signals["synthetic"]["latencies"]["10"] == "UNAVAILABLE_UNITS"
    assert len(t.entry_attempts) == 3
    assert "synthetic" not in str(list(t.entry_attempts))


async def test_primary_deadline_precedes_secondary_and_background_yields(monkeypatch):
    t, engine = telemetry()
    t.signals["other"] = dict(ts=109, markers={}, latencies={}, last_attempt=0)
    engine.tokens["other"] = SimpleNamespace(graduation=None)
    monkeypatch.setattr("backend.app.early_edge_telemetry.time.time", lambda: 110)
    seen = []

    class Oracle:
        async def observe(self, mint, *args):
            seen.append(mint)
            raise QuoteUnavailable()

    assert t.entry_pending(110)
    await t.probe_entries(Oracle(), None, engine, 110)
    assert seen == ["synthetic"]
    assert t.entry_attempts[-1]["deadline"] == 120


async def test_exact_primary_boundary_uses_only_post_boundary_state(monkeypatch):
    t, engine = telemetry()
    monkeypatch.setattr("backend.app.early_edge_telemetry.time.time", lambda: 110)
    monkeypatch.setattr("backend.app.early_edge_telemetry.fx_value", lambda *a: 1)
    monkeypatch.setattr("backend.app.early_edge_telemetry.quote_budget", lambda *a: 4)
    monkeypatch.setattr("backend.app.early_edge_telemetry.pump_buy", lambda *a: (1, {}))

    class Oracle:
        async def observe(self, *a):
            return SimpleNamespace(requested_at=109.9, acquired_at=110, data={"quote_mint": "synthetic"})

    reference = SimpleNamespace(snapshot=lambda: {})
    await t.probe_entries(Oracle(), reference, engine, 110)
    assert "10" not in t.signals["synthetic"]["latencies"]

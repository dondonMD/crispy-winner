"""Synthetic operational counters do not enroll cohorts or invent quote availability."""

import json
from types import SimpleNamespace
from pathlib import Path
import pytest
import httpx
from backend.app.early_edge_telemetry import Distribution, OperationalTelemetry, track_http_errors
from backend.app.config import Settings


def test_distribution_is_bounded_and_reports_all_values():
    d = Distribution()
    for i in range(10000):
        d.add(i)
    assert len(d.bins) == 18 and sum(d.bins) == 10000
    assert d.report()["mean"] == 4999.5


def test_no_early_no_latency_fabrication_and_bounded_signals():
    t = OperationalTelemetry(Settings(), 100)
    assert t.report()["entry_availability"] == {}
    s = dict(timestamp=101, mint="x", curve_progress=20, age=80, features={"estimated_independent_buyers": 5})
    for i in range(65):
        t.early(dict(s, mint=str(i)), [])
    assert len(t.signals) == 64 and t.counts["diagnostic_probe_capacity"] == 1
    for mint, row in list(t.signals.items()):
        t.finish_signal(mint, row, 110)
    assert t.entry_counts["10:UNAVAILABLE_INFRASTRUCTURE"] == 64
    assert t.report()["cohort_created"] is False


async def test_entry_probe_rejects_pre_latency_observation():
    t = OperationalTelemetry(Settings(), 100)
    t.signals["x"] = dict(ts=100, markers={}, latencies={}, last_attempt=0)

    class Oracle:
        async def observe(self, *args):
            return SimpleNamespace(requested_at=109, acquired_at=110, data={"quote_mint": "bad"})

    reference = SimpleNamespace(snapshot=lambda: {})
    engine = SimpleNamespace(tokens={"x": SimpleNamespace(graduation=None)})
    await t.probe_entries(Oracle(), reference, engine, 110)
    assert "10:AVAILABLE" not in t.entry_counts


async def test_http_wrapper_preserves_response_and_raises_sanitized_counter():
    counts = {}
    from collections import Counter

    counts = Counter()

    async def handler(request):
        if request.url.path == "/error":
            raise httpx.ReadError("SYNTHETIC_SECRET")
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        detach = track_http_errors(client, counts)
        assert (await client.get("https://example.test/ok")).json() == {"ok": True}
        with pytest.raises(httpx.ReadError):
            await client.get("https://example.test/error")
        detach()
    assert counts == {"ReadError": 1}
    assert "SYNTHETIC_SECRET" not in json.dumps(counts)


def test_telemetry_has_no_database_or_execution_import():
    s = Path("backend/app/early_edge_telemetry.py").read_text()
    assert "Study(" not in s and "sqlite" not in s and "sendTransaction" not in s

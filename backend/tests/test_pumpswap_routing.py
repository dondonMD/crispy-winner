"""Complete transaction routing retains canonical ordinals, never guesses identity."""
import base64
import copy
import json

from solders.pubkey import Pubkey

from backend.app.pumpswap import VerifiedPool
from backend.tests.test_pumpswap_flow import POOL, MINT, USER, WSOL, notification, provider, wire

B = str(Pubkey.new_unique())
BMINT = str(Pubkey.new_unique())


def route():
    # Unknown discriminators still occupy ordinal slots in the complete logs.
    ignored = base64.b64encode(bytes(8)).decode()
    return notification(ignored, wire(), ignored, wire("SellEvent", pool=B))


def test_mixed_pool_accepts_only_matching_original_ordinal():
    p, events, gaps = provider()
    p.handle(route())
    assert not gaps and len(events) == 1
    assert events[0].side == "buy" and events[0].evidence["event_ordinal"] == 2
    assert events[0].event_id.endswith(f":2:{POOL}")
    assert p.health["mixed_pool_notifications"] == p.health["foreign_events_ignored"] == 1
    assert p.health["failure_categories"]["pool_identity"] == 0


def test_both_subscriptions_route_separately_and_replay_is_deduplicated():
    p, events, gaps = provider()
    record = VerifiedPool(B, BMINT, WSOL)
    for mapping in (p.pools, p.registry):
        mapping[B] = record
    p.active[11] = B
    p.since[B] = p.since[POOL]
    a = route()
    b = copy.deepcopy(a)
    b["params"]["subscription"] = 11
    p.handle(a)
    p.handle(b)
    p.disconnect()
    # Restoration/ACK mechanisms themselves are covered by production transport tests.
    records = [VerifiedPool(POOL, MINT, WSOL), record]
    p.eligible = lambda: records
    p.pools = {r.address: r for r in records}
    p.selection()
    p.pending = {1: ("subscribe", POOL, 0), 2: ("subscribe", B, 0)}
    p.handle({"id": 1, "result": 10})
    p.handle({"id": 2, "result": 11})
    p.handle(a)
    p.handle(b)
    assert len(events) == 2 and p.health["duplicates"] == 2
    assert [(e.mint, e.side, e.evidence["event_ordinal"]) for e in events] == [(MINT, "buy", 2), (BMINT, "sell", 4)]
    assert len(gaps) == 2  # Actual disconnect only; routing never causes gaps.
    assert p.health["decode_failures"] == 0


def test_foreign_only_and_match_only_complete_notifications():
    p, events, gaps = provider()
    start = p.since[POOL]
    p.handle(notification(wire(pool=B)))
    assert not events and not gaps and p.since[POOL] == start
    assert p.health["foreign_only_notifications"] == 1
    p.handle(notification(wire()))
    assert len(events) == 1 and not gaps
    assert p.health["pool_identity_observations"]["MATCH_ONLY"] == 1


def test_malformed_foreign_identity_and_truncation_never_filter_away_gaps():
    p, events, gaps = provider()
    invalid = base64.b64encode(base64.b64decode(wire(pool=B))[:20]).decode()
    p.handle(notification(wire(), invalid))
    assert not events and len(gaps) == 1
    n = route()
    n["params"]["result"]["value"]["logs"].append("Log truncated")
    p.handle(n)
    assert not events and len(gaps) == 2
    assert p.health["truncations"] == 1


def test_conflicting_registry_fails_closed_and_ends_coverage():
    p, events, gaps = provider()
    p.registry[POOL] = VerifiedPool(POOL, BMINT, WSOL)
    p.handle(route())
    assert not events and gaps == [MINT] and POOL not in p.since
    assert p.health["true_identity_failures"] == 1
    assert p.health["failure_categories"]["pool_identity"] == 1


def test_unknown_units_remain_unavailable_and_categories_bounded():
    p, events, gaps = provider(str(Pubkey.new_unique()))
    p.handle(notification(wire()))
    assert events[0].currency == "unknown" and not events[0].evidence["units_valid"]
    assert gaps == [MINT]
    assert p.health["invalid_unit_quote_categories"] == {"WSOL": 0, "USDC": 0, "OTHER": 1}
    assert set(p.health["quote_observation_categories"]) == {"WSOL", "USDC", "OTHER"}


def test_routing_examples_bounded_and_wallet_free():
    p, _, _ = provider()
    for _ in range(100):
        p.handle(route())
    examples = p.health["pool_identity_examples"]
    assert len(examples) == 3 and all(len(x["events"]) <= 32 for x in examples)
    text = json.dumps(examples)
    assert USER not in text
    assert route()["params"]["result"]["value"]["signature"] not in text


def test_registry_change_during_parse_is_checked_before_submission(monkeypatch):
    p, events, gaps = provider()
    original = p.parse_logs
    def changed(logs):
        decoded = original(logs)
        p.registry[POOL] = VerifiedPool(POOL, BMINT, WSOL)
        return decoded
    monkeypatch.setattr(p, "parse_logs", changed)
    p.handle(route())
    assert not events and gaps == [MINT]
    assert p.health["true_identity_failures"] == 1

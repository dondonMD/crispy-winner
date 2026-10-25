from collections import OrderedDict, deque, Counter
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
import heapq
import math
import time
from pydantic import BaseModel, Field


class State(StrEnum):
    DISCOVERED = "DISCOVERED"
    SCREENING = "SCREENING"
    WATCHING = "WATCHING"
    MATURING = "MATURING"
    NEAR_GRADUATION = "NEAR_GRADUATION"
    GRADUATING = "GRADUATING"
    GRADUATED = "GRADUATED"
    POST_GRAD_OBSERVATION = "POST_GRAD_OBSERVATION"
    ENTRY_CANDIDATE = "ENTRY_CANDIDATE"
    COOLING = "COOLING"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


_STATE_PRIORITIES = MappingProxyType(
    {
        State.GRADUATING: 100,
        State.GRADUATED: 100,
        State.POST_GRAD_OBSERVATION: 95,
        State.ENTRY_CANDIDATE: 100,
        State.NEAR_GRADUATION: 90,
        State.MATURING: 70,
        State.WATCHING: 30,
    }
)


TRANSITIONS = {
    State.DISCOVERED: {State.SCREENING},
    State.SCREENING: {State.WATCHING, State.REJECTED, State.GRADUATING},
    State.WATCHING: {State.MATURING, State.GRADUATING, State.REJECTED, State.EXPIRED},
    State.MATURING: {State.NEAR_GRADUATION, State.WATCHING, State.GRADUATING, State.REJECTED, State.EXPIRED},
    State.NEAR_GRADUATION: {State.MATURING, State.GRADUATING, State.COOLING, State.REJECTED, State.EXPIRED},
    State.GRADUATING: {State.GRADUATED, State.REJECTED},
    State.GRADUATED: {State.POST_GRAD_OBSERVATION, State.REJECTED},
    State.POST_GRAD_OBSERVATION: {State.ENTRY_CANDIDATE, State.COOLING, State.REJECTED, State.EXPIRED},
    State.ENTRY_CANDIDATE: {State.POST_GRAD_OBSERVATION, State.COOLING, State.REJECTED},
    State.COOLING: {State.POST_GRAD_OBSERVATION, State.GRADUATING, State.REJECTED, State.EXPIRED},
    State.REJECTED: {State.EXPIRED},
    State.EXPIRED: set(),
}


class MarketEvent(BaseModel):
    mint: str = Field(min_length=1, max_length=64)
    ts: float = Field(ge=0, allow_inf_nan=False)
    source: str = Field(max_length=32)
    kind: str = Field(pattern="^(create|trade|market|migration|security|curve)$")
    event_id: str = Field(max_length=150)
    name: str = Field(default="", max_length=100)
    symbol: str = Field(default="", max_length=30)
    creator: str = Field(default="", max_length=64)
    wallet: str = Field(default="", max_length=64)
    side: str = Field(default="", pattern="^(|buy|sell)$")
    volume: float = Field(default=0, ge=0, allow_inf_nan=False)
    currency: str = Field(default="unknown", max_length=10)
    price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    market_cap: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    liquidity: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    curve_progress: float | None = Field(default=None, ge=0, le=100)
    signature: str = Field(default="", max_length=150)
    pair: str = Field(default="", max_length=64)
    evidence: dict = Field(default_factory=dict)


class Deduplicator:
    def __init__(self, maximum=10000):
        self.seen: OrderedDict[str, None] = OrderedDict()
        self.maximum = maximum

    def accept(self, key):
        if key in self.seen:
            return False
        self.seen[key] = None
        if len(self.seen) > self.maximum:
            self.seen.popitem(last=False)
        return True


class PriorityBuffer:
    """Bounded synchronous buffer consumed by a single asyncio event loop."""

    def __init__(self, maximum):
        self.maximum = maximum
        self.submitted: Counter = Counter()
        self.accepted: Counter = Counter()
        self.rejected: Counter = Counter()
        self.evicted: Counter = Counter()
        self.in_processing: Counter = Counter()
        self.heap: list = []
        self.sequence = 0
        self.created = time.time()
        self.arrivals: dict[int, float] = {}
        self.peak_depth = 0
        self.accepted_trades = 0
        self.wait_edges = (.001, .01, .05, .1, .5, 1, 2, 5, 10, 20)
        self.wait_counts = [0] * 11
        self.stale_while_queued = 0
        self.trades_stale_while_queued = 0
        self.depth_samples: deque[dict] = deque(maxlen=300)
        self.last_sample = 0.0
        self.dropped = 0
        self.dropped_trades = 0
        self.dropped_critical = 0
        self.trade_gaps: dict[str, float] = {}
        self.affected: deque[str] = deque(maxlen=1000)

    def put(self, event, priority):
        self.submitted[event.kind] += 1
        self.sequence += 1
        item = (priority, self.sequence, event)
        if len(self.heap) >= self.maximum:
            self.dropped += 1
            if priority <= self.heap[0][0]:
                self.rejected[event.kind] += 1
                self.record_drop(event)
                self.affected.append(event.mint)
                return False
            removed = heapq.heapreplace(self.heap, item)
            self.arrivals.pop(removed[1], None)
            self.record_accept(item)
            self.evicted[removed[2].kind] += 1
            self.record_drop(removed[2])
            self.affected.append(removed[2].mint)
            return True
        heapq.heappush(self.heap, item)
        self.record_accept(item)
        return True

    def record_accept(self, item):
        self.accepted[item[2].kind] += 1
        self.arrivals[item[1]] = time.time()
        self.peak_depth = max(self.peak_depth, len(self.heap))
        self.accepted_trades += item[2].kind == "trade"

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        return {"queue_wait_upper_edges": list(self.wait_edges) + ["INF"],
                "queue_wait_counts": list(self.wait_counts), "peak_depth": self.peak_depth,
                "oldest_event_age": max((now - item[2].ts for item in self.heap), default=0),
                "oldest_trade_age": max((now - item[2].ts for item in self.heap if item[2].kind == "trade"), default=0),
                "oldest_queue_wait": max((now - at for at in self.arrivals.values()), default=0),
                "stale_while_queued": self.stale_while_queued,
                "trades_stale_while_queued": self.trades_stale_while_queued,
                "accepted_trades": self.accepted_trades,
                "accepted_trade_rate": self.accepted_trades / max(1, now - self.created),
                "depth_samples": list(self.depth_samples)}

    def sample_depth(self, now):
        if now - self.last_sample >= 1:
            self.depth_samples.append({"seconds": round(now - self.created, 1), "depth": len(self.heap)})
            self.last_sample = now

    def record_drop(self, event):
        import time
        if event.kind == "trade":
            self.dropped_trades += 1
            self.trade_gaps[event.mint] = time.time()
            if len(self.trade_gaps) > self.maximum:
                del self.trade_gaps[next(iter(self.trade_gaps))]
        else:
            self.dropped_critical += 1

    def drain(self, limit=100, max_age=20):
        # Selected by priority, processed chronologically to preserve feature windows.
        selected = sorted(self.heap, key=lambda x: (-x[0], x[1]))[:limit]
        now = time.time()
        for _, sequence, event in selected:
            self.in_processing[event.kind] += 1
            arrived = self.arrivals.pop(sequence, now)
            self.wait_counts[sum(now - arrived > edge for edge in self.wait_edges)] += 1
            if abs(arrived - event.ts) <= max_age < now - event.ts:
                self.stale_while_queued += 1
                self.trades_stale_while_queued += event.kind == "trade"
        identities = {x[1] for x in selected}
        self.heap = [x for x in self.heap if x[1] not in identities]
        heapq.heapify(self.heap)
        return [x[2] for x in sorted(selected, key=lambda x: (x[2].ts, x[1]))]


@dataclass
class Token:
    mint: str
    name: str
    symbol: str
    created: float
    creator: str = ""
    state: State = State.DISCOVERED
    events: deque = field(default_factory=lambda: deque(maxlen=500))
    history: deque = field(default_factory=lambda: deque(maxlen=300))
    security: dict = field(
        default_factory=lambda: {
            "data_quality": "UNKNOWN",
            "risk_score": 100,
            "hard_failures": [],
            "warnings": ["Security unknown"],
        }
    )
    last_event: float = 0
    flow_venue: str = "PUMP"
    migration_pool: str = ""
    flow_epoch: float = 0
    postgrad_gap: float = 0
    last_trade: float = 0
    verified_quote_mint: str = ""
    trade_gap: float = 0
    # Exact timestamp of the most recent observed trade evicted from memory.
    # Not a transport/recovery gap; inclusive windows remain incomplete until it ages out.
    buffer_loss_at: float | None = None
    trade_tracking_since: float = 0
    operational_evidence: dict = field(default_factory=dict)  # Passive, current-instance counters only.
    last_price: float = 0
    last_liquidity: float = 0
    last_market_cap: float = 0
    market_source: str = ""
    cap_source: str = ""
    curve_history: deque = field(default_factory=lambda: deque(maxlen=32))
    price: float | None = None
    liquidity: float | None = None
    market_cap: float | None = None
    graduation: float | None = None
    curve_progress: float | None = None
    curve_peak_progress: float | None = None
    grad_high: float = 0
    grad_low: float = math.inf
    last_signal: float = 0
    last_analysis: float = 0
    viability_key: tuple | None = None
    last_security: float = 0
    last_security_attempt: float = 0
    last_curve_attempt: float = 0
    last_curve: float = 0
    launch_metadata: dict = field(default_factory=dict)
    degraded: bool = False
    disagreement: bool = False
    source_prices: dict = field(default_factory=dict)
    features: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)
    decision: dict = field(default_factory=lambda: {"decision": "WAIT", "reasons": ["Insufficient evidence"]})
    viability: dict = field(default_factory=dict)

    def transition(self, new):
        if new not in TRANSITIONS[self.state]:
            raise ValueError(f"Invalid transition {self.state} → {new}")
        previous = self.state
        self.state = new
        return previous

    def priority(self):
        return (
            _STATE_PRIORITIES.get(self.state, 0),
            self.curve_progress if self.curve_progress is not None else -1,
            self.scores.get("maturity", 0),
            self.mint,
        )

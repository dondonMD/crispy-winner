from collections import OrderedDict, deque
from dataclasses import dataclass, field
from enum import StrEnum
import heapq
import math
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


TRANSITIONS = {
    State.DISCOVERED: {State.SCREENING},
    State.SCREENING: {State.WATCHING, State.REJECTED, State.GRADUATING},
    State.WATCHING: {State.MATURING, State.GRADUATING, State.REJECTED, State.EXPIRED},
    State.MATURING: {State.NEAR_GRADUATION, State.WATCHING, State.GRADUATING, State.REJECTED, State.EXPIRED},
    State.NEAR_GRADUATION: {State.GRADUATING, State.COOLING, State.REJECTED, State.EXPIRED},
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
    kind: str = Field(pattern="^(create|trade|market|migration|security)$")
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
        self.heap: list = []
        self.sequence = 0
        self.dropped = 0
        self.affected: deque[str] = deque(maxlen=1000)

    def put(self, event, priority):
        self.sequence += 1
        item = (priority, self.sequence, event)
        if len(self.heap) >= self.maximum:
            self.dropped += 1
            if priority <= self.heap[0][0]:
                self.affected.append(event.mint)
                return False
            removed = heapq.heapreplace(self.heap, item)
            self.affected.append(removed[2].mint)
            return True
        heapq.heappush(self.heap, item)
        return True

    def drain(self, limit=100):
        # Selected by priority, processed chronologically to preserve feature windows.
        selected = sorted(self.heap, key=lambda x: (-x[0], x[1]))[:limit]
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
    last_trade: float = 0
    last_price: float = 0
    last_liquidity: float = 0
    price: float | None = None
    liquidity: float | None = None
    market_cap: float | None = None
    graduation: float | None = None
    curve_progress: float | None = None
    grad_high: float = 0
    grad_low: float = math.inf
    last_signal: float = 0
    last_security: float = 0
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
            {
                State.GRADUATING: 100,
                State.GRADUATED: 100,
                State.POST_GRAD_OBSERVATION: 95,
                State.ENTRY_CANDIDATE: 100,
                State.NEAR_GRADUATION: 90,
                State.MATURING: 70,
                State.WATCHING: 30,
            }.get(self.state, 0),
            self.scores.get("maturity", 0),
            self.mint,
        )

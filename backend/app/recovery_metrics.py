"""Bounded scheduling aggregates; never retain transaction identities."""
from collections import deque
import math
import time


class RecoveryMetrics:
    SAMPLE_LIMIT = 1024
    RATE_LIMIT = 8192

    def __init__(self):
        self.samples: dict[str, deque[float]] = {name: deque(maxlen=self.SAMPLE_LIMIT) for name in
                        ("queue_wait", "total_latency", "rpc_latency", "provider_wait", "http_latency")}
        self.rates: dict[str, deque[float]] = {name: deque(maxlen=self.RATE_LIMIT) for name in ("arrivals", "completions")}
        self.maxima = {name: dict.fromkeys((1, 5, 10), 0) for name in self.rates}
        self.rate_saturations = 0
        self.extrema: dict[str, tuple[float, float]] = {}

    def sample(self, name, value):
        value = max(0, value)
        self.samples[name].append(value)
        low, high = self.extrema.get(name, (value, value))
        self.extrema[name] = (min(low, value), max(high, value))

    def tick(self, name):
        now = time.monotonic()
        queue = self.rates[name]
        while queue and queue[0] < now - 10:
            queue.popleft()
        if len(queue) == self.RATE_LIMIT:
            self.rate_saturations += 1
        queue.append(now)
        for seconds in (1, 5, 10):
            self.maxima[name][seconds] = max(self.maxima[name][seconds],
                                            sum(t >= now - seconds for t in queue))

    def snapshot(self):
        result = {}
        for name, samples in self.samples.items():
            values = sorted(samples)
            result[name + "_seconds"] = ({"samples": len(values), "min": self.extrema[name][0],
                "median": values[(len(values) - 1) // 2],
                "p95": values[math.ceil(len(values) * .95) - 1], "max": self.extrema[name][1]} if values else {})
        return {**result, "rolling_max_counts": self.maxima, "sample_limit": self.SAMPLE_LIMIT,
                "rate_sample_limit": self.RATE_LIMIT, "rate_saturations": self.rate_saturations}

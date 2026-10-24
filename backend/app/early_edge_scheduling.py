"""Diagnostic-only work budgets, independent of strategy/cohort eligibility."""
import math


def quote_success(record):
    return record.get("quote_valid", record.get("match", False)) is True


class SamplerBudget:
    def __init__(self, started, seconds, maximum):
        self.started, self.maximum = started, maximum
        self.interval = max(180, seconds / max(1, maximum // 12))
        self.rounds = max(1, math.ceil(seconds / self.interval))
        self.per_round = math.ceil(maximum / self.rounds)
        self.round = -1
        self.used = 0
        self.total = 0
        self.next_at = started

    def available(self, now):
        current = int((now - self.started) // self.interval)
        if current != self.round:
            self.round, self.used = current, 0
            self.next_at = self.started + current * self.interval
        return self.total < self.maximum and self.used < self.per_round and now >= self.next_at

    def claim(self, now):
        if not self.available(now):
            return False
        self.used += 1
        self.total += 1
        self.next_at = now + self.interval / self.per_round
        return True

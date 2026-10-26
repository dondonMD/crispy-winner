"""Bounded one-product FX selection. Never validates or manufactures a token price."""

from collections import Counter
import math

from backend.app.early_edge import fx_value
from backend.app.early_edge_quotes import WSOL, USDC, QuoteUnavailable

VERSION = "fx-fresh-demand-fair-1"
PRODUCTS = ((WSOL, "SOL-USD"), (USDC, "USDCUSD"))


class FxSelection:
    def __init__(self):
        self.missed = dict.fromkeys((q for q, _ in PRODUCTS), 0)
        self.counts = {
            q: Counter(
                dict.fromkeys(
                    (
                        "selected",
                        "fresh_reused",
                        "interval_skipped",
                        "cooldown_skipped",
                        "budget_wait_skipped",
                        "budget_skipped",
                        "not_needed",
                    ),
                    0,
                )
            )
            for q, _ in PRODUCTS
        }
        self.demand = dict.fromkeys(self.missed, 0)
        self.rounds = self.mixed_rounds = self.clock_rejections = 0
        self.last_time = None
        self.last_selected = None
        self.status = dict.fromkeys(self.missed, "NOT_OBSERVED")

    def select(self, demand, cache, last_attempt, now, *, cooldown_until=0, limiter_wait=0):
        if (
            not isinstance(demand, dict)
            or not set(demand) <= set(self.missed)
            or any(type(n) is not int or not 1 <= n <= 25 for n in demand.values())
            or sum(demand.values()) > 25
        ):
            raise ValueError("Invalid validated FX demand")
        self.rounds += 1
        self.last_selected = None
        self.demand = {q: demand.get(q, 0) for q in self.missed}
        if not math.isfinite(now) or self.last_time is not None and now < self.last_time:
            self.status = dict.fromkeys(self.missed, "CLOCK_INVALID")
            self.clock_rejections += 1
            return None
        self.last_time = now
        eligible = []
        for quote, _ in PRODUCTS:
            c = self.counts[quote]
            if quote not in demand:
                self.missed[quote] = 0
                self.status[quote] = "NOT_NEEDED"
                c["not_needed"] += 1
                continue
            try:
                fx_value(cache, quote, now)  # Exact existing validity predicate.
                fresh = True
            except (QuoteUnavailable, KeyError, TypeError, ValueError):
                fresh = False
            if fresh:
                self.missed[quote] = 0
                self.status[quote] = "FRESH_REUSED"
                c["fresh_reused"] += 1
            elif cooldown_until > now:
                self.status[quote] = "COOLDOWN_SKIP"
                c["cooldown_skipped"] += 1
            elif not math.isfinite(limiter_wait) or limiter_wait >= 2:
                self.status[quote] = "LIMITER_BUDGET_SKIP"
                c["budget_wait_skipped"] += 1
            elif now - last_attempt.get(quote, 0) < 10:
                self.status[quote] = "INTERVAL_SKIP"
                c["interval_skipped"] += 1
            else:
                eligible.append(quote)
        if not eligible:
            return None
        mixed = len(eligible) == 2
        if mixed:
            self.mixed_rounds += 1
        forced = [q for q in eligible if self.missed[q] >= 2]
        pool = forced or eligible
        # Oldest attempt, then fixed SOL/USDC order, resolves equal demand/misses.
        selected = max(
            pool,
            key=lambda q: (
                self.missed[q] if forced else demand[q],
                -last_attempt.get(q, 0),
                -list(self.missed).index(q),
            ),
        )
        for quote in eligible:
            if quote == selected:
                self.missed[quote] = 0
                self.status[quote] = "SELECTED"
                self.counts[quote]["selected"] += 1
            elif mixed:
                self.missed[quote] = min(2, self.missed[quote] + 1)
                self.status[quote] = "BUDGET_SKIP"
                self.counts[quote]["budget_skipped"] += 1
        self.last_selected = dict(PRODUCTS)[selected]
        return selected

    def snapshot(self):
        return dict(
            version=VERSION,
            rounds=self.rounds,
            mixed_eligible_rounds=self.mixed_rounds,
            clock_rejections=self.clock_rejections,
            last_selected=self.last_selected,
            per_product={
                name: dict(
                    self.counts[q],
                    validated_states=self.demand[q],
                    last_selection_status=self.status[q],
                    missed_eligible_mixed_rounds=self.missed[q],
                )
                for q, name in PRODUCTS
            },
        )

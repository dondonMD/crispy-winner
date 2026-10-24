"""Bounded operational accounting; never supplies strategy or trade evidence."""

from collections import Counter
import time


class EventAccounting:
    def __init__(self):
        self.terminal: Counter = Counter()
        self.persisted: Counter = Counter()
        self.process_seconds = 0.0
        self.process_max_seconds = 0.0
        self.last_tick = time.time()
        self.observation_gaps = 0
        self.largest_tick_gap = 0.0

    def finish(self, kind, reason, elapsed):
        # kind and reason come from fixed internal enums, never from payload text.
        self.terminal[(kind, reason)] += 1
        self.process_seconds += elapsed
        self.process_max_seconds = max(self.process_max_seconds, elapsed)

    def snapshot(self, queue):
        kinds = ("create", "trade", "market", "migration", "security", "curve")
        rows = {}
        for kind in kinds:
            terminal = {reason: n for (k, reason), n in self.terminal.items() if k == kind}
            pending = sum(item[2].kind == kind for item in queue.heap)
            active = queue.in_processing[kind]
            rows[kind] = dict(
                submitted=queue.submitted[kind], accepted=queue.accepted[kind],
                rejected_incoming=queue.rejected[kind], evicted_accepted=queue.evicted[kind],
                pending=pending, in_processing=active, terminal=terminal,
                persisted=self.persisted[kind],
                reconciled=(queue.submitted[kind] == queue.accepted[kind] + queue.rejected[kind]
                            and queue.accepted[kind] == queue.evicted[kind] + pending + active
                            + sum(terminal.values())),
            )
        return dict(events=rows, process_seconds=self.process_seconds,
                    process_max_seconds=self.process_max_seconds,
                    observation_gaps=self.observation_gaps, largest_tick_gap=self.largest_tick_gap)

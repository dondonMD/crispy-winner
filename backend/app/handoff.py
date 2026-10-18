"""Read-only, bounded post-grad handoff diagnostics. No provider calls or policy."""
from collections import OrderedDict, deque
from copy import deepcopy

STAGES = ("MIGRATION_PENDING", "LIFECYCLE_INELIGIBLE", "VENUE_NOT_PUMPSWAP",
          "MIGRATION_POOL_HINT_MISSING", "SECURITY_NOT_ATTEMPTED", "SECURITY_PENDING",
          "POOL_NOT_VERIFIED", "POOL_IDENTITY_INCOMPLETE", "WSS_DISCONNECTED",
          "SELECTION_PENDING", "CAPACITY_LIMITED", "ACK_PENDING", "QUOTE_UNITS_UNAVAILABLE",
          "COVERAGE_BUILDING", "SAMPLES_INSUFFICIENT", "TRADE_UNITS_UNAVAILABLE",
          "TRADE_STALE", "INCOMPLETE_EVIDENCE", "CURRENT", "NO_LONGER_TRACKED")


class HandoffTrace:
    maximum = 100
    history_limit = 32

    def __init__(self):
        self.records: OrderedDict[str, dict] = OrderedDict()
        self.evicted_candidates = 0
        self.trimmed_history = 0

    def observe(self, status, now, event="snapshot", reason=""):
        mint = status["mint"]
        stage = status["stage"]
        if stage not in STAGES:
            raise ValueError("Unknown handoff stage")
        previous = self.records.get(mint)
        fields = ("stage", "state", "security_quality", "security_attempt_at", "security_applied_at",
                  "verified_pool_count", "eligible_pool_count", "selected_pool_count", "acked_pool_count", "decision")
        changed = previous is None or any(previous.get(k) != status.get(k) for k in fields)
        history = previous["history"] if previous else deque(maxlen=self.history_limit)
        if changed or event != "snapshot":
            self.trimmed_history += len(history) == self.history_limit
            history.append({"at": now, "event": event[:48], "stage": stage, "state": status["state"],
                            "reason": str(reason)[:240]})
        self.records[mint] = {**status, "updated_at": now, "history": history}
        if changed or event != "snapshot":
            self.records.move_to_end(mint)
        while len(self.records) > self.maximum:
            self.records.popitem(last=False)
            self.evicted_candidates += 1

    def snapshot(self, tracked, now):
        for mint, record in self.records.items():
            if mint not in tracked and record["stage"] != "NO_LONGER_TRACKED":
                record["stage"] = "NO_LONGER_TRACKED"
                self.trimmed_history += len(record["history"]) == self.history_limit
                record["history"].append({"at": now, "event": "removed", "stage": "NO_LONGER_TRACKED",
                                           "state": record["state"], "reason": "Candidate no longer tracked"})
        return {"limit": self.maximum, "history_limit": self.history_limit,
                "retained_candidates": len(self.records), "evicted_candidates": self.evicted_candidates,
                "trimmed_history_entries": self.trimmed_history,
                "counts": {stage: sum(r["stage"] == stage for r in self.records.values()) for stage in STAGES},
                "records": [deepcopy({**r, "history": list(r["history"])}) for r in self.records.values()]}

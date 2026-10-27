"""Opt-in, bounded smoke telemetry. Never supplies evidence to the engine."""

from collections import deque
import json
import math
import time


KINDS = ("create", "trade")
CAUSES = ("already_old_at_dispatch", "old_before_admission", "old_in_queue",
          "old_after_selection", "future_dated", "clock_irregular", "provenance_unavailable",
          "selection_boundary_ambiguous")
STAGES = ("dispatch_age", "admission_age", "selection_age", "processing_age",
          "dispatch_to_admission", "queue_residence", "selection_to_start")
EDGES = (-20, -1, 0, .001, .01, .1, .5, 1, 5, 20, 60)
MAX_COUNT = (1 << 63) - 1
SECTION_BYTES = 16384


class SmokeTiming:
    def __init__(self, queue):
        self.queue = queue
        self.limit = min(1100, queue.maximum + 100)
        self.records: dict[int, dict] = {}
        self.ready: deque[int] = deque()
        self.dispatch: tuple[float, float] | None = None
        self.failures = 0
        self.omitted = 0
        self.unresolved_shutdown = dict.fromkeys(KINDS, 0)
        self.missing_dispatch = dict.fromkeys(KINDS, 0)
        self.stale = {kind: dict.fromkeys(CAUSES, 0) for kind in KINDS}
        self.histograms = {kind: {stage: [0] * (len(EDGES) + 1) for stage in STAGES} for kind in KINDS}
        self.peak = 0

    def failure(self):
        self.failures = min(MAX_COUNT, self.failures + 1)

    def safe(self, name, *args):
        try:
            return getattr(self, name)(*args)
        except Exception:
            self.failure()
            return None

    @staticmethod
    def clock():
        return (time.time(), time.monotonic())

    def sample(self, kind, stage, value):
        if not math.isfinite(value):
            raise ValueError("Invalid diagnostic duration")
        bucket = sum(value > edge for edge in EDGES)
        counts = self.histograms[kind][stage]
        counts[bucket] = min(MAX_COUNT, counts[bucket] + 1)

    def admitted(self, seq, event, dropped_seq):
        if dropped_seq is not None:
            self.records.pop(dropped_seq, None)
        if event.kind not in KINDS:
            return
        if len(self.records) >= self.limit:
            self.omitted = min(MAX_COUNT, self.omitted + 1)
            return
        admitted = self.clock()
        if self.dispatch is None:
            self.missing_dispatch[event.kind] = min(MAX_COUNT, self.missing_dispatch[event.kind] + 1)
        self.records[seq] = dict(kind=event.kind, object=id(event), source=event.ts,
                                 dispatch=self.dispatch, admitted=admitted, selected=None, started=None)
        self.peak = max(self.peak, len(self.records))

    def selected(self, events, before):
        # Original drain has removed selected sequence IDs from its arrivals map.
        selected = [(seq, value) for seq, value in self.records.items()
                    if value["selected"] is None and seq not in self.queue.arrivals]
        selected.sort(key=lambda pair: (pair[1]["source"], pair[0]))
        expected = [id(e) for e in events if e.kind in KINDS]
        if [r["object"] for _, r in selected] != expected:
            self.failure()  # Missing/omitted metadata cannot claim full attribution.
        clock = self.clock()
        for seq, value in selected:
            value["selected"] = clock
            value["selection_before"] = before
            self.ready.append(seq)

    def started(self, event, now, queued):
        if not queued or event.kind not in KINDS:
            return None
        if not self.ready:
            return None
        seq = self.ready[0]
        if self.records[seq]["object"] != id(event):
            self.failure()
            return None
        self.ready.popleft()
        wall, mono = self.clock()
        self.records[seq]["started"] = (now if now is not None else wall, mono)
        return seq

    def finished(self, seq, event, queued, reason, max_age):
        if not queued or event.kind not in KINDS:
            return
        record = self.records.pop(seq, None)
        cause = "provenance_unavailable"
        if record is not None:
            stamps = [record[k] for k in ("dispatch", "admitted", "selected", "started")]
            for name, stamp in zip(STAGES[:4], stamps):
                if stamp is not None:
                    self.sample(event.kind, name, stamp[0] - record["source"])
            irregular = False
            for name, left, right in zip(STAGES[4:], stamps, stamps[1:]):
                if left is not None and right is not None:
                    wall = right[0] - left[0]
                    elapsed = right[1] - left[1]
                    self.sample(event.kind, name, elapsed)
                    # Diagnostic-only divergence tolerance, never a freshness allowance.
                    irregular |= wall < 0 or elapsed < 0 or abs(wall - elapsed) > .5
            if irregular:
                cause = "clock_irregular"
            elif any(s is not None and s[0] - event.ts < -max_age for s in stamps):
                cause = "future_dated"
            elif all(s is not None for s in stamps):
                cause = next((name for name, stamp in zip(CAUSES[:4], stamps)
                              if stamp[0] - event.ts > max_age), "provenance_unavailable")
                before = record.get("selection_before")
                if cause == "old_in_queue":
                    if before is None:
                        cause = "provenance_unavailable"
                    elif before[0] - event.ts <= max_age < stamps[2][0] - event.ts:
                        cause = "selection_boundary_ambiguous"
        if reason == "stale":
            self.stale[event.kind][cause] = min(MAX_COUNT, self.stale[event.kind][cause] + 1)

    def close(self):
        # Native accounting supplies cancellation/shutdown dispositions. Do not guess
        # an event-specific terminal reason for metadata without a processing callback.
        for value in self.records.values():
            self.unresolved_shutdown[value["kind"]] += 1
        self.records.clear()
        self.ready.clear()
        self.dispatch = None

    def snapshot(self):
        return json.loads(json.dumps(dict(version=1, boundary="decoded_notification_dispatch",
            raw_frame_arrival="UNAVAILABLE", provider_send_time="UNAVAILABLE",
            monotonic_stages=list(STAGES[4:]), signed_wall_age_stages=list(STAGES[:4]),
            edges=list(EDGES), histograms=self.histograms, stale_timing=self.stale,
            metadata_limit=self.limit, metadata_pending=len(self.records), metadata_peak=self.peak,
            metadata_omitted=self.omitted, unresolved_shutdown=self.unresolved_shutdown,
            missing_dispatch=self.missing_dispatch,
            integrity_failures=self.failures,
            attribution_complete=not (self.failures or self.omitted or self.records
                or any(self.unresolved_shutdown.values()) or any(self.missing_dispatch.values())
                or any(counts[key] for counts in self.stale.values() for key in
                       ("provenance_unavailable", "clock_irregular", "selection_boundary_ambiguous")))),
            allow_nan=False))

    def attach(self, engine):
        put, drain, receive = self.queue.put, self.queue.drain, engine.onchain.receive

        def observed_receive(*args, **kwargs):
            prior = self.dispatch
            self.dispatch = self.safe("clock")
            try:
                return receive(*args, **kwargs)
            finally:
                self.dispatch = prior

        def observed_put(event, priority):
            full = len(self.queue.heap) >= self.queue.maximum
            previous = self.queue.heap[0][1] if full else None
            result = put(event, priority)
            if result:
                self.safe("admitted", self.queue.sequence, event, previous)
            return result

        def observed_drain(*args, **kwargs):
            before = self.safe("clock")
            result = drain(*args, **kwargs)
            self.safe("selected", result, before)
            return result

        self.queue.put, self.queue.drain, engine.onchain.receive = observed_put, observed_drain, observed_receive

        def detach():
            self.queue.put, self.queue.drain, engine.onchain.receive = put, drain, receive

        return detach


def accounting(engine):
    """Copy the existing native rows; no second lifecycle counter implementation."""
    native = engine.accounting.snapshot(engine.queue)
    return {"events": {kind: native["events"][kind] for kind in KINDS}}


def capture(engine, timing):
    try:
        native = accounting(engine)
    except Exception:
        timing.failure()
        native = {"available": False, "status": "NATIVE_ACCOUNTING_UNAVAILABLE"}
    measured = timing.safe("snapshot")
    if not isinstance(measured, dict):
        if measured is not None:
            timing.failure()
        measured = dict(available=False, integrity_failures=timing.failures, attribution_complete=False)
    try:
        partition = ("events" in native and "stale_timing" in measured and all(
            sum(measured["stale_timing"][kind].values()) == native["events"][kind]["terminal"].get("stale", 0)
            for kind in KINDS))
    except Exception:
        timing.failure()
        measured = dict(available=False, integrity_failures=timing.failures, attribution_complete=False)
        partition = False
    measured["stale_partition_reconciled"] = partition
    if not partition:
        measured["attribution_complete"] = False
    return dict(session=engine.session, at=time.time(), accounting=native, timing=measured)


def bounded_section(pre, post, stop_status):
    section = dict(version=1, pre_shutdown=pre, post_shutdown=post, shutdown=stop_status,
                   byte_limit=SECTION_BYTES, omitted_histograms=False)
    def size():
        return len(json.dumps(section, allow_nan=False, separators=(",", ":")).encode())

    if size() > SECTION_BYTES:
        section = json.loads(json.dumps(section, allow_nan=False))
        for phase in ("pre_shutdown", "post_shutdown"):
            if isinstance(section.get(phase), dict) and isinstance(section[phase].get("timing"), dict):
                section[phase]["timing"].pop("histograms", None)
        section["omitted_histograms"] = True
    if size() > SECTION_BYTES:
        return dict(version=1, status="UNAVAILABLE_SIZE_LIMIT", byte_limit=SECTION_BYTES,
                    integrity_failure=True)
    return section

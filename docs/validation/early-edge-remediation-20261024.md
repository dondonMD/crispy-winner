# Controlled early-edge evidence remediation

Branch: `remediation/early-edge-evidence-readiness`. Historical research SHA `76d22105d2bb2f6e6c3c1d2f3ff9df5881d238ba` and all seven experimental evidence files preserved. No cohort, trading, threshold changes or long experiment authorized by this work. PRE_COHORT_READY remains NO.

## Phase 1: accounting and processing

Baseline documentation commit: `cb0b400`.

Files: `backend/app/evidence_pipeline.py`, `domain.py`, `engine.py`, `features.py`, `backend/tests/test_evidence_remediation.py`, this document.

Queue accounting separates submitted, incoming rejection, accepted, accepted eviction, pending, detached/in-processing and fixed terminal reasons. Invariant per event kind: submitted = accepted + incoming rejection; accepted = evicted + pending + in-processing + terminal. Persistence is a separate counter, not a synonym for processing. Existing upstream decoder/filter counters remain separate; migration submission dedup remains an intentional filter.

Processing validates actual dequeue application time for each event. Exceptions no longer silently discard the rest of a detached batch; cancellation explicitly accounts for the remainder. Processing failure gaps the affected trade token or globally for unknown non-trade loss. A tick pause exceeding the unchanged freshness window or backwards wall-clock movement invalidates coverage. A single bounded read-only evaluation task no longer suspends the consumer while awaiting the historical lab result. Retention remains a measured optimization target, not silently removed.

Profile (synthetic DEMO, 444 events, temporary DB; not research evidence): baseline cProfile 2.80s, feature calculations 1.23s, DB.add 0.78s, reserve_event 0.58s. After an exact 128-entry LRU of repeated volatility calculations, unprofiled elapsed 1.89s, same 444 events and 5,332,520 DB bytes. Profiling overhead and local scheduling mean these are indicative, not a controlled live speedup estimate. The cache does not alter mathematical output or scoring thresholds.

Validation: 14 focused accounting/engine tests passed (including frozen DEMO score/state/decision replay); 6 new accounting tests also passed separately. Ruff and mypy passed for changed application modules; whitespace passed. The slow replay completed in about 32s; a diagnostic faulthandler dump showed computation, not a deadlock.

Remaining: no sustained-load p99 acceptance claim, byte-aware storage, durable accounting, quote deadlines, high-rate 500-event buffer limitation, unit reasons, recovery pressure and the historical host observation gap. No queue capacity or recovery limit changed.

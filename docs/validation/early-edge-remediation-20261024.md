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

## Phase 2: bounded auditable storage

Files: `backend/alembic/versions/0005_evidence_audit.py`, `backend/app/db.py`, `engine.py`, `evaluation.py`, `backend/tests/test_evidence_storage.py`, this document.

Lossless SHA256-referenced context rows replace repeated all-candidate maps; replay verifies the referenced payload and supports old inline records. A bounded 128-entry digest cache avoids repeated inserts. The allocator is configured under the existing byte ceiling: 90% main-database page cap, small WAL autocheckpoint, raw pressure reclamation starting at 70% of allocated-minus-reusable pages, and essential-write fail-stop at 85% used or 95% allocated. No configured limit is raised. Each raw-pressure transaction deletes at most 256 raw `event` rows, records cumulative omissions/reclamation and conservative timestamp ranges atomically, and never deletes signals, outcomes, identities, paper history or versions. Free pages are reused; no live VACUUM/rotation. This is explicitly censored raw replay, not proof of missing in-memory flow: replay refuses a complete-replay claim after censorship. Operational session receipts are bounded to 64 KiB, refreshed every 30s and at shutdown; an unclean RUNNING receipt leaves a potentially unknown tail, not inferred completeness.

Protected evidence exhaustion raises a storage-stop error and invalidates coverage, instead of deleting protected results. Arbitrarily long essential histories cannot fit a finite disk; fail-stop remains necessary. The main-page cap and write-size bound leave WAL/receipt headroom; full-suite and live checks are still required. Existing over-budget databases refuse configuration rather than being pruned implicitly. Frozen databases were not opened or migrated.

Validation: 44 focused storage/accounting/engine/prospective tests passed. Four storage tests passed separately: sustained raw writes, lossless context/corruption, preservation of negative/unavailable outcomes, restart receipt persistence and protected-storage stop. In a synthetic 8 MiB budget, 1,000 raw writes remained below the ceiling while recording censorship and retaining all protected sentinels. Restart was simulated by disposing/reopening SQLite, not a physical power-loss test. Ruff/mypy/whitespace passed. The 444-event benchmark retained all events with 1,401,824 bytes versus baseline 5,332,520 bytes; elapsed 2.12s versus baseline profiled 2.80s (indicative, not a live causal estimate).

Remaining: contexts/essential records ultimately require stop when their protected budget fills; high-load WAL/external-writer stress is not yet established; durable receipts bound unknown crash tails but cannot reconstruct events never written. No claim of long-run storage viability yet.

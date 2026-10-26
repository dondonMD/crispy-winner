# Immutable first-review price provenance

Baseline: `610b8a35ff3df1235371774a658aaad895eed991`, branch `remediation/early-edge-evidence-readiness`. Existing uncommitted early-pricing and diagnostic work is retained. PRE_COHORT_READY=NO; Phase 4 unauthorized.

## Defect and correction

The latest frozen session (`28c1aebc-77a8-427a-964b-2819be34a3c2`) has a reconciled price pipeline but three reviews whose mutable `last_failure_at` is later than the signal. Those latest failures cannot establish the original rejection reason. A new regression reproduced the absent first-review fields with a KeyError before the correction.

New reviews freeze:

- `acquisition_status_at_signal`
- `rejection_reason_at_signal`
- `rejection_observed_at_signal` (when the diagnostic was processed locally)
- `rejection_event_at_signal` (the supplied diagnostic stage timestamp)
- explicit UNKNOWN reason fields and capture timestamp.

The existing baseline status, signal timestamp and price baseline remain unchanged. Current/latest status and last rejection retain their separate mutable fields, now with local processing timestamps. A last-known rejection can belong to an earlier attempt; it is not automatically the cause of a valid current baseline.

`note()` records local processing time separately from the caller-supplied timestamp. Both must strictly precede the signal cutoff for a status/rejection to qualify as signal-time evidence. Equal timestamps are conservatively UNKNOWN; a supplied future timestamp or a backdated event processed after the cutoff cannot supply provenance. Clock regression/out-of-order diagnostic timestamps mark ordering ambiguous and prevent a confident historical interpretation. No older history is reconstructed if the retained latest diagnostic is unsuitable.

Reasons for UNKNOWN include no recorded rejection, missing observation timestamps, non-retained diagnostic history, future/late availability, equal timestamps, non-monotonic clocks, invalid timestamps and a signal timestamp later than capture. Unknown fields never get filled from later events.

## Durable and immutable capture

A pure first-review snapshot is computed **before** writing `v21_price_signal`. The signal's existing append-only payload now includes `first_review_price_diagnostics`. The same detached snapshot seeds the bounded diagnostic review sample after commit. This protects provenance even when review-detail retention later omits that token. No table migration or update of older signal rows.

A write-time callback or later RPC/FX result may update operational latest state, but cannot alter the signal snapshot. Repeated first-review notifications return without replacing it. Retry after an uncertain signal acknowledgement uses the committed snapshot rather than taking a newer baseline or reason. Expiry, success, shutdown and restart do not overwrite signal-time fields.

Diagnostic schema version is 2; pricing instrument and V2.1 policy versions are unchanged. Legacy review views without first-review provenance expose explicit UNKNOWN with `LEGACY_SIGNAL_PROVENANCE_UNAVAILABLE`. No legacy reason is reconstructed from mutable `last_failure`, and original frozen records are not rewritten by this task.

## Bounds and size

All existing limits remain: 48,000-byte diagnostic payload, 32 token summaries, 24 review summaries, 25 active phases and 32 retained diagnostic sessions. Byte-budget omission counters now distinguish token versus review omissions; existing total omissions and durability accounting remain intact. Canonical signal snapshots preserve first-review provenance independently of sampled-detail eviction.

Measured synthetic full-cap receipt (32 tokens/24 reviews): **29,944 bytes**. The signal-time fields add **7,568 bytes** across those 24 reviews relative to the otherwise same current receipt without those fields. An in-memory UNKNOWN compatibility projection of the old frozen 15,947-byte receipt is 21,509 bytes. The original receipt remains 15,947 bytes and was not modified. Artifact: `data/early_edge/first-review-provenance-20261026/size.json`.

No network, polling, arithmetic, freshness, pricing, security, approval, outcome-horizon, scheduler or transaction-durability changes. Work is bounded scalar metadata at existing diagnostic/capture boundaries; no throughput or RSS improvement is claimed. New per-token processing/order metadata is included in the measured full-cap receipt.

## Validation

**173 passed in 18.82s** across diagnostics, early pricing, V2.1, evidence storage, storage guard, shutdown, v1 opportunity research, manual workflow and lifecycle tests. Additional writer/checkpoint/transaction-boundary tests: **31 passed in 5.68s**. Final combined rerun including the extra timestamp-skew case: **205 passed in 24.84s**, normal exit0. Ruff, mypy, secret and whitespace checks were run. All tests use synthetic observations and isolated temporary databases; no live provider or original radar database was opened.

New cases cover A-before-signal/B-after-signal, unknown-before/later failure, late processing with a backdated timestamp, future timestamps, event timestamps after processing time, timestamp equality, clock regression, expired baseline followed by success, repeated notifications, multiple later updates, canonical capture before a write callback, legacy UNKNOWN compatibility and persisted/reloaded first-review provenance. Existing bounded-retention, cancellation, storage, negative-outcome and no-backfill cases also pass.

The earlier full-suite observer ranking-call-count discrepancy and ordinary asyncio cleanup limitation are outside this narrow change; no full-suite pass or resolution of those historical issues is claimed.

## Exact changes and preservation

- `backend/app/price_diagnostics.py`: processing-time/order metadata; immutable capture and legacy UNKNOWN projections; bounded omission attribution.
- `backend/app/early_prices.py`: store the frozen snapshot in the canonical signal; reuse it on acknowledgement retry.
- `backend/tests/test_price_diagnostics.py`: deterministic temporal and immutability regressions.
- This report.

No other pre-existing implementation file was edited in this task. All **14 original preservation hashes** match; both later frozen session directories also match all **eight files each**. These checks exclude the three intentionally edited implementation/test files from this task's pre-change manifest. No staging, commit, push, provider run, cohort, wallet or trading activity. This fixes provenance semantics only; the historical three missing signal-time reasons remain unavailable, and no predictive or trading-readiness claim follows.

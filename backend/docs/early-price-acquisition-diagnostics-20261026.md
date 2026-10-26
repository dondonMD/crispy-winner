# Durable early-price acquisition diagnostics

Baseline `610b8a35ff3df1235371774a658aaad895eed991`, branch `remediation/early-edge-evidence-readiness`. Existing uncommitted indicative-price work is retained. PRE_COHORT_READY=NO; Phase 4 unauthorized. No live provider, cohort, trading, staging, commit or push.

## Confirmed gap and historical limits

Read-only audit of session `48f9350b-b9af-4aee-9a84-4795afee3311` established 107 USD marks/65 mints, 28 instrumented reviews, eight baselines and 20 missing baselines. The 16 dashboard-sampled reviews are a subset; eight never-priced sampled mints had ten hot VERIFIED curve observations. Lifecycle verification is a different contract from full price-state/mint verification.

The actual observability defect was that `curve_progress_batch()` replaced strict pre-mark failures with a generic status, and `poll_curves()` removed that status before persistence. The later rejected-mark counter could not count those failures. Generic reference health described HTTP connectivity, not FX timestamp validity. This change closes those accounting gaps. It does **not** recover missing historical reasons or establish which account condition affected those eight mints. Frozen receipts are not amended.

## Boundaries and definitions

Counters describe stages; they are not interchangeable denominators or independent signals. An acquisition attempt means one selected token entering the existing hot curve batch, **not one RPC request**. A single batch can account for 25 attempted tokens with one RPC request. Selection assessments (`NOT_SELECTED`, `NOT_DUE`, `RPC_INELIGIBLE`, `NOT_PREGRAD`) never count as attempts.

| Boundary | Recorded categories |
|---|---|
| Hot acquisition | `ATTEMPTED`, `RPC_COMPLETED`, `RPC_UNAVAILABLE`, `RPC_TIMEOUT`, `RPC_RATE_LIMITED`, `RPC_INVALID_RESPONSE`, `RPC_CANCELLED` |
| Strict input validation | `NO_VERIFIED_CURVE`, `MINT_IDENTITY`, `CURVE_ACCOUNT_LAYOUT`, `MINT_METADATA`, `QUOTE_METADATA`, `UNVERIFIED_DECIMALS`, `UNSUPPORTED_QUOTE`, `UNSUPPORTED_CURVE_STATE`, `INVALID_RESERVES`, `STATE_CONTEXT`, then `STATE_VALIDATED` |
| USD/calculation | `USD_UNAVAILABLE`, `USD_STALE`, `USD_TIME_INVALID`, `STALE_STATE`, `PROVIDER_DISAGREEMENT`, `INVALID_PRICE`, `CALCULATION_REJECTED`, then `CONSTRUCTED` |
| Submission/persistence | `SUBMITTED`, `PERSISTED`, `NOT_PERSISTED`, `PERSISTED_UNACKNOWLEDGED`, `PERSISTENCE_UNACKNOWLEDGED`, `MARK_REJECTED` |
| Later lifecycle | `ACQUISITION_CANCELLED`, `TOKEN_INELIGIBLE`, `EXPIRED`; unsupported diagnostics become `UNKNOWN_OTHER` |

`RPC_COMPLETED` means a report map returned, not usable curve/price evidence. A missing report remains `NO_VERIFIED_CURVE`. Existing strict decoders still make acceptance decisions; new wrappers only name the branch that rejected an input. Arithmetic exceptions keep their previous propagation behavior while receiving a diagnostic category. Transport failure exceptions remain RuntimeError-compatible and carry only a fixed category; retries, backoff and pressure rules are unchanged.

`PERSISTED` follows a committed receipt. On a write exception, a bounded read checks whether the exact mark exists: absent = `NOT_PERSISTED`, present but acknowledgement failed = `PERSISTED_UNACKNOWLEDGED`, failed verification read = `PERSISTENCE_UNACKNOWLEDGED`. Neither ambiguous nor present-but-unacknowledged observations enter the valid cache through that failure path. Expiry is counted once per cached mark on the next normal tick; expiry never removes history or changes a price threshold.

Every tracked attempt has a bounded active phase independent of sampled token-detail eviction. Finished attempts, current in-progress attempts and unresolved work at a prior checkpoint are separately counted. `attempt_reconciled` cannot claim completeness if the active-detail bound overflows or attempts overlap.

## FX lifecycle

SOL-USD and USDCUSD have independent counters: logical `attempted`, actual `http_started`, decoded-response `http_completed`, `request_failed`, `validation_failed`, `stale_rejected`, `cancelled`, accepted `usable`, interval skips and product-budget skips. `http_started` comes from the adapter's own HTTP request counter, so cancellation while waiting for its limiter does not invent a sent request. A returned JSON body is not an accepted exchange rate. Malformed JSON is semantic failure; HTTP failure, timeout and rate-limit branches retain transport categories.

Only `usable` records the last accepted source, product, value, publication and acquisition timestamps. Snapshots recompute both ages and 20s freshness, plus `usable_in_current_cache`. Restoring diagnostic history does not restore pricing-cache data. The previous HTTP-health field now explicitly states `HTTP_TRANSPORT_ONLY` and points to the price-diagnostic receipt; it cannot stand in for the per-product validity fields.

Attempt checkpoints precede I/O, and completion/failure/cancellation checkpoints follow it. Cancellation is re-raised after bounded synchronous receipt handling; no detached task or network operation is introduced. A hard process kill can leave an unresolved checkpoint tail, never a fabricated success or a claimed specific failure. Actual committed marks remain independently inspectable in existing records.

## Review explanations

Up to 24 reviewed mints retain immutable signal-time baseline status and a separately updated last acquisition/failure status. Categories distinguish a valid signal baseline, an earlier expired mark, an unavailable mark, an attempted rejection, no attempt, and unknown history after diagnostic eviction. Later persisted marks set `later_mark_not_backfilled`; the signal baseline itself is untouched. Selection-only assessments do not evict acquisition details. A sampled detail's absence after eviction is explicitly unknown, not evidence that no attempt occurred.

Sanitized excerpt from the deterministic failed-metadata scenario (mint redacted for presentation):

```json
{"counts":{"ATTEMPTED":1,"RPC_COMPLETED":1,"MINT_METADATA":1,"finished_attempts":1},
 "in_progress":0,"attempt_reconciled":true,
 "tokens":[{"mint":"<redacted>","last_status":"MINT_METADATA"}]}
```

The tests read the committed `evidence_runs` row to establish this result. No raw account bytes, wallets, transaction payloads, URLs or exception text are retained.

## Durability, bounds and overhead

The existing `evidence_runs` table stores a separate `px:` checkpoint keyed by session hash. No table migration or research-row rewrite. At most 32 token summaries, 24 review summaries, 25 active phases and two FX products are retained. Overflow/eviction and byte omissions are explicit. The dedicated payload is capped at 48,000 bytes, below the existing 65,536-byte operational limit; ordinary engine receipts carry only a compact summary/reference.

The reserved namespace retains the latest 32 receipts. Pruning and replacement are one SQLite transaction; the receipt records the retention policy and actual pruned count. Ordinary session receipts, negative outcomes, paper/history and non-price namespaces are excluded. This is bounded diagnostic retention, not permanent forensic history; freeze/export a session before it ages out. No retention ran against original/frozen databases in this task.

Checkpoint writes occur at batch entry/exit, FX entry/exit, first-review capture and clean stop, not per trade or every counter update. A diagnostic write failure increments `durable_failures`, remains visible in the ordinary summary, and never modifies pricing/eligibility. Entirely failed storage cannot guarantee another durable diagnostic; its last checkpoint tail remains unknown. No transaction spans a network await.

Synthetic component measurement on an isolated project-filesystem SQLite database, unchanged WAL/NORMAL settings: 75,000 notes averaged **2.90 microseconds CPU/wall per note**; 40 checkpoint writes averaged **4.60ms**, maximum **21.79ms**; representative payload **13,253 bytes** (25 tokens/24 reviews). This measures component cost, not net throughput, RSS or live scheduling impact. Diagnostic I/O consumes wall time inside existing deadlines; near-deadline availability must be checked in the bounded live validation, without extending those deadlines. Local artifact: `data/early_edge/price-diagnostics-20261026/component.json`.

## Validation and files

**326 passed, 1 skipped in 36.44s**, normal exit0, across the ten selected backend test files. Ruff passed; mypy passed all 47 application files; secret and whitespace checks passed. No frontend changes or broad performance/full-system campaign. The earlier development run's five new-test NameErrors (imports removed as unused before those tests were added) are preserved in `/tmp/price-diag-regressions.log`; corrected imports pass the final run. The previously reported unrelated full-suite observer ranking-call-count discrepancy and ordinary asyncio-cleanup limitation were not retested and are not claimed resolved. Focused tests exercise strict reason branches, both FX products, HTTP/JSON/schema/stale/timeout/rate-limit/cancellation cases, RPC versus later cancellation, real VERIFIED progression with unavailable mint metadata, stage reconciliation, failed persistence, frozen missing baselines, no later backfill, expiry, bounded memory/retention, restart and failed diagnostic writes. Existing price, V2.1, v1 research, lifecycle, manual, shutdown and SDK-golden regressions are included.

Files changed by this task:

- `backend/app/price_diagnostics.py` — bounded counters, FX/review summaries and checkpoints.
- `backend/app/early_prices.py` — reason naming, persistence diagnostics, review/expiry hooks.
- `backend/app/providers.py` — retained state failure codes and transport categories.
- `backend/app/early_edge_runtime.py` — passive per-product FX lifecycle accounting.
- `backend/app/engine.py` — acquisition-stage hooks, selection assessments and cancellation checkpoints.
- `backend/app/db.py` — atomic retention limited to the new reserved diagnostic namespace.
- `backend/tests/test_price_diagnostics.py` — new deterministic cases.
- This report.

All original **14 preservation hashes** match, as do the eight files in the audited `003245` session. Existing uncommitted implementation and unrelated files are preserved. Pricing mathematics, source/coherence/decimal checks, 20s reference freshness, polling intervals, V2.1, strict CURRENT, security and approval, signal baselines and outcome horizons are unchanged. No new source, order, wallet or cohort capability.

## Recommendation

Recommend **one separately authorized 300-second isolated OBSERVE validation**, using the existing harness and a new database, with source/configuration hashes recorded. Require reconciled acquisition attempts, zero unexplained in-progress work after clean stop, independent FX status, and a recorded reason or explicit diagnostic omission for retained reviewed tokens without marks. Inspect actual metadata/layout failures before proposing any pricing correction. Preserve failures and all missing baselines; do not demand positive EARLY counts, returns or universal price availability. No run was started here. PRE_COHORT_READY=NO.

# Controlled capacity and evidence validation — 2026-10-24

Starting source: `e2d41ea77d4708702e475828bd7d990d79e9ce86` on `remediation/early-edge-evidence-readiness`. This work uses synthetic traffic, isolated SQLite databases and mocked providers only. No new real-market run, six-hour experiment, real cohort or trading is authorized. PRE_COHORT_READY remains NO. The previous smoke and seven historical evidence hashes were verified before testing; the retired DB remains 1,073,893,376 bytes with mtime_ns 1792471574652367761.

Read the root-cause report, consolidated remediation report, preserved 306-second smoke JSON and its read-only durable receipt. Historical smoke accepted 4,324 trades, processed 4,297 and retained 27 in-memory pending events in its stopped receipt. Recovery accepted 202/completed 201; one unresolved recovery appeared in JSON but was absent from the durable stopped receipt. Historical artifacts are not rewritten.

## Demonstrated defects and targeted corrections

A pinned SQLite reader prevents WAL reuse. Baseline 8 MiB stress at `e2d41ea` crossed the configured budget after 249 attempts: 8,391,848 bytes > 8,388,608, without a guard stop. Receipt: `data/early_edge/controlled-validation-20261024/storage-baseline-reader.json`. The raw-write path treated physical pressure as permission for more cleanup transactions, growing the pinned WAL. It now raises the existing storage-budget exception at the unchanged 95% physical reserve, before more cleanup writes. Logical raw reclamation remains bounded and fail-closed.

A failed reclamation transaction could also leave in-memory audit counters changed despite SQL rollback. The audit is now built locally and published only after transaction commit. Regression injects failure at receipt insertion and verifies both the original event row and original counters survive.

Shutdown now closes transport coverage before clearing pending work, explicitly terminalizes queued events as `shutdown_unprocessed`, and records unresolved recovery cancellation separately from successful/classified completion. The durable stopped receipt includes queue and canonical recovery snapshots. Recovery accounting is `accepted = completed + shutdown_unresolved + pending`; no unresolved work becomes UNTRACKED_CONFIRMED or a success. Worker concurrency/claims, retries, lifetime, overflow and identity validation are unchanged. A regression recreates 27 queued trades plus an in-flight recovery, cancels workers, reopens the isolated DB and verifies exact terminal accounting and STOPPED INCOMPLETE coverage.

Initial focused validation: 18 tests passed (new cases plus existing storage/accounting regressions); Ruff passed. Further capacity, storage, quote/control integration and complete-suite results will be recorded below. No engineering readiness conclusion follows from these initial tests.

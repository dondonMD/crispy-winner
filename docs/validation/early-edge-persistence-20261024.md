# Bounded persistence remediation — 2026-10-24

Starting branch remediation/early-edge-evidence-readiness, source daedd4b7db97f498150b3f4026c95f3a8ae34a09. PRE_COHORT_READY remains NO. All new load is synthetic, isolated, non-enrolling and uses mocked providers. Historical experiment files, retired cohort and prior reports remain unmodified. No push, trading, live cohort or six-hour experiment.

## Isolation and confirmed baseline

Read the prior endurance report/artifacts and persistence/consumer/research/paper implementations. Exact 30,000-trade reconciliation: 19,317 processed/persisted + 9,959 stale + **26 explicitly untracked after churn** + 559 rejected incoming + 139 accepted then evicted = 30,000. The 26 are not unexplained loss or evidence. Accepted=29,441 includes the 139 later evicted; drops=698 includes incoming rejections and evictions. These predicates must not be subtracted twice.

Project database location is ext4 on /dev/sdd (rw,relatime,data=ordered) under WSL2; /tmp is tmpfs. Production SQLite remains WAL, synchronous=NORMAL, busy_timeout=5000ms, foreign_keys=ON, wal_autocheckpoint=32 pages. These settings are unchanged; NORMAL is the existing crash-consistency policy, not a guarantee of surviving host power loss for every acknowledged commit. No fsync/checkpoint policy is weakened to improve scores.

The exact prior 200-record paired component source was copied byte-for-byte (SHA256 a438c972e5e9ee642a0ff6f0a571759f5e58f2427c83413be57cc6cb3da31638) into the new artifact directory. The first component attempt overlapped replay setup, finished 9.4s before the replay's timing/profile end, and is exploratory. An uncontended repeat after replay completed took **0.726 / 0.548s on tmpfs** versus **2.293 / 2.157s on project ext4**, identical two-commit iterations. This reproduces the filesystem contribution without asserting that disk is the sole bottleneck.

Fresh 60s project replay: same 250 candidates, 50/s average with 100/s first-second pulses, 200 warm observations, 0.7 recovery/s, delayed shared-provider stand-ins. Source daedd4b with diagnostic stage timers only; source/harness hashes preserved. All 3,000 trades processed/persisted, no stale/drop, but application p99 **18.436s**, elapsed 78.987s, mean CPU 70.81%, peak RSS 187.63MiB. Stage costs: analyse 22.318s /10,567 calls; Database.add 17.551s /3,750 calls; reserve_event 10.872s /3,000; save_pending 4.253s /3,000; checkpoint 3.289s /3. Timers overlap: do not sum them as exclusive CPU. The old 600s failure remains authoritative for that longer window; this short run is not a replacement.

## Smallest chosen boundaries (before performance acceptance)

A blanket transaction around RadarEngine.process is rejected in this patch. The body mutates tokens, creator/research state and potentially paper state; multiple independent writers and observer callbacks participate. Correct rollback/retry would require a separate tested whole-event state protocol. No accepted trade is now acknowledged early, buffered behind an unbounded writer queue or silently retried with newer timestamps.

Instead:

1. **Immutable restore checkpoints only.** Existing snapshot/creator-profile content and chronological timestamps are frozen synchronously before writing. Preparation is bounded to 500 rows/4MiB. Each transaction normally holds <=10 rows/64KiB; one larger record already valid under existing per-record bounds commits alone. Signals, outcomes, raw events and paper records are forbidden in this API. The existing storage guard is checked before each group. No network or await occurs while holding a write transaction.
2. **Atomic progress.** Each group commits its rows and a single per-session cp: receipt together. Receipt holds the frozen-plan digest, committed row IDs and complete flag. Return/advance happens after commit. BEGIN IMMEDIATE serializes competing retries using the unchanged busy timeout. A failed group rolls back; older committed groups remain auditable. Retrying identical input verifies committed rows and skips them; changed or older input fails closed. No automatic retry storm is added. A new later checkpoint replaces the per-session progress receipt; this is a bounded latest-checkpoint ledger, not a full historical failure journal. Caller errors remain visible and older snapshot records remain subject to existing retention.
3. **Exact pending-state no-ops.** OpportunityResearch caches at most its existing LIMIT=1000 committed encoded pending payloads. Only byte-identical saves skip SQL. Mutable objects are never cached as proof, and the cache advances/evicts only after successful transaction commit. Failure leaves the old cache, so retry still writes. This uses the existing single-engine ownership of pending research state; concurrent independent engines sharing the same research pending namespace are not supported by this cache or the pre-existing in-memory owner model. No outcome or eligibility semantics change.

Trade identity and final raw-event commits, paper journal writes and outcome writes retain their existing boundaries. This does **not** claim whole-event atomic retry or fix the pre-existing identity-before-record failure window. Such a change needs memory-state/observer rollback or a deliberate fail-stop recovery protocol. Negative/unavailable outcomes are neither merged into checkpoint groups nor removed to improve timing.

## Initial functional checks

26 targeted transaction/replay/storage/shutdown tests passed in 52.49s. New cases cover bounded commit count, byte-identical retry, frozen-input mismatch, concurrent retry serialization, partial receipt-update failure, writer busy/locked failure then retry, SIGKILL after the first committed group followed by cold DB integrity/retry, storage guard with pinned reader, forbidden/oversized/older checkpoint input, exact pending no-op, failed pending commit and bounded cache. Protected measured -100% and unavailable outcomes survive. Process-kill tests establish SQLite restart behavior, not power-loss guarantees. Ruff/mypy/secret/whitespace checks passed after formatting the new test file.

Performance comparison and full-suite results follow; no passing latency outcome is assumed.

## Controlled comparison — improvements, acceptance still FAILED

The same committed harness, 250 candidates, 60s/3,000 deterministic scheduled trades, 200 warm events, 50/s average with periodic 100/s pulse, 42 recovery arrivals and identical shared-provider delay policy were used. Both databases reside on the real project ext4 filesystem. No competing test suite ran during either timing window. The first exploratory storage reproduction overlapped baseline setup, not its timed window; the uncontended paired reproduction is the preferred storage evidence. Absolute wall timestamps and uncontrolled WSL host scheduling differ; input amounts, identities, schedule and settings match. This is synthetic normalized input, not decoder/network/market evidence.

| Metric | Baseline daedd4b | Optimized 43fb58d |
|---|---:|---:|
| Elapsed generation/drain/shutdown | 78.987s | 76.732s |
| Committed trade throughput incl. drain | 37.98/s | 39.10/s |
| Application p50 / p95 / p99 | 9.145 / 18.149 / **18.436s** | 8.149 / 16.338 / **16.739s** |
| Queue-wait p50 / p95 / p99 | 8.328 / 17.313 / 18.108s | 7.894 / 15.709 / 16.403s |
| Synchronous process p50 / p95 / p99 | 12.625 / 27.096 / 37.163ms | 12.589 / 28.640 / 39.722ms |
| Queue peak / final pending | 728 / 0 | 673 / 0 |
| Processed/persisted trades | 3,000 | 3,000 |
| Stale / dropped trades / critical drops | 0 / 0 / 0 | 0 / 0 / 0 |
| Recovery completed / accepted | 42 / 42 | 42 / 42 |
| Mean / peak CPU (one-core %) | 70.81 / 93.3 | 70.66 / 94.7 |
| Peak RSS | 187.63MiB | 188.21MiB |
| Sampled WAL peak | 181,312 bytes | 197,792 bytes |
| DB bytes after shutdown | 10,579,968 | 10,579,968 |
| Token-local / intentional shutdown global gaps | 0 / 1 | 0 / 1 |
| Pending save time / calls | 4.253s /3,000 | 0.558s /3,000 |
| Checkpoint time / calls | 3.289s /3 | 1.003s /3 |

Every submitted event and persisted count reconciles; both cold restores passed with empty rewarming windows, stale security, $20 isolated paper cash and zero positions. No untracked/admission return occurs in these short fixtures because turnover starts at minute one. These successful short loss counts do not supersede the previous 600s failure.

Checkpoint time fell ~69.5% and pending-save time ~86.9%. Overall p99 improved ~9.2% but remains far above 5s. Individual process-tail latency did not improve, and disk timing varied. The optimized run still spent **27.890s** in Database.add + reserve_event (unchanged per-event boundaries), **22.895s** in analyse and **7.469s** in intelligence.refresh (inclusive/overlapping stages). Thus neither transaction overhead nor feature/observer work can be called solved system-wide. The old 4.295s tmpfs stress is not the acceptance baseline for durable ext4.

**The required short-run latency gate failed, so no new 600-second or 30-minute run was started.** This follows the user's conditional escalation rule; no rate, freshness, queue size or acceptance threshold was relaxed to proceed.

## Commit and transaction-duration component measurements

An additional ext4-only component used **the exact same 250 frozen synthetic checkpoint rows** from the baseline DB, with legacy/optimized order reversed for a second pair. Input hash 9e7677cdeb195804aee6e7b0712a28b575b6a70abeef808ccd3cbfb153b95cc9. Source/output are preserved as checkpoint-commit-profile-v2.py/.json. SQLAlchemy's local DBAPI commit call was timed in the diagnostic only; no production commit implementation or PRAGMA was replaced. Full transaction durations pair each precommit duration with its corresponding commit, not the sum of independent quantiles.

| Metric | Legacy (two samples) | Bounded (two samples) |
|---|---:|---:|
| Rows / commit count | 250 / 250 | 250 / 25 |
| Elapsed | 1.191 / 1.198s | 0.275 / 0.269s |
| Commit total | 0.655 / 0.654s | 0.129 / 0.135s |
| Commit p99 | 15.280 / 13.565ms | 14.158 / 14.729ms |
| Full transaction p50 | 0.864 / 0.869ms | 8.508 / 9.175ms |
| Full transaction p95 | 13.796 / 13.032ms | 16.645 / 16.167ms |
| Full transaction p99 | 15.832 / 14.254ms | 18.026 / 17.861ms |
| Full transaction maximum | 20.890 / 40.276ms | 22.648 / 22.742ms |
| SQL write statements | 250 INSERT | 251 INSERT +24 UPDATE |
| Allocated DB/WAL/SHM | 488,344 bytes | 496,584 bytes |

Batching reduces aggregate commit overhead by amortizing it, not by making every transaction smaller/faster. The checkpoint receipt adds 25 SQL writes and ~8KiB allocated space in this component. Physical OS write-byte counters were unavailable (both the psutil method and /proc accounting), so no physical write-amplification reduction is claimed. Record-payload byte bounds exclude SQLite index/receipt overhead; actual guard/WAL behavior is tested independently. The first component version lacked paired full-transaction metrics and overlapped a local Git commit; it remains preserved as exploratory; v2 adds them without overwriting prior results. WAL/synchronous/busy-timeout/autocheckpoint/page-size values were read back for every sample and match the unchanged policy.

## Additional shutdown defect and correction

A bounded injection proved that a checkpoint exception during RadarEngine.stop previously prevented the final EvidenceRun accounting receipt from being written. It printed `final receipt exists: False`. This is unsafe for auditing partial checkpoint work. Commit **0072899** changes shutdown to attempt the terminal receipt with checkpoint_complete=False and the exception category, dispose resources, and then **re-raise the original error**. A storage error retains STORAGE_STOP. Failure of the final receipt itself still propagates; an unwritable database cannot be claimed durable. This is not a silent successful shutdown or a replay of missing events.

Two additional cases cover commit-time failure (uncommitted prefix never acknowledged, exact retry) and shutdown checkpoint failure with three explicitly terminalized queued observations. The ten new transaction tests passed in 2.46s. A prior focused combined run had 26 passes across new/existing replay/storage tests before these two additions. Existing overflow/backpressure, event freshness, continuity, replay and risk-gate cases all remain covered by the complete suite.

## Full validation and preserved evidence

Complete backend: **766 passed, 1 skipped in 163.35s**. Complete frontend: **39 passed in 5.87s**; TypeScript and production build passed (3.91s build). Ruff, mypy (43 sources including harness), secret scan (202 source/document files) and git diff --check passed. Installed backend dependency audit reports no known vulnerabilities. Frontend audit first hit sandbox DNS failure, then the required external retry returned zero vulnerabilities. No dependency manifest/lockfile changed.

Seven original frozen evidence hashes, the original smoke hash, the completed failed endurance JSON/source identities and the retired database size/mtime are checked before final reporting. Synthetic DBs remain in the new persistence-20261024 namespace; original results are not rewritten, reclassified or appended to a cohort. No Pump/PumpSwap decoder, economics, security, lifecycle, eligibility, opportunity threshold, freshness, continuity, polling, recovery scheduler, paper-execution or candidate/queue capacity was changed.

Local commits: **7bd1e3d** (diagnostic stage timers/design report), **43fb58d** (checkpoint transactions and exact pending-state cache), **0072899** (final receipt despite checkpoint failure). The final documentation/assessment commit is identified in the response. No automatic push.

## Engineering decision and remaining work

**Ten-minute acceptance is NOT established. PRE_COHORT_READY remains NO. No six-hour live evaluation is justified.** The prior 600s failure remains unchanged; this patch demonstrates narrower safe persistence gains, not completion of the overall throughput objective.

Remaining priorities:

1. Design a whole-event transaction/commit protocol that includes identity, context and final evidence without acknowledging uncommitted work. Address token/creator/research/paper in-memory mutation, independent writers and external research callbacks before attempting batching/offload. The existing identity-before-record failure window and multi-method outcome/pending updates remain limitations; this patch does not claim idempotent Engine.process retry after arbitrary partial mutation.
2. Retain explicit failure, unknown coverage and negative/unavailable evidence on any proposed rollback. Never hide an event failure behind a successful processed counter. Add cross-component failure/restart tests before widening these boundaries.
3. Profile the residual feature/analysis/observer CPU cost as well as per-event SQL on the actual filesystem. Moving work to a thread cannot by itself increase durable write throughput; another unbounded queue or weaker SQLite synchronization is not an acceptable substitute.
4. Repeat the same short gate only after further reviewed, supported improvements. A 600s run becomes eligible only once that gate passes with no data loss; 30 minutes remains conditional on the existing 600s acceptance. No automatic live test follows.

The new checkpoint API is deliberately limited to immutable restoration data. Its per-session latest progress receipt is not a permanent full checkpoint-attempt history; existing raw/evidence/session records remain necessary for audit. Its exact pending cache assumes the existing single-engine writer model. WSL host/thermal/I/O variability, larger records, hour-scale memory/retention and real provider traffic remain unproven by these bounded synthetic tests. No profitability or prospective edge conclusion follows.

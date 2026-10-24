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

## Phase 3: deadline-aware diagnostic quotes

Files: `backend/app/early_edge_scheduling.py`, `early_edge_telemetry.py`, `scripts/early_edge_diagnostic.py`, `backend/tests/test_early_edge_scheduling.py`, `test_early_edge_telemetry.py`, this document.

The Python-only success predicate now uses `quote_valid` (reference mode retains `match`). A deterministic round budget spaces requests across the declared duration: for 21,600s/120 state probes this is 12 per 2,160-second round, with 180-second spacing and a hard global 120 cap. No long study was started. One background task and one entry-probe task are the only quote tasks; both reuse the shared existing provider limiter. Background probes yield while a primary entry window is unresolved. Primary-due work precedes secondary-only work; per-latency retries are bounded at three, never after the deadline. Each request is bounded by the smaller of five seconds or the remaining acquisition window. There is no pre-boundary or future-best fill substitution.

A bounded 256-receipt ring retains hashed signal identity, attempt/completion/request/acquisition timestamps, deadlines, latency list and typed outcomes; aggregate counters retain attempts beyond the ring. No wallet addresses are recorded. Unknown-unit failures remain units failures; process/capacity shutdown without an attempt is infrastructure unavailable, not automatically a provider outage or economic-zero exit. Background records now carry attempt/completion/round metadata. The old finish-probe test was updated for this more accurate infrastructure-censoring label; no economic outcome semantics changed.

Validation: 149 early-edge methodology/telemetry/scheduling tests passed, 1 opt-in skipped; 11 scheduling/telemetry tests passed after final reason-label changes. Ruff/mypy passed for changed modules/scripts. Deterministic tests cover global/per-round quotas, Python/reference success predicates, exact primary boundary, pre-boundary rejection, expired work issuing no HTTP, bounded retries, typed unknown-unit failure and primary-over-secondary selection. Historical baseline: zero of four T+10 probes and all 19 successful state receipts in the first ~160s; no comparable new live result yet. Unit results are not a claim that a congested shared provider can always meet deadlines.

Remaining: shared provider contention can still make entries unavailable; precise provider-stage timing, sustained viable coverage and real manual-entry availability require controlled validation. Background priority is enforced at diagnostic scheduling, not by bypassing the provider's FIFO limiter. No SDK runtime dependency, quote math, threshold or prospective cohort was changed.

## Phase 4: continuity, integration and controlled validation

Additional findings and fixes:

- The full observational adapter refresh at 250 synthetic candidates called the YAML settings loader 1,250 times. cProfile recorded 6.61s total, including 4.82s loading/parsing settings. A bounded eight-content parse cache reduced the same first-refresh profile to 2.43s. Every call still reads file contents and returns an independent deep copy; thresholds/configuration are unchanged and content drift is immediately detectable. The first-refresh workload includes 250 opportunity transitions and writes; this is not a steady-state or live latency claim.
- The observational wrapper now forwards queue accounting keyword arguments; an integration regression proves original processing and observer isolation coexist. This was caught before live validation.
- Long/backwards observation ticks invalidate pre-grad and post-grad coverage and retain a bounded gap history. Resource trimming explicitly gaps lost trade history rather than merely setting degraded. Unknown units now have fixed reason counters (unverified curve, unsupported quote, conflicting identity, unsupported quote semantics, zero executed amount); acceptance and conversion rules are unchanged.
- Queue wait has fixed histogram bins. Diagnostic reports include reconciliation, storage-censoring and evidence-blocker vectors. New command-line runs retain the diagnostic DB in a fresh output-adjacent `.run` directory by default; an existing directory is rejected. Direct library callers retain their explicit temporary-fixture behavior. A long observation discontinuity stops the diagnostic rather than extending an apparent continuous study. Background cancellation receives an explicit unavailable receipt.
- Pressure reclamation is bounded by both 256 records and approximately 64 KiB of payload per transaction (except one larger permitted record). Sustained-write tests check the allocated budget after every write, not only at completion. This is not a power-failure or external-writer certification.

Security validation discovered newly published advisories, rather than suppressing them: frontend dev-only `jsdom -> undici` was patched from 8.11.2 to 8.12.3 within the existing range (lockfile only, lifecycle scripts disabled). The actual installed Python environment had certifi PYSEC-2026-4320 and filelock CVE-2026-112940/112913/112907; installed certifi was patched from 2026.7.22 to 2026.10.23 and audit-tool filelock from 4.0.12 to 4.2.4. The requirements resolver had reported zero, illustrating why installed-environment audit is also necessary. No official JS SDK became a runtime dependency. Source and installed package receipts are saved under `data/early_edge/remediation-20261024/` (ignored local operational evidence).

Bounded replay benchmark: 500 synthetic trade events, ten tokens, target 50 events/s, real original intelligence plus the observational adapter, no started providers and measured zero HTTP requests. Elapsed 10.00s; 250 buys/250 sells processed; peak queue 2; no stale queued events; all 500 queue waits <=10ms; every accepted event reconciled. The overload test submits 1,500 trades plus security into the unchanged 1,000-event queue, explicitly accounts for 501 trade losses, preserves the security event, and gaps continuity. This does not demonstrate 250-candidate sustained live capacity or prove CURRENT.

Test scope also retains existing strict decoder, units, migration freshness, recovery, 180s continuity, 20s market freshness, security, lifecycle, Opportunity/Companion, economics, bootstrap and holdout regressions. Frozen seven-file hashes and retired cohort DB size/mtime remain unchanged. PumpSwap decoder/schema, risk/config files, economics gates and early-edge eligibility/manifest definitions have no changes.

Final full-suite and controlled smoke results follow after validation. PRE_COHORT_READY remains NO throughout; a new readiness experiment is not authorized by a passing unit suite.

### Final local validation before live smoke

Complete bounded backend suite: **723 passed, 1 opt-in skipped in 121.24s**. Frontend: **39 passed**; TypeScript and production build passed. Ruff passed; mypy passed for 44 checked application/diagnostic/benchmark sources using explicit package bases; secret scan passed for 191 source/document files; whitespace passed. Both requirements-resolution and actual installed-environment Python audits are clean after patches; frontend audit is clean. The existing React duplicate-key warning in the Opportunity test remains unrelated and unchanged. Earlier sandbox test runs stalled in subprocess/thread teardown; the final passing complete run used a 240s hard bound outside the sandbox. Leftover validation processes were stopped before live work.

Supported synthetic consumer scenario passed p99 queue-wait <5s (all observed waits <=10ms), no stale queue events and complete accounting. A 250-candidate sustained live workload, long-run storage viability, a physical crash/power-loss test and recovery at historical peak load remain unvalidated. The 500-event per-token buffer and the frozen recovery bounds remain explicit limitations; no arbitrary capacity expansion was made. No new readiness experiment or cohort follows automatically from these checks.

## Controlled live result (completed, not extended)

Live source: **`a940c8f1458c24d4f3efab4a2eb36a250e134ea2`**, clean when frozen. Config/source drift: false. Requested observation timer: 300 seconds. Actual total including startup/shutdown: **306.3066 seconds**, clean shutdown, no operational stop/error. No source/config edits occurred during acquisition. The later correction described below changes report export only, not acquisition.

Preserved report: `data/early_edge/remediation-20261024/smoke-20261024T040500Z.json`; retained DB: `smoke-20261024T040500Z.run/diagnostic-engine.db`; checkpoint: matching `-progress.json`. File SHA256: `c241b34ce084c7e8002eb360215d12b3f05cd70c6b23eb7bb86107d51869ae8d`. Internal report hash: `4b922969478dd5c7e1428736482b0eb649f08b0dcf1b72b38513d1efca1a1714`. Engineering receipt, package inventory, audit and benchmark receipts are alongside these files. These are new operational artifacts, separate from the completed failed experiment.

| Measure | Short live result |
|---|---:|
| Pump WSS messages / decoded launches / admitted creates | 80,022 / 105 / 104 |
| Accepted tracked trades | 4,324 |
| Processed AND persisted trades | 4,297 (2,433 buy / 1,864 sell) |
| Unprocessed trades at shutdown | 27 |
| All event-kind reconciliation invariants | true |
| Queue maximum / final count | 89 / 29 |
| Queue-stale trades / stale-processing resets | 0 / 0 |
| Overflow trade / non-trade drops | 0 / 0 |
| Drained queue-wait p99 histogram upper bound | 2 seconds |
| Maximum per-event processing / consumer tick gap | 0.139s / 2.412s |
| Unsupported Pump layouts / reconnects | 0 / 0 |
| Invalid units | 1,630: 1,211 unverified curve identity, 419 unsupported quote |
| Accepted known units / known-unit mints | 2,694 SOL / 49 mints |
| Recovery submitted / completed / pending at stop | 202 / 201 / 1 |
| Recovery overflow / expiry / peak pending / HTTP concurrency | 0 / 0 / 5 / 2 |
| Recovery classifications | 192 untracked, 9 tracked affected, 0 unsupported/unavailable |
| Global / local continuity resets | 1 intentional shutdown / 9 tracked recovery gaps |
| Distinct tokens sampled CURRENT / peak simultaneous | **7 / 5** |
| First CURRENT | **215.19s** |
| CURRENT clean-coverage observations | 181.24–252.47s; 147 repeated operational samples |
| Maximum clean coverage in 30s evidence snapshots | 267.77s |
| Background Pump state quotes | 5 attempted: 4 valid executable-USD, 1 unavailable |
| Quote slot / shape / acquisition-delay rejections | 0 / 0 / 0 |
| Primary T+10 probe availability | **1 of 1**, request at T+10.747s, state acquired at T+11.279s |
| EARLY observations / matched controls | 1 / 0 (one unmatched) |
| Solana RPC total / errors / 429 | 254 / 0 / 0 |
| Normal-path HTTP generated by trade decoder | 0 |
| RSS mean / peak | 113.99 / 135.87 MiB |
| CPU mean / peak (operational sample means) | 34.79% / 88.5% |
| Storage growth / retained final DB | 23.11 / 23.55 MiB |
| Storage censorship / resource pressure / observation pauses | none |
| Core final event decisions | 76 WAIT / 28 REJECT |
| Paper cash / positions / pending entries | $20 / 0 / 0 |
| Real cohorts / prospective outcomes / early-edge tables | 0 / 0 / none |

The 27 trade, one create and one security event still queued at stop were not applied; the stopped receipt preserves this terminal-boundary accounting. They are not overflow drops, not a promise of recoverable queued work, and not silently counted as processed. One recovery remained unresolved at cancellation. Intentional shutdown ends coverage globally; post-shutdown blocker vectors therefore cannot be used as the last live CURRENT census. The last 30-second evidence snapshot had 0 CURRENT / 14 PARTIAL / 79 UNAVAILABLE; CURRENT occurred between snapshot boundaries and is captured by the more frequent operational sampler. No 180-second window or freshness tolerance was shortened.

CURRENT-only observed buyer/flow distributions are descriptive repeated samples: independent buyers 1–42, flow ratio 0.0162–3.0186, whale share 0.0485–1.0. None of these counts implies an entry gate passed. The lone EARLY signal had 46.43% curve progress, age 205.31s and 41 estimated buyers; it had no matched control. Secondary 2s/5s entry availability was observed; 0.5s was unavailable. Three early quote attempts failed conservatively before valid later states. These are quote availability diagnostics, not realized fills, economic returns or prospective outcomes.

**Recovery export correction:** this live report's legacy `final_recovery_health.requests/successful_requests` fields are zero and must not be interpreted as zero HTTP. The already-recorded authoritative observer counted 202 recovery request starts while recovery backlog existed; total RPC was 254, leaving 52 non-recovery requests including ordinary monitoring AND diagnostic quote acquisition. The exact success count cannot be recovered from those legacy zeros; 201 classified recoveries completed and one request/recovery was pending at stop. The existing `TruncationRecovery.snapshot()` correctly merges provider counters and bounded scheduling latency diagnostics. The final reporting-only patch switches all diagnostic recovery exports to that canonical API and adds regression assertions on the existing mock-HTTP recovery test. Scheduling/limits/correctness gates are unchanged. The original live JSON is preserved rather than rewritten to hide this limitation.

### Before/after interpretation

The historical failed run accepted 165,623 trades but processed 86,913, with 72,903 queue-stale trades, 5,162 trade/44 non-trade overflows, 5,408 recovery global gaps and no sampled CURRENT. The short smoke accounts for every accepted event, with no runtime stale/overflow loss, seven CURRENT tokens and a valid primary latency quote. These outcomes, the synthetic replay and the 250-candidate profile support the targeted fixes. Different duration, candidate count and traffic prohibit claiming a normalized six-hour speedup or that reconnects/recovery pressure are solved under historical peak load. The old run's low average CPU was partly storage-censored, so CPU means are not a valid direct performance comparison.

### Acceptance and remaining limitations

**Conditional GO for a separately authorized NEW frozen readiness-validation run. PRE_COHORT_READY remains NO. No new run or cohort was initiated.**

Met in bounded testing: event disposition reconciliation; no silent detached-batch loss; actual application freshness; deliberate overflow remains fail-closed; lossless replay-context parity; protected negative/unavailable/paper/version retention under synthetic pressure; explicit storage censorship and restart receipts; fixed sampler success/quota/deadline handling; no normal trade HTTP; real canonical CURRENT under unchanged gates; no observed quote slot/integrity defect; no source drift; zero cohorts/outcomes. Full quality/security checks pass.

Not established by a five-minute smoke:

- Sustained live operation at 250 active candidates, historical peak bursts or six-hour storage pressure. Linear extrapolation of short-window growth is about 272 MiB/hour and would exceed 1 GiB over six hours without reclamation; the new byte policy must be observed at scale, not presumed adequate.
- Physical crash/power-loss and competing external-writer behavior. SQLite tests cover bounded writes, logical interruption/reopen and censorship durability, not all filesystem failures. Periodic receipts leave an explicitly unknown crash tail after their last timestamp.
- Complete windows for tokens exceeding the unchanged 500-event capacity; those remain PARTIAL after detected buffer loss. No approximate wallet/flow state was substituted.
- Known units for unsupported quote assets or before curve verification. They remain unavailable and can poison a mixed window intentionally.
- Matched-control coverage or any statistical edge. One unmatched observation cannot establish either; the original four unmatched observations remain historical and unchanged.
- Live PumpSwap state quoting in this smoke (no pool arguments supplied), or the separate fail-closed PumpSwap event suffix investigation. Its decoder was not modified. Forty-eight pinned SDK goldens remain the ordinary reference check; opt-in Node live parity was not run and its null result is not a parity pass.
- Continuous background quote availability: the sampler is intentionally budgeted and constrained to bounded mint/pool sets. Its five background samples occurred early; the independent primary-entry task demonstrated valid acquisition around T+266s of runtime. This is not proof that every future deadline can be met.

Any new readiness validation must freeze the final clean source and installed-package inventory, retain a fresh bounded DB and quality receipts, preserve censored/unknown outcomes, and stop/investigate on unexplained schema failures, failed accounting, source drift, excessive observation pauses or essential-storage exhaustion. It must report capacity and storage censorship rather than improve signal counts by changing thresholds. Creating a real cohort remains a separate review decision.

## Commit and file boundaries

### Baseline investigation: `cb0b40036a8783615e45d51a7f98b06c239174e8`

```text
docs/validation/early-edge-root-cause-20261024.md
```

### Phase 1: `e1a3dc17c3c73f73e0374c6a771b8c7f2b1fcdd7`

```text
backend/app/domain.py
backend/app/engine.py
backend/app/evidence_pipeline.py
backend/app/features.py
backend/tests/test_evidence_remediation.py
docs/validation/early-edge-remediation-20261024.md
```

### Phase 2: `b228cf89ac99638283c77c650c52dd0d664e1052`

```text
backend/alembic/versions/0005_evidence_audit.py
backend/app/db.py
backend/app/engine.py
backend/app/evaluation.py
backend/tests/test_evidence_storage.py
docs/validation/early-edge-remediation-20261024.md
```

### Phase 3: `79a3f921823ec04fae9ef91cf8450f35ae5703e1`

```text
backend/app/early_edge_scheduling.py
backend/app/early_edge_telemetry.py
backend/tests/test_early_edge_scheduling.py
backend/tests/test_early_edge_telemetry.py
docs/validation/early-edge-remediation-20261024.md
scripts/early_edge_diagnostic.py
```

### Phase 4 live-tested source: `a940c8f1458c24d4f3efab4a2eb36a250e134ea2`

```text
backend/app/db.py
backend/app/discovery.py
backend/app/domain.py
backend/app/early_edge_runtime.py
backend/app/engine.py
backend/app/evidence_pipeline.py
backend/app/opportunity.py
backend/tests/test_evidence_remediation.py
backend/tests/test_evidence_storage.py
docs/validation/early-edge-remediation-20261024.md
frontend/package-lock.json
scripts/benchmark_evidence.py
scripts/early_edge_diagnostic.py
```

The final follow-up commit contains only the canonical recovery snapshot export, its existing recovery regression assertions and this consolidated report. Its SHA is supplied in the delivery. No branch was merged or pushed.

Final follow-up validation: complete backend **723 passed, 1 skipped in 122.40s**; targeted recovery/export/telemetry/security regressions **161 passed**; Ruff, mypy (44 checked sources), secret scan (191 files) and whitespace passed. Frontend 39/39, TypeScript/build, installed Python audit, requirements-resolution audit and patched frontend audit remain green. No frontend source or dependency changed after those checks. The recovery exporter correction was regression-tested after the smoke; no second live run was started to manufacture a favorable result.

# Synthetic endurance validation — 2026-10-24

Branch remediation/early-edge-evidence-readiness; starting source 8529b467fc24d767c13847f2d3061bd745cb1d12. PRE_COHORT_READY remains NO. Historical evidence and retired cohort must remain unchanged. No live acquisition, cohort, execution, six-hour run or automatic push.

## Baseline checks and host

Corrected complete backend suite: 751 passed, 1 skipped in 153.64s. Complete frontend: 39 passed in 5.35s; TypeScript and production build passed (3.75s build). The existing load harness is extended, not replaced; no production application code changes are proposed.

Host snapshot: AMD Ryzen 7 PRO 3700U, 4 physical cores/8 logical CPUs available to WSL. Kernel 6.18.54.1-microsoft-standard-WSL2; WSL-visible RAM 11,435,442,176 bytes, swap 3,221,225,472 bytes, no cgroup CPU/memory quota. Project ext4 filesystem capacity 1,081,101,176,832 bytes with ~1,011,389,210,624 available at baseline; /tmp is tmpfs (~5.72GB). Windows/WSL host activity and thermal scheduling are uncontrolled. Full source snapshot and contemporaneous limits are preserved in data/early_edge/endurance-20261024/hardware.json. No limits were raised. The synthetic DB is retained on the project filesystem rather than temporary tmpfs for endurance; this deliberate storage-topology change is recorded, so timing is not represented as a perfectly identical short-run comparison.

## Predeclared protocol and gate

First: 600 seconds, 250 candidates, average 50 normalized synthetic trades/s (30,000 scheduled trades), 200 initial synthetic warm events/candidate, 0.7 recoveries/s, mocked standard RPC. Every ten seconds begins with 100 arrivals over one second and then 400 over the remaining nine seconds; strict order and total input rate are preserved. One normal queued create per minute exercises admission/eviction (9 over 600s). No candidate eviction rule is bypassed; all new candidates require their own evidence. Periodic shared-provider quote-load stand-ins arrive at synthetic signal T+10, deadline T+20, <=5-second request timeout, no future-selected retry or fabricated loss. Other mock RPC response delays are 0.35s, periodically 1.5s; recovery response delay stays 0.15s. The actual executable-quote/deadline semantics remain covered by existing deterministic suites; these endurance stand-ins are not real quotes or research outcomes.

Continuously preserve source/harness identity, one-second scheduled samples (actual times reflect loop lag), frozen nested counters, per-minute latency percentiles, mean/peak CPU, RSS, DB/WAL/SHM bytes, queue depth, terminal event/recovery reconciliation and gap categories. Samples and event latency arrays have explicit CLI duration/rate bounds (maximum 1800s and 100/s in opt-in endurance). Existing normal diagnostic limit remains 600s. Production limits remain 250 candidates, 25 deep, 1,000 queue, 500 event buffer, 20s freshness, 180s continuity, recovery 2/32/45s/3 attempts and existing storage guard. The 250ms consumer sleep is unchanged.

Retain isolated synthetic DB and stopped receipt. On clean shutdown read its integrity and original terminal ledger, reopen using the actual engine restore path without starting provider tasks, and verify bounded restored candidates, empty rewarming windows, security requiring refresh, cash $20 and no positions. If storage guard activates, preserve its receipt and do not bypass it merely to restart. No raw historical database is opened writable. Progress is atomically replaced only in the new diagnostic namespace; historical artifacts are never rotated.

The 30-minute run is conditional on ALL of: full 600-second generation; application and admitted-to-processing p99 <5s; no stale processing/queued-stale, queue overflow or critical loss; no unexplained accepted-event discrepancy; no observation-pause gap, recovery overflow/expiry/shutdown remainder; allocated storage below the unchanged guard with censorship visible; peak RSS <500MiB normal target; successful stop/integrity/restart with no current evidence carried across restart. Churn-related explicit admission/untracked filtering is reported separately, not called processed evidence. Any unclassified exception, source drift or audit inconsistency blocks the longer run. Intentional end-of-run coverage invalidation is distinguished from infrastructure gaps. Do not average away a failed global latency criterion; minute-level trends are also reported. No CPU threshold is invented: saturation and trends are reported as operational risk.

Only if that gate passes: separately measured 1800 seconds using the same protocol and source, 90,000 scheduled trades, 29 queued turnover creates and 1,260 recovery arrivals. No source edit between the two runs. Do not tune to the first result or start a six-hour experiment.

## Harness validation before endurance

Development-only three-second check: 150 trades processed, SQLite integrity ok, 250 candidates restored with empty windows and stale security, paper cash $20 and zero positions. This is not endurance or market evidence. Protocol tests cover burst totals/order, physical WAL/SHM accounting and refusal of selected cohort environment. Typed unavailable counts remain distinct from hypothetical economic loss. Safety guards stop new synthetic production if the actual engine or observer stops; cancelled/unfinished work remains reconciled in terminal receipts.

Endurance results and decision follow after measurement; no passing result is assumed.

Final harness regressions: **4 passed in 18.86s**, including delayed shared-provider traffic and actual engine cold restore. The first development integration test exposed a diagnostic-only short-duration scheduling bug (floor division excluded a T+10 request in a 12-second partial block); it was fixed before protocol freeze. The 600/1800-second schedules are unchanged by that correction. Ruff/mypy/secret/whitespace checks passed; backend installed and frontend dependency audits report zero known vulnerabilities. Full backend baseline above predates only these isolated harness tests; production application files remain identical to 8529b46.

## Completed ten-minute endurance — FAILED

Measured source **29857e7a7ed309eb7de40a19bb42607cfb4793b9**; unchanged production application from 8529b46. Requested input duration **600s**, with **619.54097s** measured generation/drain/shutdown and a separate **1.34947s** cold restart. All 30,000 scheduled trades and 9 turnover creates were submitted. The conditional 1800-second run was **NOT STARTED**, because the first run failed its explicit gate. No duration, rate, capacity or evidence threshold was adjusted.

| Criterion | Measured result | Assessment |
|---|---|---|
| Complete declared workload at 250 candidates | 30,000 trades; active min/max 250/250 | PASS input/capacity, not throughput |
| Application-age p99 <5s | p50 19.790s; p95 21.690s; p99 **32.804s**; max 39.572s | **FAIL** |
| Admitted-to-processing wait p99 <5s | p50 19.136s; p95 21.150s; p99 **31.921s**; max 38.306s | **FAIL** |
| No stale application / queued staleness | **9,959** stale processing rejections; **9,609** trades stale while queued | **FAIL**; different predicates, not additive |
| No overflow/critical loss | **698 trades dropped**, peak queue **1,000**; zero critical drops | **FAIL trades**, PASS critical drops |
| Complete terminal accounting | Every type and every sampled ledger reconciles; final pending/in-processing zero | PASS accounting; not evidence completeness |
| Recovery bound/fair progress | **420/420 completed**, all first attempt, peak pending 2; zero overflow/expiry/shutdown remainder | PASS mocked recovery |
| Observation pause/global loss | No observation-pause gap, max loop tick gap 3.948s; one intentional shutdown global gap | PASS tick/shutdown safety; no real transport tested |
| Bounded normal RSS <500MiB | **229.785MiB peak**, first sample 177.832MiB | PASS ceiling; no plateau established |
| Storage below unchanged 1GiB guard | <=60,433,424 bytes across run/stop/restart observations; no storage censoring or guard activation | PASS observed envelope only |
| Safe shutdown / restart | Durable STOPPED receipt, exact old accounting retained, integrity ok, 250 restored with empty windows/stale security | PASS |
| Delayed shared-provider requests | 20/20 stand-in requests within synthetic T+20 deadline; monitoring stand-in 106 requests | PASS stand-in load, not executable quote evidence |

Application-age percentiles include all **29,302 processing attempts**, including explicitly rejected stale/untracked events; dropped events have no application time and remain in loss accounting. Producer scheduling lag p99 1.739s, max 2.729s. Individual synchronous process duration p50/p95/p99/max **10.157 / 27.064 / 32.814 / 126.709ms**. These are distinct from the queue wait. Aggregate successfully processed throughput including drain is **31.18 trades/s**, versus 50/s scheduled input. Do not use fast stale rejection as evidence-processing throughput.

Exact trade reconciliation:

```
30,000 submitted = 29,441 accepted + 559 incoming rejected
29,441 accepted = 19,317 processed/persisted + 9,959 stale
                + 26 untracked after churn + 139 accepted then evicted
698 drops = 559 incoming rejected + 139 evicted
```

All 9 turnover creates were accepted into the queue: 7 processed/persisted and 2 explicitly rejected by normal admission rules. No admission threshold was weakened. The 26 untracked trade returns are separately counted intentional lifecycle/admission filtering, not successful evidence. Token-local resets total **10,656**: 9,959 stale + 697 queue. Queue-reset counts and dropped-event counts are different predicates: gap propagation applies to currently tracked mints and may coalesce; the diagnostic does not retain a raw dropped-event list proving the individual one-event difference. There is no unexplained *event-accounting* difference. Buys/sells successfully processed: **12,734 / 6,583**. No synthetic trade is prospective evidence.

Mean CPU was **71.05% of one core**, sampled peak **94.7%**. This is not simply a sustained 100% CPU saturation failure: synchronous persistence adds blocked wall time, and rejected events avoid expensive processing. The run never relaxed the 20s rejection rule to drain stale work as valid evidence.

## Time trend, persistence and memory

Minute-level application p99 (processing-time buckets): **12.092, 20.505, 21.165, 38.447, 21.216, 21.632, 22.196, 22.193, 23.171, 23.194s**; drain bucket 21.284s. Failure appeared during the first minute and persisted, rather than being a single terminal shutdown artifact. The later smaller backlog does not erase stale/drop loss. Per-minute application buckets and continuous actual-time resource/accounting samples are preserved in the JSON. Sampling produced 520 records; a nominal one-second sampler is delayed by event-loop work, so exact timestamps are authoritative rather than an invented 600 evenly spaced samples.

Inclusive stage measurements: analyse **92,433 calls / 182.876s**; DB.add **27,479 / 127.794s**; reserve_event **19,335 / 70.742s**; intelligence.refresh **294 / 79.740s**. Inclusive timers overlap (including per-event analysis inside processing); do not sum them as exclusive CPU. In the initial cold profile, 250 SQLite commits consumed **0.658s**, versus a much smaller tmpfs cost in earlier short tests. The real consumer still synchronously reserves identities and commits evidence, in addition to periodic 250-candidate analysis/checkpoints and observational research work.

A separate bounded component comparison after endurance (no competing workload) used the same production Database.reserve_event + Database.add methods, 200 synthetic 16KB records and two commits/iteration, with identical SQLite settings and both location orders:

| Location/order | Wall seconds | CPU seconds | p50 / p99 per iteration |
|---|---:|---:|---:|
| tmpfs first | 0.804 | 0.804 | 3.714 / 7.814ms |
| project second | 2.387 | 1.105 | 9.736 / 30.246ms |
| project first | 2.090 | 1.017 | 9.137 / 23.214ms |
| tmpfs second | 0.863 | 0.863 | 4.267 / 7.943ms |

This **2.4–3.0x component wall-time difference** corroborates filesystem-backed commit cost as a material bottleneck. It does not prove that storage alone explains the entire endurance failure: bursts, duration, turnover, diagnostic sampling and delayed shared-provider load also differ from the original short test. No database durability pragma was weakened. The exact component source and its SHA/output are preserved as `storage-corroboration.py/.json` in the new artifact directory; it is not a second event-processing engine or a load-acceptance substitute.

RSS rose ~52MiB over the observed window, staying below 500MiB without a demonstrated plateau. Bounded metric samples, latency arrays and growing per-token histories all contribute; these observations neither prove a leak nor establish hour-scale stability. No heap-profiling result is invented. SQLite main DB grew from 2,859,008 to 57,901,056 sampled bytes; sampled WAL peak **189,552 bytes**, not sustained accumulation. Main DB after shutdown: **60,063,744 bytes**; restart audit observed main 60,227,584 + WAL 173,072 + SHM 32,768. No raw omission/reclamation occurred. Natural long retention horizons and the physical guard were not reached during this run; earlier accelerated pressure/crash tests remain separate evidence. Growth under stale/drop loss underestimates the storage needed for successful lossless processing and must not be projected as six-hour viability.

Read-only post-run audit verified **19,574 stored event references** (250 setup creates + 7 timed creates + 19,317 timed trades), **23 context hashes**, no foreign-key violation, integrity ok, zero prospective cohort rows, and the unchanged original stopped accounting after restart. Synthetic ordinary Opportunity diagnostic records remain confined to this isolated database; they must never be imported as prospective observations. Cash remains $20 with zero positions. Restart restored no pre-earned rolling evidence or verified security.

## Post-measurement cleanup and validation

The diagnostic originally used SQLite's transaction context manager for its read-only stopped-receipt check; that context does not explicitly close the connection. It retained one bounded audit-reader handle until function/process teardown and explains why post-restart WAL/SHM could remain allocated in the recorded audit. After the completed run, local commit **3e823c5d196d5bd3ae7237831dae39c914c11f9d** uses explicit contextlib.closing. Focused regressions now also require zero WAL/SHM after restart cleanup: **4 passed in 18.02s**. This changes only post-measurement diagnostic cleanup, not production or the measured hot path. The failed 600-second source/result remains 29857e7, unaltered; no rerun is substituted for it.

Final Ruff/mypy (43 sources), secret scan (200 source/document files) and whitespace checks passed. Baseline complete backend **751 passed / 1 skipped** and frontend **39 passed** are reused; only the isolated new harness tests were added afterward and rerun following cleanup. Dependency audits: no known installed backend vulnerabilities; zero frontend vulnerabilities. No dependency manifests changed. Full production backend/app source remains byte-identical to 8529b46. Frozen historical hashes and retired database identity are reverified before final commit.

## Decision and required engineering work

**A separately authorized six-hour live readiness experiment is NOT justified yet. PRE_COHORT_READY = NO. The 30-minute synthetic run was correctly withheld.** Functional safety, terminal accounting, restart integrity, observed WAL bounds and mock recovery passed; operational lossless sustained processing failed clearly.

Priorities for further work, before repeating this gate:

1. Profile and redesign only the measured synchronous persistence path: bounded units of work for identity/context/event writes and periodic checkpoints, with explicit transactional durability boundaries. Preserve replay chronology, source snapshots and all negative/unavailable evidence. Do not simply move writes behind an unacknowledged queue or count uncommitted rows as persisted.
2. Add failure-injection/rollback/cancellation/crash regressions proving token state, event identity, terminal ledger and committed evidence remain reconcilable under any proposed batching/offload. Keep storage reserves, FULL consumption, 20s/180s rules and existing risk gates intact. No quick production batching change is made in this task because those proofs do not yet exist.
3. Separately measure CPU/analysis and observer costs on the actual project filesystem with controlled single-variable comparisons. The successful tmpfs short test does not certify sustained durable storage performance. Do not reduce sampling/admission or drop evidence to recover a passing score.
4. Establish longer memory/retention stability only after lossless throughput is restored. If 600s then passes all the same gates, a fresh separately measured 1800s synthetic test is the next conditional step; no automatically scheduled live run follows.

Reproduction of this failed protocol (new unique paths only):

```
.venv/bin/python scripts/validate_evidence_load.py --seconds 600 --rate 50 --endurance --output <new-unique>.json
```

The isolated test retains its own .run database, progress and profile outputs. `--seconds 1800 --endurance` is technically available but must not be invoked until the 600s gate passes. All artifact identities and measured decisions are summarized in `data/early_edge/endurance-20261024/assessment.json`. No source edits occurred during the measured run; post-run diagnostic cleanup is explicitly versioned separately. No push, live request, cohort or trading operation occurred.

Additional post-run report-integrity regression: the legacy embedded SHA256 is not directly JSON-roundtrip-canonical because recovery rolling-window maps originally use integer keys (1,5,10). Restoring those documented key types in `pre_stop.recovery` and `final_recovery` reproduces the original embedded hash exactly; the completed file is not rewritten. Future diagnostic reports now normalize JSON keys before sealing, with a focused roundtrip/non-mutation regression. This is a serialization-only fix after measurement, not a changed latency sample or rerun. Independent file/source SHA256 hashes remain the artifact identity. The updated harness test result is recorded in the structured assessment and final response.

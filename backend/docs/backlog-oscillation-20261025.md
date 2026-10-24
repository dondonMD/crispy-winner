# Backlog instability diagnosis — 2026-10-25

PRE_COHORT_READY=NO. Verified clean published starting HEAD6c084ae056f6a4a7c886c0a1517340230945524e on remediation/early-edge-evidence-readiness. Published storage optimization:0ad862c; regression/report commit:6c084ae. No GitHub recovery/audit, transaction consolidation or production optimization repeated.

## Preserved historical comparison

All findings use the preserved120s optimized50/s trials, identical source overlay, settings, warm history,250 candidates, deterministic50/s burst schedule and project ext4 storage. No historical artifact rewritten. Trial1 passes the unchanged gate; trial2 fails it. Their latency, durability and zero-loss checks pass; that does NOT override the growth failure.

| Measurement | Trial1 PASS | Trial2 FAIL |
|---|---:|---:|
| p99 application / queue wait, s | 2.501 / 2.358 | 2.548 / 2.409 |
| Exact deficit20s /120s | 66 /43 | 44 /75 |
| Completions20..120s, /s | 50.23 | 49.69 |
| Early-three /late-three mean deficit | 62.667 /39.667 | 51.333 /64.333 |
| OLS deficit slope, events/s | -.272727 | +.126364 |
| Commit cumulative wall, s | 26.064 | 25.876 |
| Reserve + raw inclusive writer wall, s | 34.315 | 34.138 |
| Analysis wall / calls | 40.158 /22,787 | 41.508 /22,249 |
| Intelligence.refresh wall, s | 13.218 | 13.031 |
| Restore checkpoint wall, s | .855 | .843 |
| Producer scheduling p99 /max, s | .937 /1.208 | 1.067 /1.278 |
| Sampled event-loop lag p99 /max, s | .174 /.203 | .229 /.299 |

Trial2 is NOT explained by larger cumulative SQLite write/commit time: these were slightly LOWER, as were restore-checkpoint and refresh totals. Analysis averaged ~1.762ms/call vs ~1.866ms/call (+5.9%), with fewer calls but +1.35s inclusive time. Timer totals overlap and cannot be summed as exclusive CPU. This is scheduling/cost variation, not a proven reusable-analysis defect. Last110..120s:494 vs466 completions; analysis3.674 vs3.835s; commit2.036 vs1.923s. The failed interval's commits were faster, so blaming a long SQLite stall there is unsupported.

The failure's13-trade late-minus-early mean is .26s at offered50/s. Its20..120s endpoint increase31 is .31events/s; OLS is+.126364. These are different statistics, not interchangeable estimates of long-term capacity. Aligned deficits oscillate44,66,44,57,60,67,69,45,77,41,75. They do not show an unbroken trend, but still fail the unchanged gate. Neither a low p99 nor a post-hoc alternate window may reclassify the trial.

## Burst and pipeline decomposition

The original schedule delivers100 events in the first second of each10s block, then400 over9s. Arrival-aligned cuts do not align with the consumer's100-event drain, cooperative yields, periodic analysis/refresh and unchanged250ms idle cadence. A fixed-cut deficit includes events not yet submitted, queued/detached work and failed/nonpersisted dispositions, not simply SQLite waiting.

Historical one-second samples (timestamps are slightly before their snapshots):
- Trial1: mean scheduled-not-submitted19.345, pending36.936, detached19.109, total scheduled-not-persisted75.391.
- Trial2:21.382,39.673,18.327,79.382 respectively.
- Thus mean total deficit differs by~4 trades, not continuous large accumulation. No loss/terminal divergence: decomposition residual zero. Max sampled total127 vs128, and queue peaks148 vs139. These irregular samples cannot reconstruct exact10s producer counts, so those fields stay UNAVAILABLE_HISTORICAL.

## Environment and causality limits

Same WSL2 kernel6.18.54.1, CPython3.13.16, SQLite3.53.1,8 logical CPUs/affinity0..7, memory11,435,442,176 bytes; cgroup CPU/memory limits max, no throttled periods. Project /dev/sdd ext4, discard,data=ordered. Available memory~8.37–8.39GB; swap0. No sampled memory pressure.

First-to-last sampled shared PSI: CPU .278451 vs .249848 stall-seconds; I/O4.100907 vs4.131008; memory0 in both. Mean process CPU68.19% vs68.89%. These measurements do not establish unusual host CPU or I/O contention as the cause. Per-process I/O counters are unavailable; cgroup I/O is shared. Automatic WAL checkpoint work is included in commit timing; separate fsync/checkpoint start/end traces do not exist. WAL peak234,872 vs197,792 bytes and zero after shutdown do not identify exact checkpoint timing. No forced checkpoint/caches/filesystem changes are introduced to manufacture comparability.

Confirmed: finite processing/arrival phase differences change a small positive-vs-negative slope under the fixed criterion; genuine post-warmup completion deficit exists in trial2. Not confirmed: persistent unbounded accumulation, host contention causality, automatic-checkpoint causality or an avoidable production analysis defect. Existing artifacts cannot supply exact aligned admission phase. No production change is justified yet.

## Diagnostic-only improvement and predeclared replay

Add two bounded per10s counters to the SYNTHETIC harness, reusing already captured timestamps: producer-ready and processing-start. Producer-ready is before MarketEvent construction/submit, NOT a successful durable admission. Together with existing durable bins these permit exact cuts: scheduled-not-ready + ready-not-started + started-not-durable = scheduled-not-durable. Failures remain in the event ledger; do not call nonpersisted work zero flow. No new timers/tasks/network/persistence operations or scheduling rules. Existing maximum1800s/100events/s bounds total work.12,000 counter increments measured .003367s in an isolated operation probe; not a claim of zero whole-harness overhead.

Read-only scripts/analyze_evidence_backlog.py uses the original scheduled_offset, same half-open10s cuts, same slope<=0 AND late<=early guard. It preserves unavailable historical data, rejected/evicted/nonpersisted terminal dispositions, metadata absence and finite sample limits. Five targeted tests plus existing harness/repro suite:15 passed23.71s; Ruff/type checks pass. No backend/app change.

Next: fresh serial120s40/s regression followed by up to THREE50/s trials on frozen source/config. Stop at first failure; no replacement run. All latency/accounting/shutdown/growth gates unchanged. Only three consecutive complete passes permit consideration of one600s synthetic endurance run. No 30-minute,6-hour, cohort or trading run. Every failed result retained; PRE_COHORT_READY remains NO.


## Fresh frozen-source validation

Diagnostic implementation commit: **e77ccc461589ed6d0f79085ed01b803c69daf51c**. No production changes relative to6c084ae. Both serial runs used clean e77ccc4, unchanged250 candidates/200 warm history/20s freshness/queue1000/shared recovery/burst/cadence/storage budget and identical settings hash88165dc561fc75ab068452f62079ae275a03997c166512e2c3bd01266fe5d684. The50/s workload hash remains3f426da15fc972ec62d5141b9e9317ce41ddf2546c3e4f552600553c23a3254d. Only additive diagnostic bins changed harness SHA to678953b6de31c4f75fa2bc515e2047f82c6ccc51dfc315a3c00517cf0d3d8ac9. Source/settings match at completion. No competing quality jobs/benchmarks during either run.

| Metric | diagnosis-40 | diagnosis-50-1 |
|---|---:|---:|
| Input duration, s | 120 | 120 |
| Actual elapsed incl drain, s | 121.347 | 122.385 |
| Persisted/submitted | 4,800/4,800 | 6,000/6,000 |
| Application p50/p95/p99, s | 1.166/1.807/2.015 | 1.571/2.345/2.609 |
| Durable p50/p95/p99, s | 1.176/1.818/2.021 | 1.584/2.354/2.619 |
| Queue p50/p95/p99, s | .897/1.405/1.714 | 1.073/2.224/2.484 |
| Queue peak | 107 | 146 |
| Mean/peak process CPU % | 69.77/94.0 | 68.54/88.4 |
| Peak RSS MiB | 208.45 | 210.88 |
| DBAPI commit count/wall s | 9,731/21.540 | 12,121/26.115 |
| Commit p99/max ms | 12.528/43.474 | 12.378/48.891 |
| Sampled WAL peak bytes | 197,792 | 201,912 |
| Final DB bytes | 14,639,104 | 17,281,024 |
| Stale/dropped/pending | 0/0/0 | 0/0/0 |
| Recovery completed/accepted | 84/84 | 84/84 |
| Growth early/late mean | 45.667/26.667 | 52.667/64.667 |
| Growth OLS slope events/s | -.196364 | +.183636 |
| Result | PASS | FAIL growth |

Commit quantiles retain the existing last8192 samples; total count/time covers all calls and includes maintenance. Both SQLite states unchanged: WAL,NORMAL,busy5000ms,autocheckpoint32,page4096. WAL/SHM zero after shutdown. No forced checkpoints, tmpfs substitution or limit/cadence changes.

### Exact cause of the NEW failed cut

| Cut | Scheduled-durable | Scheduled-not-ready | Ready-not-started | Started-not-durable |
|---|---:|---:|---:|---:|
| 20s | 48 | 17 | 31 | 0 |
| 30s | 68 | 6 | 61 | 1 |
| 40s | 42 | 21 | 20 | 1 |
| 100s | 42 | 26 | 15 | 1 |
| 110s | 65 | 7 | 57 | 1 |
| 120s | 87 | 9 | 77 | 1 |

Every exact-cut component sums to the ORIGINAL deficit. Early-three component means:14.667 not-ready,37.333 not-started,.667 not-durable. Late-three:14,49.667,1. Thus the12-trade mean increase is chiefly **+12.333 ready-but-not-started**, not increased producer lateness. In100..120s, ready-not-started grows62 while not-ready improves17;955 trades durably complete against1000 scheduled. This is genuine finite consumer-pipeline lag, not a SQLite commit still in flight or hidden loss. At100s debt equals40s; recurrent rises and recoveries show oscillation rather than uninterrupted accumulation. Neither fact waives the fixed criterion.

New total analysis40.155s is nearly identical to the historical PASS40.158s; commit26.115s vs26.064s also nearly identical. Refresh13.504s is+.286s; no single large stall explains the result. In110..120s analysis3.795s, commit1.944s and478 completions; the historical passing interval had3.674s,2.036s and494. This is consistent with altered placement of cooperative producer, drain, periodic work and the existing idle cadence. It does NOT establish an avoidable duplicate calculation, host bottleneck, or fully quantified causal share for each stage. No production optimization is justified from aggregate timing alone.

Fresh sampled PSI CPU .285588s / I/O4.072981s / memory0 is close to both historical trials. No rate limiting/recovery overflow, source/config drift, memory pressure or anomalous overall commit time observed. Host/hypervisor I/O contention and per-auto-checkpoint attribution remain unproven, not ruled out by averages.

The serial driver stopped after the FIRST failed50/s gate. No trials2/3, no600s, no30min or6h. Low p99 is not an authorization substitute. All failing/good artifacts are preserved under data/early_edge/backlog-diagnosis-20261025/ with reports/progress/gates/process receipts, original databases, analysis JSON, operation-cost probe and comparison.json.

### Reconciliation and failure invariants

Read-only SQL independently verifies4800/6000 unique raw trade IDs, exactly matching durable trade identities and ledger persisted counts. No rejected/evicted critical events, no stale trades, detached/queued work or recovery pending at shutdown;84/84 recovery success each, no overflow. Both processes return normally with zero remaining workers. Cold-restart integrity ok, windows empty/security refresh required, no cohort rows. One intentional global shutdown reset/run and zero token-local resets; do not report zero total continuity resets. The original transaction/counterexample tests, SQL durability and all financial/evidence semantics remain unchanged.

## Quality, files, limits and next engineering decision

Fresh focused diagnosis/harness/repro: **15 passed in23.71s**, including12s retained synthetic integration/restart and exact arithmetic, original burst schedule, unchanged pass/fail outcomes, missing historical data and loss/terminal decomposition. Fresh full Ruff; mypy45 source files; secret scan220 files; whitespace checks passed. Fresh frontend tests39/build pass. No application/frontend/dependency change, so the previous complete829 passed/1 skipped backend result at6c084ae is reused and explicitly NOT claimed as a fresh full-suite run. The existing sandbox cleanup caveat remains; no worker bypass/suppression introduced.

Fresh backend/frontend dependency-audit attempts remain UNVERIFIED due PyPI/npm DNS failures; outputs retained. Dependencies/lockfiles unchanged. No repo-wide GitHub audit/recovery repeated.

Files: scripts/validate_evidence_load.py (two counters only), scripts/analyze_evidence_backlog.py (bounded read-only analysis), backend/tests/test_endurance_harness.py (counter totals), backend/tests/test_backlog_diagnosis.py (five tests), this report and a publication-status note appended to storage-guard-capacity-20261025.md. All production backend/app code is unchanged. Final documentation commit SHA/publication outcome are supplied in the final response/receipt.

**Decision: no safe production optimization has been demonstrated as required.** The smallest validated improvement here is diagnostic visibility. The remaining qualifying failure is marginal finite consumer backlog oscillation near the50/s boundary; sustained capacity is NOT established. The next useful profiling work, before any production edit, is phase-tagged whole-consumer-pass timing and exclusive candidate-analysis/cache-miss cost attribution (bounded, no new timers), with external host I/O tracing if available. Neither a broad analysis rewrite nor a weaker/noise-adjusted acceptance criterion is authorized by these measurements. Do not relabel failure as sustainable capacity or launch longer qualification runs.

PRE_COHORT_READY=NO. No new cohort, trading, frozen-data change or readiness claim.


### Final local commit and delivery outcome

Local validated diagnostic commit remains e77ccc461589ed6d0f79085ed01b803c69daf51c. Final result/report updates in this document and storage-guard-capacity-20261025.md could not be staged: `.git/index.lock` creation failed with read-only filesystem. Both edits are preserved, not committed or discarded. Authorized normal `git push origin remediation/early-edge-evidence-readiness` returned128: could not resolve github.com. No successful push this session, no force/merge/main write or alternate remote history. The user-provided published base6c084ae remains the known prior publication; no fresh remote SHA is claimed.

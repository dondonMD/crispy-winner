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

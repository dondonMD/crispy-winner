# Time-correlated persistence and capacity investigation — 2026-10-24

PRE_COHORT_READY=NO. Started clean on remediation/early-edge-evidence-readiness at 2ed1ffcdad8856a23f2431bc83ccffb6da35e550. Synthetic only; no live cohort, trading, six-hour test or push. Historical evidence and retired database remain unchanged.

## Existing 6.129s failure: diagnosis before any production modification

Read the preceding reproducibility report and all three optimized replay JSON files. No production change was made for this initial investigation. Preserved derived correlation: data/early_edge/capacity-20261024/failed-replay-correlation.json, with hashes of original reports.

The failed B2 begins like the passing runs, then gradually falls behind during seconds10–30. At about9s all have only14–34 uncommitted trades. By29.27s B2 has169 accepted-but-uncommitted trades, versus42 at29.91s for B1 and48 at29.86s for B3. At39.10s B2 still has167; at59.10s it has267. This count includes detached in-processing work: queue.depth alone omits it. The service deficit precedes the60s outcome-expiry burst at approximately51–59s.

B2 commit wall time in bins10–20/20–30 is3.232/3.328s, versus2.126/1.888s in B1 and2.044/2.077s in B3. The extra roughly2.4–2.5s is the same order as120–127 arrivals at50/s and the observed extra backlog; this is a correlation, not a full counterfactual proof because timers overlap and samples do not land at exact boundaries. CPU feature totals remain17.78–18.01s. Longest recorded B2 refresh=.634s and longest commit=.100s, not a single6s blocking operation. The p99 process duration is63.57ms, versus23.58/24.46ms in B1/B3; queue p99=5.477s supplies most application age. No stale/drop/duplicate or queue-reconciliation defect explains the difference.

WAL stays197,792 bytes until later growth to218,392 around53s, after the deficit already appeared. That growth is not evidence that a large late WAL caused the initial slowdown. Internal automatic checkpoints, retention worker timing and physical device service cannot be assigned to a particular transaction from the old aggregate traces. These are the specific telemetry gaps to close; there is no justification for a speculative production rewrite.

## Predeclared next measurements

Keep the existing project ext4 filesystem,250 candidates,200 warm events, queue1000, buffer500,20s freshness,250ms cadence, recovery0.7/s, burst envelope and mock providers. Run120s at30,40,50 trades/s, strictly serial processes including setup/cleanup. This is a short capacity bracket, NOT proof of indefinite sustainability. Observe committed progress/backlog trends rather than equating nominal arrival rate with service capacity. Preserve every result. A50/s failure blocks endurance even if a later favorable60s replay occurs.

Diagnostic-only additions: transaction-role counts/latency in existing10s bins, timing of existing retention/evaluation/outcome operations, and successful durable-completion age after process returns from persistence. No new timer, forced checkpoint, writer queue, network request or source-evidence change. Existing application-age metric remains processing-START age for comparability; durable completion is separately labelled. Thread-local roles distinguish raw-event and identity commits from maintenance/read-only calls. Diagnostic aggregation uses a short lock, never across application work or I/O. Text reads and stage/role histories are bounded. Instrumentation overhead must be measured and disclosed.

## Diagnostic validation and reproducibility

Commit a07a1a5 changes only the harness, bounded diagnostic aggregation, focused tests and this new report. backend/app is byte-identical to2ed1ffc (Git tree30f2ae1c9c44b7d9545275cdf207ea43e208942d); frontend tree remains c4e4aa175fd529f0890ccbd712d7ce854a8460de. No production optimization or configuration change was made in this investigation. Existing bounded expiry transactions remain intact.

Ten focused tests passed in23.25s: retained synthetic end-to-end shutdown/restart, after-commit completion ages, existing settings, bounded histories, deterministic digest, thread-safe role aggregation, no added loop timers, and actual/stuck-worker cleanup controls. Stage capacity is20 diagnostic labels (previously16), NOT a change to candidate/queue/evidence limits. Role labels are a fixed nine-item whitelist; history caps remain128 long calls and181 ten-second bins; proc text reads cap8192 bytes. Thread-local writer scopes distinguish identity/raw-event from restoration, outcome, retention and read-only evaluation calls. The diagnostic lock never spans application work or I/O.

Component overhead:100,000 ordinary trace updates=.162s,100,000 role updates=.310s. Actual commit calls are only about6,000 per60s, not100,000. No cProfile, new heartbeat, forced WAL checkpoint, changed PRAGMA, reset maintenance phase, filesystem migration or CPU affinity adjustment during acceptance measurements. SQLite commit quantiles use the EXISTING last8192 sample bound: the120s40/50 runs exceed that bound, so their p99 is a trailing-sample quantile, not a whole-population quantile. Counts/totals/ten-second role summaries cover all measured calls.

All six runs used clean source a07a1a5, identical harness hash and settings hash88165dc561fc75ab068452f62079ae275a03997c166512e2c3bd01266fe5d684; fixed PYTHONHASHSEED=0. Inputs differ only by declared rate/duration and the existing deterministic schedule/normal turnover. No source/config drift occurred. Fresh project ext4 databases; kernel/Python/SQLite/PSI/affinity/resource receipts are retained. Absolute timestamps and host I/O service remain uncontrolled. Drivers wait through COMPLETE process exit before another setup begins; no benchmark overlapped another workload or quality suite.

## Rate comparison: finite observed capacity, not an indefinite guarantee

Rates use120 seconds each. Backlog is accepted minus committed, reconciled with queued PLUS detached in-processing events; queue.depth alone is insufficient. The comparison interval starts at the first sample>=20s and ends at the final sample. Endpoint/OLS-style trends are descriptive and sensitive to burst phase and one-second sampling, not statistical proof of a steady-state slope. All intentional bursts and outcome-expiry work remain included.

| Input trades/s | Persisted | App p50/p95/p99 s | Durable p99 s | Queue p99 s | Middle arrivals/commits per s | Backlog start/end | Queue peak |
|---|---:|---|---:|---:|---|---|---:|
| 30 | 3600 | 0.741/1.248/1.411 | 1.426 | 1.178 | 30.038/30.038 | 26/26 | 58 |
| 40 | 4800 | 1.091/1.664/1.846 | 1.856 | 1.530 | 40.005/40.025 | 22/20 | 93 |
| 50 | 6000 | 2.235/3.151/3.469 | 3.482 | 3.083 | 49.978/49.270 | 62/132 | 189 |

30/s: comparison20.33–118.81s, backlog26->26, observed service30.038/s.40/s:20.63–119.52s,22->20,service40.025/s.50/s:20.91–119.71s,62->132,service49.270/s against49.978/s observed arrivals,net+70 outstanding (+.708/s). This does NOT prove that50/s can never be sustained: the interval is finite and burst alignment matters. It DOES fail to demonstrate reliable non-growing backlog at50/s. Highest tested rate with clear non-growing backlog over this two-minute envelope is40/s; a global/indefinite maximum is UNKNOWN. No production input/candidate limit was reduced to40 to manufacture acceptance.

Latency passes at50/s do not erase the observed service deficit, the older6.129s replay, or filesystem sensitivity. All outstanding work drained before the unchanged freshness limit; no missed observations were hidden. CPU/RSS and exact storage/continuity records follow.

| Run | Elapsed incl drain s | Durable rows/elapsed s | Mean/peak CPU % | Peak RSS MiB | DBAPI commit count / wall s / p99 ms | WAL peak bytes |
|---|---:|---:|---:|---:|---|---:|
| capacity-30 | 120.904 | 29.78 | 66.41/84.7 | 206.54 | 7335 / 15.737 / 12.152 | 222512 |
| capacity-40 | 121.345 | 39.56 | 69.18/86.8 | 208.46 | 9712 / 20.695 / 11.975 | 214272 |
| capacity-50 | 123.282 | 48.67 | 69.63/93.1 | 210.46 | 12137 / 26.216 / 12.212 | 210152 |
| verify-1 | 62.896 | 47.70 | 69.18/92.7 | 201.84 | 6108 / 13.416 / 12.440 | 206032 |
| verify-2 | 61.871 | 48.49 | 69.74/86.5 | 201.86 | 6082 / 13.046 / 12.223 | 222512 |
| verify-3 | 63.110 | 47.54 | 69.47/87.6 | 201.93 | 6109 / 13.375 / 12.468 | 222512 |

Mean CPU is total process CPU divided by elapsed, expressed against one CPU, not all eight CPUs. Eight-CPU host saturation and memory exhaustion are not established. Sampled PSI, available memory and per-process I/O unavailability are preserved in JSON. Database allocation/WAL/SHM at start, in samples and after close are retained; WAL/SHM close to zero, storage limits unchanged. These runs do not stress the1GiB guard or establish hour-scale storage retention. DBAPI commit counts include read/no-op/connection work and MUST NOT be equated with unique durable events.

## Transaction attribution and isolation decision

| 120s input rate | Identity commit wall s | Raw-event commit wall s | Share of all commit wall | Retention total/max s | Evaluation total/max s |
|---|---:|---:|---:|---|---|
| 30 | 6.087 | 8.887 | 95.15% | 0.049/0.028 | 0.023/0.018 |
| 40 | 8.016 | 11.955 | 96.50% | 0.066/0.038 | 0.039/0.030 |
| 50 | 10.444 | 14.901 | 96.68% | 0.079/0.037 | 0.040/0.025 |

This narrows the actionable path to Database.reserve_event and Database.add(kind='event'), called synchronously from RadarEngine._process/drain_events. Normal identity/raw-event calls supply95–97% of measured commit wall time. Existing retention/evaluation are only tens of milliseconds per call in these replays; they are not the measured dominant bottleneck. Role is the active call context, not a forensic ID for an internal SQLite fsync. The old failing replay did not capture roles, so its exact slow transaction cannot be retrospectively identified.

Existing bounded expiry work remains necessary; it and candidate-wide refresh can amplify tail latency but do not explain B2's initial10–30s deficit. Feature calculation/candidate analysis remain material CPU work. No individual new maintenance operation is proven to be the unique physical cause. Internal auto-checkpoint/fsync/device waits remain conflated in commit durations; no unsupported causal claim about a specific WAL frame or external process.

**Bounded persistence isolation evaluated, not deployed.** Awaiting the same sequential commits on a worker can improve event-loop responsiveness but does not reduce required SQL/commit service or demonstrate sustainable trade throughput. It may just move delay from producer scheduling to queue wait. Offloading all Engine.process would also let the loop see partially mutated token/research/paper state; offloading only DB calls splits synchronous state boundaries and requires explicit publication/rollback semantics. A bounded immutable command/result writer and one-at-a-time durable acknowledgement would be required; no unbounded write queue or early persistence success is acceptable. The sandbox's denied executor wakeups prevent an honest normal worker-path performance validation here. No such architectural change is justified from the current measurements.

A future identity+event shared-transaction design must account for intervening independent financial/research writers, observer callbacks, token/creator mutation and crash/retry semantics before altering current commit boundaries. Existing expiry transaction regression coverage is not proof for that much wider event transaction. No SQLite durability, freshness, chronology, duplicate prevention or gate was weakened as a shortcut.

## Three60s checks and the separate capacity condition

The driver declares up to three consecutive runs and stops at the FIRST failed existing latency/accounting/shutdown gate; it never resets the sequence to seek favorable results. All three completed. Gate receipts describe those checked conditions only, not indefinite capacity or overall readiness.

| 50/s60s replay | App p50/p95/p99 s | Durable p99 s | Queue p99 s | Persisted | Exit/remaining workers |
|---|---|---:|---:|---:|---|
| 1 | 1.932/2.706/2.966 | 2.976 | 2.674 | 3000/3000 | 0/0 |
| 2 | 1.862/2.513/2.749 | 2.756 | 2.532 | 3000/3000 | 0/0 |
| 3 | 1.879/2.736/3.072 | 3.082 | 2.783 | 3000/3000 | 0/0 |

These are three consecutive latency/accounting PASSES, not a production optimization speedup: production code did not change from2ed1ffc. Short-run middle-window rates also vary with pulse phase; they must not substitute for the longer capacity comparison. **Overall sustainable50/s acceptance remains NOT ESTABLISHED**, so600s was NOT started. No30-minute or six-hour run, live observation or cohort.

All six new runs: zero stale/overflow/evicted/cancelled trade loss or critical drops, zero final queued/detached trades, all trade identities match unique persisted trade rows, normal process exit0, zero remaining workers, reconciled stopped receipt and cold-restart integrity ok. Recovery84/84 per120s and42/42 per60s, no pending/overflow/expiry. One intentional global shutdown reset/run, zero token-local resets; do not report zero total resets. Synthetic unavailable outcomes and WAIT decisions remain explicitly unavailable/WAIT. No CURRENT or genuine opportunity was fabricated. All new prospective_cohorts tables remain empty; the retired cohort was not opened for mutation.

## Environment failures and quality checks

A fresh pure-standard-library cleanup-probe.py repeats the socketpair EPERM result. Ordinary asyncio completes its worker but times out3s; bounded timer servicing retains the REAL Runner cleanup and exits0 with only MainThread; a genuinely stuck worker STILL times out3s. Fresh ordinary API test prints PASSED then exits124 at20s, traceback in Runner.close/selector. These failures are NOT unconditional test passes. No worker join was skipped and no application cleanup was patched.

**Outside-sandbox normal termination: UNVERIFIED.** Configured execution grants no unrestricted-host capability; no attempt to escape those restrictions or request unavailable escalation was made. A standard `.venv/bin/python -m pytest -q` run on a host that permits local socketpair wakeups remains required. Its result cannot be inferred from timer-assisted diagnostic cleanup. This environment issue is separate from the measured commit-time variability; there is no proof it caused the old10–30s I/O slowdown.

Relevant new diagnostics:10 tests passed. Prior full backend798 passed/1 skipped under diagnostic cleanup and frontend39 tests plus TypeScript/build are reused because production app/frontend trees are byte-identical, no API/dependency contract changed, and unnecessary expensive reruns were explicitly prohibited. Those backend results retain their cleanup qualifier; they are not relabelled as ordinary outside-sandbox passes. Ruff/mypy, secret scan and whitespace checks were repeated. New backend dependency audit: no known vulnerabilities. Frontend npm audit retry: exit1 EAI_AGAIN registry DNS, **UNVERIFIED**, not passed. No dependency manifest or lockfile changed.

## Decision and next controlled work

PRE_COHORT_READY=NO. Three short latency passes are encouraging operational observations, not permission to bypass the sustained-capacity condition.40/s is the highest non-growing two-minute rate measured in this sample; reliable50/s and unrestricted cleanup remain unresolved. Current pipeline behavior is fail closed, with no silent evidence loss.

Next: validate ordinary cleanup/storage service on an unrestricted host; measure identity/raw-event transaction I/O there; design a bounded durable transaction/publication protocol before any isolation/batching that crosses event state boundaries; repeat controlled capacity plateaus with aligned burst-phase analysis. Preserve expiry/negative evidence, old failures and all existing limits. Do not revise strategy or acquisition thresholds, trade, create a cohort, weaken durability or declare a predictive edge to resolve an infrastructure shortfall.

Artifacts: data/early_edge/capacity-20261024/ contains all six new reports/progress/process-status/driver receipts and databases, failed-replay-correlation.json, assessment.json, diagnostic scripts, security reports and fresh cleanup/API evidence. No old artifact overwritten. Source commit a07a1a5 contains only diagnostics/tests/initial analysis; final report commit is supplied in the response. No automatic push.

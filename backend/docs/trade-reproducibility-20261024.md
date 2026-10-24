# Reproducibility and bounded expiry transactions — 2026-10-24

**PRE_COHORT_READY=NO. Consistent short-run acceptance FAILS. No 600-second, 30-minute, six-hour, live or cohort run started. No push.** Synthetic operational evidence only, not evidence of profitability, prospective expectancy or trading readiness.

## Baseline and preserved evidence

Started clean on remediation/early-edge-evidence-readiness at 0087fe8d8110a7b0cb51187905b683a7b097d1db. Read backend/docs/trade-hotpath-20261024.md, prior persistence/endurance/high-load reports and original A/B artifacts. Seven original evidence SHA256 values match data/early_edge/remediation-20261024/engineering-receipt.json; retired data/prospective.db retains size 1073893376, mtime_ns 1792471574652367761. No historical report/artifact/database was used as a write workspace. All new evidence lives under data/early_edge/reproducibility-20261024/; only copies of new synthetic databases were used in component probes.

Local commit 93aaac339cb41d2ac88a375e98716cf63780327a adds opt-in diagnostics and tests, with NO production modification. Local commit ad9bf12 changes only OpportunityResearch expiry persistence and its regression tests. Report commit is identified in the response. Existing priority ranking, features, decoder strictness, recovery scheduling, freshness, risk, economics, research inclusion and paper gates are unchanged.

## Workload identity and measurement boundaries

Each replay: fresh project-filesystem database; 250 candidates, 200 synthetic warm observations each; 3,000 scheduled trades in 60 seconds, 50/s average with unchanged 100/s pulses; 42 recovery submissions, shared production limiter and existing delayed mock RPC/quote background work. Existing 250ms consumer pacing, queue=1000, buffer=500, freshness=20s and 1GiB storage ceiling apply. No unrestricted HTTP, real quotes, real CURRENT evidence or prospective outcomes are tested. All runs set PYTHONHASHSEED=0, unlike historical unseeded A/B; no performance gain is attributed solely to that protocol refinement.

All eight new replays share workload SHA256 `1fad95338758b337c7e477b92a87d7464802f6c0bcafb885b85557f46e886e34` and settings SHA256 `88165dc561fc75ab068452f62079ae275a03997c166512e2c3bd01266fe5d684`. Git SHA, harness hash, SQLite settings, end SHA and end settings hash are recorded; no source/config drift occurred inside a run. Persisted TRADE payloads excluding absolute ts share SHA256 `ff68df7fe2d937d9ae819f0d158822e81d1e16aaf4315e405a2162d5469ef54d`. All 3,000 event identities, mint assignments, directions, wallet labels, volumes and units match. Relative timestamp arithmetic differs from intended offsets only by <=1.145e-7s. Absolute time, setup ages, session IDs and resulting file bytes are not bit-identical.

Application age is the existing scheduled-event-to-PROCESS-START metric. Queue wait includes the detached batch. Process duration includes its synchronous processing/callbacks and persistence. Application p99 is not a separately measured durable-completion p99; marginal quantiles cannot be added. Completed durable throughput is counted from reconciled persisted rows and includes drain/shutdown in its elapsed denominator. Nominal arrivals of 50/s must not be misreported as 50/s committed over that interval.

Bounded tracing observes the harness's EXISTING one-second sleep; it creates no new measurement timers or workers. It stores at most 1,801 lag values, 128 long calls, 181 ten-second summaries with <=16 stage keys each; mock request plan <=8,192 entries. Existing stage and commit counters remain. Component tracing cost: .1023s/100,000 records; environment sampling costs about .05s/run. This is small but not zero; a sub-second marginal pass/failure must not be overinterpreted. No forced cache drop, WAL checkpoint, fsync, CPU affinity or durability change was used. Detailed cProfile runs were not substituted for unprofiled acceptance.

## Pre-change repeated results

Runs 1,4,5 are the three uncontended comparisons. An execution mistake started run3's SETUP before run2's process exit, overlapping about 4.7s of run2 final work. Both are retained and explicitly exploratory, not silently discarded. Run3's timed ingestion began after run2 returned, but its setup was not independent. Two extra serialized replays supplied the independent comparison set. This overlap did not explain the later uncontended failure.
| Run | Application p50/p95/p99 s | Queue p50/p95/p99 s | Process p99 ms | Queue peak | Elapsed s | Durable trades/s incl drain |
|---|---|---|---:|---:|---:|---:|
| A1 | 1.726/3.035/**3.462 PASS** | 1.141/2.777/3.009 | 24.82 | 159 | 63.803 | 47.02 |
| A2 | 1.952/3.738/**4.427 PASS** | 1.288/3.285/3.742 | 24.81 | 182 | 64.739 | 46.34 |
| A3 | 2.025/3.994/**4.354 PASS** | 1.321/3.446/3.719 | 25.40 | 194 | 64.707 | 46.36 |
| A4 | 2.455/4.776/**5.098 FAIL** | 1.889/4.058/4.935 | 26.65 | 228 | 65.096 | 46.09 |
| A5 | 1.981/3.244/**3.551 PASS** | 1.276/2.848/3.139 | 24.28 | 161 | 63.414 | 47.31 |

All A runs used source 93aaac3. A1/A4/A5 p99=3.462/5.098/3.551s: **consistency FAIL**, despite fixed source/hash seed and all three being uncontended. Historical dfe2769 A/B 5.438/3.168s remain preserved, not superseded by favorable new scores.

## Confirmed causes, environment effects and limits of attribution

1. **Serialized persistence has little latency margin and variable service time.** A1/A4/A5 execute 6,582/6,582/6,581 DBAPI commit calls (includes read/no-op transactions). Commit wall totals 13.763/14.854/13.814s; p99 12.182/13.386/12.196ms. A4 CPU demand 45.28s versus A1 44.15s and A5 44.08s; feature calculation stays 17.85–18.22s. Queue p99 grows to4.935s while individual processing p99 remains26.65ms. These are overlapping timers, not additive exclusive costs. Thousands of slightly slower calls accumulate backlog; there is no measured single five-second CPU operation or evidence of changing rankings causing the failure.
2. **A concrete, synchronized audit-write burst exists.** Setup creates 250 DATA_LIMITED opportunity signals about2.8–9.4s before the timed epoch. Their 60s horizons mature during roughly51–59s. Exactly250 UNAVAILABLE_GAP outcomes are persisted in each replay. Original OpportunityResearch.expire -> settle -> write_outcome commits each separately from Intelligence.refresh on the consumer loop. Long refreshes reach .804s in A4. On two independent copies of A1's database, settling250 outcomes takes1.453/1.494s,250 commits, .813/.864s commit time. This is a reproducible contributor, not the sole explanation for every millisecond of variance. These negative/missing outcomes must NEVER be removed, relabelled as zero, deferred past their evidence boundary or omitted to improve performance.
3. **Project I/O pressure is observed; an exact physical-device cause is not proven.** ext4 /dev/sdd on WSL2 6.18.54.1; Python3.13.16, SQLite3.53.1. Eight allowed CPUs, cgroup cpu.max=`max 100000`, memory.max=`max`, total RAM11,435,442,176 bytes. Available memory stays above8.0GB, memory PSI remains zero, host CPU averages about15.5–16.1% across8 CPUs, process mean about69% of one core. CPU PSI is negligible. I/O PSI rises during the runs. This supports I/O/serialized-service variability rather than observed RAM or eight-core saturation. Windows host scheduling/storage, other host processes and VHD cache state are not fully visible inside this sandbox; no claim of complete host isolation.
4. **WAL stays bounded, but automatic checkpoint cost is not individually attributable.** WAL/NORMAL, busy_timeout5000, autocheckpoint32,4096-byte pages unchanged. A sampled WAL peak197,792 bytes, post-batch worst218,392; WAL/SHM zero after close. No runaway WAL, observed SQLITE_BUSY failure or five-second lock timeout. Database.retention still calls wal_checkpoint(TRUNCATE) in its existing worker; engine.run_loop awaits it and then checkpoints restoration state. Tracing neither forces checkpoints nor measures every internal auto-checkpoint separately. Variable commit duration cannot be attributed uniquely to fsync, SQLite internal checkpoints, lock waits or host service latency from these aggregates. Per-process /proc I/O counters are unavailable here and explicitly null. Cgroup I/O/PSI are shared environment measures.
5. **Workload phase has controlled definitions but real timing.** Warm anchor ages are about9.35/9.40/9.35s in the independent A set; larger differences do not explain A4. Candidate creation is staggered; analysis/readiness ages and audit maturity are wall-clock based. Last maintenance/lab timers start at0, so maintenance occurs initially and again near60s. Production cadence was not reset to hide either phase. Background getSlot is completion-relative and shares a global mock-delay ordinal with recovery, a potential generator nondeterminism. The captured plan nevertheless chose the same one1.5s delay (request10) in EVERY measured replay, so this was NOT established as the cause here. Faster completion can allow one extra background request/read commit. Exact full background request timing is not claimed identical.
6. **Warm cache causality remains unproven.** Each new DB is isolated; previous artifacts are not reopened in the timed replay. Later runs are not monotonically faster. No privileged cold-cache/host-I/O isolation was available or attempted. Fresh file does not mean cold OS cache. Timing-sensitive row/context layout is another unquantified hypothesis; canonical trade identity equality is not bit-identical database equality.

## Minimal correction and failure protocol

Only OpportunityResearch expiry persistence changed. outcome_payload preserves the original fields/math. expire gathers at most10 due outcomes in original token/horizon order; commit_outcomes stores outcome rows and pending remaining horizons atomically in one bounded transaction. The same now/status/input observations are used, with no await/network or token-state mutation while a transaction is held. Acquisition-triggered settle retains single-outcome transactions. No consumer cadence, loss policy, financial model, thresholds, capacity, PRAGMA or evidence age changed.

Memory, committed-pending cache and outcome_count advance only AFTER commit. A failed group rolls back; earlier groups remain durable and acknowledged. A retry checks persistent remaining horizons and cannot reinsert a completed outcome. If a commit succeeded but its response failed, a durable matching signal/horizon Record must prove completion before recovering acknowledgement; missing proof fails closed. No new unbounded identity list is retained. Existing single-writer research-owner assumption remains. SQLite NORMAL durability remains the existing policy, not a new guarantee of every acknowledged transaction surviving host power loss.

13 focused tests cover: exact single/batched serialized positive/negative/unavailable outcomes and row order at boundary161 and multiple horizons; no premature settlement at160; three commits for25 records; committed-cache no-op; failed second group with durable prefix; partial preparation rollback; busy/locked and SQLITE_FULL errors; duplicate retry; bounded plan size; SIGKILL mid-group and cold restart; before/after-commit response failure including final row deletion; missing pending/outcome proof fails closed. The combined relevant regression run passed51 cases before the final missing-proof case; the final focused run passed13 tests. No quote, trade identity, price, wallet or execution code added.

The two post-change expiry probes take .756/.666s with25 commits instead of250; commit wall .222/.209s. All500 serialized outcome payloads (250 existing +250 newly matured) are BYTE-IDENTICAL before/after, SHA256 `5d219e3390ffed42adaae00984b8465b26b8443037b024f4048ef57750ef7749`. Repeated maturity adds zero duplicates. This validates a narrow cost reduction, not overall capacity.

## Post-change serialized comparisons

All B runs use clean source ad9bf12, same workload/settings/hash seed and fresh ext4 databases. run-optimized-short.py uses blocking subprocess.run to wait through real process exit, restart and executor cleanup before starting the next run; driver receipts preserve command, start/end and exit status.
| Run | Application p50/p95/p99 s | Queue p50/p95/p99 s | Process p99 ms | Queue peak | Elapsed s | Durable trades/s incl drain |
|---|---|---|---:|---:|---:|---:|
| B1 | 1.605/2.355/**2.501 PASS** | 1.092/2.250/2.421 | 23.58 | 137 | 62.247 | 48.19 |
| B2 | 4.351/5.712/**6.129 FAIL** | 3.575/5.185/5.477 | 63.57 | 286 | 65.757 | 45.62 |
| B3 | 1.706/2.529/**2.783 PASS** | 1.152/2.392/2.639 | 24.46 | 135 | 62.479 | 48.02 |

| Run | Mean/peak process CPU % | RSS MiB | Commit count / wall s / p99 ms | Loop-lag p99 / max s |
|---|---:|---:|---|---|
| A1 | 69.20/86.0 | 201.66 | 6582 / 13.763 / 12.182 | 0.206/0.214 |
| A2 | 69.68/87.7 | 201.77 | 6582 / 13.977 / 12.684 | 0.227/0.402 |
| A3 | 69.31/86.8 | 202.06 | 6582 / 14.183 / 12.881 | 0.376/0.419 |
| A4 | 69.56/92.7 | 202.28 | 6582 / 14.854 / 13.386 | 0.302/0.479 |
| A5 | 69.51/88.7 | 201.85 | 6581 / 13.814 / 12.196 | 0.180/0.262 |
| B1 | 69.18/87.9 | 201.79 | 6108 / 13.031 / 12.214 | 0.182/0.317 |
| B2 | 66.53/91.5 | 202.20 | 6108 / 16.489 / 22.144 | 0.281/0.286 |
| B3 | 69.27/86.5 | 201.96 | 6107 / 13.320 / 12.732 | 0.194/0.194 |

ALL eight runs:3000 submitted=accepted=processed=persisted,2000 buys/1000 sells; zero stale, rejected incoming, evicted accepted, critical drops, pending or in-processing trades.42/42 recovery completions, zero overflow/expiry/remaining recovery, explicit reconciled stopped receipts, cold-restart integrity ok, and ordinary benchmark process exit0 with zero remaining workers. Every run retains250 UNAVAILABLE_GAP outcomes and all3000 trade decisions WAIT. No real CURRENT result is inferred. Each has ONE intentional global shutdown reset and zero token-local resets, not zero continuity resets. Queue-depth/DB/WAL/pressure trajectories are retained in samples and progress receipts; no unexplained accounting loss or artificial complete coverage.

B2 STILL FAILS. Commit wall13.031 ->16.489 ->13.320s, commit p9912.214 ->22.144 ->12.732ms, with feature calculation18.012/17.845/17.777s. This is stronger evidence of service-time variability, not a deterioration of the feature algorithm or suppressed outcome persistence. Successful B1/B3 have better margin; the unfavorable B2 remains equally authoritative. Persisted throughput including drain remains45.62–48.19/s, not proven steady50/s. No favorable-only aggregate or throughput acceptance claim.

Database growth: measured starts about2.86MB, ends about10.6MB plus zero closed WAL/SHM; exact per-run allocated bytes and peaks are in JSON. No historical1GiB database was rotated or limit raised. These short tests do not establish long-run retention behavior. Loop-lag samples observe existing sampler lateness, not an independent100ms deadline timer or exclusive blocking time; quantiles must not be interpreted as full event-level traces.

## Runtime cleanup: confirmed sandbox cause

cleanup-probe.py imports only Python standard library. socket.socketpair send fails PermissionError errno1 (EPERM). Asyncio SelectorEventLoop._write_to_self uses exactly csock.send and swallows OSError unless debug logging is enabled. Executor shutdown's joining thread calls call_soon_threadsafe after REAL shutdown(wait=True); the denied self-pipe write leaves the selector asleep. The ordinary minimal probe logs that exact EPERM, completes its quote-free worker, then hits3s timeout. No Crispy, pytest, database, SDK or provider is needed to reproduce it. The actual sandbox rule beyond the observed socket policy is not independently identified.

Positive control: bounded timer servicing retains ORIGINAL Runner cleanup and exits0 with one main thread. Negative control: a genuinely stuck worker STILL times out. No futures are set by the diagnostic, joins skipped, tasks suppressed or successful exit forced. The ordinary API test again prints PASSED then times out20s with a Runner.close selector traceback. This is an environment failure, not an unconditional clean suite pass. It may also affect general thread-completion wakeup timing; these measurements cannot certify an unrestricted host runtime.

The benchmark's existing bounded cleanup watchdog runs after timed work; the new sampling instrumentation adds NO wakeup timer to measured ingestion. Application cleanup was NOT patched. An unrestricted environment where local socketpair wakeups are permitted is required for a genuine unmodified cleanup validation; changing trading/application logic to mask a sandbox policy would be inappropriate.

## Engineering decision and remaining work

**Consistent 60s acceptance FAIL. 600s NOT RUN. PRE_COHORT_READY=NO.** Two/three passing post-change tests do not authorize endurance or prospective evaluation. No six-hour/live/cohort/trading activity.

Next priorities:

1. Residual normal trade identity/final-event path still commits separately roughly6000 times/3000 trades. A safe shared transaction needs explicit rollback/idempotency for token, creator, observer, research and paper state before reducing those boundaries. Do not introduce early durable acknowledgements or an unbounded writer queue. Profile that design against actual filesystem latency, not tmpfs alone.
2. Retain negative/outcome maturity load in every future workload. This batching change addresses its proven transaction amplification; it does not justify removing unfavorable/unavailable data or changing horizons/cadence. Quantify internal auto-checkpoint and maintenance latency separately before changing any policy.
3. Establish repeatable host storage/CPU service and unmodified socket wakeups outside the restricted sandbox. WSL host cache/thermal/I/O effects and file-layout entropy remain unresolved; no automatic storage migration or durability weakening.
4. Freeze an explicit next-generation fixture epoch/background-arrival protocol if stricter cross-run state timing is needed. Keep the current results and protocol distinct; do not retrospectively normalize away a failure. Add durable-completion age tracing if that becomes a declared endpoint; current application metric is processing-start age.
5. Keep ordinary cleanup and frontend security-audit limitations explicit. Do not label synthetic processing as real complete trade evidence or use it to revive the retired cohort.

## Artifact audit

assessment-final.json corrects an exploratory assessment-initial.json calculation that accidentally included250 setup CREATE rows in the relative TRADE timestamp check. The old exploratory file is retained and explicitly superseded; only the corrected TRADE-only roundoff and digest are used. optimized-assessment.json, all eight reports/process-status companions, driver receipts, component probes and validation logs are preserved. Source/harness/config/input hashes, pressure samples, long-call summaries, resource trajectories and final accounting are available for independent review. No raw real transactions, wallets, API keys or provider URLs were captured.

## Final quality checks and file boundaries

- Complete backend suite before production change: **785 passed, 1 skipped in149.64s**, using the explicitly labelled bounded diagnostic cleanup launcher.
- Complete backend suite after production change: **798 passed, 1 skipped in148.43s**, normal process return0 using that same launcher. The original Runner.close still joins real workers; no test is skipped to mask cleanup and stuck-worker negative controls remain. This is NOT an unconditional ordinary-invocation pass. The ordinary API probe exited124 after printing PASSED; the pure-stdlib reproduction establishes the sandbox self-pipe denial without application imports.
- Frontend: **39 passed**, five files,5.91s; TypeScript and production build passed (3.95s). No frontend source or API contract changed afterwards; these verified results are reused.
- Ruff passed; mypy passed44 source files with explicit package bases; secret scan passed before final documentation and was repeated after; git diff --check passed.
- Backend installed dependency audit: no known vulnerabilities. Frontend npm audit retry: **UNVERIFIED**, exit1/EAI_AGAIN registry.npmjs.org. No package manifest, lockfile or runtime dependency change.
- No real cohort created: all new diagnostic databases have prospective_cohorts count0; early-edge collectable tables were not created. Synthetic DATA_LIMITED opportunity rows are explicitly diagnostic, not prospective EARLY/control enrollments. Retired cohort and seven original evidence hashes remain unchanged.

Exact changed files relative to0087fe8:

1. scripts/evidence_repro.py — opt-in bounded environment/lag/long-call summaries.
2. scripts/validate_evidence_load.py — opt-in workload/settings hashes, stage timing summaries, background delay plan, initial/final identity receipts; existing schedule/gates unchanged.
3. backend/tests/test_evidence_repro.py — deterministic hashing, bounds and no-added-timer checks.
4. backend/tests/test_endurance_harness.py — exercise retained diagnostic report and unchanged SQLite settings.
5. backend/app/opportunity_research.py — the bounded expiry transaction implementation described above; original business-field formulas retained.
6. backend/tests/test_opportunity_expiry_batch.py —13 focused equality, audit, rollback, retry, lock, full, crash/restart and missing-proof tests.
7. backend/docs/trade-reproducibility-20261024.md — this consolidated report.

The final documentation commit contains no additional runtime optimization. No PumpSwap/Pump decoder, engine cadence, strategy/Opportunity/Companion threshold, security/economics rule, proposed position size, approved holdout or wallet/trading implementation was changed. The system is **not ready for a new six-hour readiness request** based on this evidence; the residual filesystem-sensitive throughput/latency criterion must first pass consistently.

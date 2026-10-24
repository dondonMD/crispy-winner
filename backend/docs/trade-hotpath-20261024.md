# Trade hot-path investigation and priority follow-up — 2026-10-24

PRE_COHORT_READY=NO. Branch remediation/early-edge-evidence-readiness. Synthetic operational testing only; no market, profitability or prospective edge inference. No push, live test, cohort or trading.

## Preserved work and evidence

Resumed clean HEAD 7c9d8b0 without rerunning prior profiling. The existing priority-probe.py and completed JSON were inspected rather than overwriting or rerunning their exclusive output. Seven original evidence SHA256 values match remediation-20261024/engineering-receipt.json. Retired data/prospective.db retains size 1073893376 and mtime_ns 1792471574652367761. Historical reports/results remain unchanged.

Previous commits retained: 09bd4ed instrumentation; 8f1f8b8 exact raw-window cache/writer guard reuse; 62ed66d cache bookkeeping/Core inserts/bound identity SQL; e8181ad exact cross-window static sharing; 8f2e462 bounded diagnostic shutdown servicing; 7c9d8b0 delayed/stuck-worker shutdown tests. Whole-engine transaction batching remains deferred: identity, mutable candidate/creator/research/paper state and independent writers need an explicit rollback protocol. Durability PRAGMAs and separate identity/final-event acknowledgements remain unchanged.

The cache stores only raw static statistics, bounded to six slots per token. Selected membership is rebuilt against current time; all eight horizon-dependent metrics are recalculated. CURRENT, continuity and decisions are never cached. Exact replay/mutation/clock-reversal/venue tests protect equivalence. Raw-event Core insert commits before return; financial observer callbacks retain their original path. No no-idle processing experiment was restored.

## Priority component diagnosis and change

The preserved reverse-order probe performed 2,000 selections of 250 candidates per case. Original CPU seconds: 0.694910 and 0.544616; shared-dictionary proposal: 0.420894 and 0.321557. This is component evidence, not an end-to-end speed guarantee or a directly instrumented production call count.

Commit dfe2769ab0749c9523b39f0cf25c3e515f04a6b5 hoists the exact seven State weights into MappingProxyType. Token.priority still constructs the same tuple, reads live curve progress and maturity, and uses lexical mint tie-breaking. No ranking-result cache or candidate-wide scan removal. The probe used a normal dictionary; production deliberately uses an immutable proxy, so its timing is not claimed identical. Regression checks every State, four curve cases and two maturity values, sorted rankings and immutability. Only backend/app/domain.py and backend/tests/test_trade_hotpath.py changed in this commit.

## Comparable project-filesystem replays

Command (unique output for each):

```
timeout 115s .venv/bin/python scripts/validate_evidence_load.py --seconds 60 --rate 50 --endurance --output data/early_edge/trade-hotpath-20261024/priority-60-a.json
```

250 candidates, 200 warm observations each, 3,000 trades, existing 100/s burst schedule, 0.7 recovery/s and delayed mock providers. Outputs remain in that ignored directory with retained synthetic DB, progress, profile and process-status receipts. No CPU-heavy suites overlapped either measurement. Both used the same clean dfe2769 source and harness. Exact existing queue/freshness/retention/candidate caps apply.

| Run | Application p50 / p95 / p99 s | Queue p99 s | Processing p99 s | Queue peak | Mean / peak CPU % | Peak RSS MiB |
|---|---|---|---|---|---|---|
| Initial preserved baseline | 7.374 / 15.589 / 15.938 | see JSON | see JSON | 650 | 71.12 / see JSON | 188.34 |
| Prior clean v3 repeat | 2.589 / 5.088 / 5.363 | 5.207 | see JSON | see JSON | 66.99 / see JSON | 201.74 |
| priority-60-a | 1.607 / 3.384 / **5.438 FAIL** | 5.188 | .0423 | 154 | 65.74 / 86.4 | 201.99 |
| priority-60-b | 1.681 / 2.769 / **3.168 PASS** | 2.923 | .0256 | 146 | 68.40 / 87.5 | 201.49 |

Both new runs: 3,000 submitted=accepted=processed=persisted, buys/sells 2,000/1,000; zero stale, incoming rejection, eviction, critical drop, outstanding trade or recovery. Recovery 42/42; no overflow/expiry. Cold restart integrity ok; stopped receipts reconcile. One global shutdown reset, zero token-local resets; this is not zero continuity resets. Final DB size A=10579968 bytes, zero WAL/SHM after close. Standard Runner returned normally, zero remaining workers, watchdog one bounded tick after timed work. Companion receipts certify report hashes; report presence alone is not proof of process exit.

Elapsed measured intervals A=65.351s, B=63.204s include drain/shutdown: 45.91 and 47.47 persisted trades/s over those intervals, not proof of sustained 50/s service. Arrival target is 50/s; application age includes producer scheduling delay (p99 A=1.572s/B=1.105s), separate queue wait and processing. No six-hundred-second test was started: paired results do not consistently meet existing <5s p99. No repeated sampling until a favorable score.

Earlier best 4.802s and intermediate 14.989/11.267s reports ended in CLI timeout during executor cleanup and are not clean acceptance runs. Minimal asyncio-to_thread cleanup also reproduced the timeout; exact environment mechanism remains unproven. Diagnostic bounded loop servicing does not force futures, skip joins or change ingestion. A genuinely stuck worker still times out in regression tests.

## Residual measured costs and limitations

Priority reuse is a small proven allocation improvement, not the dominant cure. A/B each commit 6,582 transactions; measured commit wall total varies 16.393s versus 13.797s (p99 .02155/.01223s). Identity reservation totals 9.128/8.491s; raw insertion 12.309/11.285s. Feature calculation 17.608/17.965s across 11,275/11,249 analyses; observer 7.438/7.362s; checkpoint 1.628/.791s. These timers overlap and MUST NOT be summed as exclusive costs. A largest checkpoint was 1.054s versus B .275s; this corroborates variability, not proof it alone causes the tail. Shared I/O/WSL scheduling and repeated analysis remain material. Exact durable identity/event transaction coordination is still future work, with rollback and restart tests required before widening boundaries.

The workload does not establish hour-scale retention, real transport/unit availability, real CURRENT, matched research outcomes or readiness. CPU distributions include sampling overhead; memory increased from the initial baseline due bounded caches. No risk/security/economics/decoder/eligibility/continuity/recovery or paper behavior changed. Engineering criterion remains unmet; no six-hour authorization is justified by these runs alone.

## Final quality validation and explicit blockers

Focused backend hot-path tests: **15 passed in 3.25s**. Complete backend collection contains 784 tests. Ordinary full invocation hit its 360s bound after the API test reported PASSED; no failure assertion or full-suite completion is claimed. A separate isolated API test also reported PASSED then timed out. With pytest faulthandler_timeout=10 the stack shows pytest-asyncio teardown in standard asyncio Runner.close -> run_until_complete -> selector.select. Exact underlying restricted-runtime wakeup mechanism remains unproven.

A separate, preserved diagnostic launcher (`pytest-cleanup-diagnostic.py`) invokes the ORIGINAL Runner.close after installing the existing bounded 100-tick/50ms loop servicing helper. It does not complete futures or bypass worker joins. This full diagnostic run exited 0: **783 passed, 1 skipped in 143.78s**. This is not represented as an unmodified test invocation. A remaining-tests attempt also blocked on teardown; an earlier node-ID replay attempt failed collection because an existing randomized test parameter changed between collections. Those attempts and the original timeouts remain preserved, not counted as passes. No application shutdown code was modified in this follow-up.

Frontend **39 passed**, five files, 6.70s; TypeScript and production build passed, build 3.72s. Ruff passed; mypy passed 43 source files; secret scan passed (203 source/document files before this report); git diff --check passed. Backend installed dependency audit: **64 packages, zero known vulnerabilities**. Frontend npm audit **BLOCKED** by EAI_AGAIN registry DNS failure, exit1; it is not a clean audit result. No dependency manifest or lockfile was changed. The earlier direct `.venv/bin/pytest` attempt failed import collection; subsequent invocations use the project-interpreter `python -m pytest` path.

Artifacts include both reports/process-status companions, priority-assessment.json with SHA256 inventory, preserved component probe, diagnostics and validation logs under data/early_edge/trade-hotpath-20261024/. No frozen artifact overwritten. Source changes in this follow-up are solely the priority-map optimization/test and this new engineering report; previous optimization commits are retained. Local only, no push. Final report commit SHA is supplied in the response.

**Decision: short-run consistency FAIL, 600s NOT RUN, PRE_COHORT_READY=NO.** Remaining validation blockers are variable application-tail latency, ordinary suite cleanup in this environment, and the unavailable frontend advisory endpoint. Future engineering must address measured durable-write/analysis cost with exact-state equivalence and rollback evidence, then repeat the unchanged short gate. Synthetic successes do not establish current real-market research evidence.

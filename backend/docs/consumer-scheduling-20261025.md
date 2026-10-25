# Consumer-start scheduling diagnosis — 2026-10-25

PRE_COHORT_READY=NO. Starting verified local HEAD c326632. One pre-existing edit to storage-guard-capacity-20261025.md is preserved verbatim; its initial hash and patch are retained separately. No backend/app code, transaction boundary, risk/evidence threshold, queue/candidate limit or financial behavior changed.

## Question and measurement design

The previous87-trade cut was9 not-ready,77 ready-not-started,1 not-durable. Ready-not-started is NOT just heap occupancy: PriorityBuffer.drain detaches up to100 selected events, then processes that batch chronologically with yields every5. Newly arriving events cannot join it. Between drains run candidate analysis, expiry, intelligence, resources/audit, possible retention/checkpoint, then the unchanged250ms sleep. A selected trade can also wait behind earlier events in its detached batch. No inference that this is SQLite slowdown or a sustained deficit is made from backlog alone.

New opt-in --diagnose-consumer records:
- scheduled-to-ready; ready-to-queue-admission; admission-to-selection; selection-to-start; admission/ready-to-start;
- processing duration, process-start to actual db.add(event) commit acknowledgement, and process-start to durable process return;
- exclusive consumer phase clocks: event processing, drain residual, periodic candidate analysis, intelligence refresh, expiry/resources/audit/checkpoint, retention-await, cooperative yields,250ms cadence sleep and other;
- per-cycle wall/phase durations, selected batch sizes, end heap/detached counts and drain intervals; existing loop-lag/environment/counter diagnostics remain;
- queue-wait attribution by differences in phase clocks at admission/start. Totals are overlapping trade-seconds across trades, not CPU; EACH wait is exclusively partitioned.

The diagnostic is isolated in scripts/consumer_trace.py and the synthetic harness. Production run_loop bytecode is reused IDENTICALLY by a scoped function clone; only its asyncio global is a pass-through proxy to label EXISTING sleep/yield and retention awaits. No global asyncio monkeypatch, timers, tasks, changes to delay values, extra DB operations or acknowledgement shortcuts. Candidate analysis inside event processing remains event work; periodic analysis is separately tagged. Original methods are restored even on cancellation. Raw commit acknowledgement is measured only AFTER real db.add returns a nonzero identity; exceptions/omissions cannot count as durable.

Bounds: pending diagnostic entries <= queue maximum+101 (heap+detached100+incoming); metric lists <= declared events <=180,000, cycle metrics <=8192 and cycle detail last256. Diagnostic tracking/sample loss is explicitly counted; no silent complete attribution if a bound is reached. Event IDs only, no wallet/event payload logs. No production data or research outcomes collected.

## Predeclared execution

First verify diagnostics with deterministic tests (phase arithmetic, real sleep arguments, cancellation/restoration, bounds, original bytecode/scoped globals, failed raw acknowledgement and retained synthetic integration/restart). Then execute a serialized unchanged120s40/s regression and120s50/s control, followed by ONE120s50/s instrumented diagnostic. Control and diagnostic purposes/results remain separate; an instrumented pass cannot replace a failed control. If the control fails its unchanged gate, no further qualification trials or600s follow. No production optimization unless the phase results establish a meaningful reproducible cause and a safe change. All source files are frozen by hashes before/after each run because Git staging is currently denied (read-only index), not falsely called a clean commit.

Identical existing project-filesystem workload:250 candidates/200 warm events per token, deterministic10s burst pattern, shared synthetic recovery/quote traffic, existing storage/freshness/queue/cadence. No concurrent test/audit/profile jobs during measured runs. No six-hour, cohort or trading run. Original latency<5s, complete reconciliation/clean shutdown and exact aligned growth(slope<=0 AND last-three<=first-three after20s) unchanged. Three consecutive fully passing qualifying short trials would still be required before considering600s. This diagnostic experiment itself does not grant that permission.


## Measured lifecycle (120s instrumented50/s, SYNTHETIC)

All6,000 trades have complete diagnostic admission/start/raw-ack/return samples. No tracking overflow, missing admission, duplicate raw acknowledgement or retained-sample truncation; pending tracking0 and hooks restored. Admission-to-start trade-seconds equal the sum of exclusive phase attribution EXACTLY. All66 completed cycles' phase sums equal their wall durations exactly. No phase data is fabricated for prior runs.

| Stage | p50 seconds | p95 | p99 | maximum |
|---|---:|---:|---:|---:|
| Scheduled arrival -> producer-ready | .427702 | .804723 | 1.010086 | 1.267050 |
| Producer-ready -> queue admission | .000096 | .000189 | .000295 | .000622 |
| Queue admission -> batch selection | .498709 | 2.091508 | 2.246577 | 2.450682 |
| Selection -> consumer processing start | .476937 | .963531 | 1.048923 | 1.177118 |
| Admission -> processing start | 1.037735 | 2.198467 | 2.349966 | 2.607158 |
| Producer-ready -> processing start | 1.037819 | 2.198620 | 2.349987 | 2.607188 |
| Processing start -> real raw commit acknowledgement | .005887 | .018921 | .021499 | .078814 |
| Processing duration / durable process return | .008275 | .021038 | .023674 | .081054 |

Quantiles of different stages must NOT be added. Raw commit acknowledgement precedes existing intelligence/research callbacks; full durable process return includes their work. Full processing totals63.280s; start-to-raw-ack totals51.400s. The11.880s after raw ack is real callback/observer-path work, not proof it is redundant or safe to defer. All real db.add/commit/failure semantics remain untouched.

### Where admitted trades wait

| Consumer phase while trades wait | Trade-seconds | Share |
|---|---:|---:|
| Processing OTHER events | 3,809.966 | 54.39% |
| Existing250ms cadence sleep | 1,510.040 | 21.56% |
| Periodic candidate analysis | 906.251 | 12.94% |
| Intelligence refresh | 631.723 | 9.02% |
| All other phases combined | 147.144 | 2.10% |

Total admitted waiting7,005.124 trade-seconds, mean1.167521s/trade. Before selection4,090.734s; AFTER selection2,914.390s (**41.60% of waiting**). Thus77 ready-not-started need not mean77 heap residents; detached batch head-of-line work is a substantial part of delay. Queue admission itself is sub-millisecond and no mutex/await exists in PriorityBuffer.put. PriorityBuffer selects up to100 by priority then processes those chronologically; this policy remains unchanged. Drain residual includes selection and existing internal yields; it is an upper bound, not a precise isolated sort cost.

These are wall-time state attributions, NOT exclusive CPU or counterfactual savings. External preemption/I/O while a phase is active belongs to that phase's wall time. Multiple trades can wait through the same interval; totals are not summed to loop runtime. It would be wrong to claim that removing a phase saves its full trade-second share or proves it can be removed safely.

### Per-cycle service budget

66 completed cycles total120.452s (final partial drain is separate). Mean cycle1.825s, median1.858s, p952.042s, p992.104s, max2.131s. Drain-start interval p992.104s. Mean89.88 selected events/cycle, range0..100;30 full batches,7 taking>2s,9 cycles overall>2s.

Exclusive completed-cycle wall: event processing62.441s(51.84%), periodic analysis25.755s(21.38%), intelligence12.971s(10.77%), cadence sleep16.565s(13.75%), all other work2.720s(2.26%). Retention await .091s, checkpoints .570s, expiry .085s and resources .027s are minor here. Drain residual .840s includes sort/detachment/dispatch and yields between five-event chunks. It does not support optimizing heap operations as the main bottleneck.

The final full cycles took1.997,2.104,2.051s and the last95-event cycle2.012s. A full100-event cycle>2s temporarily offers<50events/s; at2.131s the optimistic trade-only rate is46.92/s. This is a confirmed finite service deficit driven by aggregate legitimate work/cadence, not a demonstrated unbounded queue or duplicate computation. Empty/underfilled cycles and burst timing also change usable capacity. First producer burst cannot join an already detached batch. Candidate/refresh work lies between drains; no event-driven wakeup occurs within that work. Periodic phase placement explains why short cuts change, but does not prove the existing scheduler sustainable indefinitely.

Actual cadence sleep p99 excess .002028s, max .002248s: this is not a multi-second oversleep. The configured250ms still contributes deliberate latency. Removing it is NOT validated: the earlier no-idle experiment worsened performance and is not restored. Disabling/deprioritizing safety analysis or changing batch selection/grouping without signal/fairness equivalence would violate the task's constraints.

## Unchanged qualification results vs detailed diagnosis

| Metric | Uninstrumented40/s | Uninstrumented50/s | Instrumented50/s (diagnostic only) |
|---|---:|---:|---:|
| Submitted/durably persisted | 4,800/4,800 | 6,000/6,000 | 6,000/6,000 |
| Application p99, s | 1.802 | 2.322 | 2.430 |
| Queue wait p99, s | 1.555 | 2.269 | 2.350 |
| Durable age p99, s | 1.816 | 2.336 | 2.445 |
| Mean process CPU % | 68.14 | 68.00 | 68.30 |
| Peak RSS MiB | 208.76 | 210.70 | 213.00 |
| Queue peak | 103 | 131 | 142 |
| Elapsed incl drain, s | 122.183 | 121.625 | 121.701 |
| Commit cumulative wall, s | 22.299 | 25.982 | 26.337 |
| Sampled WAL peak bytes | 206,032 | 201,912 | 222,512 |
| Growth early-three /late-three mean | 42.667/31.667 | 59.667/45.333 | 52/57.667 |
| OLS deficit slope events/s | -.100 | -.100 | +.027273 |
| Unchanged growth rule | PASS | PASS | FAIL |

No source edits or competing quality/benchmark jobs during measurement. Settings/workload unchanged; the only opt-in difference is instrumentation. All runs use original project filesystem,250 candidates/200 warm events, deterministic burst/recovery/quote stand-ins, existing storage/queue/freshness/cadence. SQLite WAL/NORMAL/busy5000ms/autocheckpoint32/page4096 unchanged. All source-overlay hashes matched before/after each child. All failed prior measurements remain preserved.

One control/diagnostic pair does NOT isolate overhead from natural variance. Instrumented aggregate process CPU is~.41s higher (~.5% of process CPU); commit wall also differs by+.355s. Its p99 is+.107s, and gate changes sign. That cannot be attributed solely to instrumentation OR solely to scheduler defects. Traced samples are explicitly not interchangeable with uninstrumented qualification. Historical uninstrumented failures remain alongside this new pass. Three consecutive complete qualifying passes are NOT established; **600s NOT run**. No qualification threshold or window was adjusted to waive the failure.

## Correctness and remaining engineering decision

No production scheduling or database change was made. Original run_loop bytecode, arguments, priority ordering, chronological batch order, max100 selection, yields,250ms idle, transactions, true durable acknowledgements, observers and crash/restart semantics are retained. Only the synthetic cloned function has the pass-through asyncio view. Global asyncio and production code are not patched. Hooks restore on exit/cancellation. Worker joins remain real. Failed raw inserts cannot generate raw-ack/durable-return metrics. Diagnostic capacity loss is observable separately from real queue loss.

The measured causes of consumer-start delay are other serial event work, detached-batch waiting and inter-drain analysis/refresh/cadence. The service budget has little margin when full cycles exceed2s. NOT established: an avoidable repeated calculation, priority starvation, queue-lock contention, pathological maintenance, SQLite slowdown as the pass/fail cause or external-host causality. Wall-phase attribution does not substitute for an exclusive call-path profile.

The smallest safe production improvement is **not yet demonstrated**. The next justified profiling targets are the11.88s post-raw-ack callback path and periodic analysis/refresh work, looking for exact redundant immutable context/calculation reuse. Any such change must preserve signal-time snapshots, callbacks, decisions, continuity, expiry and fairness, with failure/replay/ordering equivalence. Merely deleting idle time, increasing batch/queue/candidate limits, deferring safety work or changing acceptance is not a validated fix. No speculative change is implemented.

Artifact root data/early_edge/consumer-scheduling-20261025/ contains every control/diagnostic report, gate/process/progress receipts, actual synthetic DBs, source overlay, comparison/phase-check JSON, initial prior-doc patch/hash, test/audit outputs. Reports are synthetic and never prospective evidence. No cohort, trading, long experiment or historical-data modification.


## Final invariants, quality and delivery

Independent read-only SQL verifies4,800/6,000/6,000 raw trade records and distinct event IDs, exactly matching durable identities and reconciled ledger counts. All three runs: zero stale/rejected/evicted trades or critical drops, zero final heap/detached work;84/84 recovery success, no overflow/expiry/pending; normal process return0 with zero workers; cold restart integrity ok, rolling windows empty/security requires refresh. One intentional global shutdown reset/run, zero token-local resets; not falsely zero total gaps. No storage omission/reclamation/guard activation in these short tests. Final WAL/SHM0; no collectable cohort rows. These facts do not make the measured growth failure pass.

Source/config hashes matched before/after every run. The runtime source is an explicitly frozen uncommitted overlay on c326632523a258e519ec1529b42aa16923e33f38; it must NOT be described as a clean published commit. Git staging was denied by read-only .git/index.lock. The prior modified storage-guard report remains byte-for-byte unchanged; its saved initial hash/patch is separate from this work. Seven frozen original evidence hashes and retired database size/mtime checked again below/in receipt.

Focused final suite:12 passed22.74s, including the12s retained traced integration. Two earlier commands each had2 failed/10 passed because new MarketEvent fixtures omitted the required source field; failures are preserved, corrected units5 passed1.43s and final combined12 pass. No production validation was weakened to fix fixtures. Tests cover exact phase arithmetic/no double counting, true sleep arguments, cancellation/restoration, fixed bounds/observable diagnostic loss, original loop bytecode/scoped globals, failed raw-write acknowledgement and original cold restart/accounting. The original transaction/counterexample/ordering/financial/observer tests remain unchanged.

**Complete backend:839 passed,1 skipped in145.18s, exit0**, under the existing explicitly labelled bounded-cleanup diagnostic with real Runner.close and worker joins. This is not an unrestricted ordinary-runtime claim; the known sandbox socketpair EPERM issue is not hidden or bypassed. No new cleanup workaround introduced. Fresh frontend39 passed6.02s; TypeScript/production build passed(Vite3.70s). Ruff passed; mypy46 sources; source secret scan223 files; git diff --check passed. Backend/frontend dependency audits attempted and UNVERIFIED due PyPI/npm DNS failures; no dependency/lockfile/runtime SDK changes.

Changed files: scripts/consumer_trace.py; scripts/validate_evidence_load.py; backend/tests/test_consumer_trace.py; backend/tests/test_endurance_harness.py; this engineering report. No backend/app, decoder, SQLite settings, signal/economics, lifecycle/security or approved-research behavior change. The one pre-existing storage-guard documentation edit is preserved and excluded from the proposed change.

PRE_COHORT_READY=NO. No prospective cohort, trading,600s or six-hour experiment. Delivery attempt/final Git SHA are recorded in the final receipt and response, without claiming an uncommitted patch was published.


### Final Git delivery outcome

Latest verified local HEAD remains c326632523a258e519ec1529b42aa16923e33f38. No new commit could be created: git add of ONLY the five validated task files failed with read-only .git/index.lock. The earlier staging attempt of the preserved prior documentation note also failed; neither changed the index. Authorized normal branch push returned128 (Could not resolve host github.com). No successful new publication, no alternate history, force push, main write or permission bypass. The reviewable-diagnostic.patch includes ONLY this task's five files; the prior documentation patch/hash stays separate. Exact source/test/evidence hashes and final status are in final-receipt.json. Working-tree changes are preserved for review; do not call this a clean/published SHA.

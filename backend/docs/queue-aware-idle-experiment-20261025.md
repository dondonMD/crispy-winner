# Controlled queue-aware idle experiment — 2026-10-25

PRE_COHORT_READY=NO. Starting local HEAD0753300. Existing untracked consumer_trace.py and its unit test were preserved as exact initial copies/hashes before extension. No production scheduler, SQLite transaction, evidence/risk threshold, candidate/queue limit, cohort or trading change is implemented.

## Exclusive baseline and hypothesis before experiments

The preserved66 completed consumer cycles total120.452s. Exclusive wall phases: event62.441s, periodic candidate analysis25.755s, intelligence12.971s, cadence sleep16.565s, residual2.720s. This is NOT the overlapping7,005 waiting trade-seconds. Seven full100-event cycles exceeded2s; nominal50/s has little margin.

Every old cycle ends with nonempty heap, but old counters are AFTER sleep. They do NOT prove the heap was nonempty at sleep entry. New idle-entry counts and actual/requested delay are required. Removing all16.565s is only an optimistic upper bound; it is not a predicted gain. The earlier wholesale no-idle experiment worsened performance. Faster cycles can increase candidate analysis/refresh frequency and CPU cost; these must be measured rather than assumed.

## Synthetic-only candidate and preserved semantics

ConsumerTrace/AsyncioView gains an explicit experimental policy: fixed(default) or queued_yield. At the ORIGINAL final .25s sleep only, queued_yield uses real asyncio.sleep(0) IF accepted heap work is pending, engine.running and no resource pressure. Empty/shutdown/pressure use original .25. Existing yields inside candidate and event batches are retained; no new tasks/timers, busy polling, unbounded queue or batch, network budget or database writes. Each active pending-work loop still selects/drains the same bounded batch before yielding. All existing analysis, refresh, expiry, resource, audit and maintenance code executes unchanged.

Only the synthetic scoped clone's asyncio call is affected. No backend/app change. CLI rejects nonfixed policy unless --endurance AND --diagnose-consumer, before DB creation. The original code/global asyncio are untouched. Added cycle fields distinguish selected trades, durably completed trades and accepted work at the idle boundary. Exclusive phase accounting includes queue_yield separately.

This preserves the ALGORITHM within each selected batch and actual durable acknowledgement, but does not yet prove identical cross-batch order or time-dependent signal observations for a different scheduling policy. No production adoption without that proof and worthwhile reproducible capacity results. No benefit inferred from shorter sleep alone. Resource/backoff behavior, callbacks and failure/replay semantics remain required.

## Predeclared serial experiment

Project filesystem; unchanged120s250-candidate workload,200 warm events/token,50/s deterministic burst pattern/shared RPC/recovery/quote stand-ins, same source overlay/settings/durability/limits. No concurrent heavy jobs. Fixed40 regression, fixed50 reference, queued40 regression, then at most THREE queued50 trials; stop at FIRST candidate failure. Fixed50 failure remains preserved; reference failure alone does not prohibit the declared candidate diagnosis, but a failed lower-load candidate does. Latency/accounting/recovery/shutdown and EXACT slope<=0 AND last-three<=first-three rule unchanged. No favourable reruns or replacement failed measurements.

All policy runs are explicitly experimental diagnostics. No600s based merely on an instrumented candidate. Only a safe production change with correctness proof and three consistent uninstrumented qualifying50/s runs could allow one600s. If candidate fails, no production adoption or600s; report why. No30-minute/six-hour experiment, cohort or trading.


## Results: queued_yield rejected, NOT promoted

All measured runs are synthetic opt-in experiments, frozen overlay on0753300877c3f844825d4c201364d98b0f8fac05, not a new production commit. Source/settings fingerprints match before/after each child. No test/audit/other heavy job ran concurrently. Same filesystem and deterministic input, with policy difference explicit in reports. No source edits during timed work.

|120s result|fixed40|fixed50|queued40|
|---|---:|---:|---:|
|Submitted/durably persisted|4800/4800|6000/6000|4800/4800|
|Actual elapsed including drain,s|121.845|125.129|124.106|
|Committed rows/elapsed,/s|39.394|47.951|38.677|
|Application p50/p95/p99,s|.984/1.544/1.762|2.794/4.331/4.892|5.826/7.908/8.603|
|Producer-ready-to-start p99,s|1.436|4.731|4.763|
|Scheduled-to-producer-ready p50/p99,s|.168/.699|.508/1.213|5.202/8.018|
|Durable-return age p99,s|1.773|4.903|8.615|
|Mean/peak process CPU,% of one core|67.64/85.1|70.06/94.9|84.61/90.2|
|Peak RSS,MiB|210.52|212.88|210.19|
|DBAPI commit count/wall s|9714/21.013|12138/26.876|9740/21.967|
|Commit p99/max,ms|12.331/64.620|12.643/63.727|13.296/68.760|
|Completed consumer cycles|87|61|135|
|Mean durable trades/completed cycle|55.10|97.51|35.07|
|Idle entries already holding accepted work|87/87|61/61|135/135|
|Cooperative pending-yield substitutions|0|0|135|
|Heap-entry resource-pressure backoffs|0|0|0|
|Recovery successful/accepted|84/84|84/84|84/84|
|Monitoring stand-in requests|21|22|22|
|Quote stand-in deadlines met|4/4|4/4|4/4|
|Recovery total latency p95/max,s|.654/.912|.753/.936|.870/1.101|
|Sampled event-loop lag p99/max,s|.166/.185|.233/.255|.363/.489|
|Stale/dropped/final pending trades|0/0/0|0/0/0|0/0/0|
|Result|PASS regression|FAIL growth|FAIL latency; STOP|

The unchanged40/s regression gate checks latency/accounting/recovery/shutdown; its descriptive growth values remain published, not hidden. Fixed40 slope+.119091, early25.667/late33.667. Fixed50 exact deficits20..120s:51,61,75,99,140,152,148,152,152,152,192; slope+1.285455, early62.333/late165.333 -> FAIL. Queued40:206,222,238,286,270,138,86,113,262,274,198; slope-.263636 but early222/late244.667 would ALSO fail the mean condition if used as a no-growth qualification. Latency alone rejects the lower-load candidate. No criterion/threshold changed.

The driver stopped at the FIRST candidate failure, as declared. No queued50 trial, production patch, qualifying3-run series,600s,30-minute or six-hour run. The failed reference and failed candidate are retained beside the reference regression pass. All recorded source overlay hashes remained unchanged while running.

## Exclusive costs establish the frequency feedback

Completed-cycle phase totals ONLY (not overlapping trade waits; final partial drains/stop are separate):

|Exclusive phase,wall s|fixed40(87 cycles)|queued40(135 cycles)|Difference|
|---|---:|---:|---:|
|Event processing|49.430|52.620|+3.190|
|Periodic candidate analysis|31.231|43.312|+12.081|
|Intelligence refresh|16.000|22.780|+6.780|
|Configured cadence sleep|21.835|0|−21.835|
|Queue cooperative yield|0|.045|+.045|
|All other phases|2.893|4.206|+1.313|
|Completed cycle wall|121.389|122.963|+1.574|

No missing cycle detail(87/135 <256 cap), phase sums exactly match cycle wall. All trade waits partition exactly; no tracking loss/saturation, missing admissions or fake acknowledgements. These are logical consumer wall states, NOT exclusive CPU; preemption/I/O within a state remains part of that wall. Residual drain phase includes queue operations plus existing internal yields, not isolated heap CPU. Final partial-drain trade counts differ, so these totals are not equal-population microbenchmarks; the full-row elapsed/latency metrics above include all submitted trades.

Periodic eligible analysis invocations increase20,949 ->24,243(+15.7%), inferred from total25,749 ->29,043 minus4800 trade analyses, with the only create terminally rejected by admission. Full analyse inclusive wall41.702 ->54.908s (overlaps event/periodic phases; DO NOT add it again). Refresh calls87 ->135; cycles with >50ms actual refresh86 ->97, while others remain gated by the original1s refresh predicate. Completed cycles rise55%, but mean durable events/cycle falls36%. Existing eligibility checks were never removed; faster outer cycles amplify expensive required work. Event phase and residual work also rise. The21.835s sleep saving is consumed, without a throughput gain.

This experimentally confirms that accepted work DOES wait during fixed idle; it does NOT make that time free service capacity. Queue-aware zero-delay turns increase cycle/work frequency and worsen CPU/end-to-end latency. It reproduces the earlier no-idle warning with a bounded pending-only policy rather than assuming a better outcome.

## Fairness, producer handoff and causal limits

All RPC/recovery/quote tasks make progress, but producer deadline fairness is worse: median scheduled-to-ready5.202s vs .168s, p998.018s vs .699s. Lower heap occupancy or shorter cycles must not hide upstream lateness. In the workload the producer yields after each item, including when late; a consumer continuation with larger synchronous work per resume can keep making progress while acquisition falls behind. Snapshotting producer-ready alone would mask this failure; immutable scheduled event timestamps preserve end-to-end age. No timestamps were rewritten.

Local CPython3.13.16 source inspected read-only: asyncio.sleep(delay<=0) uses __sleep0; BaseEventLoop._run_once services a finite snapshot of _ready, with due timers moved to that queue. Cooperative yield is NOT a guarantee of per-task deadline fairness or equal CPU slices. Exact source paths/contents are retained as run_once-stdlib.txt and sleep-stdlib.txt. This explains a mechanism consistent with the measurements, not an exclusive causal accounting of every delayed item.

Recovery p95 also increases .654 ->.870s despite84/84 completing; provider progress is not proof of unchanged latency. There is no observed hard provider starvation(4/4 declared quote deadlines met, no recovery expiry). Resource-pressure fallback remains enabled and unit-tested; no pressure at these idle boundaries. No busy polling of empty queues: each pending loop still drains and yields, and empty/pressure/shutdown retains250ms.

Shared PSI first-to-last: CPU .264927 vs .249997 stall-s, I/O3.143251 vs3.040721, memory0 for fixed40 vs queued40. Cumulative commit wall rises only .953s; no new evidence that external I/O contention is the principal cause of this regression. The strong observed change is active work frequency/placement. Host/hypervisor effects and changed time-dependent feature/cache costs are not fully isolated by a single sequential pair. Full candidate safety/signal equivalence is NOT proved: all persisted synthetic decisions happen to be WAIT, which is insufficient to prove identical future decisions across different scheduling boundaries.

## Correctness scope and next decision

No backend/app, PriorityBuffer, SQLite boundary/settings, callback semantics, security/risk/eligibility/freshness/continuity or economics change. Original raw-event identities, durable acknowledgements and failure behavior remain active. The rejected policy is retained ONLY behind explicit synthetic diagnostic flags for reproducibility, default fixed. CLI rejects its use without those guards. New tests prove real provider yielding, fixed-control behavior, empty/pressure/shutdown delays, cancellation/restore/bounds and no DB creation on invalid diagnostic use. Both policies exercise the retained12s integration/restart. Full existing crash, rollback, replay, ordering, negative evidence and observer suites are required and preserved.

A safe production scheduling improvement has NOT been established. Do not deploy this policy or sweep shorter idle constants to obtain a passing run. Any next experiment must address amplification of analysis/refresh work while proving unchanged freshness, state-time snapshots and fairness; simply suppressing required passes or changing their thresholds is not justified. No new placement algorithm was guessed after this failed result. Longer validation is not authorized by these measurements.

Files: scripts/consumer_trace.py and backend/tests/test_consumer_trace.py (previously untracked, preserved before extension); scripts/validate_evidence_load.py; backend/tests/test_endurance_harness.py; this report. The pre-existing0753300 harness depends on the untracked module; both diagnostic source files must be included when publishing for fresh-clone reproducibility. If Git remains read-only, do not claim that publishing the tracked harness alone includes them.

Artifact root data/early_edge/idle-experiment-20261025/ retains every report/gate/progress/process receipt, actual synthetic DB, exact initial copies/hashes, source overlay, comparison.json, runtime source extracts and quality outputs. No historical evidence, retired cohort or production database modified. PRE_COHORT_READY=NO.


## Full validation and audit integrity

**Complete backend843 passed,1 skipped in171.84s, exit0** using the existing explicitly labelled bounded-cleanup diagnostic. Original Runner.close and real worker joins retained; this is not an unrestricted ordinary-runtime cleanup claim. No cleanup workaround or shutdown suppression was introduced. Focused16 passed40.18s (both12s policy integrations). Fresh frontend39 passed5.90s; TypeScript/production build passed(Vite4.15s). Full Ruff passed; mypy46 sources; source secret scan224 files; whitespace checks passed. Fresh backend/frontend dependency audits remain UNVERIFIED: PyPI/npm DNS failures; outputs retained. No dependency/lock/runtime SDK added or changed.

Independent read-only SQL:4800/6000/4800 unique raw trades and matching identities/persisted ledger; all event dispositions reconcile. No stale/evicted/incoming/critical drops; no final heap, detached or recovery pending work.84/84 recoveries each, no overflow/expiry. Actual queue peaks89/232/318; sampled WAL peaks206032/206032/201912 bytes; after shutdown WAL/SHM0. DB final allocations14626816/17526784/14925824 bytes, below unchanged1GiB budget with no censorship/guard activation. Normal process return0 with zero remaining workers; cold-restart integrity ok,250 candidates restored with empty windows/security needing refresh. One intentional global shutdown reset per run, zero token-local resets; never reported as zero total gaps. All synthetic persisted trade decisions WAIT; paper cash20/no positions. Empty cohort tables, no real enrollment/outcomes. Synthetic WAIT equality is not full signal equivalence.

All phase/metric samples retained:87/61/135 complete cycles, no256-detail truncation; exact per-cycle phase sums, exact wait partition, no tracking overflow/missing admission/duplicate raw ack. Initial module/test copies are checked against their recorded hashes; all seven frozen experiment artifacts and retired database size/mtime remain unchanged. No input source/config/workload drift during any timed child; final documentation is written after measurement. These are controlled synthetic resource observations, not real-market evidence.

## Publication method and remaining local limitation

Local git add failed: read-only .git/index.lock. It is not bypassed or rewritten. Connected GitHub read-only checks confirm approved remote branch head EXACTLY matches the tested local base0753300877c3f844825d4c201364d98b0f8fac05, tree77c9e8e7aa72682e270fbd9ea2c09f2be985f7dd. Under the user's existing commit/push authorization, only the five reviewed files will be placed in a normal child commit of that exact head, then advanced using force=false plus expected_sha. No existing commit is recreated, no history is rewritten, and no other branch is changed. Remote base/new file-tree differences must match those five paths exactly before publication. Actual commit/update verification is recorded in final-receipt.json and final response; this document does not assume an API write succeeds.

The existing local Git ref/index cannot be updated under the filesystem restriction, so it must NOT be described as a clean checkout of the resulting remote SHA. Exact file content hashes/overlay establish what was tested; metadata-only publication occurs afterwards. A fresh checkout of the published commit is needed for future clean-SHA runs. This is separate from the rejected scheduling policy and does not authorize a cohort or long run.

Final decision: **queued_yield rejected; no production scheduling improvement, no production code change, no600s, PRE_COHORT_READY=NO**. Next work must first demonstrate how to avoid increasing analysis/refresh demand without weakening its time/eligibility semantics. No alternative was silently substituted after failure.


### Actual publication outcome (not the planned success)

The create-tree request was blocked BEFORE execution by the connected GitHub tool: "MCP tool call requires approval, but approval policy is never". No alternate mutating endpoint or permission bypass was attempted. Final read-only ref verification confirms the branch is still0753300877c3f844825d4c201364d98b0f8fac05. No new remote commit/ref or successful publication. The local index remains read-only; no new local commit exists either. Thus the publication plan above did NOT complete. This is a tool-policy limitation despite the user's authorization, not a request for more user confirmation.

A complete reviewable-experiment.patch and final-receipt.json preserve only the five tested/reviewed files and status. The untracked module/test still need inclusion for a fresh clone; do not claim a clean/published new source identity. Existing local/remote HEAD are unchanged. No main/force/merge action occurred. PRE_COHORT_READY=NO regardless of this delivery limitation.

# ADR: evidence-pipeline capacity and analysis separation

Date: 2026-10-25. Status: **retain serial production architecture; defer implementation of separation pending proof**. PRE_COHORT_READY=NO.

Decision source: remediation/early-edge-evidence-readiness at aa75d9903250b22508034c4cd28a2b719459d1a5. This is a documentation-only architectural decision, not authorization for a runtime optimization, changed sampling policy or new experiment. No new replay, provider request, cohort or trade was run. Five pre-existing diagnostic modifications/untracked files remain outside this change.

## 1. Evidence and scope

The preserved reports are the evidence sources; their original failed results remain authoritative for their respective source/workload. This ADR does not pool different revisions, tmpfs and project-ext4 runs as if they measured one capacity distribution.

- [Original failed endurance](../../docs/validation/early-edge-endurance-20261024.md): historical 600s capacity failure and host/storage receipt.
- [Persistence investigation](../../docs/validation/early-edge-persistence-20261024.md): reconciliation, checkpoint changes and filesystem comparison.
- [Capacity bracket](trade-capacity-20261024.md): finite 30/40/50 input-rate comparison and three 60s validations.
- [Transaction counterexamples](publication-and-boundaries-20261025.md): why the two main transactions cannot naively merge.
- [Storage fast path](storage-guard-capacity-20261025.md): retained optimization, two opposed 50/s growth results.
- [Aligned backlog diagnosis](backlog-oscillation-20261025.md): exact-cut producer/consumer dispositions.
- [Consumer timing](consumer-scheduling-20261025.md): exclusive wall phases and detached-batch waiting.
- [Rejected idle policy](queue-aware-idle-experiment-20261025.md).
- [Rejected computation reuse](computation-reuse-20261025.md): actual-code measurements and restored production.

Local receipt: data/early_edge/architecture-decision-20261025/initial.json records hashes of these nine reports, the five existing worktree files, production tree and seven frozen original evidence checks. It contains no transaction payloads. Historical source76d22105d2bb2f6e6c3c1d2f3ff9df5881d238ba and retired prospective data are unchanged. Retired database size/mtime remain1,073,893,376 bytes /1792471574652367761ns; it was not opened for writing.

### Capacity envelope actually demonstrated

All following rate comparisons are synthetic. They do not establish live acquisition completeness, economic validity or future returns.

|Revision/experiment|Duration and input|Observed application p99|Accounting and capacity conclusion|
|---|---|---|---|
|Earlier endurance source29857e7|600s,250 candidates,50/s|32.804s|30,000 submitted;19,317 persisted;9,959 stale;698 dropped;26 explicitly untracked after churn. Failed capacity, freshness and loss criteria.|
|Checkpoint/pending-write optimization|60s,250 candidates,50/s|16.739s|39.10 committed rows/s including drain; short improvement, failed latency. Not current-head capacity.|
|a07a1a5 capacity bracket|120s each,30/40/50/s|1.411 /1.846 /3.469s|3,600/4,800/6,000 persisted. Sampled backlog26→26 /22→20 /62→132. Finite non-growing observation at30/40;50 deficit about.708 events/s in that comparison window.|
|Same capacity investigation|Three60s50/s|2.966 /2.749 /3.072s|All short latency gates passed; this did not erase the120s deficit or certify longer capacity.|
|Storage fast-path optimized trial1|120s50/s|2.501s|6,000 persisted, no stale/drop; aligned slope−.272727 events/s, early/late means62.667/39.667: PASS.|
|Same source/config trial2|120s50/s|2.548s|6,000 persisted, no stale/drop; slope+.126364, means51.333/64.333: FAIL. Aggregate commit wall25.876s was slightly lower than passing26.064s.|
|Aligned diagnostic control40|120s40/s|2.015s|4,800 persisted; slope−.196364, means45.667/26.667: PASS for this finite run.|
|Aligned diagnostic50|120s50/s|2.609s|6,000 persisted; slope+.183636, means52.667/64.667: FAIL despite low latency.|
|Consumer control50 /instrumented50|120s50/s each|2.322 /2.430s|Both6,000 persisted; control growth PASS, instrumented FAIL. Instrumented result cannot replace or invalidate control; overhead/phase sensitivity remain limitations.|

The original600s loss categories reconcile exactly:19,317+9,959+559 rejected incoming+139 accepted then evicted+26 explicitly untracked=30,000. Accepted29,441 already includes139 later evicted; do not subtract them twice. The26 were not shutdown disappearance. Later short trials draining every accepted trade do not retroactively repair that failed experiment.

Application latency here is scheduled event age at processing START; durable-return latency is separately measured and cannot be inferred from it. The unchanged qualification is application and admission-to-start p99<5s, complete terminal reconciliation, zero unacceptable stale/drop/pending work, recovery completion and clean shutdown. The aligned no-growth test uses the existing scheduled-arrival deficit at fixed10s cuts from20..120s: OLS slope<=0 **and** last-three mean<=first-three mean. Heap depth alone excludes detached work and cannot replace it. The40/s regression sometimes checked latency/accounting only; its passing label must not be converted into a no-growth claim. Burst oscillation does not waive this rule.

**Established:** lossless, normally terminating finite250-candidate runs at40 and50/s, some passing50/s growth tests, meaningful earlier finite30/40 margin. **Not established:** repeatable50/s non-growth, current-source600s endurance, indefinite40/s capacity,30-minute stability or a new live-readiness result. Rows/elapsed including final drain is observed delivered throughput, not the sustainable service ceiling. No production admission limit is changed by this ADR.

### Resource and environment limits

Preserved hardware: Ryzen7 PRO3700U,4 physical/8 logical WSL CPUs,11,435,442,176 bytes visible RAM,3,221,225,472 swap; project ext4, /tmp tmpfs. Host thermal/Windows activity is uncontrolled. Recent120s trials used roughly68–70% of one core and208–213MiB peak RSS. This is not proof of8-core parallel headroom for a Python/GIL-bound pipeline. Earlier identical durable-write components were2.4–3.0x slower on project ext4 than tmpfs; later pass/fail differences do not establish SQLite slowdown or host contention as their cause. Filesystem/CPU conditions remain part of reproducibility, not excuses to relabel failures.

Configured study bounds remain250 candidates,25 deep-monitored,1,000 queue,100-event selection,500-event rolling buffer,250ms cadence; recovery2 in flight/32 pending/45s/3 attempts. Normal memory target<500MiB, soft guard700MiB; byte-budget/censorship behavior remains authoritative. A prior approximately1GiB guard activation is a censored period, not complete research coverage.

## 2. Where service time goes

Consumer diagnostic:66 completed cycles occupy120.452s. Exclusive **wall-state** totals, not exclusive CPU:

|Phase|Seconds|Share|
|---|---:|---:|
|Event processing|62.441|51.84%|
|Periodic candidate analysis|25.755|21.38%|
|Intelligence refresh|12.971|10.77%|
|Cadence sleep|16.565|13.75%|
|Other, including maintenance/yields|2.720|2.26%|

Seven full100-event cycles exceeded2s; maximum cycle2.131s. That temporarily supplies at most46.92 events/s even if every selected event is a trade. It explains limited margin, not an indefinite rate limit. Maintenance was minor in this trace, not proved negligible for longer retention pressure.

Admission-to-start p99=2.350s; selection-to-start=1.049s; processing-to-durable-return=.023674s. About41.60% of aggregate waiting occurs after selection. Waiting attribution (other events54%,sleep22%,analysis13%,refresh9%) is overlapping **trade-seconds across events**, not removable CPU. No priority-lock bottleneck was demonstrated. At the failed120s exact cut87 trades were outstanding:9 not producer-ready,77 ready but not started,1 started not durable. All later persisted. Temporary consumer scheduling delay is real; perpetual growth and external-host causality are unproven.

The synchronous500-trade component measured1,000 commits/2.058s exclusive; full processing7.066s wall/5.290s CPU. The post-raw observe wrapper cost1.406s inclusive and includes coverage/readiness/ranking/snapshots/research side effects. Those nested costs must not be added to parent totals. Component profilers change timing and do not supply sustainable rates.

### Rejected approaches constrain the decision

1. **Naive transaction consolidation:** an open identity write blocks existing independently committed financial/research writers; moving identity later allows duplicate negative outcomes after restart. Counterexample tests remain. A complete unit-of-work/outbox design would be a different, substantially larger project.
2. **Queue-aware idle:** fixed40/s p99=1.762s versus queued40/s8.603s. Cycles87→135; periodic analysis31.231→43.312s; refresh16.000→22.780s. More frequent legitimate work and worse producer scheduling consumed the removed sleep. All rows eventually persisted; lower-load latency failure rejected the candidate. No production scheduler change retained.
3. **Classification reuse:**29 equivalence cases passed, but actual-code unchanged-evidence gain only~1.1–3.5%, with a new-trade regression in one pair. Feature module restored byte-for-byte. No follow-up replay justified.
4. **Storage fast path retained:**~68% guard-time reduction without stale allocation caches, durability or limit changes; it improved a component, not reliably sustained50/s. Do not optimize the database again based solely on queue growth.

## 3. Current transaction and evidence contract

Relevant source: backend/app/engine.py: process, _process, drain_events, analyse, run_loop, trade_status, refresh_trade_continuity; backend/app/domain.py: PriorityBuffer.put/drain; backend/app/db.py: reserve_event, _add_event, add, checkpoint_records, writable; backend/app/intelligence.py: project, observe, refresh; backend/app/features.py: calculate_features and window/cache helpers.

Current path: strict acquisition and intentional filtering → bounded priority admission → priority-selected batch, chronological timestamp/sequence order within that batch → freshness/dedup/identity reservation → token/creator updates and analysis → independently durable lifecycle/outcome/paper/context records where applicable → raw event containing scores/state/decision/reasons after processing → raw commit acknowledgement → intelligence/early observer callbacks. This is not global chronological ordering across all future arrivals. A selected event can wait behind99 other events; cancellation must terminalize the detached remainder.

Identity and raw insert each use their own committed transaction. Duplicate insertion is conflict-safe. Ambiguous commit responses require an independent exact committed-row proof; absent proof raises. No success acknowledgement precedes commit. There can be a committed identity without a raw event if the process stops between them. Replay suppression then fails closed and requires continuity rewarming; this is **not** whole-event exactly-once reconstruction. Crash tests cover process termination, not a guarantee against sudden host power loss. Existing WAL/synchronous=NORMAL/busy_timeout5000/autocheckpoint32 remain unchanged; commit guarantees are scoped to those settings.

Separate observer-owned transactions and in-memory mutations make combining just the two initial writes incorrect. Raw records include decision_after and context: they cannot move ahead of required analysis while claiming the same audit semantics. Counts must distinguish submitted, intentional filtered, accepted, evicted, selected, processing-rejected, identity-reserved, raw-durable, callback-completed and cancelled/pending states. Accepted trade volume is not evidence of correct units, current analysis or CURRENT coverage.

## 4. Architecture alternatives

|Requirement|A: retain current serial ownership|B: bounded ingestion/analysis separation, conditional design|
|---|---|---|
|Evidence ordering|Existing priority selection, chronological selected batch, one mutable owner.|Keep the same admission/selection order and revision stream; worker completion order must never become event order.|
|Durability|Preserve two main transactions and observer-owned commits, exact acknowledgements and censorship receipts.|Preserve these boundaries initially. No asynchronous write acknowledgement. Any later journal/outbox design needs its own atomic publication/idempotency proof.|
|Crash/replay|Existing reservation-only crash window fails closed; cold start rewarms coverage.|Snapshots/results are disposable. Restart cannot adopt pre-crash clean coverage or late results. Durable snapshot/publication records, if added, need unique revision IDs and pending/failed dispositions.|
|Time-dependent work|Every required event/periodic evaluation runs on owner with actual application time.|Worker computes explicitly as-of time; owner revalidates freshness, continuity, health, risk and financial dependencies before publication. Late results fail closed; no retrospective signals.|
|Callbacks|Stateful research/financial/coverage effects remain ordered after applicable commits.|Workers perform pure calculation only. Owner executes existing callbacks exactly once under current contract; no deferred side-effect queue without separate recovery design.|
|Decision equivalence|Current semantics remain reference.|Identical evidence, evaluation time and context must produce identical scores/decisions/state/signals/outcomes/references. Different computation timing alone does not authorize different decisions.|
|Provider fairness|Existing bounded drain/yields and cadence; measured provider progress, limited margin.|No busy loop or unrestricted executor. Bound in-flight snapshots/results and measure actual provider deadlines, not just eventual completion.|
|Resources|Known queue/candidate/buffer limits; loss/expiry/storage pressure fail closed.|Count and byte bounds for snapshots, worker jobs, results and retries, within existing memory/storage envelope; no hidden second event backlog.|
|Complexity|Lowest change risk; finite evidence does not prove50/s stability.|Higher: versioned immutable inputs, time invalidation, stale-result rejection, cross-token contexts and deterministic publication. CPU threads may not accelerate Python; process transfer/copy cost may consume gains.|
|Disqualifier|Unacceptable queue growth/staleness/loss or censored acquisition; no readiness claim.|Unbounded buffers, early acknowledgements, stale/partial snapshots accepted as current, changed ordering/signals, missed analysis deadlines, observer duplication or fairness regression.|

### Required classification of time and mutation dependencies

- **Evidence-version dependent:** ordered event content, creator identity, verified units, flow venue/epoch, security/pool identity, quote state, immutable schema/config/source versions. A key must include every effective input; mint plus last_trade is insufficient.
- **Time dependent even without new events:** window membership/half-windows/bins, acceleration/persistence, age scores, freshness20s,180s clean coverage, security TTL, lifecycle waits/expiry, deadline maturation and outstanding outcomes. Existing six-slot feature cache already reuses static statistics while recomputing dynamic classifications.
- **Global/context dependent:** provider health/disagreement, resource/storage pressure, cash/positions, approved evidence, manual-versus-provider context and config drift. Per-token versions alone cannot establish validity.
- **Effectful:** state transitions, alerts, observer acquisition/coverage, enrollment/dedup/outcome accounting, negative-evidence persistence and paper records. These are not memoizable projections.

Option B needs a frozen primitive snapshot, not shared Token/ORM references. It must bind event revision, configuration/strategy versions, flow epoch, security/health/global generations, explicit evaluation time, evidence references and relevant cross-token context. Main-owner validation must reject any changed dependency. Present-time gates must still be evaluated at publication time; a timestamped old projection is not fresh market evidence. Multi-token control risk sets require one contemporaneous view, not a mixture of asynchronously completed token results. Research snapshots cannot be rewritten by future evidence.

A bounded design should permit at most one active analysis batch and one pending replacement per token, within existing250-candidate bound, with a separately enforced total byte budget and explicit superseded/late accounting. This is a proposed prototype constraint, not an implemented limit. Supersession may apply only to pure projections whose required intermediate effects are proven absent; mandatory evaluation/transition times cannot be coalesced away. Measure snapshot size and copy/serialization cost before selecting a byte limit within the<500MiB normal target. Stale results must not accumulate or silently erase required negative observations. No network awaits inside write transactions and no database writes from pure workers.

## 5. Recommendation and projected benefit

**Retain A for production now. Do not declare sustained50/s or authorize another readiness run.** Operate only with observable bounded-loss/freshness accounting; any overload remains incomplete, never silently valid evidence. The finite30/40 results suggest more margin than50, not a validated indefinite operating-rate guarantee or permission to alter admission thresholds.

The smallest credible architecture-level investigation is a **pure periodic-projection boundary**, keeping ordered ingestion, per-event analysis required by raw audit rows, and all effectful publication/callbacks on the existing owner. Before implementing a worker, identify an actual pure subgraph of periodic analyse/refresh and specify its snapshot/result contract and required evaluation deadlines. Intelligence.refresh includes effectful observe/expire/position work; it cannot move wholesale. This ADR recommends that design/proof step, not an off-thread rewrite or another scheduler experiment.

Timing bounds clarify the opportunity but do not choose a scheduler:

- If ALL25.755s periodic analysis were free/fully overlapped with zero new work,120.452s would become94.697s: ideal speedup1.272x.
- If ALL periodic analysis AND12.971s refresh were free, residual81.726s: ideal1.474x.
- These are counterfactual upper bounds on one traced population, not demonstrated sustainable63.6/73.7 trades/s. They ignore continued CPU work, GIL, snapshot transfer, invalidation, synchronization and required effectful portions. No comparable safe implementation has measured either saving.
- If a future prototype safely removes fraction f of critical wall time, its optimistic speedup is1/(1−f); f must be measured from exclusive, equal-population samples. Existing component reuse savings were too small to establish useful f.

Moving SQLite waits alone cannot erase the25.755s required analysis or post-commit effects. Additional cores do not establish a benefit from Python threads. A process worker could offer real CPU overlap but is larger and must pay bounded snapshot costs; a logical staged implementation on one event loop could improve isolation without improving throughput. Neither is approved here. The realistic benefit of the recommended narrow boundary is **unknown until pure-work fraction and transfer cost are measured**; the defensible current improvement is architectural clarity, not a numeric capacity gain.

A broader raw-ingestion journal followed by derived materialization could be studied later, but changes the raw audit contract and crash windows. It is not the smallest credible current change and is disqualified without durable intent/publication, idempotent side effects, ordered recovery and unchanged financial/research semantics.

## 6. Evidence required before any prototype can be adopted

No prototype implementation or benchmark is initiated by this ADR. A future separately authorized prototype must predeclare:

1. Pure computation boundary, complete snapshot schema, dependency generations, maximum snapshot bytes/count, required evaluation deadlines, worker lifecycle and rejection/publication rules. Measure exclusive pure work first; do not sum nested profiles or waiting trade-seconds.
2. Deterministic baseline-versus-candidate equivalence at identical evaluation times, including time-only transitions, all six windows, boundary crossing, creator/units/security/provider/config/resource changes, venue transitions, ranking/protected positions, raw context references, signals, negative outcomes and observer acquisition clocks. All-WAIT fixtures are insufficient.
3. Crash/failure matrix: before identity commit, identity-only, raw commit-before-return, callback failure, worker cancellation, stale/out-of-order results, busy/locked DB, retention/guard, restart and duplicate replay. Retain exact commit proofs and independent transactions unless a separately proved design supersedes them. Never acknowledge undurable work.
4. Bound pressure and fairness tests: full queue plus detached batch accounting, critical events, superseded/late analysis, provider deadlines, recovery pressure, resource guard and deterministic shutdown. No change to freshness, continuity, candidate/queue limits or SQLite settings.
5. Only after meaningful component gains and equivalence: original project-filesystem workload, frozen source/config/input identities,250 candidates/200 warm histories, deterministic burst/recovery/quote stand-ins; serial comparable trials with no competing quality jobs. Record application/durable/ready-to-start p50/p95/p99, exact-cut debt components, CPU/RSS, database/WAL growth, exclusive wall phases, commit counts/latency and provider deadlines. Instrumentation overhead must be bounded and disclosed.
6. Preserve original p99<5s and aligned OLS<=0 AND late<=early rules; require zero unacceptable stale/drop/pending work, complete event reconciliation, clean recovery/shutdown, no integrity/source drift. Run40/s regression then three consecutive fully qualifying50/s short trials, stopping and preserving the first failure. If those qualify, only one bounded600s synthetic validation may be considered under the existing conditional protocol. Longer/live validation needs its own authorization; no favourable subset or revised criterion substitutes for failure.

## 7. Readiness and validation of this decision

PRE_COHORT_READY remains NO. Synthetic correctness/persistence does not demonstrate live observation fairness, complete quote deadlines, matched controls or prospective statistical evidence. Long rolling-buffer gaps, unknown units, transport/recovery loss, storage censorship and retired-cohort infrastructure missingness remain distinct and visible. A first class of gap cannot be erased because another stage eventually drains. No cohort, approved holdout, strategy/opportunity/security/economics setting or decoder was changed.

This task performs report/source inspection, arithmetic, local evidence/preservation hashes, document-link checks, secret scan and whitespace checks only. It does not rerun the prior846-pass/1-skip bounded-cleanup backend suite or39 frontend tests; those are historical results, not new full-suite passes. Backend normal-runtime cleanup qualification remains separate from the confirmed sandbox socket-pair EPERM constraint. Dependency audits were previously UNVERIFIED due DNS, not passed; no dependency change in this decision warrants claiming otherwise.

Publication outcome and final focused checks are appended only after actual results. Only this ADR is eligible for staging; the five pre-existing diagnostic changes must not be swept into its commit.

### Completed focused checks and publication

Read-only checks passed: nine document links resolve; original30,000-trade reconciliation is exact; the two optimized50/s gate JSON files independently satisfy their reported opposite outcomes under the unchanged rule; timing upper-bound arithmetic yields1.272x/1.474x. All nine source-report hashes, five pre-existing file hashes, seven original evidence hashes and retired DB size/mtime match the initial receipt. Production has no worktree diff. Basic source/document secret scan passed228 files. Tracked-diff and new-document whitespace checks pass. No application tests, benchmarks or dependency installations were run for this documentation-only change.

Staging only this ADR failed: Git could not create .git/index.lock because the filesystem is read-only. No commit or push was made; HEAD remains aa75d9903250b22508034c4cd28a2b719459d1a5. No permission bypass or API mutation was attempted. The five prior changes remain untouched. Publication from an authorized writable terminal must stage ONLY backend/docs/adr-evidence-pipeline-capacity-20261025.md, review the staged file list and commit to the approved remediation branch. No main push, merge or force push is authorized.

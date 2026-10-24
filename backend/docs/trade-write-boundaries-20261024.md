# Trade write boundaries and durable acknowledgements — 2026-10-24

PRE_COHORT_READY=NO. Start: remediation/early-edge-evidence-readiness, clean7a265dadcd6ba49e819dc87d0b69a7e4d65cfdea. Historical evidence and retired cohort preserved. All new probes/databases are isolated synthetic artifacts in data/early_edge/writer-boundaries-20261024/. No push, trading, cohort or six-hour run.

## Boundary investigation BEFORE production change

Read trade-capacity/reproducibility/persistence reports, Database, RadarEngine, OutcomeCollector, PaperBroker, OpportunityResearch, creator and observer paths. Typical existing tracked trade:

| Stage/function | Persistent operation | Mutable state / acknowledgement |
|---|---|---|
| process/_process validation | No SQL | Source/venue/epoch/freshness filters; no threshold changes allowed |
| dedup.accept | No SQL | Bounded RAM identity marked before SQL; a later failure does not clear it |
| Database.reserve_event | Session transaction1: fresh writable/free-page guard; parameterized INSERT event_identities ON CONFLICT DO NOTHING; COMMIT | New reservation acknowledged only after context commits; UNIQUE primary-key index is authoritative across restart |
| admit/creator/last_event/window updates | Creation may commit transitions; creator/window fields mutate | Existing tracked trade generally avoids admission writes; this is NOT guaranteed for every event/source |
| analyse/transition | State changes may independently commit transition rows | Features, ranks, decision and lifecycle mutate before raw-event persistence |
| collector.observe/signal, paper.observe/request_entry | Independent outcome/signal/pending/paper transactions and record observers, depending on evidence/mode | Financial/research memory can also change; immutable signal snapshots must remain intact |
| context_reference | On a cache miss, immutable context insertion has its own transaction | Context cache advances after commit |
| Database.add('event') | Session transaction2: fresh raw storage guard, JSON bound/encoding, cached Core INSERT records, COMMIT | Raw row ID returned after commit; engine then marks _event_persisted |
| intelligence.observe, research/attached observer | May independently persist opportunity/outcome/pending/cohort data | Can fail AFTER raw commit; terminal exception and persisted=true are distinct valid accounting states |
| process finally / drain_events | Session audit/checkpoint later | Terminal disposition and persisted counter; processing failure creates local/global gaps; detached remainder cancellation is accounted |

Measured low-level20 pairs:40 pool checkouts,40 transaction begins,40 freelist guards,20 identity INSERTs,20 raw INSERTs,40 commits; ONE physical pooled connection. No extra identity SELECT is required normally; EXPLAIN shows the primary-key covering index. Raw INSERT already uses Core and has no ORM Record observer/flush; Session transaction lifecycle overhead remains. Financial records retain ORM flush/observer semantics. WAL/NORMAL, busy_timeout5000, autocheckpoint32,page_size4096 unchanged.

### Why NOT combine the entire event

A write transaction opened at reservation and held through processing conflicts with independent outcome/paper/context writers and callbacks. Moving identity insertion to the end without an intent/rollback protocol permits partial financial/research writes to be replayed after a crash. A token-only memory copy does not restore creator, collector, paper, observers and all independent transactions. Full cross-component rollback/publication is not established, so identity+raw consolidation is NOT safe as a minimal patch. The existing compatible bounded expiry transactions remain unchanged; the raw/identity pair alone cannot be moved across those side-effect boundaries honestly.

Existing failure window: a committed identity with no raw event suppresses replay after restart. This avoids duplicate side effects but can leave missing evidence. It is NOT an atomic whole-event recovery guarantee. Current gap accounting/re-warm must remain fail closed; no claim that this patch fixes that larger crash window. An ordinary SQL error before reservation also poisons the RAM dedup entry until it evicts/restarts; preserve/record rather than silently reapply a mutated event.

### Measured smaller alternative

ABBA500-pair probes on real project ext4: current CPU1.525/1.131s vs direct Core transaction CPU1.168/.895s. Wall3.407/2.736s vs2.924/2.508s; all1000 commits per500 pairs, identical guard SQL/encoding/payloads. I/O service varies, so CPU evidence is stronger than attributing every wall difference to code. Avoid Session wrappers only for identity/raw writes, keeping two bounded committed transactions, existing pool and all guards. No dedicated writer/async queue or weaker durability.

Fresh baseline120s50/s from clean7a265da:6000 processed/persisted, app p992.855s, elapsed121.698s, CPU69.64%, RSS210.47MiB; all recorded evidence preserved. Previous failing6.129s remains equally authoritative; this passing baseline does not erase service variability.

### Chosen semantics, before implementation

1. Core Engine.begin for identity/raw only; return outside committed context. Financial/other record Session/flush/observer path unchanged. Same SQL, pool, unique key, size/physical/free-page budgets, censorship and two commit boundaries.
2. A commit response may fail AFTER SQLite committed. Only when an insert result/new reservation was obtained, do one bounded independent READ after the failed scope has closed. Verify the exact raw primary-key/kind/mint/session/timestamp/encoded payload or identity tuple. No write retry, guessed success, uncommitted read or arbitrary replay.
3. Verified durable row may acknowledge success; verified absence rethrows original error, and failed/mismatched proof remains explicitly uncertain/rethrows. Bounded aggregate counters and final/running audit receipts expose resolution. Never fabricate persisted=true from an attempted INSERT.
4. Preserve chronological engine execution, all financial callbacks, negative evidence and gaps. Mid-event crash after identity but before raw remains an explicit limitation; independent writes make a larger atomic transaction a separate design.

Failure tests must cover before/after-commit errors, duplicate identity, rollback, busy lock, cold crash/restart, storage censorship, observer preservation, exact output/decision parity and all terminal ledger dispositions. Benchmark gates remain unchanged.

## Implementation and authoritative transaction semantics

Code commit96e93a3 uses Engine.begin for identity/raw writes, retaining two commits and the same indexed SQL. No ORM Session is constructed for those two paths. Financial/research/non-event records keep their original Session/flush/record_observer behavior. There is no cross-event batching, background writer, early acknowledgement, altered SQLite isolation/durability, schema migration or added dependency.

Installed SQLAlchemy2.1.4 was checked against the current official [2.1 Engine/Connection transaction documentation](https://docs.sqlalchemy.org/en/21/core/connections.html#connect-and-begin-once-from-the-engine). Engine.begin commits on normal scope exit, rolls back an exception and returns the pooled connection; the verification read happens only AFTER the failed scope has closed. Pool reset-on-return removes transactional state. Fault injection verifies this behavior on the installed runtime. No package was upgraded to match documentation.

Normal trace remains EXACTLY identical before/after:20 pairs ->40 checkouts,40 begins,40 freelist guards,20 identity INSERTs,20 raw INSERTs,40 commits, one physical pooled connection. The probe is not an engine benchmark and makes no strategy inference. The expected normal transactions per trade remain **2 -> 2**, not1. SQL round trips were not falsely claimed removed; the improvement is Python transaction-wrapper overhead. The old identity-to-raw crash gap remains, explicitly.

### Commit-response proof and audit

Database._verify_committed_write performs one bounded read, not a write retry. New reservations require the exact ID/timestamp; raw writes require the exact primary-key/kind/mint/session/timestamp/encoded payload. A duplicate reservation remains False after verification, never a second successful reservation. Absence or mismatched/unreadable proof rethrows the original exception. Only independently verified committed content returns success. Six aggregate verified/absent/uncertain counters contain no identifiers/payloads; protected by a short lock, exposed in health and RUNNING/STOPPED receipts. Normal benchmarks recorded zero in every counter. No full trade list is retained.

The proof fixes a real audit discrepancy on an injected lost raw-commit response: previously a durable raw row could be counted unpersisted when the caller never received its ID. The new path resolves success only from exact durable content; accounting then records processed/persisted once. Before-commit failures still roll back and produce exception/persisted0 plus a local gap. Failed proof is explicitly uncertain, never silently complete.

This is NOT whole-engine rollback. A committed identity followed by a genuine raw rollback still has no raw record and suppresses replay, preserving the old conservative behavior after possible independent side effects. A crash may leave no final stopped receipt. Restore windows/security re-warm remain mandatory. Host-power-loss durability beyond the existing WAL/NORMAL policy is not claimed.

## Focused failure correctness

55 focused tests passed in34.57s (new writer tests plus existing hot-path, storage, evidence-accounting and harness cases). New tests cover:

- Actual SQLite two-transaction/statement counts, duplicate primary keys, raw callback exclusion and unchanged negative-outcome observer behavior.
- Failure before commit -> rollback/absence proof and safe direct DB retry; success followed by lost commit response -> exact read proof.
- Wrong kind/mint/session/timestamp/payload and unreadable proof -> reject/uncertain with original exception preserved.
- Busy/locked transaction rollback with test-only short timeout; retry after lock release. Production timeout remains5000ms.
- Raw storage censorship returns0 with a receipt and preserves negative/unavailable records.
- SIGKILL immediately after identity, before raw commit and after raw commit; cold integrity/replay checks prove the two distinct original crash boundaries. No success is invented for identity-only records.
- Engine queue/accounting after before/after raw commit errors, local gap behavior, duplicate replay, persisted counters and durable STOPPED reconciliation counters.
- A real legacy Session writer adapter on identical fixed DEMO observations, compared to the new path: features, scores, decisions, lifecycle state, ranking/tie-breaks and paper cash identical. No production mocks or alternate strategy engine introduced.

Full suite also covers existing partial expiry transactions, SQLite FULL, rollback/retry, queue eviction/cancellation, concentration/security, prospective integrity, decoder strictness, all horizons and cold restart. No strategy threshold, freshness, units, opportunity, Companion, lifecycle, recovery scheduling, paper approval or quote model changed.

## Comparable project-filesystem measurements

Baseline source7a265da before production edits; native source96e93a3, each clean. Settings/source/harness identity receipts retained; settings unchanged. The harness differs only by additive completion-bin/reconciliation recording, not input scheduling, provider budget, cadence or admission.120s,250 candidates,200 warm observations each,0.7 recoveries/s, unchanged burst pattern, shared limiter/mock quotes; fresh ext4 DBs. No benchmark/quality suite overlap. Native40 first; up to three native50 trials predeclared, stopping at the FIRST failure. No cherry-picked restart or replacement run.

| Run | Trades persisted | App p50/p95/p99 s | Durable p50/p95/p99 s | Queue p99 s | Queue peak | Mean CPU % / RSS MiB |
|---|---:|---|---|---:|---:|---|
| baseline-50 | 6000 | 1.832/2.561/2.855 | 1.843/2.572/2.866 | 2.632 | 173 | 69.64 / 210.47 |
| native-40 | 4800 | 0.994/1.564/1.785 | 1.007/1.576/1.796 | 1.447 | 99 | 67.84 / 208.56 |
| native-50-1 | 6000 | 1.512/2.257/2.552 | 1.520/2.269/2.563 | 2.418 | 143 | 68.75 / 210.72 |

Application age remains processing-start age. Durable completion age is measured AFTER successful process return and confirmed raw persistence. All records/identities are independently reconciled in read-only SQL, not counted as durable when merely enqueued.

| Run | Elapsed incl drain s | Committed rows/elapsed s | DBAPI commits / wall seconds / p99 ms | WAL peak bytes |
|---|---:|---:|---|---:|
| baseline-50 | 121.698 | 49.30 | 12112 / 25.546 / 12.148 | 206032 |
| native-40 | 120.978 | 39.68 | 9713 / 20.465 / 12.031 | 197792 |
| native-50-1 | 122.857 | 48.84 | 12138 / 25.360 / 12.048 | 230752 |

Uncertain proof does not mean an absent row: persisted counters count confirmed acknowledgements, while an uncertain write remains an explicit error/gap. Accepted-versus-terminal reconciliation alone is not proof of complete raw evidence.

Commit count includes maintenance/read-only/no-op work, not just durable trade transactions. Quantiles retain the existing last8192 bound, so these120s runs' commit p99 values are trailing-sample, not all-call population quantiles; counts/totals/role bins cover all calls. WAL durability remains WAL, synchronous=NORMAL,autocheckpoint32,4096-byte pages; no busy failures in timed runs. WAL/SHM close to zero and final DB allocation retained. No physical cache flush, limit expansion or tmpfs substitution. Statement/connection traces match before/after and show indexed primary-key lookup, not a missing-index scan.

Writer-inclusive Database.reserve_event+Database.add time falls39.434 ->35.983s for6000 trades; commit wall only25.546 ->25.360s. Component ABBA CPU savings21–23% apply to the writer adapter, NOT to total engine CPU. Overall process CPU84.75 ->84.46s is nearly unchanged. Calculate_features calls21,542 ->22,946/time34.928 ->36.534s; refresh calls62 ->68/time12.240 ->13.153s; restoration checkpoint calls3 ->4. Faster writer handling permits additional existing periodic analysis iterations; the cadence itself was not changed. Analysis timers overlap writer/observer timers and must not be summed as exclusive CPU. Native elapsed is HIGHER and committed-through-elapsed LOWER than this passing fresh baseline. No claim that sustained end-to-end throughput improved or that the old6.129s failure was eliminated.

### Backlog over time: exact phase matters

New durable completion counts use monotonic10s bins, with no extra timer or queue. At exact boundaries after20s warmup, scheduled arrivals are known, so deficit includes producer lag, detached work and queue waiting. This avoids choosing favorable one-second sample endpoints. The predeclared conservative target50 criterion requires nonpositive fitted slope across20..120s AND last-three aligned mean <= first-three mean. This is a qualification rule, not proof of a statistically significant long-term slope or a strategy threshold.

Native50 aligned deficits:20s48;30s73;40s38;50s60;60s75;70s44;80s31;90s51;100s50;110s73;120s98. Early mean53;late mean73.667;slope+.203636 events/s: **NO_GROWTH_NOT_DEMONSTRATED**. One-second sampled middle endpoints would instead show91->57 and negative growth, illustrating why that favorable comparison cannot substitute for aligned measurement. Baseline predates completion-bin instrumentation; no exact historical bins were invented from its sampled counts. Native40's latency/accounting regression passes, but its finite aligned series is also noisy; it is not proof of indefinite sustainability.

The driver stopped after the first native50 failure. Trials2/3,600s and30-minute validation were NOT run. Neither a2.552s p99 nor zero loss clears the no-growth condition. No acceptance threshold was relaxed after viewing the data.

All timed runs: every trade processed/persisted once, no stale/incoming/evicted/critical drops, no queued/detached work or pending recovery at final shutdown;84/84 recovery successes; normal process exit0, zero remaining workers; cold restart integrity ok. One intentional global shutdown reset/run, zero token-local resets, not zero total gaps. Negative/unavailable opportunity outcomes retained, all trade decisions WAIT, collectable prospective cohort tables empty. These synthetic observations are not genuine CURRENT or research opportunities.

## Quality, environment and remaining limitations

Full backend817 passed/1 skipped in150.99s using the explicitly labelled bounded cleanup diagnostic. Original Runner.close and real executor joins remain; stuck workers still time out. Ordinary API test again prints PASSED then times out20s in cleanup. Fresh pure-stdlib probe repeats socketpair EPERM, ordinary executor3s timeout, bounded real-join positive exit0 and genuinely stuck-worker timeout. No application cleanup workaround was introduced. Unrestricted-host ordinary testing remains unavailable under current permissions, not passed by inference.

Frontend39 passed in5.99s; TypeScript/production build passed (4.09s). Ruff, mypy44 sources, secret scan and whitespace checks passed; installed backend audit no known vulnerabilities. Frontend npm audit retry remains UNVERIFIED: EAI_AGAIN registry DNS/exit1. No dependency manifest, lockfile or runtime SDK added/updated. Installed SQLAlchemy2.1.4 was used throughout.

Seven frozen evidence hashes and retired DB size/mtime are checked again at completion. All new databases/reports are uniquely preserved; no historical run was rotated/reclassified. Record-ID proof data is transient in the call stack; receipts retain only six counters. No private RPC/WSS addresses, wallets or raw market transaction payloads were logged. No real cohort, trading or six-hour experiment.

**PRE_COHORT_READY=NO. Sustained50/s acceptance NOT ESTABLISHED;600s NOT AUTHORIZED BY THESE RESULTS.** This patch safely removes measured Session overhead and closes commit-response acknowledgement ambiguity, but keeps the dominant two-commit I/O floor. The fundamental identity-to-raw failure gap and independently committed side effects still prevent a trivial atomic merge. A future shared unit-of-work/durable-intent/publication protocol must explicitly handle token/creator/collector/paper/observer rollback and crash replay before eliminating a commit. Do not introduce write-behind acknowledgements, an unbounded worker or weaker SQLite settings. Physical host I/O variability and normal unrestricted executor cleanup remain unresolved.

## File/commit boundaries

-07ab863: this report's transaction map, failure matrix/design and baseline BEFORE runtime changes.
-96e93a3: backend/app/db.py Core identity/raw scopes and exact commit proof; backend/app/engine.py bounded running/stopped/health counters only; backend/tests/test_trade_writer_transactions.py failure/parity coverage; backend/tests/test_endurance_harness.py bin reconciliation assertion; scripts/validate_evidence_load.py additive completion bins and proof metrics.
-Final documentation commit: this measured report; SHA supplied in response. No additional runtime change.

Artifacts: data/early_edge/writer-boundaries-20261024/ contains baseline/native reports, progress/process-status/driver/gate receipts, actual databases, trace/probe source and results, assessment.json, cleanup/security/full-test evidence and final hash inventories. All are synthetic, non-enrolling and independent of the retired cohort. No push.

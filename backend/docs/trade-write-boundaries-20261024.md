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

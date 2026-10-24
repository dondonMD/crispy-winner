# Failed pre-cohort readiness experiment: root causes and remediation plan

Investigation date: 2026-10-24. **PRE_COHORT_READY remains NO.** This is an investigation and proposed plan, not an implementation or a new experiment.

## Preservation and scope

Frozen research commit: `76d22105d2bb2f6e6c3c1d2f3ff9df5881d238ba`. Investigation branch: `remediation/early-edge-evidence-readiness`, created at that commit. Production source, configuration, tests, thresholds and decoders are unchanged. No cohort, restart, database rotation, limit increase, commit or push was performed for this investigation.

Read the recovered `data/early_edge/pre-cohort-readiness-20261024.md` and JSON, original `throughput-6h-20261023.json`, console/checkpoint and frozen identity/plan. Original files remain unchanged. Their SHA256 inventory was captured locally in `/tmp/crispy-readiness-investigation-evidence-hashes.json`. The original temporary database was removed by the diagnostic's normal cleanup; table-level byte attribution and event-by-event replay are consequently unavailable. The retired prospective database is not an investigation workspace and was not opened for mutation.

The original process exited normally, exit 0, with clean shutdown; it is not running. A successful process exit did not mean a successful evidence experiment.

## Recorded failure and timeline

The configured 21,600-second monotonic timer occupied 44,129.33 wall seconds: 2026-10-23 10:42:26.889901Z–22:57:56.219002Z. A 22,534.32-second sampled gap occurred from 12:35:02.822255Z to 18:50:37.144085Z. Its physical cause is unproven. Suspend or a clock discontinuity is plausible, not established. This was not six uninterrupted hours of observation.

| Stage | Recorded result |
|---|---:|
| Launches decoded / candidates admitted | 10,181 / 3,091 |
| Queue-accepted / fully processed trades | 165,623 / 86,913 |
| Trades becoming stale while queued | 72,903 |
| Trade / non-trade queue drops | 5,162 / 44 |
| Global / token-local continuity resets | 5,508 / 81,213 |
| Sampled CURRENT / maximum sampled clean coverage | 0 / 860.80 seconds |
| Qualifying EARLY observations / matched controls | 4 / 0 |
| Primary T+10 availability | 0 of 4 |
| Pump / PumpSwap state quotes successful | 13 of 112 / 6 of 8 |
| Unsupported Pump event layouts | 0 |
| RPC requests / errors / 429s | 13,716 / 15 / 0 |
| WSS reconnects | 99 |
| Storage growth / maximum DB files | 1,028.19 / 1,028.34 MiB |

Storage pressure first reached 70% at 19:01:53.505271Z and full at 19:21:36.942523Z. Full storage was sampled in 430 of 681 quality records. Mean/peak RSS was 278.54/306.90 MiB; RAM pressure was not flagged. Empty final queues and low late CPU partly reflect censorship, not restored full acquisition.

## Ranked findings

### 1. Confirmed: downstream loss repeatedly destroys the evidence window

`RadarEngine.submit/process/run_loop` (`backend/app/engine.py:231,307,1002`), `PriorityBuffer.put/drain` (`backend/app/domain.py:97,148`) and `invalidate_token_trade_coverage` (`engine.py:1239`) form the main failure chain:

1. Accepted means admitted to the queue, not applied to features or persisted.
2. The queue reaches its 1,000-event bound. Selected batches are removed before processing. Ordinary events older than 20 seconds are rejected.
3. Stale tracked trades invalidate that token's continuity. The run recorded **72,592 stale-triggered local resets**, overwhelmingly more than decoder failures.
4. Queue loss, event-buffer loss and recovery loss add further gaps. These resets correctly prevent claims of complete flow.

Local reset breakdown: 72,592 stale; 4,282 queue; 4,254 rolling-buffer; 73 recovery; 12 decode. Totals are 81,213. Do not add these to dropped-event counts as independent observations: they describe overlapping effects at different stages.

`trade_status`, `refresh_trade_continuity` and `trade_coverage_seconds` (`engine.py:1265–1306`) require the conjunction of connected coverage, no overlapping pending recovery, clean 180 seconds, at least three samples, consistent known units and a fresh last trade. Aggregate trade volume or maximum clean duration alone cannot satisfy this conjunction. CURRENT was sampled as zero; no exhaustive transition ledger exists to prove no brief CURRENT ever occurred between samples.

### 2. Confirmed mechanisms; contribution not profiled: expensive consumer path and pauses

Each event synchronously runs analysis over six windows, scores and existing decisions, reserves a SQLite event identity, writes event JSON, and invokes intelligence/observational hooks. `DB.reserve_event/add` (`backend/app/db.py`) use separate transactions. `OpportunityResearch.observe/save_pending` (`backend/app/opportunity_research.py:208,31`) rewrites pending JSON during observations. Intelligence refresh also projects candidates; research hooks add projections and snapshots. These are real hot-path operations, but the saved run lacks stage timings to assign a CPU or latency percentage to each.

`run_loop` also **awaits** threaded retrospective evaluation and retention every minute. The event loop can run producers during these awaits, but this consumer does not drain its queue until they finish. A slow evaluator/maintenance task is therefore a possible burst amplifier. Original durations are unavailable.

Additional correctness hazards identified from code, not proven occurrences in this run:

- One `now` is captured before a 100-event batch and supplied to every `process`. Actual application freshness can be older than the age check indicates. Fix with application-time validation, never a larger freshness limit.
- An exception escapes the per-event loop into the outer handler after the entire selected batch was removed. Remaining selected events can be lost without a dedicated terminal counter or gap for each affected mint. No retained exception ledger establishes how much this contributed.
- Priority selection can repeatedly defer lower-priority trades. Measure age by priority and destination before selecting a fairness correction.

### 3. Confirmed: recovery failures cause global resets independently of market strength

`TruncationRecovery.submit/step/resolve/overlaps` (`backend/app/truncation.py`) recorded 16,839 submitted truncations, 14,565 accepted/completed, 2,274 overflow, 3,130 expiry and four unsupported classifications. “Completed” includes unresolved results.

Recovery global gaps reconcile exactly: **2,274 + 3,130 + 4 = 5,408**. Total globals: **5,408 recovery + 99 transport + 1 shutdown = 5,508**. Pending unknown truncations also block CURRENT before resolution. Keep this safety behavior.

The two-worker, 32-pending, 45-second lifetime and three-attempt bounds remain unchanged. The shared provider semaphore/start limiter/cooldown remains authoritative (`providers.py:25–149`). Zero 429s does not prove unused RPC capacity: local limiter waits, event-loop delay, network service and competing monitoring requests all consume the recovery lifetime. Some 2,060 accepted recoveries expired with zero attempts. The long gap is a plausible contributor; the retained counters do not attribute every expiry to it. Legacy recovery HTTP counters incorrectly show zero despite recorded requests; use shared RPC and backlog counters, not those zeros.

### 4. Confirmed: storage policy cannot sustain this workload within its byte budget

`ResourceMonitor.sample` (`resources.py:13`), `DB.size/retention` (`db.py`), and `engine.admit/process/checkpoint` gate on approximately 1 GiB of **database + WAL + SHM**. Full storage rejects new admissions and skips ordinary persistence, collector work and checkpoints. Coverage statistics after this point are infrastructure-censored.

Retention is time-based: raw events/identities 24 hours, snapshots 30 days, signals/outcomes 90 days. This run's new records were too young to reclaim under those rules. Deleting SQLite rows would not necessarily shrink the allocated database file either. There is no reserved essential-evidence byte budget or pressure-tiered raw-data policy.

`process` persists a `context_before.degraded` map containing every degraded candidate on each event (`engine.py:352–363,507`). This is confirmed repeated cross-candidate metadata. A bounded synthetic serialization measured 16 bytes at zero candidates, 1,364 at 25 and 13,514 at 250. At high degradation it can amplify storage and writes substantially. This is not a measurement of original table sizes: the original DB no longer exists. Full canonical event fields, repeated features/scores, retrospective signals and pending updates are further candidates for amplification.

### 5. Confirmed: quote sampler and deadline scheduler do not measure sustained availability reliably

`scripts/early_edge_diagnostic.py:147–245` computes a 2,160-second round interval but enforces only the **global** 120-record cap, not a per-round quota. Temporary failures consume an identity's remaining round attempts. Python-only successful receipts have `quote_valid`, but bounded mint selection checks `r.get('match')`, a reference-SDK result. Its intended two-mint restriction therefore fails in normal Python mode; this mismatch was reproduced offline.

All 19 successful quotes were acquired in the first 0.903–159.843 seconds. The remaining 101 sampler observations were unavailable. This does **not** prove quoting became permanently impossible at 160 seconds: the finite sampler is unevenly scheduled and eventually stops. Per-attempt timestamps needed to locate its final exhaustion are missing.

More importantly, the diagnostic awaits ordinary quote sampling in the same coroutine that services manual-entry deadlines and samples CURRENT. Failed sampler calls took up to 34.08 seconds (mean 17.07), longer than the declared T+10 acquisition window. They can prevent timely entry acquisition and delay evidence sampling even while engine tasks continue.

`OperationalTelemetry.probe_entries` (`early_edge_telemetry.py:174`) handles the first due signal then breaks; it does not reject already-expired attempts before HTTP. This introduces head-of-line delay. It catches all exceptions into broad QUOTE/PROVIDER counters and then labels overdue attempts provider gaps. `finish_signal` also fills missing availability as provider gap. Consequently the four failures are **not four proven network outages**, nor economic-zero outcomes.

The oracle rejects account acquisition exceeding five seconds (`early_edge_quotes.py:371`). Recorded delay rejections are 84; slot/shape rejections are both zero. Sampler provider-gap counts plus seven entry exceptions numerically match 84, supporting acquisition delay as a likely entry blocker, but typed per-entry receipts were not preserved to prove that one-to-one attribution. Quote math failure is not established. Keep all slot, freshness, latency and full-account validation rules.

## Other necessary contributors and limitations

- **Units:** 104,431 accepted observations had unknown units versus 61,145 SOL and 47 USDC. `discovery.py` resolves canonical event/account quote semantics conservatively. `features.py` invalidates windows containing unknown or inconsistent currency. Correctly so. Missing reason buckets prevent separating unsupported quote assets, not-yet-verified account context, conflicts and amount/semantic failures. Do not drop unknown trades to manufacture a valid window.
- **Rolling capacity:** `Token.events` is bounded at 500 and contains market observations as well as trades. `process` detects eviction of a trade still inside 180 seconds and gaps continuity. Above approximately 500/180 = 2.78 events/second for one token, this representation cannot retain a complete window. The 4,254 buffer resets prove this occurred; simply enlarging the global queue does not address it.
- **Lifecycle/churn:** 2,017 inactive expirations and 1,049 capacity evictions shorten observation opportunities. `admit`, `candidate_expiry_deadline` and `expire_inactive_candidates` (`engine.py:283,709,755`) are implicated, not proven defective. Never retain an evicted token's apparent continuous coverage across re-admission.
- **Fairness:** 1,512 eligible pre-grad tokens, only 262 adequately observed. Last-observed fairness rows retain 250 tokens, not a full census. A one-observation zero maximum gap is not continuity; row counters reporting zero provider-unavailable time do not cover the long absence of observations.
- **Controls:** all four qualifying EARLY observations were unmatched under the frozen contemporaneous same quote/progress/age/security readiness rules. There is no valid comparative result. These signals were not CURRENT-qualified and their buyer counts are not proof of complete evidence. Do not broaden matching or tune thresholds to produce controls.
- **USD references:** SOL/USD was fresh in 96.51% and USDC/USD in 55.91% of operational samples. A last-trade timestamp can become stale despite a working HTTP service. Keep freshness; assess a separately documented timestamped reference policy rather than assuming USD parity or using future prices.
- **Long gap:** queued events can become stale; recovery lifetime expires; wall-clock windows advance while no observations are acquired. The maximum queue age was 22,581.76 seconds. The gap explains extreme maxima but cannot explain away all earlier/later losses. No host suspend journal was preserved. Do not backfill or call the gap zero flow.

## Accepted versus processed: what is and is not reconciled

165,623 accepted minus 86,913 processed leaves **78,710** accepted trades without a terminal processed count. The stale local reset counter accounts for 72,592 processing rejections, leaving 6,118 before accounting for evictions, untracked/lifecycle returns, exceptions and other causes. The 72,903 stale-while-queued count is a different predicate: fresh on queue arrival but stale at drain. It can include events that later return before the stale-processing branch. Do not subtract both.

Queue drops include rejected incoming events and evicted previously accepted events. Offline testing confirmed this distinction. Thus subtracting all 5,162 from accepted is invalid. The 44 “critical” drops are the implementation's non-trade bucket, not proof of 44 lost migrations or security results. There is no retained mutually exclusive terminal ledger sufficient to reconcile the remaining difference exactly. This accounting defect must be fixed before treating accepted counts as evidence throughput.

## Prioritized remediation proposal — approval and implementation still pending

| Priority | Targeted change | Regression and measurable acceptance |
|---|---|---|
| P0 | Add a bounded, durable run-quality/gap ledger, clock-discontinuity detection, exhaustive per-event terminal reasons, CURRENT rejection reason vectors and actual application timestamps. Preserve per-stage queue/limiter/HTTP/analysis/SQL timings and storage-category growth. | Synthetic pause, forward/back clock change, batch exception and shutdown tests. Every accepted event reconciles to processed, explicitly rejected, evicted or pending; no unexplained loss. Every censored interval appears in reports. Stale-at-application trades remain rejected at 20 seconds. |
| P1 | Remove avoidable consumer work: batch bounded SQLite transactions, reference immutable shared context rather than repeat all-token maps, avoid repeated projections/config parsing, and move periodic retrospective evaluation off the draining critical path. Profile before choosing incremental feature optimizations. | Exact feature/decision/snapshot parity against frozen fixtures; bounded overload replay with burst envelopes from original samples. No critical loss or unaccounted batch loss; p99 queue-to-application delay below 5 seconds at declared supported load, no stale-while-queued at that load. Explicit loss/gaps above capacity. |
| P1 | Design byte-budgeted evidence storage under the existing guard: protected essential receipts, manifests, signals, all measured/negative/unavailable outcomes and gap ledger; compact deduplicated raw provenance with explicit retention/coverage metadata; incremental bounded reclamation and WAL accounting. | Accelerated byte-budget soak: essential records survive pressure/restart, total allocated DB/WAL/SHM stays within configured ceiling with a declared safety reserve; no silent sampling of complete evidence, no deletion of paper history/versions/cohort records. Report projected bytes/hour by category before a long run. Do not raise the guard or rely on hot-loop VACUUM. |
| P1 | Separate bounded deadline-aware entry acquisition from general diagnostics. Enforce per-round sampler quotas and correct Python success predicate; reject expired work before HTTP; schedule primary deadlines fairly; keep typed unavailable causes and receipt timestamps. Share existing provider protections. | Fake-clock contention tests at T+10/T+20 boundaries, slow sampler, multiple simultaneous signals, reference failures and expired work. No pre-boundary fills or future substitution. Adequate observations spread across rounds, not exhausted at startup; synthetic healthy provider makes all scheduled primary probes inside their window. |
| P2 | Measure recovery provider wait/network/loop delay and monitoring fairness before changing scheduling. Keep 2 workers/32 pending/45 seconds/3 attempts. Reduce upstream loop/storage stalls first. | Burst replay with monitoring/security progress and identical fail-closed overflow/expiry semantics. No unexplained recovery counters; supported-load completion inside 45 seconds, all residual loss attributed. Four unsupported recovery subtypes classified without guessing. |
| P2 | Preserve complete feature semantics with bounded compact per-token window state, including exact wallet dependence and units, instead of relying on a 500-event mixed history for complete high-rate windows. | Golden equivalence to retained full-window reference, busy-token replay exceeding 500 events/180s, bounded memory, true loss still gaps. No approximation silently advertised as complete. |
| P2 | Add fixed unit-failure categories, admission/eviction/readiness exposure ledger and risk-set exclusion reasons. | Mixed/unknown units never CURRENT; eligible ready non-EARLY controls matched deterministically without changing rules; later EARLY crossover preserves original pairing. Full-census aggregate counters survive bounded row eviction. |

Validation sequence after a separately reviewed implementation: offline regressions and bounded replay first; full quality/security suite; only then propose a short, non-enrolling operational verification with frozen source/config and explicit stop conditions. A further six-hour run requires separate authorization. No real cohort can be created merely because counters improve.

The readiness bar remains canonical accepted trades, genuinely CURRENT evidence under unchanged 180-second/20-second rules, coherent timely quotes, auditable losses and viable observation coverage. EARLY frequency is not a tuning target. No profitability, expectancy or causal conclusion follows from this failed experiment.

## Investigation verification

Existing targeted suites were rerun for early-edge methodology, telemetry and truncation recovery: **234 passed, 1 skipped in 19.40 seconds**. The skipped test is opt-in. Whitespace validation passed. Seven original evidence-file hashes were verified unchanged after investigation. Two additional bounded offline assertions reproduced queue rejection-versus-eviction accounting and the Python-only sampler success-key mismatch. Synthetic serialization quantified only the repeated degraded-map footprint. No live provider request or real cohort was required. Full validation is required for future code changes; this task changes documentation only.

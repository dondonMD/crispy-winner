# Dashboard/SSE performance investigation — 2026-10-26

**PRE_COHORT_READY=NO. Phase 4 unauthorized.** A redundant HTTP conversion was reproduced and removed. Synchronous snapshot/SSE blocking and per-viewer duplication are reproduced; their contribution to previous live trade losses and the reported9.905s first-byte latency remains unproven. No live request, provider, server, study, original database operation, staging, commit or push was performed in this task.

## Source and isolation

Baseline `d5bf8edf09f993b9006aeccef2e5295e0566294e`, branch `remediation/early-edge-evidence-readiness`. Six unrelated files and the preceding investigation report remain unchanged. Frozen pilot and qualification artifacts are covered by `/tmp/dashboard-preservation.json`.

Private reproducible probe: `data/early_edge/dashboard-profile-20261026/probe.py`. The final controlled results are in `baseline-r2/` and `optimized-r2/`, each containing component/HTTP JSON and cProfile text. The probe loads the published baseline main.py directly from that complete SHA for the legacy HTTP application, and the working-tree main.py for the candidate. No lifespan is entered: an isolated offline RadarEngine is assigned to an in-process ASGI application. No sockets or provider calls are involved.

Fixture:250 candidates,25 deep,200 timestamped synthetic SOL trades per token, bounded500-event token deques, verified synthetic security/curve progression, one initial intelligence refresh, no real holdings or approved evidence. No trades are attributed to live market evidence. Fixed synthetic wall time1800000000, real monotonic/performance/CPU clocks. Nine component samples, five HTTP and scheduling samples per condition; one cProfile snapshot. Timers wrap the same component boundaries in both variants. Initialization and cProfile are outside the latency samples. Timed results include Python wrapper overhead and normal GC/preemption; these are finite microbenchmarks, not sustained throughput acceptance.

To reproduce with new output names, from the repository root use `DASHBOARD_VARIANT=baseline-r3 .venv/bin/python data/early_edge/dashboard-profile-20261026/probe.py`, then `DASHBOARD_VARIANT=optimized-r3 ...` sequentially, with no competing tests. Output paths must not already exist. Baseline behavior is pinned to the SHA above. This private tool is not application code or a new monitoring framework.

## Measurements

Milliseconds; p95 equals the maximum for these small5/9-sample sets. Do not add quantiles or nested timers.

| Whole-frame operation | Baseline p50 / p95 / max | Candidate p50 / p95 / max |
|---|---:|---:|
| Engine.snapshot wall |52.239 /79.616 /79.616|41.548 /51.273 /51.273|
| JSON encoding wall |56.168 /80.775 /80.775|46.875 /74.097 /74.097|
| SSE string framing wall |6.566 /16.706 /16.706|6.488 /14.384 /14.384|
| Snapshot+JSON+framing process CPU |121.171 /157.309 /157.309|97.368 /142.291 /142.291|
| In-process HTTP GET wall |427.512 /521.851 /521.851|116.798 /142.953 /142.953|
| Scheduled task delay,1 consumer |84.784 /90.141 /90.141|110.749 /145.098 /145.098|
| Scheduled task delay,3 consumers |264.810 /338.908 /338.908|249.337 /254.998 /254.998|

The engine snapshot implementation was not optimized; its differing timings are run variation, not a claimed code improvement. HTTP median fell approximately72.7%. FastAPI's legacy recursive `jsonable_encoder` conversion alone measured309.999ms median/379.972ms maximum; it is unnecessary for this already JSON-native payload. A separate earlier unfrozen-clock probe measured412ms HTTP median and302ms recursive conversion. The corrected controlled candidate does not execute that conversion at all, verified by fault injection in tests. The legacy conversion is not part of SSE, so this HTTP saving must not be attributed to SSE.

SSE bytes including framing: **3,052,038 ->2,873,559** (~5.85% less). HTTP bytes:2,871,295 ->2,873,551 in the independent processes; legacy HTTP already used compact separators. The small cross-process size difference is not evidence of semantic loss: same-input JSON-value equivalence is tested independently. Synthetic output approximates, but is not a copy of, the live3,357,430-byte response. Final sampled process RSS229.625 ->219.953MiB; this is an end sample, not peak memory or proof of a memory improvement. No long-duration leak test was run.

Component wall timings below are **per call**, baseline corrected fixture.35 snapshots include the HTTP/profile/scheduling phases, hence8,750 token/companion calls and175 provider-health calls. Companion is nested inside token_view; never sum their totals. The profile reports exclusive self time separately.

| Component | p50 / p95 / max ms |
|---|---:|
| Token view including companion |.07453 /.24573 /9.05004|
| Companion assessment |.03955 /.12895 /8.38827|
| Opportunity list assembly/ranking |2.40135 /5.14767 /17.09210|
| Accounting snapshot |.06822 /.30584 /.52193|
| Persistence proof snapshot |.01619 /.02594 /.06240|
| Provider-health formatting |.00413 /.02678 /.06675|
| Manual view |.00750 /.01395 /.01511|
| Handoff diagnostic view |.03227 /.11848 /.36103|

In the cProfile sample, companion self time~11ms, repeated trade_status self time~10ms, token_view self time~5ms, Pydantic serialization~4ms and validation~4ms. Those are profiled call totals, not percentile measurements. Snapshot reads existing opportunity projections; it does not invoke Intelligence.refresh or research collection. JSON serialization covers all of these projections afterward. SQLAlchemy cursor instrumentation recorded **zero SQL statements** during sampled snapshot/HTTP generation. Existing handoff telemetry may sample its bounded diagnostic state; this unchanged behavior is not a financial/research write. Core event/paper/approval state and stored research projections are regression-checked.

### Retained failures and instrumentation limitations

The first private fixture failed validation because its synthetic MarketEvent lacked event_id; `/tmp/dashboard-baseline.log` preserves the failure. No live evidence was created. A subsequent fixed-clock pair used Mock(return_value=...), whose per-call bookkeeping inflated CPU/RSS and timings. Both results remain under `baseline/` and `optimized/`; they are **not** the corrected measurements above. The corrected pair uses a plain fixed-clock lambda, with no retained mock-call history. Original exploratory measurements remain in the private root. This correction affected the test instrument only, not production.

The final one-consumer scheduling median/max worsened despite smaller JSON and lower sampled frame CPU. Three-consumer results improved modestly; this is not consistent proof of an SSE scheduling-latency fix. All results are retained. No earlier failed load result has been replaced with this microbenchmark. HTTP CPU was not independently sampled; the whole-frame CPU row excludes the HTTP-only recursive conversion. No inference about OS scheduling or disk latency is made from that row.

## Confirmed mechanism and remaining hypotheses

`/api/events` independently calls snapshot and dumps JSON per connected EventSource, then sleeps2s **after** sending. There is no shared publisher/cache. Multiple viewers cause linear repeated work; callbacks contain no await until after the synchronous construction/encoding. This blocks the event loop and the small timer probe reproduces it. That probe has no competing event processing; it measures publication-induced scheduling delay, not live queue latency.

The frontend creates one EventSource per mounted App; changing notification preference closes/reopens it and cleanup closes it on unmount. More tabs/windows mean more producers on the backend. `/api/dashboard` independently constructs another full view. Token-detail polling is a different endpoint, not removed. The2s SSE delay is not2Hz: expensive construction and network backpressure extend each client's interval. Slow consumers await the existing StreamingResponse send; no background accumulation queue was introduced.

The reported9.905s first-byte wait can include waiting behind other event-loop work, snapshot construction, conversion, HTTP middleware and network scheduling. `/api/health` returns a small liveness object, so its1.52s measured response is consistent with waiting/load beyond payload size, but cannot identify the responsible task. Neither the nine-second stall nor causation of prior dropped/stale trades was reproduced here. Prior recovery/global gaps and500-event active-window losses remain independent blockers; this serialization fix cannot erase them.

## Small correction and rejected larger changes

`backend/app/main.py` now provides `dashboard_json(engine)`: take exactly one fresh snapshot on the engine-owner thread, strictly encode JSON with allow_nan=False and compact separators. HTTP returns an explicit application/json Response, avoiding FastAPI's second recursive conversion. SSE uses the same strict encoder with its original data framing, disconnect check and2s cadence. This introduces no new queue, task, thread, provider call, retained snapshot, model calculation or database transaction.

The snapshot payload values, timestamp, predicates, classification projections and source provenance are unchanged. Native JSON string-key conversion is preserved. Nonfinite serialization failures still fail, and original snapshot exceptions propagate. Security/CSP middleware remains active. There is no historical outcome rewriting or field redaction masquerading as performance work.

A shared cached publication could reduce per-viewer work further, but arbitrary2s reuse would cross trade/security/price expiry or gap boundaries. The existing UI does not independently revalidate every core status, so adding only a generation timestamp would not make caching safe. Full owner-thread invalidation/expiry handling and detached immutable publication need a separate design/proof. Passing mutable engine/SQLite-backed dictionaries to a worker is not an acceptable shortcut. Cooperative generation also needs an explicit as-of/consistency contract. Neither larger change is implemented merely on a projected speedup. No cache lifetime or freshness grace was added.

CPU and buffers remain proportional to existing payload and viewer count. This correction does **not** impose a new global viewer/output cap or prove safe operation with arbitrarily many viewers. Multi-megabyte payloads and synchronous per-viewer work remain limitations.

## Validation

- Broad applicable backend set: **438 passed in65.17s, normal exit**, including dashboard, companion, V2.1, approval boundary, pilot/qualification, manual workflow, shutdown, transport, queue accounting, buffers, gap scoping, truncation and canonical units.
- Final expanded dashboard tests: **7 passed in5.34s, normal exit** after adding explicit DEMO equivalence and viewer-call assertions; overlaps the broad set and is not additive. The first DEMO expectation incorrectly compared a Python int-keyed diagnostic mapping with JSON string keys; the corrected expectation round-trips the legacy JSON encoding. That fixture-only failure is preserved in `/tmp/dashboard-final-tests.log`.
- Frontend **62 tests/7 files passed**, including App EventSource refreshes, navigation, expiry, disconnection and scroll/filter retention. No frontend source changed. TypeScript noEmit and production Vite build passed37 modules.
- Ruff and mypy passed (49 backend application source files); secret/whitespace/preservation results are checked at completion. No dependency changes or new audit claims.

Tests prove same JSON values in OBSERVE/DEMO, single snapshot per request/frame, no recursive conversion on HTTP, strict nonfinite/error behavior, independent viewers/latest tokens, disconnect/cancellation cleanup, unchanged2s cadence, actual queued event processing without replay, reconciled/persisted dispositions and invalidation of stale/coverage-lost evidence. Snapshot reads do not change paper, approval, feature, decision, accounting or research-projection state. Synthetic results do not establish live signal quality or profitability.

## Delivery and recommendation

Intended changes only: `backend/app/main.py`, `backend/tests/test_dashboard_snapshot.py`, this report. The private probe/results stay ignored. The earlier continuity report and all six unrelated files remain untouched. If an unrelated untracked report would block a future source preflight, archive it privately with its hash through a separately reviewed file move; do not weaken the source guard or include it accidentally in publication. No staging is performed here.

**Recommend reviewing the narrow HTTP conversion fix. Do not treat it as a complete SSE/continuity remedy or authorize the prospective study from these results.** Before deciding on a shared publication architecture, measure actual owner-loop snapshot/serialization/SSE phase durations and viewer count alongside queue/recovery/heartbeat diagnostics in a separately approved bounded operational validation. Use a new isolated database with headroom, enough time to assess180s continuity, and preserve every loss/censored observation. No live qualification or long study ran in this task. PRE_COHORT_READY=NO.

Final checks: all21 preservation hashes matched; source/document secret scan passed291 files; Ruff/mypy and tracked whitespace checks passed. New-document trailing whitespace was checked separately. No source edits occurred during the benchmark runs; only test/document updates followed them.

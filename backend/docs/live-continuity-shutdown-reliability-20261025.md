# Live continuity and shutdown reliability — 2026-10-25

**PRE_COHORT_READY=NO. Phase 4 unauthorized.** Offline investigation only; no provider connection, observation, cohort or transaction started. Serial processing, strict decoding, SQLite settings, evidence gates and capacity limits remain unchanged.

## Evidence and preservation

Baseline: `9e1b4e9f9d059684b23d103ac66a1d4dbe60bc2f`, branch `remediation/early-edge-evidence-readiness`. Examined the original `live-buffer-verification-20261025-183328` snapshots and server log. The seven snapshots cover elapsed 30–210 seconds, not a final 240-second shutdown record. Original receipts were not rewritten.

Hashed the original database, WAL, SHM, maintenance backup files, observation files and five unrelated worktree files before analysis. Copied the quiescent database and sidecars into `/tmp`; verified unchanged source hashes after copying. SQLite inspection used only this private copy, opened read-only. A final source hash comparison verifies preservation. Local hashes and sanitized operational receipt are under ignored `data/early_edge/continuity-shutdown-20261025/`. The earlier seven frozen evidence artifacts are independently checked against their preserved hashes. No historical cohort was opened for writing.

## Confirmed findings

### HTTP shutdown can prevent engine shutdown

The log ends at **“Waiting for connections to close”**, after “Shutting down.” It never records application shutdown beginning. Installed Uvicorn **0.54.0**, `Server.shutdown()`, first stops accepting connections, requests connection shutdown, and waits for active connections/tasks. Only afterward does it send the ASGI lifespan shutdown event. Its default `timeout_graceful_shutdown=None` allows this wait to be indefinite.

`backend/app/main.py` exposes a persistent `/api/events` StreamingResponse. A connected dashboard can therefore keep an HTTP response active while Uvicorn waits to enter lifespan cleanup. An offline regression against Uvicorn's real shutdown method demonstrates the unbounded wait and lack of lifespan shutdown with a persistent connection. The log does **not** identify the particular outstanding request; SSE is a supported explanation, not proof of the exact historical connection.

The copied database's latest session operational receipt is **RUNNING**, without checkpoint-complete or final STOPPED fields. It records five global resets and 80 local stale resets, exceeding the dashboard's last four/78. This proves the dashboard was not the final accounting cut and supports a pre-lifespan stall. At that durable cut, 198 accepted trades reconcile as 118 processed/persisted plus 80 stale; all show zero pending/in-processing at that particular cut. Creates reconcile as 21 processed plus five stale, and 200 curve observations are processed. These are last-receipt counts, not a certified final-session total. It does not prove what every task did after the last durable receipt. SIGKILL cannot be represented as a clean shutdown.

**Correction:** the documented `python -m backend.app.main` launcher now gives HTTP response draining a five-second grace period. Uvicorn then cancels persistent HTTP handlers and enters the existing lifespan shutdown. This is **not** an engine cleanup timeout: provider-task cancellation, queued-event terminal accounting, unresolved recovery receipts, collector closure, checkpoint and database disposal still execute. No accepted evidence is declared processed merely because an HTTP response was cancelled. External `uvicorn backend.app.main:app` invocations must explicitly specify `--timeout-graceful-shutdown 5`; launcher configuration does not override external server configuration.

### A client-close failure bypassed subsequent cleanup

`RadarEngine.stop()` previously awaited RPC close and DEX close sequentially before checkpoint/terminal receipt/disposal. An injected RPC-close OSError reproduced DEX not being closed, database disposal not being reached and absence of the final receipt.

**Correction:** attempt both closes, preserve their exceptions, write the existing final receipt and dispose the database, then re-raise the first close failure. Only exception class names appear in the added `provider_close_failures` receipt field. A checkpoint failure retains precedence and its existing receipt semantics. `checkpoint_complete` describes checkpoint success, not a claim that failed client closure succeeded. Historical rows are unchanged. This additional defect is proven offline; no saved evidence establishes that it caused the historical hang.

## WebSocket continuity

| Recorded interval | Confirmed observation |
|---|---|
| 30–60 seconds | Global resets increase 0→1; recovery-global remains zero |
| 90–120 seconds | Global resets 1→2; recovery-global remains zero |
| 120–150 seconds | Global resets 2→3; recovery-global 0→1 |
| 180–210 seconds | Global resets 3→4; recovery-global remains one |
| Later durable receipt | Global resets five; local stale resets 80 |

These are sampling intervals, **not exact disconnect times**. The largest sampled clean value is 32.912 seconds, not a measured maximum connection lifetime. All seven snapshots show CURRENT=0 and PARTIAL=0. No sampled clean interval establishes 180 seconds.

`OnchainPumpDiscovery.run()` still uses confirmed subscription ACK validation, 20-second ping interval/timeout, bounded receive buffering, 90-second receive timeout and existing reconnect backoff. Transport exceptions invalidate global coverage; malformed/unattributable decoded events can also invalidate it. Cancellation separately records intentional shutdown and ends coverage. Existing passive diagnostics distinguish local ping-timeout closure from received close codes, without extra pings or private library internals.

The saved snapshots omit close categories, detailed connection transitions, passive event-loop lag and RTT distributions. The latest operational receipt contains accounting/continuity/storage, **not those transport fields**. Low sampled CPU/RSS and queue depth do not rule out short event-loop stalls, network delay, receive backpressure or missing pong. There is no evidence sufficient to assign these resets to Helius, a specific timeout, subscription rejection, or a client starvation defect. No transport code or heartbeat setting was changed.

`TruncationRecovery.resolve()` intentionally avoids a gap for `UNTRACKED_CONFIRMED`; the 103 such completions cannot be counted as 103 resets. Tracked-affected classifications invalidate only affected tokens; unavailable, malformed and other unresolved identities remain global gaps, as does overflow. The single recovery-global gap is genuine recorded missing coverage; its exact classification/signature cannot be recovered from these aggregate snapshots. It is not suppressed.

`RadarEngine.process()` independently invalidates stale tracked trade evidence when source event time is outside the existing freshness bound. Zero **queued-stale** trades is not proof that source timestamps were fresh when acquired. The 78/80 stale resets cannot safely be blamed on queue delay. Original timestamps/transport timelines are insufficient here to isolate upstream event age versus recovery age. Zero buffer evictions and queue peak 26 rule out buffer loss and queue saturation as recorded causes in this run. No resource-pressure condition was recorded. None of this certifies missing units, sample counts or per-token continuity.

## Offline regression evidence

New `backend/tests/test_shutdown_reliability.py` tests:

1. Launcher supplies the five-second HTTP drain bound without starting a server.
2. Real Uvicorn shutdown cancels an indefinitely active response and reaches lifespan cleanup.
3. Default unbounded drain reproduces waiting without reaching lifespan.
4. Provider-close exception still closes the other client, persists a sanitized failure receipt and disposes SQLite; exception remains caller-visible.
5. Cancellation of blocked provider work finishes its task; three queued trades become explicit `shutdown_unprocessed` terminal outcomes, reconciliation holds, checkpoint succeeds and a reopened isolated SQLite database passes `quick_check`.

Before correction, the launcher contract and cleanup-error regressions failed. The initial test scaffold also needed Uvicorn's `servers` initialization; that test setup error was corrected before interpreting shutdown behavior.

Validation:

- Initial focused transport/checkpoint/passive/shutdown selection: **64 passed**.
- Expanded selection: **78 passed, 1 failed**. The failure is the existing `test_observer_batch_reuses_exact_ranking_without_changing_selection` call-count assertion (two versus one).
- Exported untouched baseline HEAD into `/tmp` and reproduced that identical failure: **1 failed, 9 deselected**. Left the unrelated ranking code/test unchanged.
- Final relevant selection excluding that documented baseline failure: **91 passed, 1 deselected**, normal exit, 14.16 seconds. Includes readiness accounting, buffer-loss, transport discontinuity, passive diagnostic and checkpoint rollback coverage.
- Ruff: passed on changed Python files. Mypy: passed on both changed application modules. `git diff --check`: passed. Repository basic secret scan: passed (258 source/document files). Retired database size and mtime also match the preserved baseline.

No full-suite, frontend rebuild, endurance workload or live verification was performed for this bounded lifecycle correction. Synthetic tests are not real market continuity evidence.

## Remaining limitations and next verification

The HTTP drain bound does not forcibly terminate engine cleanup. `stop()` still waits for cancellation-compliant monitor/provider tasks and for any already running evaluator thread to finish. HTTP requests have existing finite timeouts; SQLite busy waiting is configured to five seconds, but query/retention/evaluation computation has no new universal wall-clock deadline. Cancelling an asyncio `to_thread` wrapper cannot kill its worker. No thread-shutdown bypass, forced process exit or abandoned worker was introduced. A truly cancellation-resistant provider or externally blocked filesystem can still delay cleanup; such a defect was not established in the original log. No guarantee of a universal process-exit deadline is claimed.

Provider-close cancellation of the entire shutdown coroutine and repeated forced termination are also outside the ordinary successful single-signal path tested here. Checkpoint/receipt write failures remain failures, not silently successful exits. Database contents cannot reconstruct volatile recovery work lost to the original SIGKILL.

**Further live verification is necessary**, separately authorized, to establish actual transport causes and real signalled-process exit. The minimum next observation should retain the existing sanitized connection-transition/category and passive lag/RTT fields, then exercise a single normal signal while a dashboard SSE client remains connected. Require final durable reconciliation, explicit unresolved-work counts, exit code and no surviving monitor/worker. Preserve any failure. Do not change ping settings or providers without that evidence. A socket-free regression cannot establish network reliability or 180-second CURRENT flow.

Changed files only for this task:

- `backend/app/main.py`
- `backend/app/engine.py`
- `backend/tests/test_shutdown_reliability.py`
- `backend/docs/live-continuity-shutdown-reliability-20261025.md`

All five pre-existing unrelated files are preserved. No staging, commit, push or merge. **Operational observation remains PARTIAL; PRE_COHORT_READY=NO.**

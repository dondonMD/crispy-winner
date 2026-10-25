# Passive WebSocket performance diagnostics — 2026-10-25

**Phase3 PARTIAL. PRE_COHORT_READY=NO. No live observation started.**

## Published baseline and scope

Branch `remediation/early-edge-evidence-readiness`, HEAD `0fe2723` (`test: investigate WebSocket ping timeout mechanisms`). Both the prior investigation report and four offline mechanism tests are committed there; local `origin/remediation/early-edge-evidence-readiness` matches HEAD. This confirms the local publication record, not a new remote network check. Neither published file is overwritten. Main is unchanged.

Only production change is bounded passive instrumentation in [discovery.py](../app/discovery.py). Added [focused tests](../tests/test_passive_websocket_performance.py) and this report. No provider task, new socket, ping, subscription or HTTP request is introduced. Serial scheduling, decode/submit path, recovery, backoff, persistence, evidence eligibility and approval are unchanged. Ping interval/timeout remain20s/20s; clean-flow requirement remains180s. No live run, load replay, cohort or trading operation.

## Measurement contract

Provider health now includes `passive_performance`, exposed by the existing health serializers:

|Measurement|Exact boundary and limitation|
|---|---|
|`json_decode`|Monotonic duration immediately around `json.loads` for each returned receive-loop message, including failed JSON parsing. Excludes ACK parsing, WebSocket frame parsing, decompression and socket wait.|
|`message_processing`|Starts immediately after the existing awaited receive returns; ends after the existing JSON/dispatch/error handling, immediately before next iteration. Includes JSON timing, canonical decode, synchronous callbacks, ignored-message handling and relevant decode-gap handling. Excludes waiting for recv and subsequent transport closure/backoff. This includes JSON time; these two totals MUST NOT be added as exclusive timings. Instrumentation itself has small overhead, and the final histogram write is outside its own measured interval.|
|`event_loop_lag`|One lightweight timer per discovery run, nominal1s. Measures callback start minus scheduled deadline using the running loop's monotonic clock. It observes shared-loop scheduling delay, including periods connecting/backing off. Not a packet-latency measurement or a continuous CPU profile.|
|`completed_rtt_snapshots`|Once per timer callback, reads only documented `ws.latency` on the existing ACKed connection. This is the library's last completed ping/pong RTT. A repeated value is another snapshot, NOT another heartbeat exchange. A different value cannot be assumed to count exactly one exchange.|

The installed library's documented [`latency` property](https://websockets.readthedocs.io/en/16.0/reference/asyncio/client.html#websockets.asyncio.client.ClientConnection.latency) is zero before the first measurement and reflects built-in matching ping/pong completion. Local version16.1.1 was inspected in the preceding investigation; the versioned16.0 documentation describes this supported interface. No override/subclass of keepalive or frame processing is used. No additional ping is sent. Zero, absent, nonfinite, negative, boolean or nonnumeric values are unavailable; they are not invented zero-RTT measurements. Such timer ticks increment `unavailable_rtt_snapshots`. Connection startup, backoff and disconnected periods have no active diagnostic socket. A cached RTT can remain unchanged while a later ping fails: it must never be described as current heartbeat health or fresh market data.

Each duration has fixed noncumulative buckets with upper bounds0.0001/0.001/0.005/0.01/0.05/0.1/0.5/1/5/20 seconds plus overflow, count, total, maximum and last value. Values exactly on a boundary enter that bucket. Bucket count sums equal sample counts. No unbounded raw samples or dynamic metric keys exist.

At most32 recent timer records contain only wall-clock observation timestamp, loop lag and last completed RTT (or null). `recent_evicted` accounts for trimmed history; aggregate distributions persist. Timestamps identify when a value was sampled, NOT when the last pong arrived. Histograms and recent records span reconnects; they are not independent per-connection RTT distributions. The sampler starts only for an enabled discovery run and schedules its next tick from callback completion. A delayed tick records its delay once, without catch-up callback storms. Histograms therefore describe observed ticks and can under-sample prolonged stalls; they do not pretend there was uninterrupted1s coverage.

One standard cancellable `TimerHandle` is retained, not a task or another consumer pipeline. Run cleanup cancels it and marks sampling stopped; an already queued callback cannot reschedule itself. No new await, sleep or yield is added to message processing or reconnect handling.

## Explicitly unavailable

`receive_frame_depth`, `read_pause_duration` and `outstanding_ping_age` are each `UNAVAILABLE_SUPPORTED_INTERFACE`. Actual receive queue depth, time above high-water marks, transport read-pause/resume and the current ping's send/deadline timestamps have no supported public observation interface suitable for this minimal change. No `recv_messages`, frame queues, pending-ping maps, private transport/TLS internals or sensitive frames are inspected. The existing configured max_queue is a setting, not a measured depth.

These diagnostics can reveal long synchronous receive handling or shared event-loop delays and provide last-completed RTT context. They cannot by themselves distinguish a missing provider pong from network/proxy delay or paused reads. They do not establish the causes of earlier failures retrospectively. Future observation still needs separate authorization; unexplained failures must remain unexplained when these public metrics are insufficient.

## Tests and overhead

Deterministic tests cover exact timer and histogram values, boundary inclusivity, invalid-value rejection, fixed metric names,100 samples with32-record history, eviction counts, no timer catch-up, documented-latency-only access, cancellation and queued-callback cleanup, disabled-provider behavior, unchanged subscription options and one connection/request, malformed JSON gap preservation, and no manufactured CURRENT/approval. Real timer cleanup is tested on a synthetic cancelled connection attempt; no task is left behind. Existing discovery/transport tests also exercise backoff, repeated reconnects, application shutdown, strict decoding, continuity reset and credential-safe actual API health responses.

The initial focused run exposed an existing test's replacement of the whole wall/monotonic time module with a small fake. Duration measurement now imports its independent monotonic `perf_counter` directly; the existing fake-clock test and production timing semantics are preserved. No unrelated test was edited. The first static run also required explicit numeric narrowing for mypy; both diagnostics are preserved locally rather than reported as passes.

Final focused suites: **96 passed**, normal exit0 (exact duration in ignored `focused-final2.txt`). Ruff on both changed Python files and mypy42 application sources passed. Secret and final whitespace/preservation checks are recorded below. No dependency change; full frontend/backend performance experiments, builds or online audits were unnecessary for this focused instrumentation change and were not rerun.

Small isolated instrumentation microbenchmark, seven repetitions,20,000 message-instrumentation calls per repetition: median3.166microseconds per call; slowest repetition average5.115microseconds. One-second callback microbenchmark,2,000 callbacks per repetition: median6.023microseconds, slowest repetition average8.631microseconds, including a synthetic timer allocation. These are local average per-call costs, NOT maximum individual latencies, WSL/live overhead or a throughput qualification. They exclude message work, real timer machinery and health serialization. No claims of zero overhead or guaranteed live negligible impact follow.

After140,000 message measurements and14,000 synthetic sampler ticks the numeric health extension serialized to3,895bytes, retaining32 records. Memory is bounded by four fixed histograms,32 record slots and one timer; aggregate counters grow numerically with runtime. No per-message record is retained and no new database writes are added. The future live receipt must still report any observed scheduling/resource effect.

## Preservation and publication

Ignored implementation receipts: `data/early_edge/passive-websocket-20261025/` (initial hashes, focused failures/final results, mypy results, bounded overhead script/result and final preservation receipt). No private URL, credential, signature, token or wallet is stored by these metrics. All five unrelated worktree files, original seven frozen evidence hashes, old private observation receipts and retired DB size/mtime remain preserved. No prior published report is edited.

Git metadata remains read-only. No commit/push or permission bypass attempted. From a writable WSL terminal publish ONLY these three intended files:

```bash
git switch remediation/early-edge-evidence-readiness
git add -- backend/app/discovery.py backend/tests/test_passive_websocket_performance.py backend/docs/passive-websocket-performance-diagnostics-20261025.md
git diff --cached --name-only
git diff --cached --check
git diff --cached
git commit -m "feat: add bounded passive WebSocket timing diagnostics"
git push origin remediation/early-edge-evidence-readiness
```

Verify the staged list contains exactly those three paths; exclude all private receipts and unrelated changes. No main merge or force-push. **No observation follows automatically. Phase3 PARTIAL; PRE_COHORT_READY=NO.**

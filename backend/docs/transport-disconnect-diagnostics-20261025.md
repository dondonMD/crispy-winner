# Transport disconnect diagnostics — 2026-10-25

**PRE_COHORT_READY=NO. No new live observation.** Source93e46c59cf30772e255836372d9adc07260281f5, remediation/early-edge-evidence-readiness. Existing serial architecture and Phase2A approval restrictions remain. This diagnostics-only patch **cannot retrospectively establish the causes of the two earlier WSL disconnects**; their recorded124.79s maximum connection interval and PARTIAL result remain unchanged.

## Original gap and minimal change

[OnchainPumpDiscovery.run](../app/discovery.py) already catches OSError, WebSocketException, TimeoutError and ValueError, invalidates coverage, records connection transitions and retries. It discarded exception type/structured close information. Existing errors also includes decoder failures, so that total cannot distinguish a network outage from truncated-log framing.

Only production file changed: backend/app/discovery.py. The catch tuple, ACK validation predicate, logsSubscribe request, confirmed commitment, event decoding and successful-frame processing are unchanged. Added diagnostics classify the caught exception using its type, current operation phase and limited structured numeric fields. No exception repr/str/args, close-reason text, URI, response headers/body, transaction signature, mint or wallet is retained.

No source/config/schema, queue/candidate limit, eligibility threshold, persistence transaction, provider selection or rate limit changed. Constants remain: connect15s, subscription ACK15s, recv90s, ping20s/ping timeout20s, close5s, max message262,144 bytes/max transport queue16. No new timer, network call, await or retry is added by the diagnostics.

## Diagnostic contract

Health fields exposed through existing provider/dashboard health serialization:

- transport_failure_counts: exactly16 fixed category keys; total counts caught unexpected transport failures.
- transport_shutdowns: separate count of observed application-task cancellation; not an unexpected failure or reconnect.
- transport_diagnostics: at most32 recent failure/cancellation records; transport_diagnostics_limit=32 and transport_diagnostics_evicted account for trimmed history. Aggregate counts are retained after trimming; history is not an unbounded trace.

Each record contains at, kind, fixed category, fixed phase (or other), received_close_code, sent_close_code, errno and http_status. Absent/untrusted numeric values are null: close codes only1000..4999, HTTP status100..599, errno only known OS/DNS constants; booleans and oversized arbitrary integers reject. No new per-code dynamic-key histogram exists. These are process-memory diagnostics, available to existing health/smoke receipts; not an additional durable database writer or crash-safe audit log.

|Category|Classification rule / limit|
|---|---|
|websocket_close|ConnectionClosed with structured received/sent close codes when present. Code1000/1001 still means the always-on subscription ended and retains the existing gap/retry behavior. Missing frames remain null; no invented received1006.|
|ping_timeout|The library's locally sent1011 with exact known keepalive marker and no received close, or sent-before-received ordering. A peer1011 or echoed marker alone is insufficient. The marker is compared but never stored. It identifies the local timeout signal, not why the ping failed.|
|receive_timeout /subscription_timeout /connect_timeout /send_timeout /timeout|TimeoutError plus fixed operation phase. A receive wait timeout is distinguished from local keepalive failure. Generic timeout remains available when context is insufficient.|
|dns_error /connection_error /os_error|Direct socket.gaierror, ConnectionError, or other OSError; only allowlisted errno values retained. Wrapped lower-level failures without structured exposure are not guessed from strings.|
|websocket_handshake /websocket_error|InvalidHandshake, optionally numeric HTTP status, versus other supported WebSocketException. No headers, response text or URL.|
|subscription_rejected|ValueError in the existing trusted-ACK validation step. This includes malformed/mismatching ACK identity/result, not necessarily an explicit provider policy refusal.|
|invalid_subscription_response /value_error|ValueError decoding the ACK, versus other ValueError. No JSON body or error message retained.|
|other_transport|Sanitized fallback in the diagnostic helper. The run-loop catch tuple is NOT broadened to swallow arbitrary programming errors.|
|application_cancelled (separate shutdown kind)|Outer CancelledError is recorded and re-raised. No unexpected-failure count/reconnect is added. It records task cancellation, not proof who requested it. Hard process death cannot guarantee a final diagnostic.|

Implementation compatibility was checked against installed websockets16.1.1: ConnectionClosed exposes rcvd/sent/rcvd_then_sent, and Connection.keepalive uses the recognized local marker. [Official exception reference](https://websockets.readthedocs.io/en/stable/reference/exceptions.html) confirms structured close-frame fields. The current stable documentation renders17.2; that is not the installed dependency or a package upgrade. Local-source hash/version are saved in ignored diagnostics receipts. No decoder inference relies on WebSocket exception text.

## Preserved recovery and evidence behavior

Recording occurs in the existing caught-error path before its existing DISCONNECTED transition, global transport gap, connected-interval closure, health reset and backoff. The exponential delay/jitter, reset after a stable60s connection when a message is received, subscription restoration and dedup behavior are unchanged. Application cancellation retains the existing final global shutdown invalidation and clearing connected/subscriptions; it does not become a transport failure.

Inspected timing/statistics semantics: reconnects increments for a failed attempt before backoff, including failures before a successful connection/ACK. Therefore it is not universally a count of successfully re-established sockets. Existing transport transition timestamps/connected_since are the source of observed connection intervals; errors combines decoder and transport failures. The new fixed failure counts separate these concepts without redefining them. Peer normal close remains coverage loss, not harmless continuity. No independent defect in timing/backoff calculations was demonstrated; none was changed speculatively.

No CURRENT computation,180s requirement,20s freshness, security/risk/approval gate or recovery bound is modified. Diagnostics cannot populate samples, quote units, clean start or eligibility. Prior market evidence remains exactly as recorded.

## Tests and validation

New backend/tests/test_transport_diagnostics.py uses synthetic exceptions/sockets and an isolated offline API/database fixture. No real provider connection or monitor is started.

- Original missing-observability regression preserved:1 failure(.54s), absent record_transport_failure API; after implementation it passes.
- Classification cases cover normal/abnormal/missing close frames, local ping timeout versus peer marker echo, each timed phase, DNS/refused/OS errors, handshake/status429, generic WebSocket/value/fallback errors and invalid subscription responses.
- 500 oversized secret-bearing errors preserve fixed category cardinality,32-record bound and eviction totals. Invalid huge/bool numeric fields are not stored. URL/credential-marker close reasons and exception messages never appear in provider health JSON.
- Synthetic run-path cases prove exactly the existing subscription/transport options, one failure/backoff, one transport gap and final cancellation/shutdown gap. Pure cancellation during connect, ACK and receive gives zero failures/retries. Existing stable-reset test still requires delays[1,2,1,2].
- Actual ASGI health/dashboard responses are checked without lifespan/provider startup; synthetic credentials do not leak. Previously incomplete flow remains non-CURRENT and approved_evidence remains None.

Final focused discovery/transport/trade suite: **79 passed in3.58s, exit0**. Ruff and mypy42 application sources passed. Full-suite/frontend/security results and actual publication outcome follow after completion. This is deterministic observability validation, not evidence of live provider stability or a new CURRENT window.

## Remaining uncertainty and preservation

Earlier disconnect close codes, exception types, network path and keepalive conditions were not captured and cannot be reconstructed by this patch. Even a future captured ping timeout may reflect remote/network/host scheduling effects; it does not independently identify a root cause. Nested/proxy errors can remain generic. A later controlled observation needs separate authorization; none follows automatically.

Initial preservation receipt: data/early_edge/transport-diagnostics-20261025/initial.json. Five unrelated worktree files, frozen original evidence, both prior Phase3 reports and all private WSL receipts are hashed; retired database size/mtime recorded without write access. No historical rows, settings, schemas or records are rewritten. Scope is discovery diagnostics, one focused test file and this report only. **PRE_COHORT_READY=NO.**

## Completed validation and publication

- Full backend with the EXISTING bounded-cleanup diagnostic: **944 passed,1 skipped in167.83s, exit0**. Original Runner.close and actual executor joins remain; this is not a new ordinary-runtime cleanup qualification. The previously documented ordinary invocation timeout was not needlessly repeated. No application shutdown workaround or live observation.
- Frontend39 passed6.06s; TypeScript/production build passed(Vite3.79s), exit0. No frontend edits.
- Full Ruff backend/scripts and mypy42 sources passed; source/document secret scan passed; final preservation/link/whitespace checks passed. No dependency/lock changes or install. Previously DNS-blocked online dependency audits remain unverified, not newly passed.
- AST comparison confirms every existing method/function except initializer/run is unchanged. After removing only phase tags, diagnostic recording and the cancellation-record/rethrow instrumentation, run is AST-identical to its original implementation. This supports unchanged subscription, timeout, backoff, decoding and gap logic; it is not a performance measurement.
- Five original worktree files, both prior Phase3 documents, seven original frozen evidence hashes, all11 private WSL receipt files and retired DB size/mtime remain unchanged. No historical disconnect is reclassified or edited.

Git metadata is confirmed read-only by mount flag and write-access check. No staging/commit/push or bypass was attempted. HEAD remains93e46c59cf30772e255836372d9adc07260281f5. Publish ONLY the three tested files from a writable WSL terminal:

```bash
git switch remediation/early-edge-evidence-readiness
git add -- backend/app/discovery.py backend/tests/test_transport_diagnostics.py backend/docs/transport-disconnect-diagnostics-20261025.md
git diff --cached --name-only
git diff --cached --check
git diff --cached
git commit -m "feat: add sanitized discovery disconnect diagnostics"
git push origin remediation/early-edge-evidence-readiness
```

The staged list must contain exactly those three files. Keep all private receipts and unrelated changes excluded; no main push/merge/force action. **Earlier disconnect causes remain UNKNOWN; PRE_COHORT_READY=NO. No new observation is initiated.**

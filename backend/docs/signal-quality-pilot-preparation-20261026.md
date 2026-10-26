# V2.1 prospective signal-quality pilot — preparation only

Parent baseline: `bd56824676f87c52c5d507ba6c669291ee1575c0`. Approved branch: `remediation/early-edge-evidence-readiness`. **NOT RUN. PRE_COHORT_READY=NO. Phase 4 remains unauthorized.** This is a prepared, separately authorized operational/descriptive OBSERVE pilot, not a cohort or trading-performance endorsement.

## Minimal integration

Existing `smoke_observe.py` runs the real RadarEngine and clean shutdown, but its short summary does not retain the full classification transition stream. Existing PriceResearch measures only first speculative reviews, not bearish/cooling/neutral/risk comparison populations. Neither component should be relabelled or changed to manufacture controls.

`scripts/signal_quality_pilot.py` is an opt-in harness using the same engine, providers, price cache, frozen settings and `stop()` lifecycle. Its wrappers observe original process return values and completed Intelligence.refresh outputs. They do not change rankings, selections, signals or candidate state. No production implementation was edited. There is no second intelligence engine, price oracle, matched-cohort implementation or execution path.

Default invocation prints a non-collectable protocol only. The `collectable=false` flag denotes no prospective cohort authorization; a separately authorized `--run` invocation can record these descriptive observations.

## Frozen timing and population

- Total planned observation: **1,200 seconds**.
- First-token/class measurement capture: signal timestamps in **[start, start+880s)**.
- Tail: **320 seconds**, allowing the existing 300s horizon plus its 20s acquisition allowance to finish. Normal startup/shutdown overhead is reported separately by recorded timestamps; no extension follows disappointing results.
- Preserve every observed classification transition throughout all 1,200s. New tail observations remain visible but are explicitly not scheduled for outcomes.
- Capture ACTIVE EMERGING BULLISH, BULLISH DEVELOPING, BUYING COOLING / WAIT, BEARISH PRESSURE, PULLBACK WATCH and neutral/risk/missing-data classifications. Raw model output remains intact; expired assessments have a separate effective STALE label. UNASSESSED is an administrative missing-assessment category, not a new trading interpretation.
- Measurement unit: **earliest observed token/class within this session**. Returning to that class does not create another independent sample. A mint may enter multiple classes; those measurements are dependent. Re-entry after leaving monitoring does not erase prior observations.
- Discovery records include admitted, duplicate and non-admitted creates. Missing prices, hard-risk classes, candidate departures and non-survivors remain in population accounting. No selection is based on future prices or outcomes.

This records transitions seen at the existing completed-refresh cadence (normally about one second), not every transient state between refreshes or a complete chain-wide universe.

## Baselines, horizons and missingness

Each first-class record freezes signal/recording timestamps, token age, lifecycle, quote identity where known, original V2.1 assessment/window evidence, immutable first-review price diagnostics and a valid USD mark **already available at signal time**, if any. Baselines are detached copies. No later price replaces a missing baseline.

Follow-up horizons: **15, 30, 60, 180, 300s**. Reuse the existing mark cache and temporal contract: first valid observed endpoint requested at or after target, acquired within target+20s, currently fresh, venue-compatible and with non-regressing slot/quote identity. No extra quote requests, best-price selection or spot-price fallback. Record actual endpoint timestamps; delayed marks are not exact-horizon fills.

Outcomes distinguish positive, negative and flat **gross reserve-implied USD movements**, unavailable baseline/endpoint flags, shutdown censorship and integrity-interruption censorship. Both missing flags can apply. All scheduled measurement/horizon pairs remain in the accounting. If shutdown occurs before the acquisition window matures, do not count that interval as a failed price observation.

Candidates leaving monitoring remain pending until a declared disposition. Source drift or controller/clock interruption prevents further confident measurement; affected pending observations are censored. An interrupted ledger is never resumed or repaired using later prices. No MFE/MAE or intrahorizon path completeness is claimed from sparse marks.

## Reproducible source gate

Live entry requires an explicit full `--expected-sha` that:

1. Is **not bd56824**, nor a short SHA, branch name or implicit HEAD.
2. Exactly matches current HEAD on the approved branch.
3. Exactly matches the locally fetched `origin/remediation/early-edge-evidence-readiness` ref.
4. Descends from the stated parent and contains the tracked harness.
5. Has no unpublished changes except the six explicitly preserved unrelated paths. Those paths' actual hashes are recorded too.

The new harness is currently uncommitted, so the current source cannot pass this gate. After review/publication, use the **new published successor SHA**, never this parent. Fetching GitHub must be done separately; the harness performs no GitHub network request and does not claim independent online publication attestation.

The manifest binds tracked file hashes, permitted local changes, effective settings, interpretation version, pricing/schema versions, and hashes of private provider/environment configuration (no credential values). Effective settings must equal the conservative configuration in the frozen parent. Drift is checked periodically (10s) and again at finalization. This is sampled drift detection, not an OS-enforced filesystem freeze; source edits are prohibited during a run.

## Resource and lifecycle stops

Existing application safeguards remain **250 candidates, 25 deep, 500 events/token, queue 1,000, RAM 700 MiB, DB 1,024 MiB**. Pilot stops earlier at:

- RSS >=500 MiB or combined output size >=640 MiB.
- Available storage <512 MiB.
- Queue depth >=800, any dropped trade/critical event, engine resource pressure, engine stop or ended background task.
- Source/configuration drift, controller pause >20s, clock regression or observer failure.
- 1,000 distinct observed mints or 2,000 scheduled token/class measurements.
- Trace soft limits: 32 MiB or 12,000 records; hard limits: 64 MiB / 24,000 records. Reserved headroom permits bounded final censorship output.

Ledger records are <=16 KiB; buffered data <=2 MiB / 512 records. The hash-chained JSONL is flushed/fsynced by the one-second controller. Shutdown outcomes flush in bounded chunks, including a tested 5,000-outcome synthetic closure. Failed writes retain unresolved accounting; they do not produce a complete report. Finalization calls the original engine shutdown, checks the isolated SQLite receipt/integrity and flags pending async tasks. Standard asyncio executor cleanup is retained. A blocked event loop cannot be preempted by this same-loop controller; a >20s control gap stops/censors on resumption and cannot be called a clean planned run. The operator must verify actual process exit; a written report does not prove process termination.

Output must be a **new immediate child** of `data/early_edge/`; existing folders and original databases are refused. A cooperative lock and recognized-process check prevent ordinary duplicate monitors. This is not proof that an arbitrary custom process is absent; the operator must stop other monitors before authorization. No process is killed. Initialization failure leaves an incomplete folder for inspection rather than retrying automatically.

## Expected artifacts

- `manifest.json`: source/configuration/protocol hashes and versions; no cohort/approval.
- `observe.db` plus normal WAL/SHM: existing application records in the new isolated DB only.
- `history.jsonl`: ordered START, DISCOVERY, TRANSITION, LEFT_MONITORED_SET, HEALTH, OUTCOME and STOP records, including a tamper/truncation-detecting hash chain.
- `shutdown.json`: original engine's durable shutdown receipt.
- `report.json`: planned completion versus partial stop, authoritative ledger validation/population/outcome counts, operational counters and unresolved work. Always PRE_COHORT_READY=NO and net results UNAVAILABLE.

HEALTH samples retain queue/resource measures, continuity, recovery counters, provider errors and price-diagnostic summaries without raw trade payloads, wallets, credentials or connection URLs. Raw application evidence stays in the ignored private isolated database. Reports/files must not be published without redaction review. The harness does not capture an unbounded console log.

## Testing protocol

Offline preparation:

```bash
.venv/bin/python scripts/signal_quality_pilot.py
.venv/bin/python -m pytest -q backend/tests/test_signal_quality_pilot.py
```

The default command only prints the proposed protocol; it creates no engine or database. After review, publication and **separate live authorization**, with standard HTTP/WSS configuration already present and cohort/PumpPortal environment switches disabled:

```bash
# FOR LATER AUTHORIZED USE ONLY. Replace with the reviewed, published successor.
NEW_PUBLISHED_SHA=<full-40-character-successor-sha>
.venv/bin/python scripts/signal_quality_pilot.py --run \
  --expected-sha "$NEW_PUBLISHED_SHA" \
  --output "data/early_edge/signal-quality-pilot-$(date -u +%Y%m%dT%H%M%SZ)"
```

Do not execute that command during this preparation. No automatic 600s, six-hour experiment or cohort follows it.

Offline verification of a future artifact:

```bash
.venv/bin/python scripts/signal_quality_pilot.py --verify-ledger <new-output>/history.jsonl
```

A valid chain without STOP reports interruption and outstanding horizons; duplicate/foreign outcomes or partial tails fail verification. Do not backfill or overwrite an interrupted folder. Review a separately authorized new run instead.

## Analysis limitations

Report class-specific signal counts, valid/missing baseline rates, endpoint rates, positive/negative/flat/unavailable counts and censored windows with separate denominators. Keep discovery/admission/coverage accounting separate from outcome availability. Controls are prospectively observed neutral/risk classes, **not matched randomized controls**. Do not retrospectively pick control losers. Pre/post-graduation and known/unknown quote/coverage strata are available from signal-time fields; report their differences rather than interpreting pooled means causally.

Twenty minutes cannot establish predictive profitability. Same-mint class overlap, common-market exposure, monitoring selection, non-random price missingness, sparse 30s acquisition, survivorship, regime dependence and multiple horizons limit inference. A missing sell route is not a zero-cost exit. These marks cannot establish manual T+10 execution, FOMO fees, slippage or net returns. No strongest evidence/approval status is calculated and no existing holdout is modified.

## Offline validation and scope

Validation: **162 passed in 6.46s** across the new harness tests and existing V2.1, early-price, durable diagnostic and shutdown suites; normal exit0. The new harness has **27 offline cases** (26 before the final failed-write case was added). Ruff passed, mypy passed **48 sources**, secret and whitespace checks passed. Initial development-only missing-import/type errors were corrected; their logs remain under `/tmp/signal-pilot-*.log`. No unrelated full-suite issues are claimed fixed and no full-system performance run occurred. The actual default CLI was executed and printed only the non-collectable protocol; no live `--run` was executed.

Preservation: current task's 14 hashes, the original 14-file preservation manifest, and the prior eight-file receipt manifest match. No original database, frozen observation folder or unrelated dirty file changed. Deterministic cases cover append-only transitions, controls with missing data, class deduplication, immutable baselines, negative/flat outcomes, exact capture/tail boundaries, shutdown/interruption censorship, departure, ledger capacity/partial writes, source/ref refusal, approved successor verification, drift and observational equivalence against a real offline DEMO engine. Synthetic prices and matches are never evidence of real returns.

Only new files are intended: `scripts/signal_quality_pilot.py`, `backend/tests/test_signal_quality_pilot.py`, and this report. Production code and previous harnesses are unchanged. No provider or 20-minute run was started. No staging, commit or push. PRE_COHORT_READY remains NO.

## Queued observer contract repair — 2026-10-26

Published source inspected: `0cf380396c55d2cd5a7a342d58ab9345df9f07b3` on the approved remediation branch. This is a harness correction only; no production engine, decoder, pricing, policy, scheduler, or database schema was changed. No providers/server were started. The interrupted `signal-quality-pilot-20261026T092018Z` folder remains frozen; nothing was backfilled or resumed.

### Confirmed defect and correction

`RadarEngine.process(event, now=None, *, queued=False)` finishes queue accounting in its `finally` block when `queued=True`. The real `drain_events()` passes that keyword. The pilot wrapper previously accepted only `(event, now=None)`, so Python raised TypeError **before entering the original bound method**. `drain_events()` caught the exception and invalidated coverage, but original processing/persistence/accounting never ran. The former direct-call equivalence test did not cover this contract.

The wrapper now accepts `*, queued=False` and calls `process(event, now, queued=queued)`. The original call stays outside the observer's exception handler: original exceptions propagate unchanged, original return values remain unchanged, and discovery is recorded only after return. Observer exceptions request `DISCOVERY_OBSERVER_FAILURE` without altering the engine decision. Detachment restores both original bound methods. There is no extra processing, replay, or acknowledgement.

### Frozen interrupted-attempt findings

Read-only JSON/SQLite inspection confirms 97 ledger records (START, 95 HEALTH, STOP), no discovery/transitions, CANCELLED after 955.209s total / 954.502s observation, closed ledger and completed shutdown. `complete=false` in the top-level report correctly differs from ledger closure alone. The database has only paper-account/session/session-context/strategy records, no market-event records.

The shutdown accounting records **240 accepted creates, 240 still in-processing, zero pending, zero terminal and zero persisted creates**. Accounting's structural reconciliation is true because outstanding work remains explicit; it does not establish completed processing. Pre-shutdown continuity shows 241 live global resets: 240 consistent with caught create-processing failures plus one recorded transport reset. Final receipt adds one intentional shutdown reset (242 total). This supports the demonstrated harness defect; it does not prove Wi-Fi caused any error.

The last retained HEALTH reports **298 discovery errors, one reconnect**. These are a separate counter from engine processing failures. Source inspection shows discovery.errors increases through `record_decode_failure` and the transport exception/reconnect handler. With zero initial counters and the recorded one reconnect, **297 aggregate decode failures are implied by these counter definitions**, not 298 transport failures or 298 queue-wrapper exceptions. This is derived attribution, not a retained detailed decode histogram. The old HEALTH fields and the two durable evidence receipts contain no discovery failure category histogram or transport diagnostic history. Exact notification/layout/framing categories, timestamps, exception cause, and relationship to network interruption are therefore **UNKNOWN**. No stale-event rejection can be inferred from that discovery total. The 240 failed queued creates are independently recorded as outstanding, not stale or recovered.

### Bounded HEALTH improvement

Each new HEALTH record copies existing numeric counters only: messages, launch_events, ignored_events, decoding_errors, last_success/last_event; fixed allowlists of decode reason/event counts, framing details, transport failure counts and global reset reasons. Unexpected keys and nonnumeric/nonfinite values are omitted or null. Dictionaries are copied at capture time. Missing counters remain null rather than invented zero. No payloads, signatures, wallet information, arbitrary exception strings or URLs are copied. Existing error/reconnect/connected fields remain.

This adds constant-size work once per existing HEALTH interval, not per message. The discovery object with unavailable values serializes to 1,288 bytes; a real offline engine HEALTH record passes the existing 16 KiB limit. Integer digit growth still obeys the unchanged fail-closed ledger size cap. The 64 MiB / 24,000-record ledger limits and buffering/retention rules are unchanged. No live CPU-throughput result is claimed.

### Regression and validation

- The corrected real-queue regression was run with the original wrapper restored temporarily: **1 failed**, with `Event processing failed; kind=create`, no admitted token. Restoring the fix made it pass. Explicit keyword-forwarding tests also fail against the original signature. An initial test-fixture error (using dataclass replacement on a Pydantic event) was corrected before this real-queue demonstration; it was not evidence of the production defect.
- Real isolated offline engines use `submit()` then actual `await drain_events()` for canonical-shaped DEMO create fixtures, duplicate and stale rejection. One create persists, all dispositions reconcile, queue/in-processing clear; results match the unobserved engine. Intelligence refresh after admission produces identical outputs and recorded transitions.
- Direct/queued forwarding, original exceptions, observer failures, real queued failure accounting, original return values, and exact detachment are covered. Real engine shutdown is awaited normally; no executor/worker cleanup bypass.
- Dedicated pilot, event-accounting/remediation, shutdown and V2.1 suites: **80 passed in 18.90s**, exit 0 (33 pilot cases). No full-suite or performance campaign was needed.
- Ruff passed; mypy passed (48 source files); basic secret scan passed (278 source/document files); whitespace check passed.
- Existing preservation manifests: 14/14 preparation hashes, 14/14 original pricing hashes and 8/8 diagnostic hashes match, including all six unrelated files. No historical database writes, checkpoint, vacuum, migration, receipt edits, staging, commit or push.

Intended changes only: `scripts/signal_quality_pilot.py`, `backend/tests/test_signal_quality_pilot.py`, and this report.

### Remaining action (not executed)

After review/publication of this fix, separately authorize one short isolated read-only discovery smoke using the corrected published SHA. It should prove submitted creates reach terminal processing/persistence, zero stranded in-processing work, DISCOVERY and post-admission classification records, bounded new failure histograms, and normal shutdown. Require this before another 20-minute pilot; do not resume or repair the interrupted attempt. Such a smoke would not establish 180-second CURRENT coverage, predictive quality, executable fills or net profitability. Any still-unexplained discovery failures need their newly captured categories reviewed.

Phase 4 remains unauthorized. **PRE_COHORT_READY=NO.**

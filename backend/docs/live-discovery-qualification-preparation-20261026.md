# Short live discovery qualification — preparation only

**PRE_COHORT_READY=NO. Phase 4 unauthorized. No live smoke was run.**

Inspected published HEAD `b3b346b168878526bd8b41574b12e780a07f669e`, branch `remediation/early-edge-evidence-readiness`. The six pre-existing unrelated files are preserved. This adds only `scripts/qualify_live_discovery.py`, `backend/tests/test_live_discovery_qualification.py`, and this report; nothing staged, committed or pushed.

## Minimal reuse decision

The old `scripts/smoke_observe.py:counted_process(event, now=None)` still lacks the production `queued` keyword. **Do not use that older script unchanged.** It was neither invoked nor modified.

The dedicated qualification script imports the published corrected `signal_quality_pilot.attach()` without replacing production processing. It also reuses the pilot's bounded hash-chain ledger, discovery recording, numeric HEALTH allowlists, source-integrity verification, conservative resource guards and offline ledger verifier. It does not change that script, its 1,200-second protocol or 880-second measurement boundary.

Its small recorder subclass records canonical-source create dispositions and classification transitions only. It never schedules signal-quality measurements or horizon outcomes. Classification observations must come from actual completed intelligence refreshes for admitted live-source tokens. Canonical-source checks require `Onchain Pump`, Pump program identity and confirmed commitment. There is no synthetic event injection in the runtime harness. Offline fixtures explicitly simulate those shapes solely for tests.

## Preflight and isolation

An explicit full 40-character published SHA is required. Reused checks require the approved branch, HEAD equality, fetched approved origin-ref equality, original frozen ancestry, no source modifications beyond the existing six-file allowlist, and tracked source/configuration hashes. Additional checks require ancestry from the corrected wrapper commit and that the new qualification script itself is tracked. **The current uncommitted preparation cannot run:** it must be reviewed and published first, then invoked with that new full SHA. The origin check uses the local fetched ref, not an online GitHub attestation; operator must ensure it is current.

Configuration must exactly equal the frozen conservative configuration in OBSERVE mode. Existing standard HTTP/WSS credentials are required privately. Any enabled PumpPortal or nonempty cohort environment setting refuses execution. No invented endpoints, extra subscriptions, wallet/signing functions or transaction submission are added.

Output must be a new immediate child of `data/early_edge/`; existing directories are refused. One existing RadarEngine is constructed with an explicit new `observe.db`. No original `data/radar.db` or old observation folder is opened. The cooperative lock is shared with the long pilot. A preflight scan refuses recognized competing Crispy Winner/uvicorn/observation processes and never terminates them. This cannot prove absence of an arbitrarily renamed custom monitor; operator must also verify no server is running.

Tracked source, permitted dirty files and private environment/configuration hashes are rechecked every ten seconds and at shutdown. No credentials are printed or copied into reports. Source/config drift fails qualification.

## Duration, stops and cleanup

The fixed observation budget is **120 seconds**, including startup; no duration override or automatic extension exists. An asyncio deadline bounds startup and the controller. A blocked startup yields `STARTUP_TIMEOUT`, not a completed observation. Cancellation remains `CANCELLED`, never a completed short study. Shutdown time is reported separately and may exceed the observation budget because normal durable cleanup is preserved.

The controller samples once per second and emits bounded HEALTH records every ten seconds, plus the last live snapshot. Existing earlier guards remain:

- RSS >=500 MiB (production limit remains700 MiB).
- Combined output >=640 MiB (production storage limit remains1,024 MiB).
- Free disk <512 MiB; queue occupancy >=800/1,000.
- Any dropped trade/critical event, storage stop, resource pressure or ended engine task.
- Controller gap >20 seconds, source drift, observer/ledger failure.
- Ledger soft stop at12,000 records or32 MiB; unchanged hard caps24,000 records/64 MiB,16 KiB per record,512 buffered records/2 MiB.
- Token/discovery retention uses the existing1,000-mint bound. No per-trade tracing or new market polling.

An asyncio deadline cannot preempt synchronous event-loop blocking or an OS stall. Measured cutoff and deadline overshoot are retained; scheduled cutoff exceeding the budget by more than one second is explicitly failed as `OBSERVATION_DEADLINE_OVERRUN`, not called a compliant120-second observation. This is an overrun detection tolerance, not a longer configured observation or relaxed evidence gate. Same-loop resource checks likewise cannot enforce instantaneous OS-level quotas. No forced-exit watchdog, worker-shutdown bypass or suppressed evidence gap is introduced.

The original engine stop is awaited, with unresolved queue work left in its terminal accounting. The isolated database is reopened read-only to verify SQLite quick_check, the durable session STOPPED/checkpoint receipt and zero prospective cohorts. A SQL aggregate independently counts session-specific canonical create event rows and distinct mints without exporting their payloads. Qualification requires correspondence with both engine persistence accounting and the observer's post-return persistence count. Pending asyncio tasks and closure/integrity failures prevent PASS. Standard asyncio executor shutdown remains intact; the operator must verify actual process exit.

## Measurements and acceptance

Provider counters and engine counters have distinct meanings:

| Measurement | Actual source |
|---|---|
| Received on-chain notifications | Discovery `messages`, incremented at subscription notification receive; not all network frames |
| Decoded creates | Discovery `launch_events`, incremented after canonical decode before submit |
| Submitted/accepted creates | Shutdown accounting `events.create.submitted/accepted` |
| Terminal creates and reasons | Shutdown accounting `events.create.terminal`, including duplicates/stale/rejections/unprocessed shutdown work |
| Persisted creates | Engine persistence count, post-return observer count, and read-only matching session event-row count |
| Distinct admitted tokens | Bounded observer set after successful processing; corroborated by durable distinct create mints |
| Classification transitions | Append-only TRANSITION records after actual intelligence refresh; first classification counts as initial transition |
| Queue and in-processing reconciliation | All event-kind rows in durable shutdown accounting |
| Provider state/failures | Live and post-shutdown numeric discovery snapshots; separate decode reason/event, framing, transport and reset histograms |
| Resources | Sampled peak RSS/combined output, queue peak, final database/WAL/SHM sizes and exact final trade/critical drop counters |

PASS requires scheduled completion, unchanged source, complete ledger, valid database/shutdown receipt, no cohort/approval, no pending tasks, no stranded processing, all event kinds reconciled with no pending queue work, no trade/critical loss or processing exceptions, readable fixed histograms, at least one decoded create, corresponding processed/persisted create, admitted token and recorded classification transition. Unexpected/noncanonical create sources fail. WebSocket connected status alone cannot pass.

If no decoded create arrives but all integrity conditions hold, the result is `INCONCLUSIVE_NO_LIVE_CREATE`. If decoded creates arrive but cannot be admitted/persisted/classified, or integrity/resource/cancellation checks fail, the result is FAILED. Decode errors do not silently disappear or change decoder acceptance: exact categories/counts are retained even if an otherwise valid operational sample passes. Any unexpected category must be reviewed before a long pilot. A PASS does not establish180-second CURRENT, executable prices, signal quality, net returns or cohort readiness.

## Expected output (ignored/private)

New output contains:

- `manifest.json`: operational protocol, exact source/config hashes, conservative settings.
- `observe.db` and optional WAL/SHM: the isolated engine's normal durable evidence.
- `history.jsonl`: bounded START, DISCOVERY, TRANSITION, HEALTH, STOP chain; every transition has `measurement_scheduled=false`; no OUTCOME records from this recorder.
- `shutdown.json`: copied durable isolated engine shutdown receipt.
- `report.json`: PASS/FAILED/INCONCLUSIVE verdict with per-check booleans, failed checks, reason, source/session, actual observation and shutdown durations/overrun, provider histograms, observer counts, create accounting, corroborated durable create counts, queue/drop/resource summaries, ledger integrity and pending tasks.

The existing engine can still write its ordinary research/price diagnostic records as part of unchanged OBSERVE behavior. These are not a newly enrolled prospective signal-quality sample. No new prospective cohort, protocol or approval is created. Do not combine the smoke's observations with a subsequent study sample. Keep token-level private outputs ignored; redact any future public report.

## Commands — later authorization and publication required

Plan only (safe offline):

```bash
.venv/bin/python scripts/qualify_live_discovery.py
```

**Do not run the following yet.** After review/publication, fetch/verify the approved branch, confirm no server/monitor is running, then supply the full newly published successor SHA containing these files:

```bash
cd /home/modisa/projects/crispy-winner
EXPECTED_SHA='<full-40-character-reviewed-published-successor-SHA>'
RADAR_MODE=OBSERVE RADAR_CONFIG=config/conservative.yaml PUMPPORTAL_ENABLED=false \
  .venv/bin/python scripts/qualify_live_discovery.py --run \
  --expected-sha "$EXPECTED_SHA" \
  --output "data/early_edge/discovery-qualification-$(date -u +%Y%m%dT%H%M%SZ)"
```

No timeout wrapper or manual cancellation is used to turn a longer study into this smoke. A non-PASS exits nonzero. Do not automatically rerun, resume or backfill any interruption.

## Offline validation

- **111 passed in9.21s**, normal exit0:31 new qualification cases plus corrected pilot, event accounting/remediation, shutdown and V2.1 regression suites.
- Real offline RadarEngine queued synthetic canonical-shaped create/duplicate events, intelligence callbacks, durable shutdown and read-only SQL corroboration agree with the unobserved engine; no providers started. No scheduled measurement/outcome records.
- Negative cases cover missing source/ledger/SQLite/shutdown integrity, cohort, pending tasks, stranded processing, reconciliation, loss, processing failure, missing histograms, persistence mismatch, missing admissions/transitions, cancellation and noncanonical source. Connected/no-create is inconclusive. Startup deadline and successful bounded lifecycle are tested with an offline engine and a short synthetic clock budget; the production default remains120.
- Existing resource guard behavior is verified for RSS, storage, queue, loss and engine stop. The sparse storage fixture is confined to pytest temporary output, never historical data.
- Ruff passed. Mypy with `--explicit-package-bases` passed49 source files. The first combined invocation without that flag reported duplicate namespace mappings (`signal_quality_pilot` vs `scripts.signal_quality_pilot`); this was a checker invocation issue, not a suppressed type error. No package architecture change was needed.
- Preservation manifests:14/14 preparation,14/14 original pricing,8/8 price diagnostics match, including the six unrelated paths. No original database or interrupted pilot was modified.
- Basic secret scan passed281 source/document files; whitespace check passed. No frontend code changed; no broad full-suite or performance campaign is required or claimed.

This is prepared operational tooling, not live qualification evidence. The next action is review/publication, then separately authorized execution of exactly one smoke. **PRE_COHORT_READY=NO.**

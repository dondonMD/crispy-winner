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

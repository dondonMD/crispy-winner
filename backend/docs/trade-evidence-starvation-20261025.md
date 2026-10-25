# Trade-evidence starvation: bounded retention correction — 2026-10-25

**A narrow correctness defect is fixed; live CURRENT recovery is NOT established. PRE_COHORT_READY=NO. Phase4 unauthorized.** Source `63e63d6eff2c54f0bbb75144aca5ae28e7fa62c9`, remediation/early-edge-evidence-readiness. No live run, cohort, trading, provider/subscription change, commit, staging or push.

## Findings and limits of the evidence

The latest supplied aggregates reconcile:269 global resets =265 recovery-related +4 transport;6,371 local resets =3,144 buffer +3,052 stale +175 recovery. These are reset calls, not unique missing transactions or tokens. The exact matching latest receipt/timeline was not supplied or identified locally, so these counts remain operator-reported rather than a newly reconstructed live experiment. Older frozen Phase3 runs are not substituted for this workload.

|Cause|Established behavior / interpretation|
|---|---|
|500 shared retained events|`Token.events` holds trades and market events. A501st relevant event evicts evidence. Sustained demand above roughly500/180=2.78 trades/s for one token cannot fit a full180s window, even before market samples consume slots. This is a real capacity limit; asserting CURRENT despite an in-window loss would be incorrect.|
|Avoidable retention recovery delay|Engine formerly reset the generic gap to processing time whenever a recent retained trade was evicted. If that known trade was already170s old, it still imposed another180s recovery rather than waiting only until the actual missing point left the window. This defect is reproduced offline.|
|Inclusive-boundary error|Features include timestamps at exactly now-180. Old eviction test used `<180`, so an exactly180s-old eviction could incorrectly leave CURRENT true while one required trade was missing. This is also reproduced before the patch.|
|Recovery-global resets|Recovery overflow, expiry/unavailability, malformed/unsupported or conflicting transaction evidence conservatively invalidates globally. Only complete canonical UNTRACKED_CONFIRMED avoids a gap; TRACKED_AFFECTED invalidates identified tracked tokens. Unknown instructions may hide trades/migrations, so filtering away unknown recovery work or treating it as harmless is unsafe. No new evidence justifies changing this path. The265 resets require their classification/overflow/expiry breakdown and timeline to diagnose.|
|Stale queue work|The supplied1,421 trades stale while queued establish an admission-to-selection freshness problem for that metric.3,052 stale local resets have a different scope: some events may be old at admission or expire after selection in detached batches. Their numerical difference cannot be assigned entirely to arrival staleness or lost trades without per-stage receipts. A741/1,000 peak is not a complete disposition ledger.|
|Unknown units|4,651 curve-not-verified events lack the independent account evidence needed for legacy quote interpretation.1,103 unsupported-quote events cannot be assumed SOL/USDC. Counts are not distinct tokens; quote identities/categories need recorded evidence. Existing unknown/mixed-unit gates remain unchanged.|
|Transport/framing|Four locally detected ping timeouts invalidate continuity; their underlying network/provider/client cause remains unproven.1,432 framing failures may overlap explicit truncations and recovery. They must not be added as independent global loss counts. Decoder full-consumption/framing rules remain strict.|

Read-only inspection included the existing `PriorityBuffer` handoff, `drain_events`, synchronous processing/persistence, feature caches, consumer-trace tooling and retained capacity/architecture reports. The100-event detached batches,250ms cadence, serial analysis/callbacks and two durable transaction boundaries remain unchanged. Prior service-margin limitations are relevant hypotheses for this workload, not a new measured attribution to SQLite or host contention. The five unrelated diagnostic files were not edited or executed as new load experiments.

## Smallest correction and proof

Only [domain.py](../app/domain.py) and [engine.py](../app/engine.py) production source changed. Add one optional per-token `buffer_loss_at`, the **maximum timestamp of known retained trades evicted from memory**. Canonical late arrivals mean deque insertion order is not necessarily timestamp order; maximum lost timestamp cannot move backward.

Known retention loss is distinct from a transport/queue/stale/recovery gap. It no longer overwrites the generic processing-time gap with an unnecessarily later barrier. Every affected feature window stays incomplete while its inclusive timestamp range contains the known loss. For a window W and latest lost timestamp L, completeness additionally requires `now - L > W`, alongside existing coverage, units, freshness, sample and pending-recovery requirements. This strict comparison preserves the inclusive endpoint, including zero/future timestamp edge cases. Connection/session/venue/epoch and unknown gap barriers still dominate when later. No missing sample is reconstructed or assigned invented volume/wallet identity.

All automatic trade evictions are audited in fixed `buffer_trade_evictions`. Those outside both the existing event-time analysis window and current processing-time180s window are separately counted in `buffer_expired_trade_evictions`; they do not manufacture a fresh180s outage. Window-relevant buffer invalidations still increment the existing local reset counter and clear completeness. All evictions still update the loss fence, including for longer descriptive windows. Therefore raw reset-counter changes must be interpreted with these eviction classifications, not presented as less source loss.

Resource trimming retains its degraded flag and conservative processing-time resource gap. It also records known lost timestamps and recognizes the inclusive boundary/future-stamped losses. No resource-pressure or unknown-gap relaxation. Restart discards event windows and rewarms; the new scalar is not used to restore old evidence as CURRENT. PumpSwap coverage still requires independently eligible verified pools, ACK coverage and the current flow epoch; no schema/decoder or migration logic changed.

### Before/after deterministic evidence

Two regressions failed against the untouched baseline, preserved in ignored `data/early_edge/trade-starvation-20261025/before.txt`:

|Controlled scenario|Before|After|
|---|---|---|
|500 previously observed retained trades, then one eviction whose timestamp is170s old|At +11s, PARTIAL despite the complete required180s scoped-input window being present|CURRENT only after the lost point is181s old; retained180s feature dictionary equals the full-input oracle exactly. Latest trade remains actually11s old; no timestamp rewritten.|
|Evicted trade exactly180s old|Incorrect CURRENT despite missing an inclusive-boundary trade|Not CURRENT at the boundary; eligible only once the point is strictly outside the window and all other gates pass.|
|Burst with eight in-window evictions|Incomplete rolling evidence|Still incomplete through the burst, still500 retained records. After all missing points expire and three new genuinely observed samples arrive, retained features equal full-input oracle and may become CURRENT.|
|Mixed/unknown units or additional queue/stale/recovery/resource loss|Unavailable/partial|Still unavailable/partial; a known retention fence cannot override other gaps.|

These are synthetic clock-controlled observations, not newly observed market trades, profitable signals or throughput measurements. The170s example demonstrates removal of avoidable delay; the actual live benefit depends on the timestamp ages of evicted trades and competing gaps. Continuous overflow inside every180s window remains a valid blocker.

## Validation, resource implications and remaining blockers

- Final focused run: **169 passed in7.62s, exit0**: new buffer cases plus canonical Pump trades, adversarial truncation recovery, PumpSwap flow/epoch and exact feature-hotpath regressions. Includes actual queue eviction/stale rejection, unknown/mixed units, out-of-order/future timestamps, inclusive resource trimming and offline cold restart.
- Final new module alone:16 passed3.85s. Counts overlap; do not add them. Ruff, mypy44 application files, secret scan and whitespace/preservation checks pass. No broad endurance, full backend/frontend campaign or CPU benchmark; no frontend or dependency edits.
- Fixed500-event retention,250 default candidates,25 deep slots,1,000 queue,100-event selection and all timing/strategy/security/approval settings remain unchanged. One optional timestamp per candidate and two aggregate counters are added; no extra event list, task, RPC, subscription or SQL transaction. CPU/RSS under the latest real workload is unmeasured; this is not proof of the <500MB normal target or sustained50/s capacity.
- Genuine in-window overflow, recovery-global uncertainty, stale queued work, unknown units and transport outages remain. Accurate complete evidence for a token whose required window continually exceeds500 shared slots is impossible with this representation. A compact retention design would need a separate measured resource/equivalence study; no such speculative redesign is implemented here.
- Historical evidence and negative outcomes are not deleted/reclassified. Decoder, discovery, recovery scheduling/classification, persistence/durability, source units, strict entry and approved_evidence are unchanged. CURRENT remains scoped observed-flow evidence, not proof of chain-wide delivery or trading quality.

## Next bounded verification

**One separately authorized existing240s OBSERVE verification is justified after review**, to determine whether this correctness fix helps real retention-limited windows. None is started. Preserve the same settings/resources and report both success and failure: CURRENT/coverage, the two new eviction counters and local reset reasons, recovery classifications/overflow/expiry/global gaps, transport transitions, queue staleness/dispositions, unit failures and CPU/RSS. No duration extension or threshold change to obtain a success. If no token has a complete known-unit clean window, report that honestly. The latest265 recovery-global resets may still prevent any CURRENT; the fix is not evidence that those resets are avoidable.

Exact intended files: `backend/app/domain.py`, `backend/app/engine.py`, `backend/tests/test_buffer_loss_window.py`, and this report. All five unrelated worktree files, seven frozen artifacts, private receipts and retired database metadata remain preserved. No commit/push/staging. **Implementation correction validated offline; live starvation not yet resolved. PRE_COHORT_READY=NO.**

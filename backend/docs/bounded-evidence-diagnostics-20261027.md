# Bounded evidence diagnostics — 2026-10-27

PRE_COHORT_READY=NO. Phase4 unauthorized. Baseline `248ecc31d031dfd2b7dbc7fb2e49cf8ab9c96f57`, branch `remediation/early-edge-evidence-readiness`. The preceding forensic report was read and remains unchanged. No live provider, observation, server, cohort, wallet or transaction was started. No original/historical database or outcome was changed; nothing staged, committed or pushed.

## Scope and behavior

Intended files: backend/app/truncation.py; scripts/smoke_observe.py; new scripts/smoke_evidence_diagnostics.py; new backend/tests/test_bounded_evidence_diagnostics.py; this report. The engine, discovery decoder, queue implementation, strategy/classifications, prices, budgets, paper balances, heartbeat settings and source-integrity allowlist were not modified. Timing wrappers are installed **only by the isolated smoke harness**, not the production dashboard/engine. Event-CPI additions are numeric telemetry after the original rejection branch.

Before: the frozen120s report could not distinguish15 CREATE dispositions, the observer inferred trade rejections from age, and three event-CPI failures had no subreason. After: new observations retain native pre/post accounting, actual process dispositions, bounded timing partitions and fixed event-CPI condition masks. **No frozen observation is repaired or backfilled.** The legacy timing/instruction ambiguity remains unavailable for historical cases.

## New schema and semantics

### Smoke report

Existing report fields remain report-time values, detached before shutdown so cleanup cannot rewrite them. The report is now saved after stop (compact JSON; console remains indented) with an added evidence_diagnostics version1 section, capped at **16,384 compact UTF-8 bytes**:

| Field | Establishes | Does not establish |
|---|---|---|
|pre_shutdown.session/at/accounting.events.create,trade|Exact copied EventAccounting rows: submitted,accepted,rejected_incoming,evicted_accepted,pending,in_processing,terminal,persisted,reconciled|Not inferred rejection counts; heap-empty does not erase in_processing|
|post_shutdown.session/at/accounting.events.create,trade|Actual native accounting after stop, including cancelled/shutdown_unprocessed dispositions and honest nonzero outstanding work|A returned stop is not an independent file-fsync or retained-SQL proof|
|shutdown|RETURNED,FAILED or CANCELLED for stop; original failure propagates|Not automatic study or cohort success|
|timing.histograms|Fixed12 buckets per7 stages per2 event kinds|Not a per-event history, exact percentile or provider latency|
|timing.stale_timing|Partition of native stale CREATE/TRADE callbacks only|Age cannot relabel untracked/venue/duplicate as stale|
|timing.stale_partition_reconciled|Sum of classified/unknown timing buckets equals native terminal stale counts|Unknown provenance remains unknown even when counts reconcile|
|metadata_pending/peak/limit/omitted; missing_dispatch; unresolved_shutdown|Bounded telemetry coverage and explicit missing boundaries/unobserved terminal metadata|Unresolved timing metadata is not relabelled rejected, recovered or cancelled by guesswork|
|integrity_failures/attribution_complete|Explicit telemetry errors/incomplete attribution; false for unknown/ambiguous clock or stage histories|Never supplies CURRENT market evidence|

The wrapper reads the original engine's _process_reason, which is also the source used by EventAccounting.finish(). Full queued dispositions (stale,untracked,venue,pool_epoch,duplicate_memory,duplicate_db,exception,etc.) are retained in native rows. Existing trade_process_rejections keeps its two-key compatibility shape, but now stale means the native stale disposition; every other false result goes to other. trade_rejection_policy=native_process_disposition_v1 makes this diagnostic semantic correction explicit. No extra lifecycle counters are maintained.

If sampling/report assembly fails before a pre-stop view exists, status is PRE_SHUTDOWN_REPORT_UNAVAILABLE and the pre view is null, not fabricated. Cleanup still attempts final native accounting and rethrows the original failure. Timing faults cannot change processing results; missing diagnostics are explicit. Histogram omission is explicit via omitted_histograms if the byte cap is reached. Unexpected remaining oversize produces UNAVAILABLE_SIZE_LIMIT/integrity_failure rather than silent truncation or a successful report. Ordinary file-write failures still fail the command; an original shutdown failure takes precedence. Existing engine STOPPED receipt/checkpoint behavior is unchanged, including legacy temporary DB removal after the script finishes.

### Timing boundaries

The first local boundary is **entry to OnchainPumpDiscovery.receive(decoded_notification)**, after raw receive and JSON parsing. It is deliberately named decoded_notification_dispatch. Raw frame arrival and provider send time are UNAVAILABLE. Events emitted during that synchronous dispatch share its observation clock; other producers/direct submissions have missing_dispatch accounting. No payload is retained.

Age stages dispatch_age,admission_age,selection_age,processing_age are signed wall seconds minus the unchanged event timestamp. Durations dispatch_to_admission,queue_residence,selection_to_start use monotonic differences. Selection_age is measured at drain return; the original native selection instant is bracketed by clocks before/after drain. A20s crossing within that bracket is selection_boundary_ambiguous, not an invented precise queue/processing attribution. The native queue's existing arrival/selection clocks and freshness tests remain authoritative.

Eight fixed native-stale partitions:

- already_old_at_dispatch: old at the first **recorded application boundary**, not proof it was old at socket arrival.
- old_before_admission: known dispatch age valid, old at admission.
- old_in_queue: known earlier boundaries valid, old before the selection bracket begins.
- old_after_selection: valid through selection return, old at actual processing start.
- future_dated: a recorded age is more than20s negative; no claim which clock is wrong.
- clock_irregular: negative elapsed time or wall/monotonic interval divergence >.5s. This is only a diagnostic conservatism threshold, never a freshness allowance or clock correction.
- selection_boundary_ambiguous: cannot distinguish crossing inside drain from one side of it.
- provenance_unavailable: missing/invalid boundaries prevent assignment.

Bucket upper edges are [-20,-1,0,.001,.01,.1,.5,1,5,20,60], plus overflow. Equality stays in the lower bucket; native freshness remains strict abs(now-event.ts)>20. Even perfect local stage clocks cannot independently separate chain/program clock offset from provider/network/client buffering before dispatch. Timestamp values, units and market-event payloads are never rewritten.

Ephemeral metadata is keyed by existing queue sequence and object identity, never persisted. Actual queue put/drain results are passed through unchanged. Selected metadata is matched to the original returned chronological list. At most min(queue.maximum+100,1100) entries are kept, covering the existing1000 heap +100 detached selection. Actual evictions remove metadata. Any cap/mismatch is visible; counters saturate instead of unbounded numeric growth. Shutdown records unresolved metadata before clearing it. Native lifecycle accounting, not this cache, supplies cancellation/rejection dispositions. Original methods are restored; no timing task, thread or poller is created.

### Event-CPI rejection namespace

recovery.snapshot().event_cpi_rejections version1 adds rejected_instructions, five fixed conditions,32 masks,integrity_failures,available,reconciled. The existing unsupported_instruction_counts.other remains authoritative and unchanged. Failures are counted only after the original canonical predicate failed and instruction lookup was unsupported with exact EVENT_CPI prefix:

| Bit | Condition |
|---|---|
|0|not_inner|
|1|account_count not exactly one|
|2|authority mismatch, only when exactly one account exists|
|3|short_data, less than16 decoded bytes|
|4|unknown_event discriminator, only when16 bytes exist|

Multiple simultaneous conditions are preserved; condition counts overlap and must not be summed as rejected attempts. Mask counts sum to rejected_instructions and reconcile with the original other instruction counter. Account-count mismatch does not invent an authority comparison; missing data does not invent an unknown event tag. Canonical events, other instruction prefixes and malformed pre-validation paths keep their original classifications. Existing event-body interpretation is unchanged.

Updates are staged atomically, fixed-key and bounded64-bit numeric. Calculation, corrupt aggregation or snapshot failures expose an integrity counter and available/reconciled false; they never broaden acceptance, replace the original unsupported result, output arbitrary diagnostic strings or silently report success. Snapshot copies arrays/conditions. No raw instruction/account bytes, mints, signatures, wallets, URLs or exception text enter this namespace. No new schema acceptance claim is made.

## Before/after verification

A private baseline reproduction executed the **published** smoke harness in an isolated temporary directory with a real offline engine. An old untracked trade produced native terminal {untracked:1} but legacy trade_process_rejections {stale:1,other:0}, and no native report section. The new integration cases produce other:1 with the same native untracked decision. Data: ignored data/early_edge/bounded-evidence-20261027/final/measurements.json. This is a reporting correction, not new trade eligibility.

Deterministic regression coverage includes24 feasible CPI context/account/length/tag combinations compared directly with the published transaction_impact implementation; returned classification and input transaction content are identical. Fault injection covers calculation, corrupt shape and unsafe nonnumeric counters. Synthetic signatures/authority values are absent from exported diagnostics.

Native-rejection integration covers untracked,venue,pool_epoch,both duplicate paths and stale. Timing tests cover every stage bucket classification, future/irregular clocks, uncertain selection bracket and missing provenance. Additional cases exercise an actual decoded notification, receive exception/context restoration, pressure/eviction/cap omissions, timing method/snapshot failures, pending CREATE before stop, detached cancellation, body/stop exceptions and size overflow. Existing smoke integration still verifies durable accounting and decision/paper equivalence. The complete pre-stop report is copied so final shutdown cannot rewrite it.

An early new-test fixture omitted the required synthetic MarketEvent source; it failed validation before application logic and was corrected. The initial pytest iterator warning was removed by making parameter cases a list. The failures/warning are retained in /tmp/bounded-evidence-focused.log, not hidden as passing runs.

## Resource measurements

Fixed synthetic component,7 samples/1000 events each, original PriorityBuffer versus opt-in wrappers and stage accounting. Event construction was outside timers; no engine/provider/DB work was benchmarked. Final CPU medians3.055ms baseline versus23.727ms instrumented: **~20.7 microseconds added/event**. Wall medians3.059ms versus23.733ms. At50 events/s the simple added-CPU projection is~1.03ms CPU/s (~.10% of one core), not a live capacity guarantee.

At1100 entries, metadata plus ready deque measured548,229 bytes; histogram structures3370 bytes; aggregate snapshot1922 bytes in that fixture. These are Python deep-size/component measurements, not whole-process RSS or peak live allocation. Snapshot size does not grow with token IDs or history length. Per-drain metadata scanning is boundedO(1100), per-event buckets have fixed sizes, and native accounting is copied only for pre/post summaries. Event-CPI telemetry adds fixed numeric data to existing snapshots, no new table, write schedule or retention policy. Counter saturation/fault/omission is explicit. New report section is capped16KiB compact, plus the unchanged bounded existing report fields; console whitespace is not counted as persisted JSON bytes.

## Validation and publication recommendation

Validation totals and final preservation checks are appended from actual logs below. The broad test selection includes pilot/qualification source guards, transport, truncation, queue accounting, shutdown and reference-security tests. No ordinary backend or SDK dependency was added. No frontend change calls for an unrelated frontend campaign.

Mypy for the application plus new helper is clean. Including legacy smoke_observe retains its eight previously documented method-assignment/None-inference errors; no ignore directives or unrelated type cleanup were added. Those existing errors are reported rather than labelled a green script-inclusive check.

Review only the five intended files and the selective review.patch stored in the ignored bounded-evidence folder; do not stage unrelated changes or the pre-existing forensic report. Source-integrity guards and their unrelated-file allowlist are unchanged; unpublished source remains ineligible for live qualification. After review, a successor publication and separately authorized bounded operational verification would be needed. Do not automatically run a probe or retrospective reconstruction. This change explains future missing evidence; it cannot certify CURRENT, recover past missing outcomes, resolve ping timeouts or establish predictive profitability.

### Final recorded results

- Final applicable backend/source-guard/security selection: **289 passed in13.98s**, normal exit.
- Final dedicated new diagnostics: **49 passed in2.44s**; focused CPI/new diagnostics **140 passed in4.69s**. These overlap and must not be added to289.
- Ruff passed for backend/app and changed/new scripts/tests. Mypy passed50 application/helper source files. Script-inclusive mypy retains the same8 documented legacy smoke errors; no new errors were introduced or suppressed.
- Basic secret scan passed296 source/document files. Tracked diff and new-file trailing-whitespace checks passed.
- All32 initial preservation hashes matched, including six protected files, preceding forensic report, frozen120s artifacts and preserved investigation data. The original radar.db was never opened by this implementation or its tests.
- HEAD and branch remain the stated published baseline/approved branch. No providers, staging, commits or pushes.

Exact selective diff: ignored `data/early_edge/bounded-evidence-20261027/review.patch`, covering only the five intended files. Existing unrelated diffs and untracked reports are deliberately excluded.


## Independent release-review corrections — 2026-10-27

The earlier Git-backed equivalence comparison above records a completed development check, not the current CI contract. The release test no longer runs git show, exec, subprocess or historical-module loading. All24 CPI cases use independently specified expected classifications: only inner+single correct authority+known tag is UNTRACKED_CONFIRMED; the other23 combinations are UNSUPPORTED_PUMP_TRADE, always with an empty affected set. Explicit account/context/data bit tables define expected masks and individual conditions independently of cpi_failure_mask(). Input-transaction immutability, mask totals, size and redaction assertions remain.

Verification without a historical object/executable: the24-case test ran with PATH=/tmp/crispy-no-git-executables and GIT_DIR=/tmp/crispy-unavailable-object-db, using the absolute virtualenv Python path. **24 passed in1.18s**, no skip/fallback. No repository metadata or object was removed/modified. Shallow checkouts no longer need the historical baseline object for these tests. This does not remove the separate intentional Git/SHA requirements of live source-integrity preflight.

A simultaneous observation-body RuntimeError and report-write OSError was reproduced **before** correction; the OSError incorrectly replaced the observation failure (one failing regression, log /tmp/bounded-review-before-fix.log). The harness now retains the original body exception while cleanup/reporting runs. A failed report publication increments the in-memory telemetry-integrity counter and attaches only the fixed note `Smoke diagnostic report publication failed; report integrity is unverified.` to the primary error. No raw secondary exception strings are added. File contents may be partial or uncertain; no successful report write is asserted and no persistence retry is attempted.

Failure precedence is tested explicitly:

|Observation body|Shutdown|Report write|Primary failure|
|---|---|---|---|
|Fails|Returns|Fails|Original observation exception, identical object/arguments, with integrity note|
|Returns|Fails|Fails|Original shutdown exception, preserving existing cleanup precedence, with note|
|Fails|Fails|Fails|Original shutdown exception, preserving existing cleanup precedence, with note|
|Returns|Returns|Fails|Original report-write exception; never suppressed into success|

All four cases verify one write attempt, honest attempted shutdown status and reconciled final native accounting. Existing pre/post report-integrity indicators remain unchanged. The original observation does not become a successful observation merely because cleanup completed. No market processing, timing schema, CPI acceptance or diagnostic-limit change was required by this correction.

Validation for the reviewed correction: **60 focused tests passed in3.60s;293 applicable broad backend tests passed in15.03s**, normal exit. The24 no-Git cases and focused tests overlap the broad suite and are not additive. Ruff passed. Mypy passed50 application/helper files; script-inclusive mypy still reports the8 documented legacy errors, without suppressions or new errors. Final secret, whitespace and preservation checks are recorded at handoff. No provider, server or live observation was started.

### Proposed private archival — operator commands only, NOT EXECUTED

The untracked forensic report remains at backend/docs/event-cpi-stale-trade-forensics-20261026.md. Its exact SHA256 is **7756e3588279305ffc28cbf21afd54233da84083e6102c05002ffed81a553a74**. It was not edited, moved or deleted. No source-integrity allowlist expansion is proposed.

From a writable WSL terminal, an operator may first create an exclusive, byte-verified private copy **outside** the repository. This first step intentionally retains the source and therefore does not yet resolve its preflight blocker:

```bash
cd /home/modisa/projects/crispy-winner
.venv/bin/python - <<'ARCHIVE_COPY'
import hashlib
import os
from pathlib import Path
repo = Path('/home/modisa/projects/crispy-winner').resolve()
src = repo / 'backend/docs/event-cpi-stale-trade-forensics-20261026.md'
expected = '7756e3588279305ffc28cbf21afd54233da84083e6102c05002ffed81a553a74'
root = Path('/home/modisa/crispy-winner-private-archive')
assert not root.resolve().is_relative_to(repo)
assert src.is_file() and not src.is_symlink()
data = src.read_bytes()
assert hashlib.sha256(data).hexdigest() == expected
root.mkdir(mode=0o700, parents=True, exist_ok=True)
dst = root / ('event-cpi-stale-trade-forensics-20261026-' + expected + '.md')
with dst.open('xb') as target:  # Existing files are never overwritten.
    target.write(data)
    target.flush()
    os.fsync(target.fileno())
assert hashlib.sha256(dst.read_bytes()).hexdigest() == expected
assert hashlib.sha256(src.read_bytes()).hexdigest() == expected
with dst.with_suffix('.md.sha256').open('x') as manifest:
    manifest.write(expected + '  ' + dst.name + '\n')
    manifest.flush()
    os.fsync(manifest.fileno())
fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
try:
    os.fsync(fd)
finally:
    os.close(fd)
print('Verified archive; original retained:', dst)
ARCHIVE_COPY
```

Stop and inspect the copy/manifest. If any check fails, retain both files and resolve the discrepancy; do not delete or overwrite anything automatically. Only after that review and separate authorization should an operator complete archival by removing the untracked original. This second step rechecks both hashes and the manifest immediately before unlinking, and refuses a tracked source:

```bash
cd /home/modisa/projects/crispy-winner
.venv/bin/python - <<'ARCHIVE_COMPLETE'
import hashlib
import os
from pathlib import Path
import subprocess
repo = Path('/home/modisa/projects/crispy-winner').resolve()
relative = 'backend/docs/event-cpi-stale-trade-forensics-20261026.md'
src = repo / relative
expected = '7756e3588279305ffc28cbf21afd54233da84083e6102c05002ffed81a553a74'
dst = Path('/home/modisa/crispy-winner-private-archive') / (
    'event-cpi-stale-trade-forensics-20261026-' + expected + '.md')
assert not dst.resolve().is_relative_to(repo)
assert src.is_file() and not src.is_symlink()
assert dst.is_file() and not dst.is_symlink()
assert not subprocess.check_output(['git', 'ls-files', '--', relative], cwd=repo, text=True).strip()
assert hashlib.sha256(src.read_bytes()).hexdigest() == expected
assert hashlib.sha256(dst.read_bytes()).hexdigest() == expected
assert dst.with_suffix('.md.sha256').read_text() == expected + '  ' + dst.name + '\n'
src.unlink()  # OPERATOR ONLY after the separate review above; not run by this task.
fd = os.open(src.parent, os.O_RDONLY | os.O_DIRECTORY)
try:
    os.fsync(fd)
finally:
    os.close(fd)
print('Archive retained and verified:', dst)
ARCHIVE_COMPLETE
```

These commands are a proposal, not an executed move. All previous evidence and six protected files remain in place. The source-integrity guard must continue rejecting an unexpected untracked report until verified archival is actually completed. Review/selective publication of the intended release files and a full new published SHA are still required before any separately authorized live qualification. No live-readiness or predictive-performance claim follows from these offline corrections. PRE_COHORT_READY=NO.

Correction handoff checks: all37 captured preservation hashes matched. The external archival snippets were parsed for syntax/newline correctness only; neither was executed. Source report remains byte-identical at its recorded hash. Secret scan passed296 files; Ruff/whitespace checks passed. Exact correction-only diff (relative to the accepted dirty worktree at this task start) is `data/early_edge/bounded-evidence-review-correction-20261027/review-correction.patch`. The prior review.patch and measurements remain unchanged. Publication is conditional on operator-reviewed archival and selective review/publication of the complete intended release; live preflight is not yet satisfied.

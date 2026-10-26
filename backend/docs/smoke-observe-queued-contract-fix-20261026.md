# Legacy OBSERVE smoke: queued process contract correction

PRE_COHORT_READY=NO. Phase 4 unauthorized. Baseline `773e727316a96446f41f61ac072a8f86a83db1b1`, branch `remediation/early-edge-evidence-readiness`. No providers, servers or live probes were started. No original database, frozen report or historical observation was modified. Nothing staged, committed or pushed.

## Confirmed defect and minimal correction

`RadarEngine.drain_events()` invokes `self.process(event, time.time(), queued=True)`. The nested observer in `scripts/smoke_observe.py` accepted only event/now. Argument binding failed before the original processor ran, so the engine's process-finally block could not finish queue accounting or persist/admit a CREATE. The drain exception handler invalidates global coverage for a failed non-trade event and logs only its kind.

Exactly two production-harness lines changed:

```python
def counted_process(event, now=None, *, queued=False):
    # Existing counters and pre-processing observations unchanged.
    ...
    accepted = original_process(event, now, queued=queued)
```

The ellipsis above abbreviates unchanged code; there is no placeholder in implementation. No catch, replay, coercion, new counter or altered rejection predicate was added. The original return value and exception propagate unchanged. Existing launch/migration/trade/curve/state counters still update only after the original method returns, under their original conditions. Queued calls now reach the original durable acknowledgement and terminal-accounting logic; direct calls retain queued=False semantics.

No changes to engine.py, domain.py, discovery.py, truncation.py, conservative configuration, provider budgets, heartbeat timing, 180-second gates or approval semantics.

## Regression evidence

The new test invokes the actual `smoke_observe.main()` and therefore its actual nested observer, not a copied wrapper. Only engine construction/start are replaced for isolation: a real offline RadarEngine and SQLite database are used; start submits events and calls the real drain_events(). Test cwd redirects the legacy fixed data/observe-smoke.json output into a pytest temporary directory. The sampling duration is zero **only in this offline test**; no live probe duration or CLI behavior was changed. Actual engine stop/checkpoint runs and its durable STOPPED receipt is read back.

Before the fix, `test_real_queued_create_matches_unobserved_engine` failed in1.85s: an actual queued CREATE produced the engine's processing-failure log and no token was admitted. Log: `/tmp/smoke-observe-before-fix.log`.

After the fix, the focused seven cases passed in2.36s:

- A valid synthetic on-chain CREATE goes through submit/drain, admits exactly one token, persists exactly one raw event and has processed1/persisted1/pending0/in_processing0 with reconciled counters, including the durable shutdown receipt.
- An equivalent unobserved engine produces identical lifecycle/features/scores/decisions, paper state and no approved evidence. Comparison uses the same stopped lifecycle phase; shutdown intentionally invalidates continuity.
- Duplicate event identity, duplicate mint with a distinct identity and stale CREATE retain explicit rejection dispositions and produce no extra raw records or leaks.
- Direct process calls preserve boolean results and stale-trade/migration rejection counters without manufacturing queue accounting.
- Original RuntimeError identity propagates through a direct observer call. The real queued failure path catches it normally, invalidates coverage and records exactly one exception terminal disposition with no pending/in-processing leak.
- Cancellation at the real five-event cooperative yield accounts for five committed CREATEs and one cancelled detached remainder. Shutdown remains reconciled and checkpoint complete.

An initial post-fix equivalence assertion compared an observed stopped engine against an unobserved still-running engine. That test-only lifecycle mismatch was corrected by stopping both before comparison; no production gate or expected decision was relaxed. The intermediate failure is retained in `/tmp/smoke-observe-after-fix.log`.

## Frozen 600-second report and reset arithmetic

The matching live report is **data/observe-smoke.json**, elapsed600.03s. It records111,543 notifications,118 decoded creates,0 admitted/processed launches,126 engine global resets,0 final heap events and0 dropped events. Discovery records7 transport resets, all7 classified ping_timeout; recovery records1 global reset. Recovery accepted/completed142, with141 UNTRACKED_CONFIRMED and1 UNSUPPORTED_PUMP_TRADE, no pending, overflow or expiry at the report snapshot. Its discovery errors137 equal130 decoding_errors +7 transport errors; those130 are not wrapper exceptions.

**Numerical reconciliation:** 118 +7 +1 =126. After the8 source-attributed global resets,118 engine resets remain. This is exactly consistent with one failed queued CREATE per decoded create under the confirmed wrapper defect. It is **not a retained count of118 TypeError exceptions**: the report lacks a per-exception processing histogram/complete queue lifecycle receipt, and no matching per-event exception log was found. Other unrecorded engine invalidations cannot be excluded solely by subtraction. The deterministic regression proves the wrapper's failure mechanism, not a reconstructed exception count for every historical event. Historical in-processing leaks cannot be counted exactly from this report's empty heap.

The similarly named `data/early_edge/observe-smoke-no-discovery-773e727.json` and `observe-773e727-console.log` describe a different600.01s attempt with discovery disabled, zero notifications/creates/resets. They must not be substituted for the enabled live report or used as a matching processing-exception log. The earlier pre-run backup report is also preserved.

**Seven WebSocket ping timeouts remain unresolved.** This signature fix does not alter ping/pong behavior, timeouts, provider load, parsing or continuity rules and is not evidence that any timeout was caused or cured by the observer. The failed probe cannot be retroactively turned into a successful continuity or signal-quality study.

## Broader offline validation and existing failures

Relevant suite: **293 passed,2 failed in18.19s**, normal test-process exit with failure status. It includes the seven new cases plus observe enrichment, prospective pilot, discovery qualification, evidence accounting, shutdown, trade-gap scoping, canonical trades, truncation, buffers and transport diagnostics. Log: `/tmp/smoke-observe-regressions.log`.

Both failures are unchanged `test_observe_enrichment.py::test_free_observe_funnel_bounded_and_conservative[90/100]`. They also fail when run alone without collecting the new smoke tests (2 failed in1.94s). Their async curves(mints,size) mock does not accept the existing price_inputs keyword passed by the unchanged hot acquisition path, which catches the TypeError and safely submits unavailable curve state. These tests do not import/use the modified diagnostic script. Engine/provider/test source is unchanged; no fix or suppression was bundled here. Logs: `/tmp/smoke-observe-existing-enrichment-isolated.log`. The broad suite is not reported as green.

Ruff passes for the script and new tests. Mypy passes49 backend application files. Including the smoke script reports8 pre-existing errors: dynamic method assignments and numeric min/max dictionaries inferred as None. Checking the published script from Git against the same application reports9 errors; this patch removes the process-wrapper incompatible-signature error at line106. The remaining8 locations/categories match the baseline; no ignore directives or unrelated annotation changes were added. Logs: `/tmp/smoke-observe-mypy-baseline.log`, `/tmp/smoke-observe-mypy-current.log`, `/tmp/smoke-observe-mypy-app.log`. Script-inclusive mypy is **not** reported as passing.

## File scope, integrity and next step

Intended changes only:

1. scripts/smoke_observe.py — signature at line63, forwarding at line67.
2. backend/tests/test_smoke_observe.py — actual-harness offline regressions.
3. This engineering report.

Six unrelated local files remain outside this scope. Available frozen pilot/qualification files, both unsuccessful600-second reports/logs and local continuity receipts are preservation-hashed in `/tmp/smoke-contract-preservation.json`. The earlier recently authored standalone continuity Markdown is not present in the current checkout; it was not recreated, removed or edited here. Existing historical continuity documentation is untouched.

Local HEAD remains the published baseline. The working tree contains an unpublished harness correction: it must not be represented as the published baseline's behavior. Any future source-integrity qualification must use the complete reviewed successor SHA and ordinary preflight, preserving the unrelated-change allowlist; do not weaken the guard or backfill the old probe. This task adds no source guard to the legacy smoke and does not assert that invoking it alone freezes source identity.

Recommend review of this narrow correction and the separately documented pre-existing test/type-check failures before publication. Any subsequent live smoke requires separate authorization; none started automatically. No claim of genuine CURRENT coverage, useful predictive signals or profitable executable outcomes follows from offline synthetic tests. PRE_COHORT_READY=NO.

Final preservation: all27 captured files matched their initial SHA256 values. Secret scan passed292 source/document files; tracked diff and new-file trailing-whitespace checks passed. No unrelated file was modified or staged.

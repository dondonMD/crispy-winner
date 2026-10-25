# Pre-graduation research instrument qualification — 2026-10-25

**CONTRACT NOT QUALIFIED. Phase4 unauthorized. PRE_COHORT_READY=NO.** The existing hypothetical state-quote instrument has substantial tested safeguards, but does not satisfy the requested independently sourced executable-route quote contract. Synthetic fixtures establish software behavior only, not real quotes, profits or predictive success.

Reviewed source `14f301e8a2aa8d386772b8abc09be67167b04fd1` on `remediation/early-edge-evidence-readiness`. Only addition besides this report: [test_research_instrument_contract.py](../tests/test_research_instrument_contract.py), seven deterministic characterization cases. No application, schema, settings, threshold or protocol changes. No live requests, real cohort or market observations. Test studies use explicitly synthetic manifests and temporary isolated databases.

## Existing contracts must remain distinct

[OpportunityResearch](../app/opportunity_research.py) records action transitions and provider-derived descriptive price/curve outcomes. It freezes research/core versions and cost settings and atomically persists outcomes with pending progress. Its baseline is the signal-time provider price, not a T+10 route quote; repeated transitions are not the early-edge study's independent sample rule. It has no matched risk-set comparison or provider route contract. Its estimated after-cost outcomes cannot be promoted into executable returns or approval.

The separate [early-edge study](../app/early_edge.py), [design](../app/early_edge_design.py), [observer](../app/early_edge_runtime.py) and [report](../app/early_edge_report.py) implement frozen pre-grad eligibility, risk-set matching, immutable evidence, entry deadlines, missingness and clustered comparison. [ResearchExecutionOracle](../app/early_edge_quotes.py) reads verified coherent accounts and applies pinned Python quote math. This is level2 hypothetical snapshot calculation, not a provider-issued routable quote or simulation. Its sources are pinned Pump SDK4.1.0 and PumpSwap SDK2.1.0; exact integrity/source hashes are retained in [early_edge_sources.json](../app/early_edge_sources.json). Golden agreement does not independently establish current deployed-program compatibility or route availability.

## Requirement-by-requirement decision

PASS below means the stated offline behavior passed, not live qualification. PARTIAL/FAIL blocks the complete requested contract.

|Requirement|Implementation evidence|Focused test evidence|Status|
|---|---|---|---|
|Immutable contemporaneous eligibility/version/features|`signal_snapshot`, `Study._enroll_one`; no graduation, curve<85, verified current curve, canonical units, readiness, no hard failure/creator sale/disagreement; JSON copies and DB immutable triggers|Existing snapshot purity, safeguard, historical/version-drift and manifest tests|PASS for isolated early-edge study|
|Comparable controls at T|`risk_set`: exact timestamp, quote mint, curve/age bands, security status, same readiness; closest curve/age then lexical mint, no replacement; immutable original pair survives crossover|Exact-time tie-break/readiness/crossover tests; positive and negative matched scenarios|PASS for supplied observable set; completeness of real sampling remains unverified|
|Prevent repeats, retrospective entry and favorable-only enrollment|First per arm/mint/session, repeated observation counter, fixed manifest, unmatched pair persisted, no interruption backfill|Dedup, historical refusal, restart, capacity and new unmatched/missed-entry test|PASS for enrolled observations|
|Account for rejected and missing attempts|`signal_snapshot` returns None on refusal; observer maintains bounded coverage summaries; `ee_quality` stores infrastructure quality|New refusal characterization proves snapshot API does not emit a durable reason receipt|PARTIAL: no complete immutable reason-coded attempted-observation/selection funnel|
|T+10 timing and bounded acquisition|Request starts>=T+10, acquisition<=T+20; confirmed coherent state acquired within5s and fresh<=20s; primary USD4; earlier requests cannot supply fills|New9.999/10/20/20.001 boundary cases; existing first-state/no-future-best tests|PASS for state-based hypothetical calculations|
|Independently issued executable entry quote|`ee_entries` stores calculation, input/output, SDK source and state request/acquisition/slot/hashes; `StateObservation` has no route-provider quote expiry/status contract|New receipt characterization proves successful state calculation contains no route ID/availability/provider/expiry|FAIL: numerical state estimate cannot substitute for route quote|
|Predeclared exit horizon and first valid observation|Primary T+300 from signal, secondary60/180/600/1800; bounded exit acquisition delay20s; no carrying pre-boundary requests or future-best selection|Existing horizon/expiry tests; new unsupported-sell test|PASS for hypothetical timing; provider sell route/expiry remains FAIL|
|Costs, impact, liquidity and quote units|`pump_buy`/`sell`, verified mint/vault/reserve checks and `result_costs`; embedded protocol fees/impact once, external network/priority/failed reserve, extra1% each-leg manual reserve, rent lockup separate|SDK goldens, account/units/slot tests, cost/rent-ledger tests|PARTIAL: controlled-state math passes; actual interface fees, route constraints and current quote compatibility not established|
|Unavailable entry/exit is not a winning exit or -100% loss|Deadline exhaustion writes unavailable status; unsupported/zero quote never proves economic zero; automatic ECONOMIC_ZERO_EXIT disabled|New unsupported sell and missing-entry/backfill tests; existing failure/rate-limit/deadline tests|PASS for state instrument; provider reason taxonomy/expiry validation absent|
|Full primary denominator and missingness|Reports retain unmatched signals, terminal unavailable, pending, capacity/gap/session quality and coverage; unresolved primary outcomes block strongest status|Missing control denominator, new paired unsupported sell, no interim approval and incomplete-outcome tests|PASS for enrolled primary observations; pre-enrollment refusal/censorship funnel PARTIAL|
|Meaningful comparison|Frozen300s after-cost mean, normal CI and fixed-seed10,000 mint-cluster bootstrap; immutable pairs; missing controls/unmatched remain explicit|Deterministic positive/negative pair tests and mint-cluster/crossover tests|PASS for hypothetical inputs; no executable or prospective predictive conclusion|

The new characterization tests deliberately pass when a documented gap is present; they are not “all requirements passed” assertions. The complete contract verdict remains NOT QUALIFIED.

## Minimum executable-quote contract still required

No provider is selected or called in this task. Smallest external requirement: a read-only source that can quote both directions for supported Pump/PumpSwap venues and the exact token quantity, without wallet secrets, signing or submission, and supplies enough versioned metadata to validate the following receipt. If the source needs an unsupported wallet/route capability, that path remains unavailable; do not fake an anonymous executable route.

1. Freeze treatment and control eligibility at T, research/config/source identity, signal evidence and deterministic pair. Append bounded auditable refusal/matching receipts with fixed reasons before filtering: rejected/ineligible, missing units, stale source, readiness failure, unmatched and infrastructure/storage censorship. Record summary totals plus lossless evidence references; do not require unlimited raw snapshots. Distinguish discovered candidates, attempted observations, eligible unique signals, selected controls and repeated observations. Nonselected control candidates are selection accounting, not invented independent outcome samples.
2. At or after T+10, request an exact-amount provider quote; record scheduled boundary, actual request/response/acquisition times, provider quote creation/context timestamp or slot, source/version, quote identifier/hash, venue/route, base/quote mints and decimals, input and quoted output, minimum output/slippage constraint, notional/USD reference, fee decomposition, available liquidity/impact when actually supplied, and provider expiry/time-or-slot validity. Store only necessary sanitized fields, never opaque transaction blobs or credentials. Validate temporal ordering and units. A quote acquired by T+20 must still be unexpired when evaluated. Do not invent an expiry or replace missing input fields with spot prices. A provider quote is still conditional, not a guaranteed fill or confirmed transaction.
3. Freeze the first valid receipt; keep prior failed attempts and reason codes. A late response, expired quote, missing/unsupported route or provider gap terminates as UNAVAILABLE with its specific reason when the predeclared window closes. Never search later prices for a better entry. The current T+10..T+20 window and hypotheses are not changed by this report.
4. Request sell quotes for the acquired hypothetical quantity at predeclared signal-relative horizons, validating route and expiry using the same contract. Canonical migration/verified pool identity is required where venue changes. Preserve separate gross proceeds, quote-embedded fees/impact and external interface/network/priority/failure/slippage reserves; report recoverable rent separately. No double counting or assumed free exit. A NO_ROUTE response is an unavailable quote with reason, not proof of permanent economic zero. Economic-zero classification remains disabled pending its separate canonical proof rule.
5. Retain all enrolled signals and chosen controls in denominators with measured, pending, unavailable and censored totals. Report both primary accounting and resolved-economic coverage, by arm and session quality. No favorable-only completion or exclusion of degraded sessions. Quote-attempt availability must be distinguished from SDK-calculation success. Match/report only frozen signal-time information; pair/mint dependence remains clustered. Primary outcome and supported-status gates cannot be satisfied by substituting secondary horizons or synthetic results.

A reviewed provider-receipt validator plus a small persistent reason-coded attempt ledger are the minimum next implementation work. They must be separately authorized/tested against success, expired/late/missing quote, unknown units, no sell route, partial fees, duplicate delivery, cancellation/restart and storage censorship. Until a provider can supply this evidence, retain snapshot-model returns under their existing descriptive semantics; do not relabel historical MEASURED outcomes as executable outcomes. No production integration or new route protocol has been implemented here.

## Validation, preservation and publication

Command:

```bash
.venv/bin/python -m pytest backend/tests/test_research_instrument_contract.py backend/tests/test_early_edge.py backend/tests/test_readiness_quotes_controls.py backend/tests/test_opportunity_research.py backend/tests/test_early_edge_scheduling.py -q
```

**167 passed,1 skipped in25.65s, normal exit0.** The skipped SDK-reference case remains skipped, not live parity proof. Existing pinned golden fixtures ran without installing/executing npm packages. Tests use only synthetic state, isolated temporary DBs and existing mock transports. Ruff on the new test file passed. Secret scan, whitespace/link checks and frozen/unrelated-file preservation are checked before delivery; full suites/build/performance experiments are unnecessary for tests/documentation only and were not repeated.

Ignored local validation receipts: `data/early_edge/instrument-qualification-20261025/`. The five unrelated worktree files, frozen originals, private Phase3 receipts and retired cohort database remain unchanged. No real prospective cohort was created; test-only synthetic databases cannot be counted as prospective evidence. No approval, wallet/trading behavior, post-grad strategy, event decoder or runtime source changed.

Publish only these two intended files from a writable WSL terminal (Git metadata is read-only here):

```bash
git switch remediation/early-edge-evidence-readiness
git add -- backend/tests/test_research_instrument_contract.py backend/docs/pregrad-research-instrument-qualification-20261025.md
git diff --cached --name-only
git diff --cached --check
git diff --cached
git commit -m "test: qualify pre-graduation research evidence contract"
git push origin remediation/early-edge-evidence-readiness
```

Staging must contain exactly those two paths; exclude private receipts and unrelated changes. No commit/push attempted here. **CONTRACT NOT QUALIFIED; live quote availability unverified; Phase4 unauthorized; PRE_COHORT_READY=NO.** Stop before implementation or collection.

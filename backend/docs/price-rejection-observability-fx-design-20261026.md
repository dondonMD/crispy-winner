# Bounded reserve rejection telemetry and FX scheduling design

**Implementation scope: diagnostics only. FX scheduler unchanged. PRE_COHORT_READY=NO; Phase4 unauthorized.**

Baseline inspected: `c65494dd0f3e0c55894919c4801a44d4b8c9d225` on `remediation/early-edge-evidence-readiness`. Read the complete `price-evidence-coverage-root-cause-20261026.md` and corresponding source before edits. That report, the completed pilot and qualification remain frozen. No live provider, DEMO/OBSERVE server, cohort, wallet or execution was started; no staging/commit/push.

## A. Confirmed source problem and minimal correction

`early_prices.reserve_state()` previously raised the same `QuoteUnavailable("UNSUPPORTED_CURVE_STATE")` for supply mismatch, completion, Mayhem and any nonzero depth/post-completion amounts. `providers.curve_progress_batch()` exposed only the public reason; engine hot polling retained counts but discarded the full state. Thus the frozen179 failures cannot be decomposed retroactively. Source also proves `max_products=1` can leave a required quote's FX reference stale; that is evaluated separately below.

The original state rejection predicate, order and short-circuit behavior remain verbatim. Only **after it already rejects**, the code creates fixed numeric detail. There is no additional acceptance route or skipped check. Rejected unknown quotes keep the original earlier rejection order; they do not acquire invented state subreasons from fields that were never checked. The exception is still exactly `QuoteUnavailable`, with unchanged `.reason`, `str()` and `.args`.

A private `_reserve_rejection` attribute carries `(condition_mask, quote_category)` on that exception. Both elements are integers, not account fields. The RPC adapter carries it as a transient internal report field, then the engine consumes it solely for hot acquisition diagnostics. It is explicitly excluded from submitted curve-event evidence, alongside price_state/price_status. External market/provider schemas, canonical decoders, accepted reserve-state dictionaries, price formula/version/timestamps, persistence acknowledgement, first-review provenance, classifications and processing rules are unchanged.

### Fixed mask and counter semantics

| Bit | Fixed condition name | Meaning at the original rejection branch |
|---:|---|---|
|1|CURVE_COMPLETE|complete was true|
|2|MAYHEM_MODE|is_mayhem_mode was true|
|4|SUPPLY_MISMATCH|verified mint supply differed from curve total supply|
|8|NONZERO_DEPTH|depth was nonzero|
|16|NONZERO_POST_COMPLETE_BASE_OUT|post_complete_base_out was nonzero|
|32|NONZERO_POST_COMPLETE_QUOTE_IN|post_complete_quote_in was nonzero|

There are64 fixed bins. Mask0 means **diagnostic conditions unknown**, not “no rejection.” Masks1–63 preserve exact combinations, including all six together. Missing diagnostic fields produce unknown detail after the original rejection, without replacing it with a new exception. Malformed canonical accounts still fail earlier through their original paths.

`reserve_rejections` is an additive namespace in the existing version2 price-diagnostic receipt/HEALTH summary, with its own `version=1`:

- `rejected_state_attempts`: sum of64 mask bins, one per rejected state attempt.
- `condition_masks`: keys `"0"` through `"63"`, numeric counts;0 is unknown.
- `condition_counts`: six fixed names; each increments for its condition. Their sum can exceed rejected attempts and **must not be used as an attempt denominator**.
- `multi_condition_attempts`: masks with two or more bits, counted once per attempt.
- `unknown_condition_attempts`: mask0 count.
- `state_quote_categories`: UNKNOWN/SOL/USDC/UNSUPPORTED_IDENTITY numeric counters for state rejections. Normal state rejections have a permitted SOL or USDC category; unsupported identity is never promoted to a state.
- `unsupported_quote_categories`: same fixed category vocabulary for quote rejections; ordinary current failures count UNSUPPORTED_IDENTITY. Missing old metadata is UNKNOWN. These are not counts of all accepted/validated quote states.
- `invalid_updates`: malformed/unrecognized retained metadata count; no arbitrary keys or values are copied.
- `reconciled`: state mask total and state quote total must equal the existing UNSUPPORTED_CURVE_STATE count; quote category total must equal existing UNSUPPORTED_QUOTE count.

The source-defined quote codes are0 unknown,1 SOL (native zero normalized or WSOL),2 USDC,3 unsupported identity. No unsupported address, reserve quantity, mint, transaction, credential or endpoint is retained in this new namespace. Its rejection metadata cannot alter an existing public price status. Non-rejection status updates do not enter these histograms.

Legacy receipts without this namespace restore their existing public rejection totals into UNKNOWN bins. No old subreason is inferred; no historical row is rewritten by this task. Corrupted/new-version or malformed detail stays unknown or reports invalid/reconciliation failure. Restored whitelists cannot introduce arbitrary keys. An inconsistent namespace does not change stage counters or market decisions.

### Durability, limits and compatibility

The existing flush and evidence_runs write path is reused. No new write call, table, polling round, subscription or callback is introduced. Existing48,000-byte receipt,32 token,24 review,25 inflight and32 session limits remain. If byte pressure removes sampled rows, existing byte-omission counters remain explicit; the aggregate namespace is preserved. Original counters, omissions, immutable first reviews and public statuses remain intact. Older consumers can ignore the additive namespace. Consumers requiring exact JSON equality must account for this additive diagnostic field; market-event payloads are unchanged.

Legacy179/215 totals would be categorized as unknown if restored in an isolated copy—not retroactively assigned conditions. Existing UNKNOWN_DIAGNOSTIC_EVICTED labels are untouched; they still do not prove an individual eviction. The new histograms explain future aggregate rejected-state composition, not an unbounded per-token chronology.

### Equivalence and resource evidence

Deterministic tests cover all64 combinations of the original six-condition predicate, individual conditions and overlaps, quote normalization/restriction/order, same exception contract, malformed accounts, missing fields under original short-circuit rejection, overlapping counts, restore/legacy unknowns, arbitrary-key injection, corrupted details and reconciliation, numeric retention and byte-pressure omission accounting.

Real SolanaProvider response parsing is tested offline using synthetic same-batch accounts and mocked RPC. Real isolated offline RadarEngines compare queued processing with and without the transient detail: stage counters, terminal/persisted accounting, state, features, scores, decisions, intelligence results and empty paper positions agree; no approval appears. The transient field never enters persisted market events. Existing price/FX freshness, baseline no-backfill, persistence/cancellation/shutdown, V2.1 and pilot regressions also pass.

A bounded local micro-measurement (three repeats, no market replay) gave median condition-mask computation2.21µs, aggregate recording0.91µs, snapshot57.46µs. The new work is per rejected acquisition and diagnostic snapshot, not per trade. Arrays have64 mask bins plus eight quote bins; memory cardinality does not grow with tokens or attempts. Ten thousand synthetic updates retained a roughly1.1KiB serialized namespace. These are component measurements, not live CPU/RSS or sustainable-throughput guarantees.

For a serialization-only copy of the frozen final receipt, adding unknown legacy bins changes32,498 to33,632 bytes, below48,000. The largest frozen HEALTH record was3,843 bytes; adding a populated synthetic namespace yields4,835 bytes, below16KiB. Neither copy was written back or treated as newly observed evidence. An explicit byte-pressure test confirms48k enforcement with omissions; no resource limit was raised.

## B. Separate FX scheduling proposal — NOT IMPLEMENTED

### Actual current behavior

1. Hot polling gathers a set of quotes from validated states, then calls `UsdReference.refresh(needed_quotes, max_products=1)` under a2s wait_for.
2. Supported products are Coinbase SOL-USD and Kraken USDCUSD. Needed products are sorted by product-specific `last_attempt`, stable SOL-first tie-break; only the first is considered. Products beyond the budget generate budget_skipped diagnostics.
3. That product is skipped if its last attempt is less than10s old. An attempted product's timestamp is updated before its request, including failures/cancellation; a later retry must respect it.
4. Existing reference cache is reused by mark construction only if **both** publication and acquisition timestamps remain within20s with no future time, correct source/product and finite positive value. Generic HTTP connected health is irrelevant to reference validity. Rejected refreshes do not extend cache expiry.
5. HttpProvider has rate0.2 (5s minimum request spacing), concurrency2, provider cooldown/rate-limit handling and retry_attempts=1 for FX. This serial hot caller requests at most one product per poll. Sharing the httpx client with DEX does not share its provider limiter or prove absence of connection-pool/host delays.
6. The2s timeout includes limiter/cooldown/request awaits. Cancellation remains explicit in diagnostics. Raising max_products to2 would conflict with5s pacing inside2s; it is not an approved solution. A cancelled or stale refresh cannot justify a second out-of-budget request or a fabricated reference.

Frozen observations establish34 successful SOL refreshes and four USDC HTTP completions (three usable, one publication-stale). Seven mixed-quote polls had one product skipped. They show the coverage problem, but not what an unmade alternative request would have returned at that time.

### Alternatives within one request per existing hot poll

| Design candidate | Rule | Load bound | Principal issue |
|---|---|---|---|
|Current LRU|Refresh least-recently-attempted needed product, regardless of whether cache is already fresh|At most one request per poll; current pacing/cooldowns|Fair to attempts, not to number of affected token states; can refresh one small cohort while the other reference expires|
|Fresh-cache-aware LRU|First validate cache with the original FX predicate; reuse genuinely fresh references, otherwise retain recency ordering among needed eligible products|Same or fewer requests, no new polling|Little gain when every poll is31s apart and validity is20s. Cache may expire before RPC/mark acceptance; must revalidate at actual construction, never assume a predicted lifetime|
|Missing-demand weighting|Among needed products without usable references, choose the largest number of current validated states; recency tie-break|Same maximum one request per poll|Can indefinitely starve the smaller USDC cohort; changes missingness/comparison population. Not acceptable as an ungoverned production policy|
|Fairness-bounded weighting|Use fresh-cache reuse and demand weighting, but force service after a predeclared finite number of missed eligible mixed rounds; retain cooldowns and10s attempt floor|Same maximum one request per poll; no background task|Fairness rule/meaning of missed round require approval. Still cannot make both products fresh in every mixed batch; deadlines, stale publications and timeout can defeat either choice|

No candidate changes request frequency, max_products, deep set, RPC composition or market polling. Nothing proposes relying on a stale ref, requesting before the actual signal then assigning it a later timestamp, or moving a later mark back across an immutable baseline. A fresh reference is not itself a token price; all original state/slot/account/unit requirements and mark acceptance must still pass.

### Deterministic design comparison (fictional states, not live prices)

Test-only simulations use four existing rounds31s apart,14 SOL states and one USDC state each round, expired prior caches, and assume the selected provider always immediately supplies a fresh valid reference. They yield:

| Policy | Requests | Toy states with a newly refreshed quote reference | Minority coverage |
|---|---:|---:|---|
|Current LRU|4|30|Served on alternating rounds|
|Demand weighting|4|56|USDC never served: starvation counterexample|
|Illustrative fairness after two missed rounds|4|43|USDC served once|

The value “two missed rounds” is an illustrative design parameter, **not** an implemented threshold or a recommendation optimized from returns. The adapter's actual existing LRU selection matches the simulated four-call sequence under a mocked request boundary. No external request occurred; the real HTTP limiter was inspected, not replaced in production or load-tested. Tests also show fresh-cache reuse can avoid a request when all needed refs are truly fresh, preserve the10s attempt interval, and cannot make stale/future/missing FX pass the existing validator.

These numbers demonstrate mechanics and risk only. They do not estimate recovered historical marks, baseline coverage or profit. In particular, one historical USDC response was already publication-stale; an unmade SOL request's publication timestamp, latency, timeout behavior and token state are absent. **Historical counterfactual improvement: UNKNOWN.** No frozen USD failures or unavailable outcomes can be revised.

### Proposed review decision and disqualifiers

Do not deploy the maximum-demand rule: the starvation counterexample is deterministic. If a scheduler change is separately authorized, prototype only fresh-cache-aware selection with an explicitly approved fairness contract inside the original one-request budget. Freeze its version/selection rules before another prospective measurement. Require actual construction-time revalidation, unchanged request attempts/cooldowns/timeouts, bounded state, and cancellation-safe diagnostics. Do not weaken predicates to meet a desired coverage count.

Before implementation, settle the fairness rule and whether serving more majority-quote states at the cost of minority coverage is consistent with the research estimand. Test cooldown,429, slow/cancelled HTTP, stale publication, publication/acquisition expiry during RPC, all-fresh/no-needed sets, ties, repeat mixed batches, no starvation, missing denominators, and immutable pre/post-signal separation. Any proposal requiring an extra request, timeout increase, background refresh, larger deep set or relaxed freshness is outside this design and needs separate approval. Evidence of higher mark availability still would not validate predictive accuracy or execution economics.

## C. Validation, changed files and next steps

Intended changes only:

- `backend/app/early_prices.py`: attach numeric detail after the unchanged rejection.
- `backend/app/providers.py`: transient internal detail transport, no external-schema change.
- `backend/app/engine.py`: aggregate detail and exclude it from curve evidence.
- `backend/app/price_diagnostics.py`: additive receipt namespace and legacy restore.
- `backend/app/reserve_rejection_diagnostics.py`: fixed masks/categories/aggregation.
- `backend/tests/test_reserve_rejection_observability.py`: diagnostic equivalence and durability cases.
- `backend/tests/test_fx_scheduling_design.py`: test-only selection alternatives; no production import/use.
- This engineering report.

Validation: **408 passed,1 skipped in24.64s**, normal exit0, across the new tests plus early-pricing, diagnostic, pilot, V2.1, shutdown, event-accounting/remediation and early-edge/golden suites. The skip is the existing opt-in isolated official Node SDK reference; ordinary pinned golden checks ran. No SDK installed or live provenance command executed. Initial development failures were confined to a new fixture assuming offline/DEMO constructors create PriceResearch; the corrected fixture explicitly creates it on an isolated offline engine. No unresolved regression failure remains.

Ruff passed; mypy passed49 source files (explicit package bases); basic secret and whitespace checks passed. Preservation checks cover21 captured files (six unrelated paths, the root-cause report, frozen pilot and qualification files), plus existing preservation manifests. No historical data or outcomes are rewritten; no new market samples are claimed.

Next: review only this diagnostic change and the independent design proposal. Publication is not performed here. After separately reviewed publication, authorize a bounded non-enrolling validation if desired to observe whether new aggregate masks reconcile and stay within budgets. Do not automatically repeat the20-minute pilot. A scheduling change requires its own authorization and tests first. New source SHA/diagnostic version must be recorded in any subsequent manifest; no append/backfill to the frozen original study, and any acquisition-policy change must be analyzed separately because it changes missingness/selection. Gross indicative marks remain non-executable and carry no claimed net profit.

**PRE_COHORT_READY=NO. Phase4 unauthorized.**

## Final publication review — defensive isolation

The final review reproduced two telemetry isolation defects with seven initially failing fault-injection cases: condition computation could replace the already-decided QuoteUnavailable, and aggregation failure could abort normal curve-event submission. Both are now corrected. No original rejection predicate, order or accepted outcome changed.

The original QuoteUnavailable is created before optional mask calculation. A narrowly scoped `except Exception` covers only telemetry import/computation/shape checking; failure attaches unknown mask0 and a numeric/Boolean failure marker, then raises the original exception. Invalid computed mask types/ranges are treated the same way. No diagnostic exception text is retained. Cancellation/process-control BaseExceptions are not broadly suppressed. Errors in original account decoding, pricing and providers remain outside this catch.

The provider transports the fixed failure marker privately. Engine aggregation alone is guarded; a failure increments a dedicated counter owned by PriceDiagnostics, outside the possibly failed aggregator, and processing continues with unchanged curve-event payload. Both private fields are stripped before submission. Failures before aggregation or after a partial/successful aggregate update therefore cannot strand or change the event.

The additive namespace now also contains:

- `calculation_failures` and `aggregation_failures`: nonnegative, saturating at2,147,483,647, fixed-field telemetry failure counters.
- `telemetry_integrity_failed`: sticky across subsequent updates and restart whenever either counter is nonzero.
- `snapshot_available`: false if even the optional subreason snapshot fails or returns an invalid shape. In that case the receipt contains an explicit bounded failure namespace, not fabricated histograms.

A telemetry failure forces **namespace `reconciled=false`**, even if numeric totals happen to match. Original acquisition stage counters/attempt reconciliation retain their original independent meanings. Snapshot isolation covers only the new diagnostic namespace; it does not hide existing FX, account, persistence or pricing errors. A good later update never clears the historical telemetry failure. Persisted failure counters restore conservatively; malformed counter values become explicit failure, not silent zero. No extra write or network request is introduced. A serialization-only illustration of the final additive shape changes the frozen32,498-byte receipt to33,751 bytes, below48,000; the historical receipt itself is untouched. Prior component micro-measurements above predate these final guard checks and are not claimed as new end-to-end measurements.

Fault-injection coverage includes RuntimeError/ValueError/TypeError during calculation, malformed computed masks, actual RPC-adapter propagation, aggregation failure before and after updating counters, snapshot exception/malformed return, durable integrity failure/restoration, unchanged real queued processing and market payloads, and original non-telemetry errors continuing to propagate. Valid states never invoke rejection telemetry. All64 normal mask cases still pass.

**Final validation supersedes the initial result above:**423 passed,1 expected opt-in SDK-reference skip in25.34s, normal exit0, using the same relevant regression suites. Ruff and mypy (49 source files) passed. The FX runtime file is unchanged; design simulations remain test-only. Secret/whitespace and preservation checks are repeated at delivery. No live provider/server or new study was started.

### Root-cause document publication decision

Read all202 lines of `price-evidence-coverage-root-cause-20261026.md` and checked consistency with this report. Its890/215/179/496/59/437 funnel,88 baselines,101 comparisons, unresolved subcauses and non-counterfactual limitations agree. The old detailed subcauses remain UNKNOWN; this new implementation cannot repair them.

No URLs, Base58-address-shaped identifiers, credentials, token-level mint histories or wallet identifiers were found. It does contain one internal session UUID, the exact private frozen-run locator and ledger fingerprint. These are operational provenance, not authentication secrets, but publishing them is unnecessary for this narrow code change. **Recommendation: keep that original report as an unchanged local research artifact for this publication.** If desired later, separately review a redacted aggregate public version. Do not automatically stage or edit the original. The eight-file engineering report already supplies the relevant rationale without needing that ninth file.

The six unrelated files, root-cause document, frozen pilot and qualification remain preserved. Nothing has been staged, committed or pushed. After review, publish only the eight files listed above; do not use `git add .` or `git add -A`. PRE_COHORT_READY=NO; Phase4 unauthorized.


Publication-preflight limitation: if the root-cause report is kept untracked at its current backend/docs path, the existing source-integrity guard will correctly refuse a later qualification/pilot, because it is outside the six-file unrelated allowlist. Before any future authorized run, explicitly decide whether to publish that additional document or preserve a byte-identical copy in an ignored local research location and resolve the untracked source-tree path. No move, ignore-rule/allowlist change or extra staging was performed here; do not weaken the guard. This does not affect the completed offline validation.

# Verified early price evidence — bounded observation path

Baseline `610b8a35ff3df1235371774a658aaad895eed991`, branch `remediation/early-edge-evidence-readiness`. PRE_COHORT_READY=NO. No Phase 4 activation, market-data collection, wallet, transaction, staging, commit or push.

## Why the saved run has no price marks

Session `39cf31f1-a579-4b50-8690-714f92a25422` contains six unique speculative reviews. Read-only immutable SQLite inspection (WAL size zero) found 145 create, 6,173 trade, 250 curve, two security and one migration event; **zero nonzero event prices**. These are persisted event categories, not claims that every trade was usable. Existing `enrich_once()` passes only graduated tokens to DEX Screener; `DexScreenerProvider.markets()` accepts only PumpSwap pairs. This intentional post-graduation source cannot provide pre-graduation curve prices. No inference about DEX Screener's chain-wide coverage follows from its absence here. Completion percentage and trade direction do not supply a price.

The six historical reviews remain unchanged and receive no retroactive baseline or outcome. None establishes executed prices, profits or predictive value.

## Source and calculation

The existing hot curve RPC batch can now request the same tokens' mint metadata plus canonical WSOL/USDC mint accounts **in the same confirmed getMultipleAccounts context**. Derived Pump curve PDA, program ownership/discriminator, supported schema, initialized mint metadata, supply identity, decimals and quote identity are checked. Existing reviewed `decode_account()`/`mint_info()` are reused. Unsupported account versions, unknown quotes/extensions, mismatched metadata, complete/mayhem/depth/migration states and missing reserves fail closed. No PumpSwap or trade-event decoder is changed.

The mark is explicitly **model-derived indicative marginal virtual-reserve value**, not an executed price:

`quote per whole token = virtual_quote_raw / virtual_base_raw × 10^(base_decimals − quote_decimals)`

`USD mark = quote-per-token × independently observed quote/USD reference`.

The ratio is the marginal derivative of Pump's documented synthetic constant-product curve. Real reserves are not substituted for virtual reserves, and percentage completion is never used. It is not a finite-size SDK buy/sell quote and includes neither fees nor finite-size impact. Actual sellability, route availability and executable liquidity remain unknown.

Official provenance already pinned in `backend/app/early_edge_sources.json`: `@pump-fun/pump-sdk@4.1.0`, git `b1a02a5ca87b4a7f3715a3cb921e503e1c2b3a66`; `src/bondingCurve.ts` SHA256 `c9d796111d676861d6fe6359cc96dd045afda4bd4bf1702f48d326cb3d5910da`. The bundle's current SHA256 is `2b0c24a4842d301d9448270c1ce4697f5376bcd274b9e3d084a5661b46fd2fdb`, included in every mark. This account/math provenance is separate from the later Pump TradeEvent schema revision. Pinned schema compatibility with future live account bytes is conditional on successful strict decoding; no fresh live compatibility claim is made here.

Official documentation checked 2026-10-26:

- [Pump program documentation](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_PROGRAM_README.md): canonical curve PDA and synthetic reserve invariant. Narrative examples may describe older fees; no fee assumptions are copied from them.
- [Coinbase Exchange product ticker](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-ticker): last-trade snapshot with price/time; the existing SOL-USD adapter is reused.
- [Kraken public recent trades](https://docs.kraken.com/api-reference/market-data/get-recent-trades): timestamped trade prices; the existing USDCUSD adapter is reused. No assumed $1 peg. Unexpected response naming or stale trades remains unavailable.

No SDK installation or execution is added. No private RPC endpoints appear in receipts.

## Timing, integrity and bounded acquisition

Each mark captures mint, venue, raw reserve units, verified decimals, curve identity, account hashes, confirmed context slot, state request/acquisition times, USD reference source/publication/acquisition times, composite observation/acquisition time, currency, source-schema hash and verification level. Composite observation time is the later of state and FX acquisition; a later FX reference is never backdated to curve acquisition time. Both inputs must be available and no more than 20s old; state acquisition must complete within 5s. Provider quote expiry is explicitly unknown; `valid_until` is a local freshness deadline, not invented provider expiry. Source disagreement, regressing slots/times, altered prices/units and malformed receipts are rejected.

Curve events are submitted before USD reference I/O, with unchanged original curve evidence; mark metadata never becomes a market event or changes `token.price`. The new path asks for at most one needed public FX product per hot poll (oldest attempted first), bounded by a two-second wait. Existing reference callers retain their two-product defaults. No new task, Solana RPC request, subscription or polling interval is introduced. At configured capacity the curve batch is at most 25 curves +25 base mints +2 quote mints +one global account =53 accounts. When both assets need a new FX reference, they alternate by oldest attempt; the unchanged 30s hot cadence can therefore leave one reference unavailable for an interval. This is disclosed missingness, not filled using a peg. Background polling remains unchanged. A synthetic serialized mark is 1,363 bytes: 250 cached marks plus 250 baseline copies are about 0.65 MiB serialized, excluding Python object overhead. At 25 marks/30s, mark payloads alone are approximately 3.9 MiB/hour before SQLite/index/WAL overhead, subject to raw retention and the unchanged storage guard. These are bounds/estimates, not RSS or sustained-storage measurements. The additional account payload and reference wait may increase hot enrichment duration; sustained/live overhead has not been measured.

## V2.1 descriptive follow-up

New kinds in existing `records`: `v21_price_mark`, `v21_price_signal`, `v21_price_outcome`. Instrument version `v21-reserve-marks-1`. No new cohort/table/approval route.

- Earliest fresh V2.1 speculative review per mint/session, up to 250 unique reviews, freezes its assessment and the latest mark already available at signal time. A baseline can be up to 20s old, with actual timestamps retained; it is not an exact signal-time fill. Missing baselines are explicitly recorded and never replaced later.
- Targets are 15/30/60/180/300 seconds. Select the first available valid subsequent mark requested at or after the target, acquired within **20s** of that target. Actual endpoint time/delay is retained; this is not an exact-horizon execution price. No future best-price selection. Current 30s polling can leave endpoints unavailable, especially around short horizons.
- Only compatible pre-graduation marks with non-regressing slots and the same quote identity can yield `OBSERVED_GROSS_MARK`. It reports gross marginal-mark change only. **Net return is always null; executable is always false.** No hypothetical cost scenario is fabricated.
- Missing baselines, late/missing prices, migration, disagreement, shutdown and restart retain explicit unavailable outcomes. An available endpoint is retained even when no baseline exists. All accepted reviews retain all five horizon dispositions; duplicates do not add independent samples. Capacity omissions count assessments, not deduplicated unseen mints, and are disclosed in bounded operational receipts.
- Pending state is bounded to 250 reviews/five horizons; latest mark cache is bounded to 250. Restart finalizes interrupted work as unavailable rather than collecting replacement outcomes. Production marks enter the cache only after their receipt commits. A storage-budget failure records STORAGE_STOP, invalidates coverage and prevents the consumer resuming; pending evidence is not certified complete. Retried acknowledgements reuse committed signal baselines and skip already committed horizons under the existing single serial writer. Clean shutdown resolves remaining work explicitly. New-session startup inspects only the latest 250 signal rows: this assumes the existing single-engine lifecycle; arbitrary multi-session concurrent writers or externally imported unfinished histories are unsupported.
- Signals/outcomes use existing outcome retention; marks use existing raw retention. Existing byte guard remains authoritative and can halt collection. No original data is pruned by this implementation task. Baseline references avoid duplicating full signal contexts in every outcome. A normal shutdown receipt and periodic operational receipts expose instrument counts and omissions.

The dashboard opportunity payload additionally exposes `verified_price_observation` when currently valid. No graph or new frontend trading label is added. This field does not feed V2.1 classification, v1 research, manual PnL, core strategy or approval. Existing price-series limitations remain accurate: a single marginal mark is not an executed chart.

## Validation

Focused instrument tests: **43 passed**. Final wider regression selection: **282 passed, 1 skipped in 35.15s**, normal exit0. Selection: early_prices, lifecycle_fairness, early_market_v2, opportunity, opportunity_research, opportunity_expiry_batch, manual_live_workflow, shutdown_reliability and early_edge. Ruff passed; mypy passed all 46 application files; whitespace and basic secret checks passed. Frontend code was not changed and no frontend suite/build was rerun. This is a targeted regression result, not an unconditional full-system validation claim. All tests use synthetic accounts, mocked FX responses and isolated temporary databases. No live provider was contacted; official documentation retrieval is not a market observation.

Coverage includes known reserve scaling, incorrect quote decimals, mint/PDA/owner/supply errors, unsupported quotes, stale/future/missing FX/state, disagreement, out-of-order observations, tampered marks, bounded cache ownership, capacity omissions, missing baselines, negative gross movement, target boundaries, late/missing endpoints, migration, shutdown/restart, unchanged historical v1 rows, coherent single RPC batch, original curve delivery before FX work and unchanged core token price/decision. Existing SDK golden comparisons remain ordinary Python tests with no Node dependencies.

Initial fixture/validator failures were retained in `/tmp/early-price-*.log`; they were corrected rather than hidden. No broad backend or endurance run is needed for this observation contract. Existing unrelated full-suite observer-count/cleanup limitations are not claimed resolved.

## Exact changed files and preservation

- `backend/app/early_prices.py`: verified indicative marks and bounded separate follow-up records.
- `backend/app/providers.py`: optional same-context mint metadata in the existing hot curve batch.
- `backend/app/early_edge_runtime.py`: optional needed-product/max-product selection; existing reference defaults preserved.
- `backend/app/engine.py`: mark acquisition/persistence, storage-stop handling, receipts and shutdown completion. Normal consumer cadence and trade persistence transactions remain unchanged.
- `backend/app/intelligence.py`: separate observational follow-up and current mark field in opportunity payloads.
- `backend/app/db.py`: retention entries for the three new record kinds only.
- `backend/tests/test_early_prices.py`: focused synthetic/regression cases.
- `backend/tests/test_lifecycle_fairness.py`: mocks accept the new optional input argument and distinguish background retry requests explicitly.
- This report.

All 14 pre-change hashes (six unrelated files and eight saved-run files) match. The original radar database was not opened or modified; test engines/databases used explicit temporary paths. No frozen outcome was relabelled or backfilled. The preserved worktree changes remain unstaged, as do the changes in this task. Local validation logs are `/tmp/early-price-*.log`; the preservation manifest is ignored under `data/early_edge/verified-price-20261026/`.

## Verdict and remaining blind spots

Fresh pre-graduation USD **indicative reserve marks are implementable with verified inputs** using existing infrastructure. Their real-market availability, supported live account layouts, FX latency and effective short-horizon coverage remain **UNVERIFIED** until a separately authorized bounded observation. No such observation was started here. The saved session cannot establish these results retrospectively.

RPC context is a provider assertion, not a cryptographic state proof; no second RPC consensus is added. The FX source is independent of the curve source but not a multi-exchange consensus. Sparse polling, candidate churn, quote incompatibility, missing security/flow/route evidence and migration can legitimately censor follow-up. No executable fill, FOMO fee, finite-size exit feasibility, after-cost expectancy or predictive edge is established. Phase 4 remains unauthorized.

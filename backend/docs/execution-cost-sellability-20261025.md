# Execution costs and sellability — Phase 2C, 2026-10-25

**PRE_COHORT_READY=NO.** Starting source7cb7e9c851f6500ce2dedda9d8ac6d3eafe0c2d9, remediation/early-edge-evidence-readiness. Serial architecture, Phase2A disabled approval and Phase2B pool identity rejection are retained. No wallet connection, signing, transaction simulation/sending, real-market monitor, cohort or endurance experiment occurred. Public official documentation was browsed read-only on2026-10-25. All numerical scenarios below are explicitly synthetic.

## 1. Current capabilities and evidence levels

|Evidence level|Existing implementation|What it can and cannot prove|
|---|---|---|
|1. Liquidity-based cost approximation|[economics.py](../app/economics.py): TradeCostEstimator.side/estimate/break_even/exitability, PositionSizer; [manual.py](../app/manual.py): manual_economics; [paper.py](../app/paper.py): PaperAccount; [exit_intelligence.py](../app/exit_intelligence.py): exit_view.|Estimated costs from assumed fees and balanced-pool reserve approximation. A provider USD price/liquidity mark is not a verified route, actual reserve quantity, interface fee or fill. No SELLABLE flag is justified.|
|2. Exact integer calculation on supported verified state|[early_edge_quotes.py](../app/early_edge_quotes.py): ResearchExecutionOracle.observe, pump_buy, sell, rates; [early_edge_runtime.py](../app/early_edge_runtime.py): timestamped FX; [early_edge.py](../app/early_edge.py): immutable receipts/deadlines/result_costs.|Implements pinned SDK integer math for supported coherent account snapshots and amounts. Exactness is relative to those verified inputs and that supported program/fee version, not guaranteed inclusion/fill. The separate research instrument is not promoted into core/manual execution.|
|3. Current executable route / transaction simulation|No production route builder, wallet-specific account validation or transaction simulation in this scope.|MISSING. Pool identity and numeric reserve output do not establish route permissions, user account/funding, compute budget, minimum output, blockhash, transfer success or inclusion. No simulation is performed in Phase2C.|
|4. Successfully confirmed execution|No user execution integration.|UNSUPPORTED by this research/manual-support application. Observed public trades are not proof that a particular user's order executed. Journal open/close is not an on-chain transaction.|

An approximate exitability score, HEALTHY exit context, affordable estimate or snapshot sell result is not a sellability certificate. Startup evidence approval stays disabled and cannot be restored by positive hypothetical returns. Actual after-cost predictive value remains unproven.

## 2. Verified documentation versus configured assumptions

### Official sources checked on2026-10-25

The [official Pump fee page](https://pump.fun/docs/fees), updated17October2026, lists SOL/USDC bonding-curve fees0.30% creator+0.95% protocol, no LP fee. Canonical PumpSwap tiers range from1.25% total to0.30%; noncanonical pools have a separate0.30% schedule. Custom pairs, holder rewards/cashback and multi-pool routes require their applicable rules. Pump web/mobile adds0.45% platform fee without referral,0.40% with referral; third-party interfaces are different. Graduation costs0.015 SOL, with payer depending on pairing/trigger. Smart contracts determine actual charges. These facts do not define a universal all-interface fee or prove support for every current program variant.

[FOMO's official terms, section7](https://fomo.family/terms) say its buy/sell fee depends on amount, token, type and route and is displayed before confirmation; external costs are separate. No authoritative numeric spot fee/minimum applicable to the proposed trades was established. help.fomo.family was inaccessible through the browsing tool. [An older official FOMO comparison](https://fomo.family/blog/learn/fomo-vs-phantom-wallet) describes sponsored gas/priority/rent, but cannot establish present per-order coverage. **FOMO fee and sponsorship for this use case remain UNKNOWN**, not zero. Community fee tables/referral claims are not used. FOMO Companion inside CRISPY is decision support, not a FOMO execution integration.

[Solana fee documentation](https://solana.com/docs/core/fees) currently states5,000 lamports/signature; legacy/v0 priority charge depends on requested CU limit and price, whereas v1 uses its configured absolute fee. [Fee structure](https://solana.com/docs/core/fees/fee-structure) explains that processed failed transactions still pay fees. Rejected/dropped attempts before processing do not establish the same charge. SOL/USD, message signatures, account creation, compute/tips/route and sponsorship determine actual USD costs; fixed cents are not observed network charges.

[Solana token-account close documentation](https://solana.com/docs/tokens/basics/close-account) confirms that closure returns account lamports; ordinarily the token balance must be zero, and the owner/close authority controls closure. Rent-exempt balance is therefore potentially recoverable capital, not an automatic irreversible loss or guaranteed refund to the original payer. ATA presence, owner and ability to clear/close must be known before treating that capital as immediately available.

These public pages are review-date references, not permanent fee promises. Their live response bodies were not used to modify frozen settings or infer a transaction. Source/code pins below are separate from current website documentation.

### Current core/manual/paper assumptions — unchanged

|Component|Configured/model value|Observed or assumed?|
|---|---|---|
|Account / size|$20 account;20% base position cap, volatility adjustment; normally at most$4 initially|Configuration/paper balance, not user's funded live balance.|
|Protocol/DEX fee|1.25% per side|Flat configured approximation, not per-token current fee-tier lookup. It is not universally correct for every PumpSwap pool.|
|Creator fee|Not a separate additional core charge|Included only insofar as the configured1.25% total approximates it; no separate verified creator schedule in this estimator. Do not add it twice.|
|Platform fee|0%|Explicit assumed model value, NOT verified absence of Pump app/FOMO/interface charges.|
|Network / priority|$0.005 /$0.005 each side|USD constants, not transaction-message fee query or actual priority requirement.|
|Failed-transaction allowance|$0.01 round trip, half allocated to each leg|Conservative reserve, not measured failure probability or actual fee debit.|
|Slippage|.5% of value each side|Modeled adverse execution reserve, not a transaction's minimum-output instruction.|
|Impact|notional/(liquidityUSD/2+notional)|Balanced constant-product approximation. Quote reserve=liquidityUSD/2 is assumed; virtual reserves, imbalanced pools and routes can differ.|
|Price/liquidity|Timestamped DEX observations, where acquired|Observed provider marks, not execution fills or independently verified USD reserves. Manual observations remain labelled user-provided/unverified.|
|Fee verification label|2026-10-08|Static configuration provenance label; no per-order verification occurs. Current official interface terms differ in scope/date.|
|ATA creation/wrapping/closure/funding|Not fully represented by the core estimate|Unknown practical requirements, not proven zero.|

No assumption is changed here. A future named-interface model must explicitly separate charges embedded in a supplied quote, additional interface charges, network/setup costs, execution reserves and refundable capital, without double counting sponsored fees or price impact. Frozen historical versions cannot silently adopt that model.

### Separate research quote/cost policy

The Python quote port pins official @pump-fun/pump-sdk4.1.0 (gitHead b1a02a5ca87b4a7f3715a3cb921e503e1c2b3a66) and @pump-fun/pump-swap-sdk2.1.0 (gitHead0bc59090bbd0b8d6c27b8df72d52e30bfc069c3b). [early_edge_sources.json](../app/early_edge_sources.json) records package integrity, source hashes and account schemas; [SDK goldens](../tests/fixtures/early_edge/sdk_quotes.json) pin48 reference comparisons. No SDK install/execution was needed in normal tests. This is distinct from the Pump TradeEvent SDK4.2.0 event-schema provenance.

rates/tier reads on-chain fee configuration, fee tiers/flat-pool branch, creator presence/configurable creator fee and applicable token supply. Integer fees round up; reserve/output operations use the pinned SDK rounding. This is stronger than the flat core assumption but limited to supported account versions and quote assets. A website rate cannot substitute for those validated inputs, and pinned math is not automatic proof of compatibility with every new deployed instruction or fee variant.

Research protocol fees and reserve impact are embedded once. The frozen design adds1%/leg manual execution reserve, configured network/priority/failed allowance and account-close allowance. Rent is excluded from primary PnL, reported as temporary capital, with a full non-recovery sensitivity. Quote inventory is assumed funded. No named interface was selected; a0% platform assumption cannot be represented as verified FOMO or Pump-app pricing. No research protocol is changed or enrolled here.

## 3. Hypothetical quote accuracy and receipt contract

ResearchExecutionOracle identity discovery is not a fill. The final pricing inputs come from one confirmed getMultipleAccounts context at/after discovery and prior observed slot; a batch taking>5s, regressing context, missing or incompatible account is unavailable. Receipts include identity, account addresses/hashes, acquired/requested time, commitment and slot. Source/config hashes and quote input/output integers are retained by the research path. Rent is a separate cached ancillary read, not an independently time-coherent pricing input.

Pump entry calculates quantity within actual remaining tokens, then its exact-out quote cost, including configured protocol/creator fees, must fit the budget. Sell uses the supplied actual base quantity. Pump virtual reserves price the curve but real quote reserves constrain withdrawal; complete/depth/synthetic migration routes are unavailable rather than guessed. PumpSwap sale uses base/quote vault balances, virtual quote reserve where supported, reserved fee buckets, correct fee basis and real usable quote constraint. Sell-disabled pool flag is checked. Ordinary post-grad quotes require canonical migration/pool/mint provenance; diagnostic identity-only receipts cannot become research outcomes.

Only proven WSOL9/USDC6 quote decimals are supported. Base mint decimals and raw quantities are read and kept separately. [UsdReference](../app/early_edge_runtime.py) uses cached timestamped Coinbase SOL/USD and Kraken USDC/USD observations, with no future interpolation or automatic$1 stablecoin assumption. Neither source was contacted for the synthetic calculations below. Unknown/expired FX is unavailable.

Primary research latency remains10s with first valid post-boundary state inside the predeclared additional10s acquisition window; secondary .5/2/5s variants cannot replace it. Current reserve amounts at one confirmed bank do not prove they will remain available at manual execution. Snapshot outputs are not observed realized volumes or future best prices.

### Controlled integer-quote examples — NOT LIVE

The examples use the first WSOL PUMP and PUMPSWAP states in the pinned synthetic SDK golden file, with an **ASSUMED150 USD/SOL**, not a current market price. Pump reserves: base800,000,000,000,000 raw, virtual quote70,000,000,000 raw, real quote40,000,000,000 raw. PumpSwap: base800,000,000,000,000 raw, effective quote65,000,000,000 raw, real quote60,000,000,000 raw. Fee tiers are the fixture's artificial values, not claimed to be current public schedules. Underlying raw quantity/fee decomposition and fixture/state hashes are saved in data/early_edge/execution-cost-20261025/scenarios.json.

|Venue / amount basis|Base quantity raw|Entry quote including embedded fees,$|Independent same-state sell proceeds after embedded fees,$|
|---|---:|---:|---:|
|Pump $2 budget|150471372633|1.99802445|1.95185760|
|Pump $4 budget|300886174666|3.99604920|3.90224820|
|Pump $10 budget|751791350524|9.99012315|9.74463045|
|PumpSwap existing position, $2 reserve-mid mark|164102564102|UNAVAILABLE: no AMM buy helper|1.97059545|
|PumpSwap existing position, $4 reserve-mid mark|328205128205|UNAVAILABLE: no AMM buy helper|3.94038300|
|PumpSwap existing position, $10 reserve-mid mark|820512820512|UNAVAILABLE: no AMM buy helper|9.84490230|

These are independent quote queries on a fixed state, NOT a sequential buy/sell state-transition simulation or future return. The PumpSwap input quantities are explicit marked-existing-position scenarios; mid-reserve mark is only the sizing reference, never an execution buy fill. Entry/exit network/interface/reserves/rent are NOT included in this table. No live sellability or profitability inference is possible. Ordinary golden tests compare the port with their pinned expected integers; no new live SDK-parity attestation is claimed.

## 4. Actual sellability checks and missing proof

|Condition|Implemented proof / limitation|
|---|---|
|Canonical venue and identity|Oracle checks account owner, schema, PDA/expected mint, pool/migration and quote consistency; Phase2B parser rejects default required mint/vault keys. No DEX pair alone establishes this.|
|Vault ownership and initialization|vault_amount checks supported token-program owner, stored mint, pool authority, supported account shape and initialized rather than frozen state. This is pool-account verification, NOT verification of a particular user's token account or close authority.|
|Adequate sell reserves and quantity|Supplied positive integer base quantity; output/fees calculated with real quote-reserve constraint. Zero/insufficient output yields QuoteUnavailable. No API zero or absent account proves permanent economic-zero exit. Automatic economic-zero proof is disabled.|
|Current quote/price|Coherent acquisition receipts, FX freshness and entry/exit deadlines exist in research. Core/manual estimates use current marks per their existing policy. No websocket or off-chain price guarantees reserve availability at submission.|
|Transfer restrictions|Security scans detect active mint/freeze authority and dangerous/unknown Token2022 extensions. Oracle supports legacy token program and bounded metadata-only base-mint extensions; transfer fees/hooks/confidential/default-state behavior is rejected, not silently fee-adjusted. Quote token is restricted to supported legacy-program mints.|
|Frozen/restricted user position|NO wallet/account inspection. mint_info validates initialization/shape/known extensions but is not a comprehensive authority/security approval. Known security hard failure blocks relevant signal gates; absent proof of user transfer permission remains unknown. No claim that balances are spendable.|
|Token-program/route compatibility|Supported asset/account formats only; oracle does not prove a selected interface supports that token/program, routing or destination account setup. No general multi-hop execution quote.|
|Migration|Pump complete is not a sell through the old curve. Canonical migration and independently verified pool needed for supported post-grad quotes. Missing/ambiguous transition is unavailable, not an invented exit or−100%.|
|Failure/inclusion|No message construction, wallet funding, blockhash, simulation, compute-budget adequacy, front-running/MEV guarantee, confirmation or finality proof for a user's trade. RPC success is data retrieval, not transaction success.|
|Economically executable small exit|Can estimate net proceeds under assumptions or compute a supported snapshot output. Cannot prove all unavoidable user/interface costs or future sell route. Positive gross quote is insufficient; unknown costs remain unverified, not zero.|

The core TradeCostEstimator does not perform those on-chain checks and must remain labelled ESTIMATED. Its exitability score and partial liquidation scenarios are numeric heuristics. Exit intelligence can flag creator selling/security failure, provider disagreement, liquidity deterioration/drawdown or stale data, but HEALTHY is not a transaction guarantee. Manual journal opening/closing preserves external observations only; no on-chain balance or completed sale is inferred.

## 5. Small-position break-even scenarios — NOT LIVE

Use unchanged default settings, ASSUMED balanced$10,000 liquidity, same flat entry/exit mark and no chosen interface. Table debit/proceeds include all modeled fees/impact/slippage and allocated failed-tx allowance. Reserves are conservative budgeting allowances, not necessarily paid cash fees. Tokens are marked by an abstract gross price ratio, not an executable route. The$10 case exceeds the initial$20 account's20% cap and is sensitivity arithmetic only; it does not change allowed sizing.

|Position,$|Modeled entry debit,$|Modeled exit proceeds at flat mark,$|Round-trip modeled cost,$|Break-even gross move,%|Net return at +4% gross,%|
|---|---:|---:|---:|---:|---:|
|2|2.050800|1.949200|.101599|5.174771|−1.153230|
|4|4.088197|3.911803|.176395|4.495896|−.486392|
|10|10.209960|9.790040|.419920|4.291790|−.285472|

Fixed round-trip network+priority+failed allowance is$.03. Variable fee+slippage is3.5% of notional for flat marks, plus two impact charges. This is the core approximation's accounting, not the research SDK-cost ledger. Entry/exit price impact is already in the snapshot math above; applying these impact charges on top of those quotes would double count.

For$4, changing only hypothetical inputs/independent Settings instances gives:

|Hypothetical case|Modeled flat cost,$|Break-even gross move,%|Impact per flat leg,%|
|---|---:|---:|---:|
|Default $10,000 liquidity / .5% slippage /0 platform|.176395|4.495896|.079936|
|$1,000 liquidity, otherwise same|.233492|6.041390|.793651|
|1% slippage, otherwise default|.216395|5.543710|.079936|
|.45% interface charge, otherwise default|.212395|5.438445|.079936|

The last row illustrates adding the published Pump-app no-referral rate to this approximation; it is NOT a FOMO fee or exact Pump-app quote. The low-liquidity row fails the unchanged core$10,000 liquidity gate. No source/configuration file was changed for any sensitivity.

One additionally processed failed exit, under the unchanged assumed network/priority amounts, could consume$.010 before a later successful attempt: .5%/.25%/.1% of$2/$4/$10 respectively, while leaving the position exposed. The existing$.01 round-trip reserve is already included above; do not automatically charge this example again as though the reserve and observed expenditure were two actual debits. Actual paid failure cost/sponsorship is unknown until transaction/interface evidence exists. Repeated failures and market movement can exceed that allowance. Missing quote data is neither a charged failed transaction nor economic loss.

### Core, paper and research accounting are distinct

Core/manual estimate debits explicit modeled impact/slippage charges. Paper embeds those adverse prices into quantity/fill and charges remaining fees separately, using actual newly observed price after configured latency; unknown exit liquidity does not magically close a position. Paper quantity-based realized estimates can differ from a constant-notional scenario table and are not on-chain outcomes. Account/trade journal commits remain atomic with rollback; no paper behavior changed here. Research receipts explicitly separate embedded fees, external/reserve charges, unused cash and rent. No reported economic outcome or historical version was rewritten.

## 6. Confirmed defect, correction and regressions

TradeCostEstimator.break_even previously bisected the fixed0..1000% interval without checking a profitable upper bracket. For hypothetical$1 liquidity it returned1000% for each$2/$4/$10 position although net PnL there was−$3.561111/−$7.931174/−$21.156072. That is a demonstrably false break-even number, even though other core risk gates already reject the scenario.

New test_execution_cost_sellability.py was run before modification: **3 failed in.28s**. Preserved at data/early_edge/execution-cost-20261025/before-fix.txt. Minimal fix checks the upper estimate is available, finite and nonnegative before bisection; otherwise returns None. Existing45 bisection iterations,1000% search ceiling, fee inputs, impact formula and valid roots remain unchanged. None means no verified root inside this bounded model search, not proof of no conceivable exit or a−100% loss. The frontend already accepts null break-even and displays unavailable; manual economically_viable remains false.

New15 deterministic cases cover unbracketed2/4/10 roots, supported roots at$10,000/$25,000 liquidity, ledger debit/proceeds reconciliation, +4%-gross net losses, unchanged account/cap settings and manual propagation of unknown/unbracketed economics. Existing tests cover goldens, fee decomposition/rounding, unsupported extensions, mint/vault identity, insufficient reserves, migration, quote age/slots, rent exactly once, no-backfill/unavailable outcomes, manual separation and paper rollback/recheck. No new SELLABLE Boolean or production execution path is added.

Focused suite: **254 passed,1 skipped in16.86s**, including execution_cost_sellability, economics_paper, manual_intelligence, early_edge, early_edge_scheduling and companion. SDK reference execution is opt-in; skipped reference test is not a new parity claim.

## 7. What remains before a controlled manual execution assessment

1. Select the intended interface and obtain a current authoritative order-specific fee breakdown, minimums, sponsored costs and route coverage. No default-zero replacement for unknown charges. Reconcile protocol/interface/network/setup/reserves exactly once; a revised economic policy would need separately reviewed immutable versions.
2. Validate current deployed supported account/fee versions against pinned math, with read-only same-state official SDK parity and exact integer rounding. Unknown variants remain unavailable; public fee pages alone cannot certify the program implementation.
3. Demonstrate coherent state acquisition, FX freshness, T+10 deadlines, primary position quantity, true usable quote reserves and explicit unavailable outcomes under a separately authorized bounded run. Stored historical compatibility is insufficient. Known PumpSwap event-tail blockage remains relevant to strict buyer evidence even though account-state quotes do not parse that tail.
4. Distinguish numeric quote from practical execution: user account funding/permissions/frozen state, ATA existence/rent recovery, destination/route compatibility, current network/interface costs and minimum accepted output are presently missing. Any future account/route/simulation work needs explicit scope and no automatic signing/sending. None is implemented here.
5. Keep statistical approval disabled and retain all existing security, concentration, freshness,180s continuity, post-grad and economic gates. No new cohort or favourable hypothetical PnL can qualify strict entry. Small-account after-cost signal value still requires separately authorized prospective evidence.

## 8. Acceptance conditions for Phase 3

Phase3 is NOT started. A proposed bounded non-enrolling read-only validation should have frozen clean source/config, local regressions/quality checks, named-interface cost policy or explicit unavailable status, authoritative source pins and declared quote/account freshness/slot/time budgets. It must record target identities, exact raw input/output quantities, embedded fee decomposition, ancillary costs, unused cash/rent, provider failures, unknown variants and unavailable denominators. Same-state parity mismatch, inconsistent slot/mint/vault, unexplained fee or missing cost prevents a verified execution-economic claim.

Only a later, explicitly scoped assessment could establish route simulation, account compatibility and ultimately an independently executed confirmed trade; neither a snapshot nor a simulation is a guaranteed fill. Phase3 observation cannot automatically authorize a wallet, actual trade, new cohort or long readiness run. All ignored historical outcomes/negative/missing observations remain accounted. **PRE_COHORT_READY=NO.**

## Scope and validation receipts

Only planned Phase2C files: backend/app/economics.py bounded-root guard; backend/tests/test_execution_cost_sellability.py; this report. Existing five worktree changes and seven frozen original evidence hashes are preserved in data/early_edge/execution-cost-20261025/initial.json, alongside unchanged ADR and retired DB size/mtime. No historical database was opened for writes. All settings, quote source/schema files, research protocols, manual/paper/exit implementations and published prior-phase artifacts remain unchanged. No runtime SDK dependency or package installation.

Public documentation links were read on2026-10-25; no private endpoint/key/wallet appears in this report. Scenario receipts contain only synthetic quantities/assumptions and source hashes, not prospective outcomes. Full-suite/static/frontend results and actual publication status follow after completion.

### Completed validation

- Before-fix regression:3 failed,.28s; focused post-fix suite254 passed/1 skipped16.86s, exit0. All failed evidence remains preserved separately.
- Complete backend under the EXISTING bounded-cleanup diagnostic: **906 passed,1 skipped in168.73s, exit0**. This includes historical evaluation/replay, approvals disabled, market identity, observer, paper-account durability/rollback and quote/protocol regressions. Original Runner.close and real executor joins remain; bounded wakeup assistance is diagnostic-only. No new runtime cleanup workaround, and unrestricted ordinary invocation is not newly qualified. Its previously recorded300s timeout was not unnecessarily repeated.
- Frontend39 passed5.47s; TypeScript/production build passed(Vite3.75s), exit0. Existing null rendering supports unavailable break-even without frontend changes.
- Full Ruff backend/scripts and mypy42 application sources passed; source/document secret scan passed. Final document-link, arithmetic, preservation and whitespace checks passed. No dependency manifest/lock/install change; previously DNS-blocked online dependency audits remain UNVERIFIED, not newly passed.
- Five existing worktree files, unchanged architecture ADR, seven original frozen hashes and retired database size/mtime are checked again. No actual research outcomes, old cohort or historical configuration was altered. Unknown route/account/interface conditions were not promoted to executable assurance.

**Outcome:** one false numerical break-even result is corrected. Current tools support estimated or supported-state hypothetical economics, not independently proved practical sellability. PRE_COHORT_READY=NO. This ends Phase2C; no Phase3 collection or execution begins.

### Publication result

Attempted to stage only the three tested Phase2C files. Git metadata is read-only (.git/index.lock), so no commit/push or permission bypass occurred. HEAD remains7cb7e9c851f6500ce2dedda9d8ac6d3eafe0c2d9. The five prior changes remain untouched.

From a writable WSL terminal, review and publish ONLY this correction/report:

```bash
git switch remediation/early-edge-evidence-readiness
git add -- backend/app/economics.py backend/tests/test_execution_cost_sellability.py backend/docs/execution-cost-sellability-20261025.md
git diff --cached --name-only
git diff --cached --check
git diff --cached
git commit -m "fix: reject unbracketed break-even estimates"
git push origin remediation/early-edge-evidence-readiness
```

The staged list must contain exactly these three files. No main push, force push, merge, cohort or later phase is authorized.

# Manual EARLY entry study — hardened, non-collectable design

No real cohort exists. This work remains uncommitted on `research/prospective-early-entry-edge`, based on `2bebbf2863de21041fffca80fb99507356a815b6`. Production strategy/opportunity thresholds, security, economics, acquisition/recovery, PumpSwap event decoding, strict cohort and paper approval logic are unchanged. The retired strict cohort is not selected or modified.

## Primary question and fixed endpoint

Does the existing EARLY classification predict superior hypothetical, manually delayed, after-cost outcomes relative to contemporaneous observable non-EARLY candidates? This is observational predictive research, not a causal trial or an execution guarantee.

Primary: **USD 4, 10 seconds minimum latency, 300 seconds from signal time**. State requests must begin at/after `T+10`; acquisition must finish by `T+20`. This stricter request boundary also guarantees acquisition after the boundary. First valid state wins; no future best-price selection. The additional acquisition allowance is **10 seconds**, deliberately finite for manual execution. Actual acquisition delay is retained in receipts; a 10-second label is a minimum, not a promise of an exact 10-second fill.

Secondary latencies are 0.5/2/5 seconds. Every enrollment receives these variants automatically; all consume the **same prospective observation stream**, each taking its first valid state after its own boundary with the same 10-second acquisition allowance. Separate immutable entry/outcome tables prevent sensitivity results replacing the primary. Secondary horizons 60/180/600/1800 seconds are exploratory. Missing variant fills remain missing; no later cohort selection.

Entry is still a pre-grad PUMP buy quote. If migration happens before an executable manual entry, record unavailable quote; do not invent a PumpSwap buy. Canonically verified PumpSwap pool-state **sell** quotes support exits. This restriction can censor fast migrations and is a declared limitation requiring review, not a hidden exclusion.

## Treatment, fair observation floor and exact-time risk set

Treatment is the first qualifying existing EARLY_OPPORTUNITY per mint/session:

- No graduation, PUMP venue, verified current curve in `[0,85)`, not rejected/expired/core REJECT.
- No hard security failure, creator-selling evidence or provider disagreement.
- Independently known quote mint and consistent canonical Pump units, including a canonical Solana-WSS trade in the existing 180-second feature window.
- Same observation-readiness floor as controls.

Readiness uses only observations already acquired at T, in the existing opportunity 1800-second curve-history lookback. Both arms require the last verified point to agree with the current curve and be no older than the existing 180-second curve freshness. Largest inter-observation gap must be <=180 seconds. CURRENT_VERIFIED security requires >=3 observations spanning >=existing `progression_min_seconds` (60 seconds); other security status requires >=4 spanning >=120 seconds. No momentum, positive progress, persistence or acceleration condition is added to controls. These are research readiness rules; opportunity classification and its existing thresholds do not change.

For each treatment T, project other scanner candidates at **exactly T**. Filter with the same safeguards/readiness, excluding current EARLY actions. Require exact quote mint, predeclared progress band, age band and verified-security status. Exact T supplies the contemporaneous market regime; there is no later retrospective time matching.

Progress bands: `[0,30),[30,60),[60,75),[75,85)`. Age bands: `<120,120–<300,300–<600,>=600` seconds. From the exact-match risk set select one control by absolute progress difference, absolute age difference, then lexical mint. No replacement of a control mint within a session. Ambiguous duplicate candidate views are rejected. No match means an explicit immutable unmatched record; treatment remains enrolled and cannot later acquire a better control.

A control later becoming EARLY remains the original control. Its later first EARLY may separately enter treatment expectancy. Mint dependence across arms/sessions remains grouped in resampling. No generic control enrollments at unrelated times are accepted. Pair insertion and both immutable snapshots are atomic; pair references are unique and foreign-key constrained.

Snapshots retain opportunity action/reasons/version, core decision, scores, features, security, curve, age, readiness, monitoring tier/coverage and descriptive market context. `token.price` never supplies a fill.

## Fixed stopping and finalization

Close enrollment at the earlier of:

1. First **100** unique treatment mint/session enrollments, including treatments with unavailable quotes or no controls.
2. `created_at + 30 * 86400` seconds (30 UTC calendar days).

Closure persists immutably across sessions/restarts. It cannot be extended or reopened. After closure, declared outcomes may mature; normal sessions drain up to 1821 seconds beyond their enrollment period. Session interruption explicitly censors unfinished horizons, with no retrospective recovery.

Interim reports show only enrollment, matching, coverage, provider quality and accounting counts. They do not return outcome distributions, bootstrap intervals, secondary results or an edge conclusion. Final statistics appear only after persistent enrollment closure **and all enrolled primary horizons have terminal accounting**. Reaching the calendar limit below 100 numerical EARLY results is INSUFFICIENT_SAMPLE. Unavailable outcomes are terminally accounted but are not economic measurements.

## Read-only measurement and provenance

The minimal schemas, source hashes, package integrity and compiled reference-helper hashes are in `backend/app/early_edge_sources.json`.

| Official artifact | Exact version | gitHead |
| --- | --- | --- |
| `@pump-fun/pump-sdk` | 4.1.0 | `b1a02a5ca87b4a7f3715a3cb921e503e1c2b3a66` |
| `@pump-fun/pump-swap-sdk` | 2.1.0 | `0bc59090bbd0b8d6c27b8df72d52e30bfc069c3b` |

Pump quote sources: `src/bondingCurve.ts`, `src/fees.ts`; account readers and PDAs: `src/sdk.ts`, `src/pda.ts`, pinned IDLs. PumpSwap sell math: `src/sdk/sell.ts`, fees/util/PDAs, account versioning in `src/sdk/offlinePumpAmm.ts`, pinned IDL. All relevant paths/hashes plus `dist/index.js` are pinned. Published tarball integrity and extracted source hashes were verified. The Python port matches 48 deterministic official-SDK golden cases exactly.

The research oracle verifies owner/discriminator, curve PDA or independently parsed pool/base identity, quote mint/decimals, both vault mint/authority identities, supported token extensions, fee config and global config. PumpSwap requires a canonical migration already accepted by the normal engine. Diagnostic pool verification can omit lifecycle provenance only in a separately flagged read-only mode; such observations cannot enter study outcomes.

An identity discovery read is never a fill. **All pricing inputs come from one confirmed `getMultipleAccounts` bank/context**, including state, mints, fee config/global and pool vaults. Context cannot precede discovery or the previous accepted context for that identity; tracking is bounded to 128 identities. The final batch must complete in <=5 seconds. Unknown nonzero state extensions fail closed; historical account defaults and version-selected fee allocation semantics are allowed only where the pinned SDK explicitly defines them. No undocumented event payload extension is accepted. The Pump-only SDK 4.2.0 TradeEvent schema update does not change PumpSwap event acceptance.

Receipts retain signal/boundary time, request/acquisition times, commitment, discovery/pricing slots, identity/address list, account hashes, quote mint, SDK/source identity, raw input/output, fee decomposition and USD references. Rent is independently read/cached as capital metadata, not mixed into pricing state. Confirmed-bank coherence does not prove inclusion, finality or protection from MEV/future movement.

Live parity diagnostics pass the **same captured normalized account state** to the local port and official SDK. Integers are serialized as decimal strings to avoid JavaScript precision loss. Comparison tolerance is zero. Pump buy and sell are checked; PumpSwap sell is checked because only post-grad exits are supported. No instruction, signature or transaction is built/sent. The SDK child receives no credentials, has a 15-second deadline and a bounded output. Artifact version/source/compiled hashes are checked before execution.

Real creation requires an explicit reviewed-design flag, clean source, and a source/config-bound live parity report: >=2 Pump mints and >=2 verified PumpSwap pools, >=2 distinct contexts per identity, complete confirmed receipts, exact SDK equality, no unexplained mismatch, fresh reference-source preflight. Report/source/config drift or absent provenance blocks creation. Starting collection independently rechecks both USD references and refuses enrollment if either is unavailable. There is no real creation in this task.

## USD reference correction

The red team found that Coinbase Exchange `USDC-USD` returned **404 NotFound**. It is not a usable reference. Before any enrollment, the new research client was corrected to:

- SOL/USD: Coinbase Exchange public `products/SOL-USD/ticker`, retaining its publication time.
- USDC/USD: [Kraken public Recent Trades](https://docs.kraken.com/api-reference/market-data/get-recent-trades), `pair=USDCUSD&count=1`, using the one trade's actual price and Unix timestamp. No USDC peg assumption.

At most one attempt/product/10 seconds; both publication and acquisition must precede the valuation time and be <=20 seconds old. Missing/stale/future/incorrect-product values fail closed, without fallback. This single off-chain FX observation is only USD normalization, never Pump buyer-flow evidence. USD 4 is converted using the reference already available at **entry acquisition**, preventing pre-entry SOL/USD movement being counted as token-entry return. Exits use already available exit references. All values/times/source identifiers persist in receipts.

## Explicit USD-4 manual cost ledger

Scenario: funded quote inventory, direct canonical manual execution, new base ATA, and a conservative separate close-account transaction. No named trading interface has been selected; default platform fee **0% is a scenario assumption, not an authoritative interface fee**. If the intended interface charges more, resolve that before creation, never after results appear.

| Component | Classification | Primary policy |
| --- | --- | --- |
| Protocol, creator, LP fees | Embedded authoritative quote | Exact SDK integer decomposition, once |
| Nonlinear price impact | Embedded authoritative quote | No second impact charge |
| Network entry/sell/close | Unavoidable external cost | Frozen USD estimate $0.005 each; $0.015 total |
| Priority entry/sell/close | Conservative reserve | Frozen $0.005 each; $0.015 total |
| Failed transaction | Conservative reserve | Frozen $0.01 round trip |
| Manual execution/slippage | Conservative reserve | **1% each leg**, predeclared research-only assumption |
| Platform/interface | Not applicable in default scenario | 0%; configurable assumption must be reviewed |
| Base ATA rent | Recoverable capital lockup | Excluded from primary PnL; separately reported |

Thus at approximately $4 entry and $4 fee-net exit the external manual assumptions are approximately **$0.12 round trip**, plus embedded protocol fees; actual reserves/fees alter both proceeds and reserve amounts. Do not add the core generic fee model on top. Account-close fees are already included; refunded principal rent is not profit. Full non-recovery rent sensitivity and a protocol-only view (SDK fees/impact plus network costs) are reported separately. Record upfront capital including rent and entry costs. Funding/cashout fees and interface-specific behavior outside this scenario remain limitations.

## Missingness and economic zero

Terminal statuses remain MEASURED, ECONOMIC_ZERO_EXIT, UNAVAILABLE_INFRASTRUCTURE, UNAVAILABLE_QUOTE, UNAVAILABLE_UNITS, UNAVAILABLE_PROVIDER_GAP, UNAVAILABLE_OTHER. Every primary enrollment remains in the denominator. No unavailable value becomes zero, a winner, or -100%.

**Automatic ECONOMIC_ZERO_EXIT is disabled**, including superficially plausible fabricated proof dictionaries. Candidate future proof rule: resolve the canonical relevant venue/migration, verify coherent authoritative state and the full acquired quantity, obtain an authoritative executable sell calculation and independently verified unavoidable exit-fee schedule, and prove net recoverable proceeds <=0 at the endpoint. Optional reserves, unknown platform fees, zero API fields, missing vaults, integer dust, absent pools and temporary transport failures are insufficient. Preserve state/fee evidence for review. This is a proposal, not implemented proof; any implementation needs a new frozen version.

Strongest status requires 100 numerical primary treatments, all treatments matched, every matched control resolved economically, no unavailable outcomes, full accounting, source/snapshot/pair integrity and positive primary/comparison bootstrap lower bounds. Unmatched, pending or unavailable samples block it. Degraded sessions are retained, not silently excluded.

## Two crowd markers and coverage

Primary descriptive crowd marker: first prospectively observed verified curve >=85%. Secondary: first **CURRENT, valid-unit pre-grad** rolling evidence with `estimated_independent_buyers >= settings.min_buyers` (currently 20). Partial flow cannot establish that marker. Record signal buyers/progress, first marker times, first bounded subsequent executable marks, quote acquisition times, graduation and elapsed times. Markers may predate a later EARLY; do not backfill a missing mark. Price advantages are conditional descriptive comparisons, never a survival condition for primary enrollment.

Per-candidate summaries include curve count, observed duration/max gap, eligible monitoring seconds, hot/background time, provider unavailable time, resource pressure and capacity censoring. Readiness is recomputed from the actual history for both arms at T. These floors improve comparability but do not prove equal monitoring intensity; residual hot/background differences remain visible.

Cohort/session diagnostics retain discovered/eligible/adequately-observed counts, treatment/match/unmatched counts, provider/recovery/queue quality and capacity events. Create rejections coincident with capacity are labelled as such rather than assumed unique causal losses. Active buffers remain bounded; persistent study data use a separate namespace/database and storage guard.

## Statistical finalization

Primary mean 10s/300s net return has normal 95% CI for comparability and 10,000 deterministic percentile bootstrap resamples, seed **20261020**. Primary expectancy resamples mint clusters with all sessions for that mint together. The immutable paired difference uses mint-connected components: union mints connected by pairs, including later crossover, and resample whole components. No pair or shared mint is split. This can leave few independent components; <2 yields no supporting comparison CI. Matching/resampling are not revised after results.

Also show median/wins/profit factor, MFE/MAE from observed marks, observed drawdown, crowd/graduation reach, exploratory horizons/latencies, strata, best-winner contribution and mean without the best outcome. Missing marks understate excursions; overlapping notional exposure is not a capital-constrained portfolio.

Statuses are INSUFFICIENT_SAMPLE, NEGATIVE_OR_UNPROVEN, PROMISING_NOT_PROVEN, EARLY_EDGE_SUPPORTED, with INTERIM_OPERATIONAL_ONLY before finalization. Strongest status also requires all 10,000 relevant resamples usable, positive means/difference and both lower bounds >0. It never changes paper, holdout or live approval. Supported wording is predictive association under the frozen quote/cost assumptions, not causation.

Residual risks include temporal/market correlation not fully covered by mint clustering, confounding, heavy tails, endpoint missingness, quote-model/deployed-execution divergence, confirmed-bank/reorg risk, manual-interface assumptions and regime dependence. Fixed stopping removes discretionary extension/positive-result stopping; it does not remove these risks.

## Non-enrolling throughput command

The diagnostic constructs no Study/cohort and writes no prospective treatment/control outcomes. It runs ordinary OBSERVE in a disposable engine DB, records bounded aggregate counts/coverage, and samples current quote states using the Python quote port. Official-SDK comparison is opt-in only. Old cohort selection and PumpPortal are refused. Attempts/errors/unsupported quotes remain in the diagnostic denominator; SDK-only fallback budgets when FX is absent never count as executable USD quotes.

Six-hour command **for later review**, not run in this task:

```bash
RADAR_MODE=OBSERVE PUMPPORTAL_ENABLED=false .venv/bin/python scripts/early_edge_diagnostic.py \
  --seconds 21600 \
  --pool 9YUjnsFY82tKEG3egMZ4WvbKCUi7FZ6ng6kWv62ppump:CQPkog392tYDxkcGXTG8skEis4VUAJ7kaYc6smmTFroz \
  --pool 3sacwJKxseFQQViwGRgqTk7apL9r6bvy2Vfv7DKFpump:2ReuQBdqxEQ2KUc8f18WDQHKcoBLaZ8zBux6Ni48wia9 \
  --max-state-samples 120 --output data/early_edge/throughput-6h-review.json
```

Pool ownership/layout/identity are freshly verified, never trusted from the command. State sampling is spread in bounded rounds across the requested duration; this is an availability diagnostic, **not proof that 64 concurrent research signals meet every deadline**. Runtime buffers/samples are capped. Reports distinguish raw SDK parity success from USD-normalized quote readiness and expose admission, decoder, provider, queue and resource pressure. A short run is always marked smoke-only and cannot establish a stable signal/hour or N=100 completion estimate.

Normal diagnostics and cohort collection require no npm SDK environment. `--node-path` enables a separate reference diagnostic only; it fails closed unless Bubblewrap can create a private network/PID/filesystem namespace. Only system libraries, the Node executable, a read-only disposable reference tree and the verifier script are mounted; no home, project, credentials or host network is available. The child gets bounded captured state on stdin, <=128 MB V8 heap, a 15-second deadline and bounded output. See the Pump/SDK security investigation report. Ordinary tests use pinned goldens and never automatically execute a local SDK install.

Opt-in provenance check (no network inside Node, no fixture overwrite):

```bash
.venv/bin/python scripts/early_edge_reference.py --node-path /tmp/crispy-early-quote-ref/node_modules
```

An unavailable namespace is `REFERENCE_SECURITY_BLOCKED`, never an unrestricted fallback. SDK-only fallback raw budgets when USD references are unavailable are diagnostic-only and cannot become executable USD outcomes.

## Safe review commands only

```bash
.venv/bin/python scripts/early_edge_cohort.py plan --output data/early_edge/new-review-draft.json
.venv/bin/python scripts/early_edge_smoke.py --output data/early_edge/new-synthetic-smoke.json
.venv/bin/python -m pytest -q backend/tests/test_early_edge.py
```

The plan is `collectable=false`. Real creation/run commands are deliberately not executed. Future creation additionally needs reviewed design, a clean committed implementation and fresh source-bound parity/FX preflight; starting a run independently requires fresh references. Existing databases/manifests are never auto-migrated. Resolve the live acquisition/instrument/security findings in the validation record before considering enrollment.

## Frozen six-hour operational gate

Before running, freeze two reviewed commits on the research branch and push that
branch only. A non-collectable proposal may be generated with `early_edge_cohort.py
plan`; this creates no database/cohort. Pass its path as `--frozen-plan` to the
non-enrolling diagnostic, together with `--seconds 21600 --max-state-samples 120`
and explicit `--output`/`--progress` paths under ignored data/. No Node SDK option
is required. The diagnostic checks clean Git/source/config identity every30s and
at completion. Do not edit source during the run.

Bounded operational telemetry records CURRENT token identities as hashes, sampled
coverage/buyer/flow/whale distributions, resource/storage/queue usage, sanitized
HTTP exception categories and reference freshness. It observes the same risk set
and treatment-readiness rules without constructing Study or outcome tables. Up to
64 live EARLY marker probes measure first valid state availability after .5/2/5/10s
from the same state stream, within the existing10s acquisition-delay bound; these
are availability counters, never hypothetical outcome returns. Entry probes are
rate-bounded and use the shared RPC provider. Excess diagnostic probes are counted
as censored, not dropped silently. Marker summaries and rolling samples are bounded.

The report must distinguish sampler availability from actual primary-entry
availability (which is undefined if no EARLY signals occur). Time-sampled
operational distributions are descriptive, not independent statistical samples.
Unknown units, failed/unavailable quotes, transport loss, capacity limitations and
queue staleness remain explicit. A new unsupported Pump layout stops the run.
Account-slot rejection counters add observability only; quote acceptance/math is
unchanged. No prospective cohort or outcome is created by this command. A failure
leaves the last atomic progress report and a sanitized error category for review.

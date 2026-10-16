# Opportunity Intelligence and the manual journal

Opportunity is **UNVALIDATED RESEARCH INTELLIGENCE**. EARLY OPPORTUNITY means high-priority
manual investigation, never a validated buy, calibrated edge, probability of profit or promise of
returns. Core Companion WAIT can coexist with an Opportunity label. Opportunity outputs never
enter `evaluate_candidate`, approved Strategy Lab evidence, paper sizing or paper orders.

## Architecture and isolation

`opportunity.py` and `exit_intelligence.py` are pure typed projections. `intelligence.py` coordinates
existing observations, cached views, the local journal and independent prospective research.
There are no provider clients in these layers. `Token.curve_history` stores at most 32 timestamp /
progress pairs from already received VERIFIED curve/security observations containing valid progress.
Unknown, duplicate-time and out-of-order samples are not appended. No account payload is duplicated.
History is session-only and rewarms after restart; prospective research work persists in SQLite.

Settings in `config/intelligence.yaml` belong to their own `opportunity-v1-<hash>` version. They do
not change core Settings, strategy hash, thresholds or evaluation. Candidate limits, lifecycle
hysteresis, expiry fairness, hot/background scheduling and RPC pressure control are unchanged.

## Dynamics and classification

Only verified history at or before the observation timestamp is used. History older than 1,800s
is excluded. Current lifecycle requires the latest verified point to match the current curve and
timestamp and be at most 180s old (configurable). Unknown latest curve evidence invalidates
freshness rather than extending old evidence. Missing samples are not zero movement.

Short / medium velocities use actual elapsed time across points in the last 120 / 600 seconds.
They require two observations and at least 30 seconds of coverage. Acceleration requires three
observations, at least 15s between adjacent points and at least 60s total; it is the difference
between successive pp/min velocities divided by midpoint elapsed minutes. Persistence is the
fraction of eligible adjacent intervals (>=15s apart) with strictly positive progression. Curve
retreat is session peak minus current in percentage points, not a price return. Observed region
duration covers consecutive observed points in the <30 / 30–85 / >=85 curve bands; it does not
prove continuous behavior between irregular samples or replace lifecycle hysteresis.

Classification precedence:

1. AVOID: existing core REJECT, hard security failure, observed creator selling, or material provider disagreement.
2. TOO EXTENDED: existing core MISSED, which supplies chase evidence. High curve percentage alone never implies this state.
3. DATA LIMITED: current verified curve unavailable, or severe verified retreat >=25pp without a sound progression thesis.
4. PULLBACK WATCH: at least three samples, a prior observed rise >=4pp, and verified retreat >=4pp but <25pp, absent hard rejection/chase.
5. EARLY OPPORTUNITY: current verified curve; >=3 samples spanning >=60s; net progression >=4pp;
   positive persistence >=75%; increasing medium progression; retreat <=3pp; and either current
   verified security or >=4 lifecycle observations spanning >=120s. No hard risk/chase may apply.
6. DEVELOPING: current lifecycle worth observing but not yet meeting those conditions.

EARLY OPPORTUNITY receives HIGH attention. Other ranked candidates with score >=30 receive MEDIUM;
otherwise LOW. No outcome history was used to tune these rules. Missing security may coexist with
HIGH attention only with the stronger temporal-history condition; that is explicitly LIMITED and
not safety or independently confirmed buying. Missing flow is never fabricated as buyers/flow=0.

Opportunity priority is bounded 0–100, used only for sorting:

| Component | Formula / maximum |
| --- | --- |
| Persistence | positive interval fraction ×25 |
| Net verified progression | clamp(net pp, 0, 20) |
| Sample coverage | min(10, samples ×2) |
| Current lifecycle freshness | 15 |
| Controlled retreat | max(0, 10−retreat pp), only with current curve |
| Current verified security | 10 |
| Genuine current structured trade flow | 5 |
| Current source-labelled market context | 5 |

AVOID and DATA LIMITED have priority zero. A FULLER EVIDENCE grade requires current lifecycle,
security, actual flow and market context. Other grades expose NO TRADE FLOW / SECURITY UNKNOWN /
MARKET UNKNOWN / LIFECYCLE UNKNOWN or STALE. The shortlist filters all candidates and shows at
most 20, with deterministic tie ordering. Scores are never probabilities.

## Entry context, market truth and costs

No automatic pre-graduation USD price/market cap is calculated. Reserve interpretation, decimals,
quote currency and conversion are not independently established in this phase. Launch metadata
never becomes current context. Existing DEX market observations can supply current USD fields
within the core 20-second market age; price and market cap have separate timestamps. FDV is not
market cap: provenance distinguishes the existing provider fallback, and the projection withholds
FDV. Current/stale market-cap fields and history display do not forward-fill old values.

Review zone and maximum chase are **UNAVAILABLE**: there is no calibrated exit-target basis.
The strict economics model's maximum acceptable entry semantics remain unchanged. No price band
is invented from current market cap or curve progression.

Manual observations accept positive finite USD price and/or market cap, validate mint syntax,
store automatically assigned timestamps and always say MANUAL USER OBSERVATION / not VERIFIED.
They become visibly STALE after 120 seconds by default. This is user-reported context, not a
provider measurement. It cannot change token price/liquidity/security, core decisions, approved
evidence or provider health. Provider-only research strips manual context from signal baselines.

Available manual cash is a separate initially unknown, user-maintained setting. It does not read
FOMO/wallet funds, hard-code a user balance, alter the $20 paper account or automatically reconcile
journal entries. Proposed positions show fraction, entry/exit/round-trip costs, break-even, impact
and remaining cash using the unchanged TradeCostEstimator only with current existing liquidity.
Unknown liquidity means UNKNOWN costs and impact; estimates are balanced-pool approximations,
not executable quotes or proof of viability. Missing cash cannot establish affordability.

## Manual workflow and exit context

Copy mint → independently inspect FOMO → optionally enter a current manual observation → review
entry context → decide and execute outside this app → explicitly record the external entry.
No wallet, FOMO credentials, browser automation, signing or execution exists.

The journal accepts amount, price and/or cap, optional notes and entry time. Defaults: 3 open
positions, configurable 1–10. Opening and closing both require explicit confirmation. Opening
captures current Opportunity reasons, dynamics, warnings, source quality, invalidation conditions,
research version and core version. Backdated entries >5s receive no retroactively invented thesis;
backdating is limited to 30 days. Manual positions do not acquire extra scanner protection or RPC
polls. If a mint leaves the scanner, missing intelligence becomes stale rather than adding pressure.

Marks and observed peaks are kept separately by source and basis (price versus cap). Current price
marks allow gross price change; cap change is only a proxy and never P&L. Net estimates require
current liquidity and a comparable current price/entry basis. Missing marks, security or important
lifecycle evidence cannot produce HEALTHY. Confirmed migration remains authoritative for migrated
positions, so an expired pre-grad curve does not itself demand new curve calls after migration.

Exit states are explained unvalidated context, never guaranteed sell instructions:

- THESIS INVALIDATED: hard security failure, observed creator selling, material disagreement, or
  verified retreat >=25pp from recorded entry-curve thesis.
- DATA STALE: important mark/lifecycle/security evidence missing or stale.
- EXIT RISK: peak drawdown or entry-basis decline >=20%, current liquidity below the existing core
  minimum, or current liquidity <=50% of its entry snapshot.
- PROTECT PROFIT: estimated net return >=3% after estimated costs **and** verified curve regression
  or peak retreat >=8%. Positive price movement alone never forces this state.
- MOMENTUM DETERIORATING: verified curve regression, without the above higher-priority conditions.
- HEALTHY: current mark/lifecycle/security and genuine trade evidence, no configured deterioration.
- MONITOR: current partial evidence without deterioration; flow remains unavailable, not bearish zero.

The caution/profit/liquidity fractions above are configurable in the independent research config.
Journal closure changes a local record only. User should enter a final observed mark before closing;
these are estimates, not reconciled fills. Closed history is preserved and the UI loads the latest
100 records on that page, not during SSE. Original thesis and source-separated peaks persist.

## SQLite, security, research and bounds

Alembic 0003 adds manual-position state and bounded pending research tables in the existing database.
Open/mark/close state plus its journal event commit together. Manual open/close history is retained;
compact mark/context detail follows snapshot retention, and current state/peaks survive retention.
Research signal/outcome records follow 90-day outcome retention. Existing cap/maintenance applies;
manual writes are refused at the storage cap. History still requires monitoring of database growth.

Every real Opportunity action transition creates an immutable `opportunity_signal`, including
DATA LIMITED transitions. Snapshots use only then-known features and provider-only baselines.
Separate `opportunity_outcome` horizons default to 60/180/300/600/1800s. Pending work is bounded
at 1,000, indexed in memory by mint and persisted across restart. Outcome records and their horizon
checkpoints commit atomically, with rollback/retry tested. Signal-time cost assumptions are frozen. Capacity evictions produce explicit
UNAVAILABLE_CAPACITY outcomes. Missing coverage produces UNAVAILABLE_GAP. Horizon extrema are
frozen before admitting any observation after their deadline; actual endpoint sample timestamps
are recorded, never interpolated. Curve extrema/regression, migration/time-to-migration and genuine
provider-price gross returns/excursions are recorded when measurable. Estimated after-cost return
also requires fresh entry/exit liquidity; otherwise it is null. Gross research measurements never
become approved edge. Manual observations never enter these provider outcomes. Tiny counts show
no significance and there is no automatic threshold fitting or approved-evidence promotion.

DEMO examples are synthetic projections outside engine.tokens, research, strict Strategy Lab and
paper trading. They cover the five Opportunity states and four manual-position states requested.
Real snapshots have no fixtures. Browser alerts reuse local debouncing for entering EARLY and
manual PROTECT PROFIT / EXIT RISK / THESIS INVALIDATED transitions, not unchanged observations.

Mutating endpoints require bounded JSON, finite/range-checked values, syntactically valid Solana
mints, strict extra-field rejection, localhost Host and permitted Origin / same-site checks. They
are local journal endpoints, not order endpoints. SSE uses bounded cached projections with zero DB
SELECTs or network calls. No service, dependency, wallet key or remote control integration was added.

Verified integration references: [FastAPI request bodies](https://fastapi.tiangolo.com/tutorial/body/),
[origin rules](https://fastapi.tiangolo.com/tutorial/cors/), [SQLAlchemy sessions](https://docs.sqlalchemy.org/en/20/orm/session_basics.html),
and [DEX field reference](https://docs.dexscreener.com/api/reference).

## Verification — 2026-10-16

Complete backend suite: **160 passed** (including 41 new Opportunity/manual/research cases).
Frontend: **33 passed** (10 new component/workflow cases; existing Companion tests unchanged).
Ruff, mypy (25 application source files), TypeScript, production build, secret scan and diff checks
passed. Python exact-lock audit and npm audit found no known vulnerabilities; no dependency was
added or changed. The existing Python lock lacks artifact hashes (the auditor's documented warning).
An initial sandbox test run stalled at an async API test and was interrupted; unrestricted complete
runs passed, including the final 160-test run in 53.40 seconds.

Final offline synthetic check: 250 candidates / 25 hot / 8,000 curve points; 88.95 MB initialized
RSS, 94.38 MB loaded RSS (5.43 MB delta); mean 33.73 ms projection refresh and 12.61 ms snapshot.
Twenty snapshots issued zero SQL SELECTs and zero RPC requests. This benchmark uses synthetic
observations with acquisition disabled, so it measures projection/view overhead, not full live
research/write load. DEMO produced all five requested Opportunity actions and all four manual
exit examples. Separate running DEMO smoke: 12 scanner candidates, original four Companion
examples, $20 paper cash, 90.8 MB RSS, 4.4 ms mean snapshot, zero RPC and zero drops.

### Live OBSERVE limitation

Two isolated 180.01-second read-only probes were attempted, first sandboxed and then with approved
network access. Both returned the same result: PumpPortal attempted discovery but could not
establish a connection (8 errors / 8 bounded reconnects per probe, DEGRADED). A separate bounded
free handshake diagnostic returned **HTTP 502 (InvalidStatus)**. The origin of that gateway
response is unresolved; this is not evidence that the endpoint or the new feature worked live.
No provider/reconnect redesign or polling increase was made to work around it.

| Final probe metric | Observed |
| --- | ---: |
| Real launches / active / hot / background | 0 / 0 / 0 / 0 |
| EARLY / DEVELOPING / PULLBACK / TOO EXTENDED / AVOID / DATA LIMITED | 0 / 0 / 0 / 0 / 0 / 0 |
| Evidence-grade counts | empty (no discovered tokens) |
| Trade-flow-unavailable candidate count | 0 (no candidates; not evidence of available flow) |
| Prospective signals / outcomes | 0 / 0 |
| RPC HTTP requests / 429s / errors | 0 / 0 / 0 |
| RPC pressure | level 0; NOT USED YET |
| Effective hot / background revisit / security scan | 30 / 180 / 30 seconds |
| Curve accounts checked / background batches | 0 / 0 |
| RSS / sampled CPU | 94.4 MB / 0.0% (idle, not a load measurement) |
| Queue / dropped observations | 0 / 0 |
| PumpPortal | DEGRADED; 8 errors / 8 reconnects |
| DEX | NOT USED YET |
| Paid trade subscriptions / paper cash | 0 / $20 |

The zero requests above cannot establish live pressure behavior under load. Structural checks,
existing RPC/fairness regressions and synthetic snapshots establish zero **additional** request
paths; successful live Opportunity coverage and sustained pressure/resource behavior remain
unverified in this environment. No real trade or manual journal position was opened during live
verification, no synthetic data was injected into OBSERVE, and no profitability/edge claim is made.
The engineering probes used temporary databases, so they do not contribute production research.

Files changed in this phase:

```text
backend/alembic/versions/0003_manual_research.py
backend/app/db.py
backend/app/domain.py
backend/app/engine.py
backend/app/exit_intelligence.py
backend/app/intelligence.py
backend/app/intelligence_demo.py
backend/app/main.py
backend/app/manual.py
backend/app/opportunity.py
backend/app/opportunity_research.py
backend/app/providers.py
backend/tests/test_manual_intelligence.py
backend/tests/test_opportunity.py
backend/tests/test_opportunity_research.py
config/intelligence.yaml
docs/architecture.md
docs/limitations.md
docs/operating-guide.md
docs/opportunity-intelligence.md
frontend/src/App.tsx
frontend/src/components/ManualPositions.tsx
frontend/src/components/Opportunity.test.tsx
frontend/src/components/Opportunity.tsx
frontend/src/intelligenceTypes.ts
frontend/src/style.css
frontend/src/types.ts
scripts/smoke_observe.py
scripts/verify_intelligence.py
```

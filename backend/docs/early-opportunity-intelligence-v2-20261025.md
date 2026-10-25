# Early Opportunity Intelligence V2 — 2026-10-25

**Implemented for unvalidated manual research. PRE_COHORT_READY=NO. Phase 4 remains unauthorized.** No providers, live engines, cohorts, wallets or transactions were started. Work begins at `60859f3431e396d94c3f30619208d5efa00529a5` on `remediation/early-edge-evidence-readiness`; changes are uncommitted.

## What changed

The existing Opportunity projection now carries a separately versioned `early_market` assessment: **`early-market-v2-75cf82683626`**, pinned to the interpretation function's source and declared research policy. This extends the existing Intelligence orchestration, not a second candidate registry or processing pipeline.

It reports 10/30/60/180-second retained samples, buy/sell counts, buyer addresses, estimated independent buyers when supported, amount units, flow, arrival acceleration, buying persistence, whale share, suspected coordination, source recency, clean coverage and recovery limitations. Values reuse the existing feature cache only when timestamp membership matches exactly; expired/future membership is checked anew. No new rolling history is maintained.

Clean coverage comes from the existing engine and is additionally capped by tracking/gap/buffer-loss watermarks. “Complete” means the requested observed time window has no recorded continuity barrier; it is **not** guaranteed chain-wide delivery, strict CURRENT, proof of security or an executable quote. A 500-event loss can invalidate 180 seconds while a later clean short window eventually becomes usable. Recent losses and recovery overlap cannot be silently upgraded.

The first supported interpretation can arise after a clean 10-second window with three canonical trades and a fresh verified curve observation. It is not promised ten seconds after launch: discovery, admission and verification can arrive later.

### Explicit research rules

These are descriptive, uncalibrated heuristics, not changes to the trading strategy:

- **EMERGING BULLISH:** clean recent 10s/30s window, at least three samples, buy-count dominance and at least three observed buyer addresses. Unknown amounts remain unknown; this can be a count-led interpretation with VERY HIGH uncertainty.
- **BULLISH DEVELOPING:** additionally, clean 60s consistent-unit evidence, at least three estimated independent buyers, positive net flow, buying in at least half of the existing six bins and non-declining recent arrival.
- **BEARISH PRESSURE:** observed short-window sell dominance by count or known net flow; also the existing verified-curve collapse boundary. Numerous small buys cannot hide a larger known sell.
- **NEUTRAL / WAIT:** mixed participation or declining arrival after earlier buying; earlier hype alone does not establish continuation.
- **PULLBACK WATCH:** verified curve retreat reaching the existing pullback boundary, below its collapse boundary, with renewed buying. This is not called a price pullback without price evidence.
- **TOO EXTENDED:** existing MISSED assessment, post-graduation, or the existing >=85% high lifecycle region. Curve progression is not price appreciation.
- **AVOID:** recorded hard security/core rejection, creator selling, concentration above unchanged limits, invalid distribution data, disagreement or degraded evidence. Suspected size/timing coordination also withholds bullish attention and is explicitly not proof of common ownership.
- **INSUFFICIENT DATA:** fresh verified lifecycle or a usable clean short window is absent.

Known risks have precedence. Unknown security, missing concentration measurements and missing amount evidence are visible, not treated as safe. Raw address breadth is never labelled proven independent ownership. Attention 0–3 is ordinal; uncertainty is descriptive, not a profit probability.

## Product workflow

The existing Opportunity page has a **SPECULATIVE REVIEW — RESEARCH ONLY** filter and early-quality/urgency sorting, reversible to the original lifecycle ranking. Existing strict reviews stay separate. Cards show compact interpretation, age, security/uncertainty, and expandable window metrics, missing evidence, strengthening conditions and invalidations. The existing detail view exposes the full context. Copy mint, external FOMO workflow and manual fill recording remain unchanged.

The same fresh assessment appears alongside existing Manual Position exit intelligence. HOLD WATCH/PROTECT PROFIT/EXIT RISK and other exit predicates/notifications are not rewritten by this research layer. There are no new targets, profit estimates or automated actions.

Interpretations expire after at most **10 seconds**, sooner if trade, curve, security, liquidity or supported displayed-price evidence expires. Browser timers and disconnected-state handling replace stale bullish interpretations with DATA STALE. This is a **research display deadline**, not an invented quote expiry.

Only a current series of at least three timestamped DEX Screener USD market observations can describe rising/falling/mixed sampled price marks. Pump trade direction and curve progress cannot create prices, candles, returns or market cap. Manual price input is excluded from these provider-pattern calculations. Even supported displayed-mark movement is not a fill, executable return or profit. No fake chart was added.

## Separation and remaining limitations

- Original Opportunity-v1 actions, ranking, research version, inclusion/outcome logic, strict 180s CURRENT, entry review approval and `approved_evidence=None` are preserved. New research attention cannot grant ALLOW_PAPER_ENTRY.
- The V2 display calculation runs in the existing periodic UI/manual projection. The `manual=False` provider-only frozen-v1 research path does not calculate/adopt V2, so no extra V2 work is added to the per-trade research callback. There is no new research enrollment or outcome stream. Existing manual thesis snapshots can retain the displayed interpretation; V2 transitions do not constitute a complete prospective dataset.
- Existing deep/hot curve polling, last-attempt fairness, background batches and RPC budgets were inspected and left unchanged. New attention is deliberately not fed back into provider selection. Verification can still be delayed under the 25-deep/250-candidate bounds; no quote identity is guessed and no rate limit is raised.
- Unknown quote units still prevent amount-weighted interpretation and independence/coordination estimates. An unknown-unit window may support counts only.
- Executable entry/exit routes, interface costs and after-cost outcomes are unverified. Current displayed liquidity is not proof that a position can sell. Missing price/liquidity information remains conspicuous.
- PumpSwap schema acceptance is unchanged; this is pre-graduation research. No unknown suffix is accepted.
- Interpretation quality/predictive value and live operational capacity remain unvalidated. Nothing here demonstrates profitability or readiness for real-money recommendations.

## Offline examples and rendered evidence

The ignored `data/early_edge/early-market-v2-20261025/scenario-assessments.json` contains full synthetic, timestamped assessments; no real outcomes or wallets are exported.

| Synthetic case | Result |
|---|---|
| 15-second early buying | EMERGING BULLISH |
| 65-second persistent breadth/flow | BULLISH DEVELOPING |
| Buying followed by selling | BEARISH PRESSURE |
| Buying arrival exhaustion | NEUTRAL / WAIT |
| Verified curve retreat plus renewed buying | PULLBACK WATCH |
| 500-event history with active-window loss | INSUFFICIENT DATA |
| Suspected coordinated sizes/timing | AVOID |
| Unknown units, missing price | EMERGING BULLISH; counts only, VERY HIGH uncertainty |
| Stale evidence, recovery overlap or late observation | INSUFFICIENT DATA |
| Hard security failure | AVOID |
| High lifecycle region | TOO EXTENDED |

Additional regressions cover severe curve collapse, invalid distribution data, future observations, underlying-evidence expiry and net selling despite buy-count dominance. No case invents a price series or upgrades strict CURRENT.

[Open the styled offline DEMO render](../../data/early_edge/early-market-v2-20261025/demo-render.html). This is the actual React Opportunity component rendered to static HTML using existing isolated DEMO examples and the current stylesheet. It is **not a browser screenshot or a live application session**. Interactive filtering, sorting, expiry and manual workflow are covered by frontend tests. The render contains bullish, bearish, pullback, extension and avoid examples, all explicitly synthetic.

## Validation and resource cost

- Focused backend regression selection: **266 passed**, normal exit, 17.87s. Includes new scenario tests plus original opportunity, manual workflow, approval boundary, token receipts, features, buffer-loss, canonical trade and truncation suites.
- Complete frontend suite: **55 passed** across seven files; final DEMO artifact generation also passed its isolated render test.
- TypeScript check and Vite build passed; JS bundle 294.50 kB / 89.19 kB gzip. No dependency manifests changed.
- Ruff and mypy passed for changed backend sources; basic secret scan passed (265 source/document files), with a separate pass for the renderer test outside those scan roots; `git diff --check` passed. Preservation results are recorded below.
- No full backend suite, live run, throughput/endurance campaign or prospective evaluation was performed.

A direct synthetic component measurement (250 evaluations, each reading the existing maximum 500 retained events over four windows) is in `component-cost.json`. Final figures are appended below. It excludes settings construction and existing curve calculation; it is **not** a sustainable event-rate measurement. A worst-case 250-token refresh can consume hundreds of milliseconds, so full-population runtime service margin is not established. No additional cadence, queue or provider changes were made to hide that cost.

The largest generated assessment was 3,675 JSON bytes. A decoded synthetic assessment measured about 9.7 kB of Python objects, suggesting a few MiB for 250 result objects plus transient serialization. This is an estimate, not a whole-process RSS measurement. Work is bounded by 500 existing events, four fixed windows and existing candidate limits; no extra raw histories, network requests, writes or outcome samples are created by the new UI projection. Original bounded operational receipts are unchanged.

## Exact files changed

1. `backend/app/opportunity.py`
2. `backend/app/intelligence.py`
3. `backend/app/intelligence_demo.py`
4. `backend/tests/test_early_market_v2.py`
5. `frontend/src/intelligenceTypes.ts`
6. `frontend/src/components/Opportunity.tsx`
7. `frontend/src/components/ManualPositions.tsx`
8. `frontend/src/style.css`
9. `frontend/src/components/EarlyMarket.test.tsx`
10. `frontend/tests/early-market-render.test.tsx`
11. `backend/docs/early-opportunity-intelligence-v2-20261025.md`

**No staging, commit, push or merge.** The practical improvement is visible, explainable short-window research before established 180-second evidence, while preserving the distinction between attention, entry approval and proven after-cost performance.

Final direct component measurement: 1.230ms mean / 2.759ms maximum; 307.487ms for 250 worst-event-count evaluations.

Preservation verified: 15 initially hashed files unchanged, including the five unrelated files, original database/sidecars and backup; all 7 original frozen artifacts match, and the retired database stat is unchanged.

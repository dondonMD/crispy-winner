# Early Momentum Freshness V2.1 — offline implementation

Source baseline: `c8b176310e1dd57a8ac2905c6f460162010f6bbc`, branch `remediation/early-edge-evidence-readiness`. Interpretation version: **`early-market-v2.1-efaf95120908`**. This is a separately source-hashed descriptive policy; opportunity-v1, strict entry approval, strategy configuration and research outcome protocols are unchanged. PRE_COHORT_READY=NO; Phase 4 remains unauthorized.

## Correction

V2 preferentially interpreted a supported 30s window and accepted recency up to the existing general freshness bound. Consequently, positive historical buying could remain EMERGING BULLISH with an empty latest 10s window. V2.1 uses the existing minimum three samples and three observed buyer addresses in a clean, recovery-free latest 10s window for active bullish interpretation. Addresses are not guaranteed independent people. No new numerical cutoffs were fitted to subsequent outcomes.

| Assessment | Supporting evidence | Speculative attention |
|---|---|---|
| ACTIVE EMERGING BULLISH | Clean 10s, at least three trades and three buyer addresses, buy-count dominance; known net flow must be positive | Possible before 30s/180s; existing risk/lifecycle gates still apply |
| BULLISH DEVELOPING | Active 10s plus supported positive 30s and consistent-unit 60s breadth/persistence; no declining 10s/30s arrival evidence | Possible, research only |
| BUYING COOLING / WAIT | Supported positive 30s history without sufficient latest 10s buying | No urgent speculative review; valid historical context remains visible |
| BEARISH PRESSURE | Supported current sell dominance by count or known net flow; alternatively existing verified curve-collapse condition, explicitly identified as lifecycle evidence | No |
| PULLBACK WATCH | Existing verified curve-retreat condition plus genuinely renewed active 10s buying | Possible, research only |
| NEUTRAL / WAIT / INSUFFICIENT DATA | Mixed current activity, thin evidence, stale curve or incomplete continuity/recovery | No; inactivity is not inferred selling |

Known security/creator/concentration/core rejection risks retain precedence. Unknown units permit count-led interpretation with VERY HIGH uncertainty: amount-weighted flow, coordination and independent-buyer estimates remain unavailable. Stronger developing claims require available consistent-unit metrics. Active 10s buying against adverse 30s context carries an explicit contradiction warning rather than a developing claim.

Assessments expose supporting timeframe, immediate participation state, latest observed trade/buy age and active-buying flag. Existing expiry remains binding; active bullish validity is additionally capped at last observed buy plus 10s. A fresh cooling assessment is distinct from a stale assessment. The frontend requires V2.1 active participation for the speculative lane. Existing retained cards, manual refresh ordering and expanded disclosures are preserved. Manual Positions reuses the shared evidence panel; exit predicates are untouched.

## Frozen observations and deterministic results

The original session `39ef6a42-1ea3-4663-b458-704eeacfbe81` was inspected read-only. The comparison uses signal-time processed prefixes (61 PEPEOZ events, 12 MineMons events), verifies original window sample totals, and excludes later-processed events even when their source timestamps precede assessment time. It does not replay all final events backward as if already known. Risk state from later observations is not imported.

| Scenario | V2.1 result | Review |
|---|---|---|
| PEPEOZ: 19 buys/7 sells in clean 10s, three buyer addresses, mixed/unknown units, latest trade age 1.33s | ACTIVE EMERGING BULLISH; count-led, VERY HIGH uncertainty | Yes at that historical assessment |
| MineMons: 5 buys/1 sell in clean 30s, approximately +2.558 SOL, empty latest 10s, latest trade age 12.62s | BUYING COOLING / WAIT | No |
| Continuously supported strengthening buying | BULLISH DEVELOPING | Yes |
| Quiet historical buying, then three genuinely renewed buyers after verified curve pullback | Cooling, then PULLBACK WATCH | Only after renewal |
| Recent selling overturns earlier buying | BEARISH PRESSURE | No |
| Unknown amounts but canonical clean 10s count/breadth support | ACTIVE EMERGING BULLISH, VERY HIGH uncertainty; no amount claim | Possible |
| Creator selling, hard security failure or known coordination | AVOID | No |
| Missing continuity, pending recovery, truncated active history or late discovery | INSUFFICIENT DATA where required window unsupported | No fabricated CURRENT |
| Expired activity | No fresh review; inspectable historical card | No |

These are policy interpretations, not fills, profits, forecasts or proof of improved returns. No validated execution prices or after-cost outcomes were introduced. Historical reports and original receipts are not rewritten. A backdated call over a mutated token is not an availability replay: callers must supply the actual as-of processed snapshot. Regression tests explicitly freeze the prefix and prove later processed trades cannot mutate it.

## Resource measurement

Ignored local comparison artifacts: `data/early_edge/early-market-v21-20261025/`. A bounded component probe alternated 200 evaluations per policy over identical cached 500-event inputs and four windows. Final baseline mean 1.591ms/max 3.698ms versus V2.1 mean 1.827ms/max 4.965ms: approximately +0.236ms mean. Serialized result 3,418→3,649 bytes (+231); recursive result-object estimate 8,900→9,425 bytes (+525). An earlier measurement is preserved and also showed a small increase. A separate 200-call alternating CPU probe measured mean process CPU 1.144→1.294ms (+0.149ms, approximately 13%); wall means 1.138→1.286ms. Both measurements are preserved, including the less favorable first timings. Timing is environment-sensitive, not a throughput or RSS guarantee. No new persistent event history, tasks, provider requests or timers; existing 500-event buffer and four windows remain unchanged. Existing bounded receipt selection is not expanded.

## Changed files

- `backend/app/opportunity.py`: isolated interpretation policy and metadata.
- `backend/tests/test_early_market_v2.py`: scenario, immutability, continuity, unknown-unit and expiration regressions.
- `frontend/src/intelligenceTypes.ts`: optional V2.1 receipt metadata, compatible with historical V2.
- `frontend/src/components/Opportunity.tsx`: active-lane guard and shared timeframe/participation display.
- `frontend/src/components/EarlyMarket.test.tsx`: cooling transition retains card/filter/disclosure; manual position reuses context without changing exit assessment.
- This report.

No engine, database, decoder, manual journal, strategy, position-size, approval or cost-model implementation changed. Existing unrelated files and frozen evidence are preserved. No provider run, cohort, transaction, staging, commit or push.

## Validation

- Focused policy suite: **31 passed**, normal exit (1.02s).
- Complete frontend: **62 passed / 7 files**, normal exit; TypeScript and production build passed (Vite 3.48s). Initial fixture failure is retained in the local validation log.
- Ruff passed; mypy passed all **45 application source files**; basic secret scan passed **268 source/document files**; whitespace checks passed.
- Ordinary full backend invocation did not complete: 349 progress markers, then stalled at/after `test_api_demo_and_local_security` before the next test. It was interrupted (exit130), not reported as a full pass. The broader selected regression invocation was also interrupted and is not counted as passing. The existing bounded cleanup diagnostic is being used separately; it preserves `Runner.close` and actual worker joins rather than bypassing unfinished tasks.
- Preservation: all 17 pre-change file hashes match (unrelated files, frozen live receipts and maintenance backup); all seven original experiment evidence hashes match. Retired database size matches the older reference; its mtime differs from that old reference, and no session-start retired-file mtime was captured. This task did not open it for writing, so no causal attribution or stronger preservation claim is made from that metadata.

Full diagnostic backend result: **1,105 passed, 1 skipped, 1 failed in 169.77s; exit1**. This is not a green full-suite result. Failure: `test_observer_batch_reuses_exact_ranking_without_changing_selection` expects one `deep_mints()` call but observes two. The unchanged `attach_observer.refreshed()` computes the batch ranking, and unchanged `Intelligence.refresh_positions()` obtains the monitoring ranking. Replacing only `early_market_view` in memory with the exact baseline HEAD implementation reproduces the same failure (1 failed in 1.36s). Neither caller is modified by V2.1. The pre-existing assertion/observer contract discrepancy is recorded and left outside this policy task. No test is skipped or weakened to conceal it.

Local logs: `/tmp/crispy-v21-policy.log`, `/tmp/crispy-v21-frontend-final.log`, `/tmp/crispy-v21-backend-full.log`, `/tmp/crispy-v21-backend-diagnostic.log`, `/tmp/crispy-v21-baseline-ranking.log`. The ordinary invocation and selected run were incomplete; the diagnostic invocation completed normally with failure status. Ordinary backend runtime cleanup remains a separately unresolved environment/runtime validation limitation. An initial frontend test fixture omitted the required current monitoring receipt and correctly rendered DATA STALE rather than HOLD WATCH. The fixture was corrected to supply that receipt; production monitoring gates were retained.

## Remaining limitations

These heuristics are uncalibrated. Three buyer addresses do not prove independent ownership; unknown-unit activity cannot establish amount-weighted demand or rule out coordination. Ten-second support can reverse rapidly. Missing executable quotes, price history, liquidity/security evidence and outcome data remain explicit. No profitability or strict entry approval follows from speculative attention. No predictive study has been activated.

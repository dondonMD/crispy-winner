# Manual entry and exit companion — 2026-10-25

**Research/manual decision support only. PRE_COHORT_READY=NO. No automated trading.** Baseline `9c5f0297a5b2785e9fc770960283f7020dad275f`, branch `remediation/early-edge-evidence-readiness`.

## Existing workflow and narrow additions

|Workflow|Already implemented|Added here|
|---|---|---|
|Discovery/review|Opportunity rankings, explicit missing evidence, strict Companion WAIT/REJECT/TOO_LATE/ENTRY_CANDIDATE, detail review and copyable exact mint|Presentation-only ENTRY REVIEW — RESEARCH ONLY for existing EARLY_OPPORTUNITY; other research actions map to WAIT/REJECT/TOO LATE. Original research action remains visible. No backend action or eligibility changes.|
|External purchase journal|Local confirmed-entry API/form with mint, notional, price/cap, timestamp, notes and immutable thesis; backdated entries cannot reconstruct historical thesis|Optional positive human-unit token quantity and nonnegative actual entry fees, persisted/displayed with explicit unverified-user-report provenance. Blank is unknown; explicit0 is a user-reported known zero.|
|Position monitoring|Existing source-separated marks/peaks, manual/provider freshness, local storage/restart, journal closure and risk/invalidation assessments|HOLD WATCH display for existing MONITOR/HEALTHY, retaining the underlying evidence assessment. Existing PROTECT PROFIT, EXIT RISK, THESIS INVALIDATED, deterioration and DATA STALE remain. No new exit thresholds.|
|Cost context|Configured conservative liquidity-based estimates, never executable quotes|Complete consistent recorded fills use actual entry fees exactly once, replacing estimated entry charges; future exit costs remain the existing model plus reserves. Partial/inconsistent fill data yields no net estimate.|

Affected files: [manual.py](../app/manual.py), [exit_intelligence.py](../app/exit_intelligence.py), [test_manual_fills.py](../tests/test_manual_fills.py), `frontend/src/components/Opportunity.tsx`, `Opportunity.test.tsx`, `ManualPositions.tsx`, `frontend/src/intelligenceTypes.ts`, and this report. Reused existing APIs/tables/components; no new provider, database migration, pipeline or execution service.

## Evidence and cost semantics

Amount means filled token notional excluding paid fees. Quantity is human token units; price is the reported average execution price in USD. Actual fees are paid entry expenses outside that token notional, excluding recoverable rent. The user must not enter a fee twice when translating their interface receipt. Reports are not independently chain-verified. Optional fields preserve old amount/price or cap-only journals; an incomplete purchase report is still recordable, never fabricated into a complete fill.

For complete fills, quantity×entry price must agree with notional within one US cent (absolute rounding allowance, not an opportunity/strategy threshold). Otherwise no net estimate. With a fresh price and fresh liquidity, gross marked value is quantity×current price; estimated net P&L is that value minus notional, actual entry fees and modeled exit costs. Modeled entry fees/slippage/impact are not charged again: the actual fill price already embeds entry execution. Configured exit protocol/platform/network/priority/slippage/impact and failed-attempt reserves remain unchanged. Return percentages retain the existing notional denominator, not a claim about full cash-debit ROI.

When neither fill field exists/is supplied, legacy modeled estimates remain explicitly estimates; existing historical records are not migrated or rewritten. When one new fill field is supplied without the other, the net estimate is unavailable. No current mark, price basis, consistent inputs or current liquidity means no net P&L. Market-cap-only marks remain descriptive proxies. Estimates are not realized profits, executable sell quotes or independently verified fees. Actual manual cash is user maintained; journal actions never debit the paper account or grant core approval.

The existing exit predicates consume the corrected manual cost estimate; this can remove a PROTECT PROFIT assessment when actual paid entry fees eliminate the modeled gain. Risk/freshness thresholds and the core economic estimator/settings are untouched. HOLD WATCH is only a display label: it is not safety, a recommendation to keep holding, or a confident exit time. Underlying MONITOR can mean current partial evidence with unavailable trade flow. Missing important evidence still produces DATA STALE; supported adverse evidence retains risk/invalidation precedence.

## Coverage and remaining limitations

Pre-graduation coverage is **insufficient for trustworthy real-money recommendations**. Existing curve/trade intelligence can support research review, but security scans are selective, many early tokens lack verified quote units/current buyer evidence, and the production USD/liquidity enrichment primarily serves graduated PumpSwap candidates. User-entered marks remain visibly unverified and expire; they cannot create verified provider research or strict entry evidence. Evicted/untracked journal mints receive no additional scans and cannot be called healthy. Recording a holding does not silently expand provider capacity or monitoring guarantees.

Approved evidence remains None: no ALLOW_PAPER_ENTRY or strict ENTRY_CANDIDATE is manufactured. Research ENTRY REVIEW is deliberately distinct. The separate pre-grad research contract remains NOT QUALIFIED for executable-route outcomes. Reliable route availability, actual exit liquidity, interface-specific fees, sell restrictions, current program compatibility and validated prospective after-cost predictive evidence remain unresolved. No exit timing or profitability is promised. No historical or new cohort is activated.

## Offline validation

- Initial regression failed because quantity/actual-fee inputs were forbidden; this gap is now covered.
- Final focused backend: **133 passed in16.60s, normal exit0**. Covers external fill persistence/reload/closure, local API round trip, unknown versus zero fees, invalid/partial/inconsistent inputs, actual-fee non-double-counting, negative after-cost scenarios, stale marks, legacy workflows, research isolation, origin protection and Phase2A approval restrictions. API test initially used a disallowed synthetic hostname and correctly received403; corrected to existing allowed testserver without changing security middleware.
- Frontend: **44 passed in6.49s**. New tests cover research-only labels/action preservation, local entry payload with quantity and explicit zero fees, negative-fee refusal, and cautious HOLD WATCH display. Existing mint-copy, journal-only close, missing-data and DEMO isolation tests remain green.
- Ruff on changed backend files/tests passed; mypy42 application files passed. TypeScript and production build passed (Vite5.79s); TypeScript was checked again after final test additions. No dependency changes or installs.
- Secret scan, whitespace/source-scope checks and preservation checks are completed before delivery. No full backend rerun, live monitor, quote-provider call, endurance workload, wallet access or transaction. All fixtures are synthetic, not real purchases or profits.

The five unrelated worktree files, seven original frozen artifacts, private receipts and retired database metadata remain preserved. Ignored local validation results: `data/early_edge/manual-companion-20261025/`.

## Publication

Git metadata is read-only; no commit/push or bypass. Publish only the eight intended files from writable WSL:

```bash
git switch remediation/early-edge-evidence-readiness
git add -- backend/app/manual.py backend/app/exit_intelligence.py backend/tests/test_manual_fills.py frontend/src/components/Opportunity.tsx frontend/src/components/Opportunity.test.tsx frontend/src/components/ManualPositions.tsx frontend/src/intelligenceTypes.ts backend/docs/manual-entry-exit-companion-20261025.md
git diff --cached --name-only
git diff --cached --check
git diff --cached
git commit -m "feat: complete external manual fill journal workflow"
git push origin remediation/early-edge-evidence-readiness
```

Verify exactly those eight paths; exclude private data and unrelated changes. No main merge/force-push. **Manual workflow connected with explicit limitations; not validated buying or selling advice. PRE_COHORT_READY=NO.**

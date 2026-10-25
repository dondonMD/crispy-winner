# Live manual companion workflow — 2026-10-25

**PARTIALLY READY: connected manual workflow, incomplete market evidence. PRE_COHORT_READY=NO.** Baseline `b528c9c26ce4687d5d4193a26f4114e36efebbf6`, branch `remediation/early-edge-evidence-readiness`. No live run, cohort, provider change, order/wallet integration, commit, push or merge.

## Reused functionality and minimal corrections

- Existing Opportunity Intelligence, strict FOMO Companion, copy-mint control, external-fill form, durable ManualJournal, source-separated marks/peaks, Exit Intelligence and opt-in browser alerts are reused. No new research system or quote service.
- Opportunity is now the initial page. A ranked **RESEARCH ONLY** entry-review shortlist appears before the ordinary watchlist; qualifying candidates are selected before the20-result display cap. No qualifying candidate displays **NO QUALIFYING ENTRY REVIEW** (respecting selected filters). Original research actions, ranking components, lifecycle, evidence grades, missing evidence, exact visible/copyable mints, assessment/source timestamps and clean trade coverage remain visible.
- ENTRY REVIEW presentation now requires the existing EARLY research action, current pre-grad state/curve<85, current verified security, known creator/holdings, concentration within existing10%/30% gates, current continuous unit-valid flow and nondegraded data. This does not change research classification or permit strict entry. Approved evidence remains None; no ALLOW_PAPER_ENTRY, economic allowance or strict ENTRY_CANDIDATE is manufactured. USD prices/quotes may still be missing, prominently labelled.
- Review receipts expire using the existing source TTLs. The browser withdraws ENTRY REVIEW after expiry, application-stream disconnection or resource pressure, including when no new SSE message arrives. Missing legacy receipt metadata fails closed. Simulated examples never enter the real shortlist.
- External manual workflow retains exact mint copying and fill recording. Links use the official [FOMO homepage](https://fomo.family/) for copy/search and the existing encoded exact-mint Pump.fun route. An authoritative FOMO per-token deep-link format could not be verified; none is guessed. Links require user clicks, open with noopener/noreferrer, contain no referral, credentials or transaction parameters.
- Already-tracked open manual holdings receive deterministic deep-slot priority after paper protection and before ordinary candidates. They are protected from ordinary capacity eviction/inactivity expiry while open, without raising candidate/deep/RPC limits. Lower-capacity/resource-pressure cases can still leave holdings outside the deep set and are explicitly degraded. No untracked/expired token is silently reactivated or admitted just because a journal entry exists.
- Journal reload/cold restart restores holding priority for candidates recoverable from existing checkpoints. Evidence still rewarms; old security/trades/prices do not become current. Migration uses the existing epoch transition and independently verified/security-eligible pool workflow. Held status never forces an unsafe/unverified pool into PumpSwap subscriptions.
- Each position now has a time-bounded monitoring receipt. Missing tracking, deep capacity, provider connection, current security/flow/curve/mark or resource/storage health yields **MONITORING DEGRADED**. The browser hides cached P&L and favorable assessments after receipt expiry/disconnection, while retaining adverse historical risk notices with an explicit stale warning. No past negative information is deleted.
- Existing exit predicates are unchanged. DATA STALE and MOMENTUM DETERIORATING transitions join the existing risk/profit-protection notifications. Per-position/action deduplication prevents repeated unchanged alerts and avoids one action's cooldown masking a different urgent action. Existing browser permission/high-water dedup and bounded delivery remain; repeated SSE alerts do not notify twice, and WAIT cannot become an entry alert. OS/browser delivery is not guaranteed; all assessments remain visible in the UI.

## Pre-grad price and practical limitations

**No indicative pre-grad USD number was fabricated.** Live curve polling verifies curve progress/reserves but does not acquire the complete coherent pricing/fee state, verified base decimals and fresh USD reference required by the existing isolated quote oracle. The UI says UNAVAILABLE and distinguishes user-entered spot marks from provider observations/executable quotes. The research quote math remains isolated; no background oracle/FX poller was added or promoted into core evidence. Thus this task does not complete automatic pre-grad USD marking or executable sellability.

Selective security coverage, missing quote units, gaps, absent early USD/liquidity marks and the preserved PumpSwap schema issue still limit real entry/exit evidence. Current adverse evidence can invalidate a thesis; absence of evidence cannot establish safety. A holding outside restored candidate coverage requires an explicit degraded status and manual external review, not a guessed historical reconstruction. FOMO/interface fees and real route availability are not independently verified by journal entry. These limitations prevent trustworthy buy/sell recommendations or profitability claims.

## Exact intended files

1. `backend/app/engine.py` — bounded holding priority/protection; optional action-specific alert dedup key.
2. `backend/app/intelligence.py` — monitoring receipts and exit transition notifications.
3. `backend/app/opportunity.py` — presentation-only review eligibility/freshness metadata.
4. `backend/tests/test_manual_live_workflow.py` — synthetic workflow regressions.
5. `frontend/src/App.tsx` — initial Opportunity view and stream-health propagation.
6. `frontend/src/components/Companion.tsx` — shared safe external manual links.
7. `frontend/src/components/Companion.test.tsx` — initial-view adaptation and browser-alert regression.
8. `frontend/src/components/Opportunity.tsx` — current-only shortlist, timestamps, explanation and unavailable-price notice.
9. `frontend/src/components/Opportunity.test.tsx` — stricter label/ordering/expiry/position regressions.
10. `frontend/src/components/ManualPositions.tsx` — monitoring degradation and stale-client evidence handling.
11. `frontend/src/intelligenceTypes.ts` — optional receipt metadata; old journal rows remain compatible.
12. This report.

## Validation and disposition

Focused backend: **173 passed in17.82s, exit0**. Includes new presentation, concentration, held-slot/capacity/expiry, journal/cold restart, migration/epoch and notification tests; existing manual-fill, Opportunity, Companion, PumpSwap and approval-boundary regressions pass. Cold restart explicitly does not grant CURRENT, and migration without an eligible verified pool remains unavailable. Additional existing candidate-expiry/lifecycle/RPC/enrichment regressions: **40 passed in15.96s, exit0** (a disjoint focused group).

Frontend **49 tests passed** and TypeScript/production build pass on the final source (results recorded under ignored `data/early_edge/manual-workflow-20261025/`). Tests cover shortlist priority ahead of higher-ranked incomplete tokens, stale/graduated/dangerous/disconnected exclusion, original research semantics, copy/fill forms, historical risk retention, cached-profit withdrawal and deduplicated opt-in browser alerts. These are component/SSE fixtures, **not a live browser/market validation**. Initial expected label/default-page regressions were updated to the stricter intended behavior; failed receipts remain preserved. No broad backend/full-load campaign.

Ruff, mypy44 application files, secret and whitespace/scope checks are completed before delivery. Five pre-existing unrelated files, all frozen historical artifacts/private receipts and retired cohort database metadata are preserved. Source/configuration risk limits, strict decoder/full consumption, recovery/durability and approved_evidence behavior are unchanged.

**Browser workflow available:** review ranked evidence → copy/check exact mint → open external interface manually → record the actual external fill → inspect holdings' fresh/degraded evidence and existing exit assessments. **Not established:** continuous coverage of every holding, current pre-grad USD quotes, FOMO token deep links, executable fills/exits or validated predictive performance. PARTIALLY READY, not approval to trade. No further experiment is started. Changes remain uncommitted for user review.

# Opportunity scroll-reset fix — 2026-10-25

Branch: `remediation/early-edge-evidence-readiness`; baseline `44c0555`. Frontend usability correction only. **PRE_COHORT_READY=NO.** Nothing staged, committed or pushed.

## Reproduced causes

1. **Between-tick clock defect.** `useNow()` returned state sampled by its one-second interval. A fresh SSE receipt arriving 500ms after that sample had `observed_at > now`, despite being current at render time. The speculative-only predicate rejected it as future data. A deterministic regression reproduces the fresh-review count dropping to zero before correction.
2. **Automatic list collapse.** The page reapplied the fresh speculative predicate every timer/SSE render. Legitimately expired records disappeared outright. A pre-fix regression confirms the inspected card is removed on expiry. Removing all cards can shorten the document enough for a browser to clamp scroll to the top.
3. **Moving reading targets.** Every update re-sorted the cards. A pre-fix regression confirms the first card changes as scores change while scrolled.

`App.tsx` uses the same Opportunity component at the same tree position for routine data updates, and card keys are mint-based. There is no document reload, navigation command or scroll-to-top call in these update paths. CSS uses ordinary document scrolling; no CSS scroll-container defect was established. The physical browser clamp explanation is supported by the reproduced DOM collapse, but pixel-level scrolling was not measured here.

## Minimal correction

- `useNow()` retains the existing one-second idle refresh, but reads the **actual clock on every render**, including SSE-driven renders. The existing `observed_at <= now <= valid_until` checks remain intact; truly future-dated and expired observations remain ineligible. No time tolerance was added.
- A small inspection hook retains **at most 20 existing display records**, matching the existing card limit. It holds order while the speculative filter is selected, or after scrolling/focus/pointer interaction with a card. Latest data replaces each matching mint's contents without remounting the card.
- Expired, disqualified or removed cards remain inspectable. They do not count as qualifying reviews. Removed-feed records are forced historical immediately, even if their old receipt deadline has not passed. Stale headers show DATA STALE, zero attention and UNKNOWN direction; interpretation/price/window details are explicitly historical instead of being removed.
- Existing native evidence disclosures keep their DOM identity and open/closed state across updates. Historical interpretations remain readable, including when an opportunity stops being speculative.
- New matching records append when there is room. If all 20 reading slots are occupied, a count announces matching records outside the list. **Refresh ranking** explicitly applies current order and clears retained history. No arbitrary scrolling occurs.
- User filter/sort changes reset the reading selection. Mode changes discard retained records across DEMO/OBSERVE. Genuine navigation unmounts the page and clears its checkbox/inspection state; routine SSE refreshes do neither.

The cache is page-local and ephemeral, holds one latest/display snapshot per visible record, and has no database or local-storage persistence. It is not an evidence buffer or eligibility source. No additional polling, EventSource connection or timer was introduced; there is one passive scroll listener with cleanup. When not inspecting, the original ranked-list contents are preserved.

## Validation

New regressions cover filter selection, scrolled data updates, expiry while expanded, changed ranking, explicit refresh, new arrivals, removed-feed records, 20-card bounds, mode changes, actual `App` SSE handling, native disclosure toggling, navigation/unmount cleanup and between-tick time comparisons. The future-dated receipt negative test still rejects a timestamp one second ahead of actual time.

**Final complete frontend suite: 60 passed across seven files, normal exit, 11.48s. TypeScript (`tsc --noEmit`) and Vite production build passed (3.37s).**

The App test uses the real component and EventSource message handler with an isolated synthetic in-memory stream. It confirms one stream instance, unchanged page/card nodes, checkbox persistence, no `scrollTo` calls, historical labeling and expected navigation cleanup. This is dynamic application testing, not merely a static render and not a real provider session.

**Browser limitation:** Chromium, Firefox and Playwright were unavailable in the environment. jsdom does not calculate document height, browser scroll anchoring or actual scroll clamping. Its scroll-position property assertions do not prove pixel-level stability. No browser-level result or live dashboard session is claimed. The remaining manual check is the user's original DEMO sequence with regular updates: select the filter, scroll, expand evidence and wait through several updates/expiry; cards should remain in place and turn historical. An explicit Refresh ranking may intentionally change the list.

## Exact files modified

- `frontend/src/components/Opportunity.tsx`
- `frontend/src/components/useOpportunityInspection.ts` (new)
- `frontend/src/components/EarlyMarket.test.tsx`
- `backend/docs/opportunity-scroll-reset-20261025.md` (this report)

`App.tsx` and `style.css` were inspected but did not need changes. No backend source, database, monitoring, classifier, risk, approval or manual-execution logic changed. The five unrelated worktree files and pre-existing investigation report are preserved, verified by before/after SHA256. Basic secret scan passed (267 source/document files), and `git diff --check` passed.

**Assessment:** the demonstrated clock/filter-collapse and reordering defects are corrected and covered by dynamic update regressions. Browser pixel-level confirmation remains unverified; no promise of zero layout movement from changing text is made.

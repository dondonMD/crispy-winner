# Final audit — 2026-10-08

- Backend: 36 pytest tests passed; full risk/state/score replay comparisons, migration, delayed paper fills, restart balances/dedup, missing-first-outcome bias, provider malformed/429/timeout/reconnect, resource pressure and storage cap.
- Python: Ruff backend/scripts and mypy backend/app passed (18 source modules).
- Frontend: TypeScript build and 2 Vitest tests passed; compiled assets served by FastAPI. No browser screenshot or browser interaction test was run. Frontend lint consists of strict TypeScript checks, not ESLint.
- Basic source secret scan passed; .env/data/logs/build output/venv ignored. Credential-bearing URLs are not logged. Scan is a heuristic, not a forensic guarantee.
- npm audit: zero known vulnerabilities after upgrading Vitest; removed unused chart library.
- pip-audit: exact 40-package application/dev lock, zero known vulnerabilities. Auditor installed only for development and excluded from lock/runtime requirements. Lock has exact versions but no wheel hashes; provenance is PyPI/npm registries.
- Read-only real providers: free discovery yielded 19 launches in provider probe; full OBSERVE pipeline yielded 14 real candidates, all WAIT, no simulation or account spending. Public RPC and DEX endpoints responded. Paid trades not verified without a funded provider credential; real graduation delivery was not witnessed during the short probe.
- Final DEMO health and dashboard responses verified on 127.0.0.1:8765. Synthetic migration/recovery scenarios are visible; paper cash stays $20 without evidence.
- Performance: see measured benchmark, 88.6MB idle / 108.1MB bounded load; actual SSE demo server snapshot was 118.1MB RSS and 32.4% process CPU before reducing idle recomputation. CPU is a point sample, not a sustained mean.
- No claim of an established positive real-market after-cost expectancy. No autonomous execution, wallet secrets, inbound remote access or telemetry.

Remaining practical constraints are documented in limitations.md, not represented by production stubs. Significant future research: independent prospectively frozen cohorts; accurate route/effective-reserve/fee quotes; bounded funding-source evidence and execution-latency sweeps.

## Free OBSERVE enrichment fix — 2026-10-12

Code inspection reproduced the dependency: full RPC enrichment required migration or five
observed buyers; with disabled trade subscriptions buyers stayed unobserved and no curve evidence
could unlock the score-gated lifecycle. Added bounded batched curve RPC, separate observational
lifecycle thresholds, selective deeper security scans, unavailable trade presentation and truthful
unused-provider health. Entry thresholds/economics remain conservative; missing trade subscriptions
now explicitly block entry even if a fixture supplies apparently favourable quality scores.

- Backend: 43 tests passed, including free-mode/no-trade curve monitoring, batched order/cache,
  malformed accounts, completion vs migration, lifecycle/score separation, scan bounds, failed
  security refresh, provider states and DEMO/replay. Entry-gate fixtures now explicitly enable
  trade data to test the existing gates independently. Restricted sandbox suite stalled in
  DEMO/replay; the complete suite passed outside it.
- Provider smoke: PumpPortal connected, five live launches in its window; RPC connected; DEX
  connected, zero matching PumpSwap markets for the probe mint (expected).
- Isolated 65-second OBSERVE: 16 real launches, 21 curve-account attempts, 18 successful curve
  observations across repeated polls, 14 candidates with progress at final snapshot (0–6.43%).
  Eight HTTP RPC request starts, 0.1231 requests/second averaged over the window. Active/deep
  candidates 16/16; 93.5MB sampled RSS; no provider errors/rate limits; PumpPortal/RPC CURRENT,
  DEX NOT USED YET with zero requests. Zero paid trade subscriptions; paper cash $20.
- No live MATURING/NEAR_GRADUATION/migration example occurred in the initial window. Full security
  scanning was not triggered by the low observed progress; bounded higher-progress behaviour
  is covered by fixtures. This is a short connectivity/resource observation, not a sustained
  load benchmark or proof of positive after-cost expectancy.

- Frontend: three tests passed, including unused/current/degraded/rate-limited provider wording
  and null metrics; strict TypeScript and production build passed. Ruff, mypy (18 modules)
  and the basic source secret scan passed. No browser automation was used.

Final repeat after all backend tests passed: provider smoke observed three launches with all
three providers connected and zero expected probe markets. The final 65-second isolated OBSERVE
run discovered 18 launches and made 28 curve-account observations, all successfully parsed with
compatible progress. Final active/deep counts were 18/18, RSS 93.6MB, ten RPC request starts
(0.1538/second). PumpPortal/RPC ended CURRENT; DEX remained NOT USED YET with zero requests.
RPC recorded three throttling errors and a Retry-After cooldown timestamp, then recovered.
One real token reached 70.76% and MATURING without trade events; no NEAR_GRADUATION or migration
was witnessed. Zero paid subscriptions and $20 paper cash remained. This supersedes the initial
window's absence of MATURING; fixture coverage still supplies the near-graduation/migration cases.

## Fair and regression-aware lifecycle monitoring — 2026-10-12

User-reported longer-run checkpoint (not a measurement taken by this change): approximately
80–85 active real candidates, hot cap 25, two NEAR_GRADUATION tokens, 2,464+ processed events,
zero drops, queue 0/1000, about 121.7MB RSS, unavailable buyer/flow evidence, zero entries and
$20 paper balance. Code inspection reproduced a missing NEAR_GRADUATION → MATURING transition
and curve polling restricted to the hot set.

Implemented near-entry 85% / near-exit 75% hysteresis with separate session peak, conservative
stale/unknown lifecycle handling, oldest-first bounded background sweeps, single-attempt
background requests, adaptive error/429 backoff and health/UI counters. Economics, risk and
trade-evidence gates are unchanged; no wallet or trading capability added.

Validation: 54 backend tests passed, including the full 84/86/82/75/70/90 progression/regression
sequence with unchanged maturity/momentum and WAIT, completion vs authoritative migration,
250-candidate repeated fair sweeps at the 25-hot cap, promotion, newer-arrival fairness, unknown/
stale label removal, 429 backoff/recovery, one-attempt background HTTP behaviour, expiry during
RPC awaits, pressure pausing and restart re-verification. Four frontend tests, strict TypeScript/production build, Ruff, mypy and the basic secret scan passed.
Full backend suite ran outside the restricted sandbox. No browser automation was used.

Live verification, default settings (300 seconds): 30 real launches, active/hot/background
30/25/5, 136 account attempts, 104 returned account observations and 99 verified curve values.
Sixteen hot logical batches, 22 actual RPC HTTP request starts (0.0733/second), 4.73 returned
curve accounts per curve HTTP request including retries. RSS 96.1MB (sampled peak also 96.1),
queue 0 at final snapshot / 21 sampled peak, zero dropped events. RPC recorded eight connection/
timeout errors, zero HTTP 429s; adaptive background backoff grew, and the five background tokens
were still recently attempted (oldest 62.1 seconds). Consequently no background batch became
due within this window. PumpPortal recorded six reconnects; both PumpPortal and RPC ended CURRENT.
DEX remained NOT USED YET with zero requests. No security scans, entries or paid subscriptions;
paper cash $20. Observed progress was below the maturing threshold, so no near-regression,
high-progress promotion or migration case was witnessed. Current/peak differences were observed
on early curves; the near-regression/promotion cases are deterministic tests, not invented live cases.

An initial 300-second probe was inconclusive: two late launches, one RPC request still pending
at shutdown, no completed curve observations, eight PumpPortal reconnects and 93MB RSS. A separate
connectivity probe then timed out on PumpPortal but confirmed RPC/DEX connectivity (zero expected
probe markets). These failures are recorded rather than reported as successful verification.

Isolated background diagnostic (`--seconds 240 --max-deep 2`; production default remains 25):
94 real launches, active/hot/background 94/2/92. Seven background batches emitted 59 curve
observations across 58 background mints, with one repeated background observation. Twenty-nine
hot batches and seven background batches made 36 actual curve/RPC HTTP requests (0.1500/second),
94 returned curve account observations / 91 verified progress values, 2.61 accounts per curve
HTTP request. Three parsed/compatibility results remained unknown rather than inferred. Final
background due count 16, oldest background attempt age 204.7 seconds. RSS and sampled peak
96.7MB, final queue 0 / sampled peak 3, zero drops. All provider error/429/reconnect counts zero;
PumpPortal/RPC CURRENT, DEX NOT USED YET with zero requests. No security scans (and therefore no
scans outside hot), entries or paid subscriptions; cash $20. Real MATURING progress reached
57.47%; earlier maturing curves also retreated (53.18% peak to 29.11% current, WATCHING).
No NEAR_GRADUATION regression or migration was witnessed; near hysteresis, hot promotion and
fair repeated 250-candidate coverage are verified by deterministic tests. This diagnostic
exercises background scheduling with a deliberately reduced hot limit; it is separate from the
30/25/5 default-run measurement, not a claim that application configuration changed.

## FOMO Companion — Phase 3

Extended clean HEAD `ebcf61d` without changing strategy thresholds, lifecycle transitions, polling schedules or provider acquisition. The typed backend companion is pure and revalidates stored ALLOW_PAPER_ENTRY with the existing evaluator plus finite positive sizing, current security/trade/market evidence and the engine's approved evidence context. No frontend eligibility strategy exists. Missing evidence fails closed. Current/peak curve, UNKNOWN security sentinel suppression, evidence completeness, deterministic blockers, existing small-account economics, manual ceiling and invalidation conditions are exposed through existing dashboard/detail/SSE views.

The new responsive companion queue has action counts, action/lifecycle/attention filters, mint search, accessible textual badges, exact Copy mint with visible success/selectable fallback, and Token Intelligence integration. SSE immediately replaces former entry statuses and clears evicted intelligence. Existing explicit notification permission is retained; entry alerts require a current backend companion entry. No additional endpoints, RPC/DEX acquisition, wallet, private key, transaction submission, FOMO integration, browser automation, telemetry or LLM service was added. Optional local watchlist/watched-token notifications were deferred.

Deterministic DEMO smoke: five seconds, 12 scanner candidates plus four separate labelled UI fixtures showing ENTRY CANDIDATE / WAIT / REJECT / TOO LATE. Fixtures use synthetic evidence under unchanged core gates and never enter scanner tokens, paper fills or Strategy Lab. Cash remained $20; 89.6 MB RSS, zero provider requests/drops; 100 snapshots averaged 5.2 ms with this small DEMO set. This is UI demonstration, not validation of market returns.

Default read-only OBSERVE smoke: 95.47 seconds; 43 real launches, 60 successful verified curve observations, active/hot/background 43/25/18. RPC 15 requests, 0.1571 requests/sec; five curve batches inspected 12 accounts/request on average. Six RPC 429s triggered existing backoff; final RPC/PumpPortal CURRENT, DEX NOT USED YET with zero requests. Two selective security attempts, none outside hot. RSS 94.9 MB; sampled queue peak 5/1000, final queue 0, zero dropped events. All 43 companion actions WAIT, zero entries, all trade evidence UNAVAILABLE, zero paid subscriptions, paper cash $20. MATURING occurred; no natural NEAR_GRADUATION or migration was observed. Current-vs-peak retreats were observed, but near-graduation regression/entry invalidation are established deterministically, not invented as live events. Rendering 101 snapshots added zero RPC requests. Background polling was suppressed during this short throttled run; this alone does not establish background revisit behavior.

Frontend DOM behavior tests follow the official [React Testing Library documentation](https://testing-library.com/docs/react-testing-library/intro/) and [Vitest environment documentation](https://vitest.dev/guide/environment.html). Human visual review remains necessary: open FOMO Companion in desktop/narrow windows, inspect the isolated DEMO showcase, filter WAIT/lifecycle, copy a full mint and open intelligence. No screenshot capture or automated browser was used. No validated real-market edge or profitability is claimed.

Targeted lower-pressure background probe: 241.10 seconds with an isolated hot limit of 2 (application default remains 25). 99 launches, active/hot/background 99/2/97; 91 curve accounts attempted/checked, 87 verified observations, 23 hot plus 6 background batches. 59 background mints received observations; this window did not observe repeat background visits. Oldest background attempt/discovery age 223.9 seconds, 37 waiting at stop. RPC 37 requests, 0.1535 requests/sec; 3.14 curve accounts per curve HTTP request overall (small two-account hot batches dilute background batch efficiency). Four 429s, final Solana RATE LIMITED with backoff honored; PumpPortal CURRENT, DEX NOT USED YET. Two deep security attempts, zero outside hot. RSS 96.7 MB, sampled queue peak 11/1000, final queue 0, zero drops. All 99 companion actions WAIT; unavailable trade evidence for all, zero paid subscriptions/entries, paper cash $20. MATURING occurred without fabricated buyer evidence; no natural near-graduation or migration example occurred. 101 synchronous snapshots again added zero RPC requests. Existing fairness/hysteresis deterministic tests passed; these two windows do not prove indefinite public-provider availability or a revisit bound under persistent throttling.

Final checks: **80 backend tests** (26 companion-specific), **22 frontend tests**, Ruff backend/scripts, mypy backend/app, TypeScript/Vite build, basic secret scan and `git diff --check` passed. npm audit and pip-audit of `backend/requirements.lock` found no known vulnerabilities. Python auditing used the exact pinned lock with dependency resolution disabled; the lock retains its documented lack of wheel hashes. Build: 257.25 kB JavaScript / 79.22 kB gzip and 9.01 kB CSS / 2.71 kB gzip. No runtime dependency was added; DOM tools are development-only. New files: backend companion/result tests, React companion/rendering tests, offline companion smoke. Changed: engine view integration, isolated DEMO fixtures, App/types/styles, frontend dev lock, OBSERVE smoke instrumentation and the five requested documents. Neither strategy/risk/economic/trade-evidence settings nor provider/state-machine logic changed.

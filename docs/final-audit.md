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

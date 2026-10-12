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

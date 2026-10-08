# Delivery report — CRISPY WINNER

## Project status

Working local research application, with an unvalidated strategy. The software does not establish a profitable real-market edge. Free OBSERVE is verified; funded trade-stream operation needs the optional provider credential and was not exercised. Remaining limitations are explicit in limitations.md.

## Working features

Twelve offline demo scenarios; real discovery; bounded priority funnel/state transitions; migration/post-graduation observation; RPC mint/Token-2022/holder/creator/pool/curve screening; rolling breadth/flow/clustering/maturity/momentum/chase scores; central fail-closed gates; one cost estimator; $20 scenario sizing; delayed persistent paper fills/exits; signal/outcome snapshots; first-signal chronological evaluation and coverage; isolated decision replay; compiled React/SSE dashboard; resource pressure, rate-limit/backoff/reconnect and retention controls.

## Providers

Free PumpPortal discovery/migrations, public Solana RPC and DEX Screener. Optional PumpPortal trades are metered (currently 0.01 SOL/10,000 events), opt-in with funded provider credentials. Optional Helius standard RPC via URL; no paid enhanced streams required. Jupiter was evaluated but is not used. Provider probe saw 19 launches; full OBSERVE probe saw 14 real candidates, all WAIT, with $20 unchanged. Documentation and dates: providers/.

## Exact install/run/test

Windows (repository root):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
$env:RADAR_MODE='DEMO'
.\.venv\Scripts\python.exe -m backend.app.main
.\.venv\Scripts\python.exe -m pytest -q
```

Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
RADAR_MODE=DEMO .venv/bin/python -m backend.app.main
.venv/bin/python -m pytest -q
```

Dashboard: http://127.0.0.1:8765. Change mode to OBSERVE/PAPER/MANUAL ASSIST as needed; OBSERVE is default. Normal runtime needs no Node. Further checks: Ruff backend/scripts, mypy backend/app, frontend Vitest/build, scripts/check_secrets.py. This environment used uv to create the venv because system Python lacked ensurepip.

## Resource usage and storage

5,000 events + 250 discoveries, 250 candidates, deep limit 25: **88.6MB idle, 108.1MB load RSS**; 128.9 events/s; median 6.701ms / p95 13.759ms processing; 38.8s wall / 38.81s CPU; 16.22MB database+WAL. A 2,500-event burst retained 1,000 and dropped 1,500. These are synthetic local processing measurements, not provider latency or a sustained live-market guarantee. Details: performance.md.

WAL, indexed journal and restart-safe dedup; raw/dedup 24h, aggregate/security/creator/graduation/state snapshots 30d, signals/outcomes/session context 90d. Paper history, strategies, frozen evidence and summaries protected. 1GB soft cap; 70/85/95% warnings; retention then stop expendable writes at cap. Manual optimize only; no continuous VACUUM. RSS soft guard 700MB, action at 85%.

## Strategy and risk

Graduation → price discovery → pullback → stabilisation/recovery → distributed persistent buying → verified security/pool/liquidity → costs → positive independent historical evidence. Default thresholds: ≥20 estimated independent buyers, maturity ≥65, momentum ≥70, top wallet ≤10%, top five ≤30%, liquidity ≥$10k, impact/slippage ≤1%, chase <60. Any creator sale or critical security issue rejects. Unknown/stale/unhealthy/degraded/disagreeing information waits. High price/volume alone cannot create entry.

## Using the $20 paper account

Default proposed maximum $4 initially, at most one position; no minimum forced trade. Zero allowed size until all gates and historical evidence pass. Both sides include costs. Fills use later observable prices after 500ms plus adverse slippage/impact. Stops/targets/time exits await later prices and actual observed exit liquidity. Account/trade state commits atomically and survives restart. DEMO account/database are separate from real data. No-trade baseline is $20 unchanged.

## Data needed before trusting signals

Complete first-eligible signal outcomes across many independent launches and multiple market periods; fixed strategy version; later independent validation and holdout; ≥100 observations in the holdout and positive intervals in both later splits; full outcome coverage; explicit evidence freezing/restart. Normal intervals still understate dependence. Record failed exits/gaps, do not replace missing outcomes with later winners, and do not tune against the holdout. No such real edge has been validated yet.

## Validation and limitations

36 backend tests, two frontend tests, strict TypeScript production build, Ruff and mypy passed. npm and pinned Python dependency audits found no known vulnerabilities; basic secret scan passed. DEMO health/dashboard and built assets respond. No browser screenshot or interaction automation, Windows desktop run, paid trade stream or witnessed real migration was claimed. Cost estimates are approximate, holder data top-20, clustering heuristic, replay retention-limited. See final-audit.md and limitations.md.

## Git delivery

Milestone commits, all pushed to origin/main:

- 0199d6f research and architecture
- a44ccc1 configuration/storage/demo foundation
- c756f55 discovery/providers/security
- b1d06c8 explained signals
- 096db04 after-cost risk and paper trading
- 1855423 graduation monitoring/outcomes/replay
- af1eeda compiled dashboard
- e028a7f resources/reliability/setup/CI

The final documentation commit follows these; `git log --oneline` gives its exact hash. No force pushes or history rewrites.

## Next three most valuable improvements

1. Collect and prospectively freeze independent real-market cohorts, with dependence-aware intervals and honest latency sensitivity.
2. Use venue/effective-reserve-specific quotes and dynamic fee/priority estimates to tighten small-account entry/exit economics.
3. Add bounded funding/transfer evidence to clustering and broader creator/holder checks, then validate that their cost improves after-cost signal value.

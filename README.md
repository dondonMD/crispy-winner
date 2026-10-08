# CRISPY WINNER — Graduation Radar

A local Solana/Pump.fun intelligence and paper-research application for a small account. It filters launches, explains participation quality and risk, tracks graduation/recovery, estimates entry **and exit** costs, and records later outcomes. A **$20 account** and **NO ECONOMICALLY VIABLE TRADE** are first-class outputs.

**Historical or paper-trading performance does not guarantee future results. Highly speculative tokens may lose most or all of their value, and liquidity can disappear rapidly.**

No predictions, guaranteed profits, autonomous live trading, trading wallet, private keys, telemetry or cloud database. Initial strategy status is UNVALIDATED. Scores alone never justify entry.

## Requirements

Python 3.12+, Node 20.19+/22.12+ for frontend installation/build (tested Node 24), outbound internet for dependencies/real providers, modern browser. SQLite is bundled with Python. Normal runtime uses **one Python process**, not Node. No Docker, GPU, ML runtime or paid institutional subscription.

## Windows PowerShell

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
$env:RADAR_MODE='DEMO'
python -m backend.app.main
```

Or `powershell -File scripts/setup.ps1`, then `powershell -File scripts/run.ps1 DEMO`. If activation is blocked, use `.\.venv\Scripts\python.exe` directly; no system policy change is required.

## Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
RADAR_MODE=DEMO python -m backend.app.main
```

Or `bash scripts/setup.sh`, then `bash scripts/run.sh DEMO`. If Python lacks ensurepip, use a complete Python installation or `uv venv .venv` / `uv pip install --python .venv/bin/python -r backend/requirements.txt`. No sudo is needed by the application.

Visit **http://127.0.0.1:8765**. FastAPI serves compiled assets and SSE. Build once; close Node. `GET /api/health` verifies the monitor. Ctrl+C stops safely.

## Modes and configuration

- `DEMO`: offline deterministic simulated scenarios; separate database/account, prominently labelled.
- `OBSERVE`: default real discovery/migration, no wallet or trades.
- `PAPER`: real data, durable simulated account and delayed fills after strict gates.
- `MANUAL ASSIST`: reports and venue links; actual purchase remains external/manual.

Set `RADAR_MODE` before running (`$env:RADAR_MODE='PAPER'` on Windows). `RADAR_CONFIG` selects `config/conservative.yaml` (default) or `config/experimental.yaml`. Invalid/unknown settings refuse startup. Configuration hashes version every strategy; old results retain their version. `.env` may be copied from `.env.example` and is ignored. Never put credentials in YAML or Git.

## Providers and cost

| Provider | Default role | Cost / access |
|---|---|---|
| PumpPortal | New launch and migration WebSocket | Free streams verified without key; one connection |
| PumpPortal optional trades | Bounded wallet-level candidate trades | Opt-in API key; funded provider account; docs currently 0.01 SOL/10,000 events |
| Solana public RPC | Authorities, Token-2022, holders, creator balances, pool/curve verification | Free, throttled; custom URL optional |
| DEX Screener | Batched post-grad USD price/liquidity | Public/free; 30 addresses per batch; local TTL/limiter |
| Helius | Optional replacement standard RPC URL | Provider plan/key; no premium streaming dependency |
| Jupiter | Evaluated, not used in v1 | No requests or execution integration |

Detailed verified docs: [providers](docs/providers), [research](docs/research.md). No funded trade-stream key was supplied during development. **Free sources cannot establish independent buyer flow**; the system waits rather than inventing it. Enable metered subscriptions only knowingly using `trade_stream_enabled: true` and private `PUMPPORTAL_API_KEY`. No provider wallet key/seed is stored here.

## Dashboard

Radar sorting/filtering, token detail with six compact charts, recent graduations, rare entry candidates, $20 viability scenarios, gross/net paper journal, chronological Strategy Lab and System Health. Select a token for WHY THIS TOKEN / WHY NOT TO BUY, security/distribution, creator evidence and costs. Browser notifications are opt-in and debounced. SVG charts use no chart dependency or remote fonts.

## $20 research workflow

1. Observe launches and collect real eligible signals and their complete later outcomes across varied market periods.
2. Inspect net outcomes/sample counts/coverage in Strategy Lab or `evaluate`.
3. Keep thresholds fixed for independent later validation. Changing YAML creates a new strategy version.
4. Only if validation and holdout meet strict sample/positive interval/coverage requirements, explicitly freeze historical evidence; restart to load it.
5. PAPER simulates ≤20% cash per position (default $4 initially), one open position, adverse next-observation fills after 500ms latency, entry/exit fees, impact and slippage. WAIT means no fill.

```bash
python -m backend.app.cli evaluate --horizon 300 --output data/evaluation.json --csv data/buckets.csv
python -m backend.app.cli replay SESSION_ID --output data/replay.json
python -m backend.app.cli freeze-evidence
# Stop monitor first; explicit maintenance only:
python -m backend.app.cli optimize
```

For DEMO analytics set RADAR_MODE=DEMO first. Session IDs appear in the dashboard/API. Replay uses a temporary DB and no external requests. A few successful trades never establish profitability. [Strategy](docs/strategy.md), [methodology](docs/methodology.md), [risk and costs](docs/risk-model.md).

## Tests and audit

With the virtual environment active:

```bash
python -m pytest -q
python -m ruff check backend scripts
python -m mypy backend/app
npm --prefix frontend test
npm --prefix frontend run build
python scripts/check_secrets.py
python scripts/profile.py --events 5000
python scripts/smoke_providers.py
```

The last command makes read-only free-provider network requests; never subscribes to paid trades. Unit/integration tests use isolated fixtures for failures and unknown data, not production mocks. Some restricted sandboxes block asyncio thread wake-up sockets; tests need a normal local process. [Measured performance](docs/performance.md).

## Storage and resources

SQLite WAL; indexed records and restart-safe event identities. Raw events/dedup 24h, candidate/security/creator/graduation/state snapshots 30d, signals/outcomes/session context 90d. Paper accounts/trades, strategy/evidence versions and evaluation summaries are protected. 1GB default soft cap, warnings 70/85/95%; eligible retention cleanup/checkpoint, then block new expendable writes if still full. VACUUM only via explicit optimize, never continuously. Back up the database after stopping.

Defaults: 250 candidates, 25 deep subscriptions, 500 events/token, 1,000 queue slots, 2,000 pending outcomes, bounded caches and charts. 700MB RSS soft guard reduces monitoring, trims buffers and degrades data; it does not promise an OS-enforced memory cap. Measured synthetic load was far below 500MB. No full historical DB is loaded into RAM.

## Troubleshooting and safety

- No candidates: check System Health, outbound connectivity and provider status. DEMO needs no network.
- No entries: expected before independent evidence, security, fresh breadth, recovery and economic gates pass. Do not loosen gates merely to create trades.
- RPC/DEX failure or 429: finite retries, Retry-After/backoff; stale data waits. Optional custom RPC can improve availability.
- UI returns 503: run frontend production build before starting Python; build assets are intentionally ignored by Git.
- Port busy: stop the existing process or set RADAR_PORT. Bind remains 127.0.0.1.
- Logs: rotated JSON in logs/radar.log, no raw event INFO spam; API credential URLs are not logged.
- Resource/database pressure: inspect health, stop/reduce monitoring, run maintenance when offline; protected histories are never automatically discarded.

[Operating guide](docs/operating-guide.md), [architecture](docs/architecture.md), [known limitations](docs/limitations.md). Windows scripts are supplied but this build was measured/tested on Linux/WSL. No real after-cost trading edge is established yet.

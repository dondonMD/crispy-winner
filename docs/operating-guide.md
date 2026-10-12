# Operating guide

Start DEMO to inspect all twelve scenario families offline. SIMULATED DATA is prominent and stored in data/demo.db. Approximately 90 seconds after launch, migration scenarios begin; developing, dumps and recovery become visible over the next minutes. No synthetic evidence calibrates the real strategy. Absence of entries is expected while historical evidence is insufficient.

OBSERVE is the default: outbound public APIs only, no wallet. The Radar prioritizes candidates rather than every chain launch. Open a token for risk reasons, individual costs and charts. Unknown/stale information is visible. System Health includes provider connectivity, rate-limit state in the API, RAM/CPU, queue drops and storage warnings.

For optional trade observations, set PUMPPORTAL_API_KEY privately and trade_stream_enabled: true in YAML, after reviewing provider charges. This is a data-provider credential; no wallet secret is requested by this application. Never paste keys into a tracked file. You can instead supply SOLANA_RPC_URL for an optional Helius/custom standard RPC endpoint.

PAPER uses real data and the durable $20 ledger. It will not force trades. Use evaluate before interpreting scores. A strategy must have sufficiently many complete first-eligible signal outcomes and positive later validation/holdout evidence. `freeze-evidence` explicitly records the current historical result for that strategy version, then restart to load it. Read methodology limitations first. This is research approval for simulated entries, not permission to trade real money.

MANUAL ASSIST displays the same strict decisions and venue links. Any actual purchase is performed independently by the user; the application never submits a transaction.

Stop with Ctrl+C before manual database optimization or updates. Back up data/radar.db after shutdown (or use SQLite backup tooling including WAL consistently). Paper history and strategy summaries are protected. Never edit database balances to make performance look positive.

## Free OBSERVE monitoring

Keep `trade_stream_enabled: false` for free discovery, verified bounded bonding-curve progress,
selective security analysis and migration notifications. Buyer breadth, flow, synchrony and
trade-dependent momentum components display — / unavailable. Zero observed events is not proof
of zero buyers. Launch fields (`bondingCurveKey`, `initialBuy`, `marketCapSol`, `vSolInBondingCurve`,
`vTokensInBondingCurve`) are retained as unverified snapshots without assuming undocumented units
or converting SOL to USD. On-chain parsers supply lifecycle evidence.

Defaults in conservative YAML: `curve_poll_seconds: 30`, `curve_batch_size: 25`,
`lifecycle_maturing_pct: 30`, `lifecycle_near_pct: 85`, `security_min_curve_pct: 60`,
`security_scan_interval_seconds: 30`. Keep `max_candidates: 250` and `max_deep: 25`.
Thresholds choose observation stages/scan priorities, never recommendations. All changes create
immutable strategy versions; historical scores/evaluations retain their original version.

The enrichment loop checks every five seconds but each selected token backs off for the polling
interval, including failures. One batch can contain at most 50 curves plus the global account,
well below Solana's 100-account limit. Stable default deep sets need roughly one curve request
per 30 seconds; churn can generate one batch per five-second loop. A full security scan uses
several RPC requests (roughly 6–9 depending on creator/pools) and starts at most once per 30
seconds. The shared limiter allows at most two requests/second, two concurrent HTTP requests;
the funnel itself is serial. Existing response caps, candidate bounds and resource-pressure
reduction remain active. Retry-After cooldown is honoured across requests. Public RPC can still
throttle; unknown/stale evidence blocks entries.

System Health: NOT USED YET means no attempted request, CURRENT means successful transport/RPC
activity, DEGRADED means attempted activity failed, RATE LIMITED means an active cooldown.
CURRENT does not mean a token's security/progress is known. DEX normally remains NOT USED YET
until a migrated candidate needs market data. PumpPortal CURRENT describes its live connection.

Run `python scripts/smoke_providers.py`, then `python scripts/smoke_observe.py` for a 65-second
read-only run with a temporary database and disabled trade subscriptions. Reports under `data/`
are local ignored artifacts. The run reports discovery, curve attempts/successes, request rate,
counts, provider health, RSS and actual lifecycle outcomes. It need not witness graduation.

Integration references checked 2026-10-12: [PumpPortal streams](https://pumpportal.fun/data-api/real-time/),
[Solana getMultipleAccounts](https://solana.com/docs/rpc/http/getmultipleaccounts),
[official Pump IDL](https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump.json).
The public stream page documents subscription methods/costs, not complete create-field semantics;
those fields therefore remain telemetry only.

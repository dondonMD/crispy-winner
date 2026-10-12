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
`security_scan_interval_seconds: 30`, `lifecycle_near_exit_pct: 75`. Keep `max_candidates: 250` and `max_deep: 25`.
Thresholds choose observation stages/scan priorities, never recommendations. All changes create
immutable strategy versions; historical scores/evaluations retain their original version.

The enrichment loop checks every five seconds but each selected token backs off for the polling
interval, including failures. One batch can contain at most 50 curves plus the global account,
well below Solana's 100-account limit. Stable default deep sets need roughly one curve request
per 30 seconds; churn can generate one batch per five-second loop. A full security scan uses
several RPC requests (roughly 6–9 depending on creator/pools) and starts at most once per 30
seconds. Background sweeping adds at most one batch per 30 seconds when healthy. The shared limiter allows at most two requests/second, two concurrent HTTP requests;
the funnel itself is serial. Existing response caps, candidate bounds and resource-pressure
reduction remain active. Retry-After cooldown is honoured across requests. Public RPC can still
throttle; unknown/stale evidence blocks entries.

System Health: NOT USED YET means no attempted request, CURRENT means successful transport/RPC
activity, DEGRADED means attempted activity failed, RATE LIMITED means an active cooldown.
CURRENT does not mean a token's security/progress is known. DEX normally remains NOT USED YET
until a migrated candidate needs market data. PumpPortal CURRENT describes its live connection.

Run `python scripts/smoke_providers.py`, then `python scripts/smoke_observe.py` for a default 65-second
read-only run; use `python scripts/smoke_observe.py --seconds 300` to exercise background cadence.
Both use a temporary database and disabled trade subscriptions. Reports under `data/`
are local ignored artifacts. The run reports discovery, curve attempts/successes, request rate,
counts, provider health, RSS and actual lifecycle outcomes. It need not witness graduation.

Integration references checked 2026-10-12: [PumpPortal streams](https://pumpportal.fun/data-api/real-time/),
[Solana getMultipleAccounts](https://solana.com/docs/rpc/http/getmultipleaccounts),
[official Pump IDL](https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump.json).
The public stream page documents subscription methods/costs, not complete create-field semantics;
those fields therefore remain telemetry only.

## Current lifecycle and background fairness

Near-graduation means fresh verified progress reached `lifecycle_near_pct` (85%) and has not
fallen below `lifecycle_near_exit_pct` (75%). Thus 86% enters, 82% remains, 70% returns to
MATURING, and 90% can enter again. This is hysteresis, not probability/confidence/buy quality.
A 60.2% token with an 88.4% session peak displays MATURING and both figures separately.
Unknown/stale curve evidence removes a current near label; the last observed value is labelled
stale rather than current. Freshness remains two hot polling intervals (default 60 seconds).
Session peaks reset on restart and restored pre-grad states require re-verification.

Background defaults: `curve_background_revisit_seconds: 180`,
`curve_background_batch_seconds: 30`, `curve_background_batch_size: 25`,
`curve_background_backoff_seconds: 60`. Never-polled candidates are eligible immediately;
previously polled candidates become eligible after the revisit interval. Oldest attempt wins,
with stable discovery/mint ties, so newer launches cannot indefinitely overtake older waiting
candidates. At 250 active / 25 hot, a healthy stable background set of 225 gets roughly 270-second
revisits. At lower counts revisits are around 180 seconds. The scheduler makes no guarantee of
successful observations during provider outages, resource pressure, eviction or candidate expiry.
A meaningful verified background observation promotes the token through the normal lifecycle
analysis and ranking; it may enter the bounded hot set. Background itself only retrieves curves.

If RPC reports errors/429s, background backoff grows before issuing more low-priority work.
RATE LIMITED is shown during Retry-After, then CURRENT or DEGRADED reflects subsequent activity.
System Health exposes hot/background batch counts, curve accounts checked, background due count
and oldest attempt age. Due count includes never-polled tokens; attempt age includes failed
requests, so it does not assert that a successful observation exists. Provider `rate_limits`
counts actual HTTP 429 responses. The smoke report distinguishes total RPC HTTP starts from
curve HTTP starts and reports accounts per curve request, sampled peak RSS/queue, scan membership,
background observations/revisits and counts. No browser automation is required.

Public RPC behaviour remains provider-controlled. Current official documentation confirms
[getMultipleAccounts batching](https://solana.com/docs/rpc/http/getmultipleaccounts) and warns
that [public endpoint limits can change](https://solana.com/docs/references/clusters).

For a low-arrival diagnostic only, `python scripts/smoke_observe.py --seconds 240 --max-deep 2`
uses two hot slots in the isolated temporary probe to make background membership easier to
exercise. The report includes the configured limit; this does not edit application settings or
replace the 25-hot default resource/fairness verification. Do not present this diagnostic as a
production-default measurement.

## FOMO Companion

Choose **FOMO Companion** in the left navigation. Its summary counts actions separately from lifecycle. Filter by action, lifecycle or attention; search name, symbol or full/partial mint. ENTRY CANDIDATE comes first, then high/medium/low attention waits, TOO LATE and REJECT. Within each group existing scanner priority is retained.

- **ENTRY CANDIDATE:** existing strategy and current evidence/economic gates permit manual review. Check the supplied manual position ceiling, round-trip costs, break-even move and validity conditions. This is not BUY NOW or a profit forecast.
- **WAIT:** required conditions are missing. Read Current blockers and Evidence completeness; satisfying a blocker never promises entry. HIGH ATTENTION can coexist with WAIT.
- **REJECT:** core risk failures currently reject the setup. There is no frontend override.
- **TOO LATE:** the core strategy considers entry chasing. No invented pullback target is supplied.

Use **View intelligence** for the same current decision above technical details. **Copy mint** copies the complete exact mint; “Copied” confirms success. If clipboard permission/API is unavailable, focus the read-only mint field, select and copy manually. Open FOMO yourself, paste the mint and review there. The app never executes trades, opens an invented FOMO link, connects a wallet or logs clipboard contents. Existing Pump.fun links remain explicitly manual.

Curve current and session peak are distinct; retreat is descriptive percentage points, not a recommendation. Unknown security displays UNKNOWN with no sentinel risk score. Trade stream not subscribed means buyer breadth/flow are unavailable, not observed zeros. A nonviable position allowance is genuinely $0; unknown costs remain dashes. The $20 account and 20% default allocation remain unchanged.

DEMO shows an unmistakable banner and a separate four-action synthetic showcase excluded from action counts and strategy evidence. `python scripts/smoke_companion.py` verifies it using a temporary database. In free OBSERVE, zero entries is a valid outcome; historical edge remains unvalidated. Notifications require an explicit browser-alert click; entry alerts require a current backend companion entry decision.

Manual visual checks: visit the page at desktop and narrow widths; filter WAIT/NEAR GRADUATION, inspect current vs peak, copy a full mint, and open intelligence. In DEMO, scroll to the labelled synthetic cards to see all four badge texts. Watch SSE replace current action when evidence changes.

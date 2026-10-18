# Operating guide

Start DEMO to inspect all twelve scenario families offline. SIMULATED DATA is prominent and stored in data/demo.db. Approximately 90 seconds after launch, migration scenarios begin; developing, dumps and recovery become visible over the next minutes. No synthetic evidence calibrates the real strategy. Absence of entries is expected while historical evidence is insufficient.

OBSERVE is the default: outbound public APIs only, no wallet. The Radar prioritizes candidates rather than every chain launch. Open a token for risk reasons, individual costs and charts. Unknown/stale information is visible. System Health includes provider connectivity, rate-limit state in the API, RAM/CPU, queue drops and storage warnings.

Standard Solana WSS supplies free tracked Pump trade observations when units and continuity are verified. For optional PumpPortal trade observations, explicitly enable PUMPPORTAL_ENABLED=true and set PUMPPORTAL_API_KEY privately and trade_stream_enabled: true in YAML, after reviewing provider charges. This is a data-provider credential; no wallet secret is requested by this application. Never paste keys into a tracked file. You can instead supply SOLANA_RPC_URL for an optional Helius/custom standard RPC endpoint.

PAPER uses real data and the durable $20 ledger. It will not force trades. Use evaluate before interpreting scores. A strategy must have sufficiently many complete first-eligible signal outcomes and positive later validation/holdout evidence. `freeze-evidence` explicitly records the current historical result for that strategy version, then restart to load it. Read methodology limitations first. This is research approval for simulated entries, not permission to trade real money.

MANUAL ASSIST displays the same strict decisions and venue links. Any actual purchase is performed independently by the user; the application never submits a transaction.

Stop with Ctrl+C before manual database optimization or updates. Back up data/radar.db after shutdown (or use SQLite backup tooling including WAL consistently). Paper history and strategy summaries are protected. Never edit database balances to make performance look positive.

## Free OBSERVE monitoring

Keep `trade_stream_enabled: false` for free discovery, verified bounded bonding-curve progress,
selective security analysis and migration notifications. With standard `SOLANA_WS_URL`, tracked Pump TradeEvents supply buyer breadth, flow and synchrony
when quote units and a clean 180-second window are established. Until then these fields
display — / unavailable or PARTIAL. Zero observed events is not proof
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
per 30 seconds; a global batch guard also applies during hot-set churn. A full security scan uses
several RPC requests (roughly 6–9 depending on creator/pools) and starts at most once per 30
seconds when healthy. Background sweeping adds at most one batch per 30 seconds when healthy. The shared limiter allows at most two requests/second, two concurrent HTTP requests;
the funnel itself is serial. Adaptive pressure reduces request cadence and spacing; see
[rpc-pressure.md](rpc-pressure.md). Existing response caps, candidate bounds and resource-pressure
reduction remain active. Retry-After cooldown is honoured across requests. Public RPC can still
throttle; unknown/stale evidence blocks entries.

System Health: NOT USED YET means no attempted request, CURRENT means successful transport/RPC
activity, DEGRADED means attempted activity failed, RATE LIMITED means an active Retry-After cooldown,
and BACKING OFF means adaptive RPC pressure remains elevated during recovery.
CURRENT does not mean a token's security/progress is known. DEX normally remains NOT USED YET
until a migrated candidate needs market data. PumpPortal CURRENT describes its live connection.

Run `python scripts/smoke_providers.py`, then `python scripts/smoke_observe.py` for a default 65-second
read-only run; use `python scripts/smoke_observe.py --seconds 600` to exercise background cadence.
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

## Opportunity and manual positions

Open **Opportunity** for the ranked top-20 research shortlist. These are **UNVALIDATED RESEARCH
SIGNALS**, not core Entry Candidates or probabilities of profit. Inspect progression, missing
security/flow/market evidence and entry context before acting. Copy the mint and independently
inspect it in FOMO; CRISPY WINNER never interacts with that interface.

Token detail supports timestamped **MANUAL USER OBSERVATION** price/cap input, a separate manual
cost estimate and an explicitly confirmed external-entry journal form. Manual context expires
visibly after 120 seconds by default. Set available manual cash on **Manual Positions**; it is a
local user setting, not a wallet balance, and the $20 paper account is unchanged. Mark and close
positions manually; closure records no transaction. Review stale evidence and explained exit
states rather than treating warnings as guaranteed sell instructions. There is no automatic entry
zone without target evidence. Research defaults are in `config/intelligence.yaml`.

DEMO includes isolated synthetic Opportunity/exit examples, labelled prominently. For offline
verification run `python scripts/verify_intelligence.py`; it checks the examples and measures a
250-candidate, 8,000-point synthetic load without provider requests. See
[Opportunity methodology and limitations](opportunity-intelligence.md) for exact rules, storage,
research horizons and the boundary separating this workflow from the strict strategy.

## Configure launch discovery

Set SOLANA_WS_URL privately to a standard mainnet Solana WSS endpoint, and SOLANA_RPC_URL to its HTTP endpoint. Helius standard endpoints are supported without enhanced subscriptions. PumpPortal defaults disabled; PUMPPORTAL_ENABLED=true explicitly opts into that optional source. Keep trade_stream_enabled=false. Without configured/connected discovery, the application starts safely but reports unavailable/degraded and cannot discover launches. Inspect Onchain discovery in System Health: connection, messages, decoded creates, ignored/decode errors, duplicates, reconnects and connection age. Ordinary discovery/trade decoding makes no HTTP calls. Explicit log truncations alone use bounded standard getTransaction identity recovery. Existing adaptive lifecycle polling remains bounded. See [setup and decoding reference](providers/onchain-discovery.md).


## Standard WSS trade flow

Keep `PUMPPORTAL_ENABLED=false` and `trade_stream_enabled: false`; the latter
controls the optional paid PumpPortal stream, not standard Solana logs. No separate
per-token subscription, account lookup for units, or HTTP trade polling is used.
System Health distinguishes decoded trades, tracked accepted trades, ignored
untracked trades, invalid units, duplicates, and trade versus critical drops.
Token evidence requires 180 clean seconds, valid consistent quote units, three
samples and the existing freshness limit. A reconnect starts the window again;
a quiet/outage window is not evidence of zero buyers. PARTIAL flow cannot satisfy
Companion or core gates. Public RPC security can remain UNKNOWN despite strong
flow. See [canonical schema and bounds](providers/onchain-discovery.md).

For an isolated live probe use `scripts/smoke_observe.py --seconds 600`. Its report
includes aggregate flow examples only for CURRENT candidates, separate loss
counts, coverage, resources, actions and unchanged paper cash. Reports in `data/`
remain ignored local artifacts. No real trade is executed or recommended.


Explicit `Log truncated` notifications now show PENDING RECOVERY / incomplete while
standard getTransaction establishes affected mint identities. Untracked confirmation
preserves clean timers; tracked impact gaps only those mints. Unresolved recovery,
backlog overflow and transport loss remain global. Watch pending/oldest/peak recovery,
recovery request/error/429 counts, and queue peak/oldest trade age/stale-while-queued.
Recovery shares RPC pressure with monitoring and increases HTTP usage only for explicit
truncations. A growing queue can still prevent fresh evidence; capacity and the
20-second limit are unchanged. See [recovery semantics and bounds](providers/onchain-discovery.md#targeted-truncation-recovery).


System Health now separates unsupported curve-call / unknown-discriminator / other
recovery instructions and shows multi-hop calls, associated routes and unresolved /
ambiguous calls. These are identity-recovery diagnostics, not PumpSwap trade flow.
The 600-second probe records bounded relative WSS connection timing and CURRENT-only
aggregate ranges. A route can preserve unrelated candidates only after complete,
unambiguous canonical mapping; unknown/malformed routes remain fail-closed.

## Verified post-grad flow

Use the existing `SOLANA_WS_URL` for the standard PumpSwap connection. No new
credential, paid stream, PumpPortal flag or HTTP trade polling is needed.
System Health distinguishes verified eligible pools, subscribed/ACKed pools,
capacity-limited pools and post-grad evidence counts. At most 25 pools share
one connection. A migration alone supplies no flow: the existing security scan
must independently verify the pool, then its subscription must ACK and collect
180 clean seconds, three samples, known units and a fresh trade within 20 seconds.
Candidate cards identify PRE-GRAD FLOW versus POST-GRAD PUMPSWAP FLOW.
A missing pool, capacity limit, disconnect or local event loss keeps evidence
incomplete. The existing scan cadence/backoff is unchanged; public-RPC delays
can postpone pool eligibility. See [provider details](providers/pumpswap-flow.md).

For a migration that produces no eligible PumpSwap pool, inspect
`health.postgrad_handoff` (or `postgrad_handoff` in the OBSERVE report). It retains
bounded lifecycle exit reasons, security inspection hints/results, independent
pool verification, capacity/ACK and flow-coverage blockers after candidate removal.
See [handoff trace](postgrad-handoff-trace.md). This is diagnostics only and does
not trigger scans or relax entry gates.

Recovered canonical migration observations retain their real chain timestamp.
Inspect the four lifecycle/acquisition-age counters and last age sample under
`health.truncation_recovery` to distinguish old chain time from expired recovery
evidence. The limits are 45 seconds from truncation to verification and 20 seconds
from verification to processing; ordinary trade freshness and the 180-second
post-grad window are unchanged. See [time semantics](recovered-migration-freshness.md).

# Known limitations

- No profitability claim, wallet, autonomous live trading, private key, manipulation, front-running or private order flow.
- Standard Solana WSS can supply free canonical Pump bonding-curve trade evidence for tracked mints. It requires explicit supported quote units and clean continuity; unknown/partial evidence remains unavailable to gates. Paid PumpPortal remains optional and disabled by default.
- The default RPC is public and may throttle. DEX data is indexed, not tick-accurate. Receive timestamps do not establish on-chain event age or guarantee low latency. Market gaps make outcomes unavailable.
- Live probe results are run-specific; see [trade validation](pump-trade-validation.md). Short runs do not validate a funded stream, complete coverage, profitability or edge. No funded account was supplied.
- Creator identity is provider-reported, not cryptographically linked ownership. Current creator fee recipients can change. Recent creator history is bounded to observed launches, not exhaustive.
- Largest-account distribution is limited to top 20, grouped by wallet; concentration across many smaller accounts may escape detection. Program exclusions require known addresses/verified pools. No full holder census.
- Timing/size clustering is intentionally conservative and can false-positive. Funding-source/transfer-graph clustering is not implemented; RPC fan-out would be substantial.
- Current-global curve progress applies only when supply and invariant offsets match. Historical global changes may still affect its interpretation; graduation is separately evidenced.
- USD prices exist primarily after graduation via DEX. No SOL amount is silently converted into USD. Curve-native prices are not displayed as dollar prices.
- Costs approximate balanced-pool impact, configurable fees and slippage. No route-specific quote, priority fee forecast, Token-2022 execution simulation or virtual-reserve quote is promised.
- Research mean intervals understate dependence; no production edge is validated. Frozen evidence requires data collection and explicit command, not automatic learning. Offline logistic regression, walk-forward tuning experiments and latency sweeps are future research improvements.
- Replay is limited by 24-hour raw retention and may report mismatches for sessions with incomplete recordings or unrecorded asynchronous expiry/resource trimming. It never labels a mismatch successful.
- One compact indexed record journal replaces dozens of nearly identical v1 tables. Alembic evolves it; event identities have a separate indexed table. This keeps migrations/querying small but does not provide full relational foreign-key analytics.
- A protected history alone can exceed the soft database limit. It is never deleted automatically; new expendable writes stop and maintenance requires user decisions.
- Windows setup scripts are provided; this build was tested on Linux/WSL, not a Windows desktop. No browser screenshot or visual browser automation was used. The production dashboard build and served assets were checked.

- Free OBSERVE polls the hot set frequently and admitted background candidates through a fair
  slower sweep. Admission/eviction/expiry and RPC failures still limit coverage; the application
  does not claim to observe every chain launch or guarantee successful refreshes during outages.
- Configurable 30%/85% lifecycle stages, with a 75% near-exit hysteresis threshold, describe
  current progress rather than the highest historical state; they are not trade quality or calibrated
  graduation probabilities. They do not raise maturity/momentum or satisfy entry gates.
- Current-global compatibility can fail for changed baselines/layouts/supply variants. UNKNOWN
  is expected in those cases. Repeated successful RPC calls do not imply verified security.
- A short live sample may show only early progress; the initial 2026-10-12 run observed no later lifecycle stage. The final repeat observed
  MATURING at 70.76%, but no NEAR_GRADUATION or migration. Those transitions have deterministic
  regression coverage. Public RPC throttling was also observed during the final run.
- Launch-time reserves are unverified snapshots. The application does not continuously reuse
  them, infer buyer breadth, infer migration from completion, or fabricate pre-grad USD values.

- Session peak progress resets on restart and never supplies lifecycle priority or entry evidence.
  Stale/unknown curve observations can remove current pre-grad labels without asserting a sell.
- Background fairness is scheduling fairness under available RPC/resources, not proof that every
  account parsed successfully. Backoff can extend refresh intervals and candidates can expire.
  Background attempts are single-request probes and never trigger holder scans or DEX queries.

## FOMO Companion

The companion translates current evidence and conservative strategy decisions; it does not establish a validated real-market edge or predict profitability. ENTRY CANDIDATE permits manual review only. Speculative tokens can lose most or all value. Lifecycle progress, session peak, attention and uncalibrated chase scores are not success probabilities.

Free OBSERVE supplies buyer breadth/flow only from tracked canonical WSS trades with verified quote units and adequate clean continuity. High-progress or migrated tokens can remain WAIT because security, liquidity, recovery, fresh trade evidence or approved historical evidence is missing. Missing economic values remain unavailable; no calibrated maximum entry, take-profit, stop-loss or pullback price is invented. Pool cost estimates retain their existing approximation limitations.

No FOMO deep-link/API contract is assumed. Copy mint and manual search are the complete workflow. Clipboard permissions may fail, with manual copying available. No wallet, private key, transaction, LLM explanation service, telemetry or trading endpoint is added. Optional watchlist and watched-token notifications are deferred UX work; current backend classification and existing entry notifications take priority.

The current interface depends on existing SSE delivery. Disconnection remains visibly warned; an old screen must not be treated as current evidence. Data acquisition remains bounded and provider-dependent. Four DEMO UI fixtures include explicitly synthetic historical evidence solely to exercise presentation; they are never accepted as real evidence or passed to paper trading/Strategy Lab. DOM tests cover behavior, but visual layout still needs human browser review.

## Opportunity/manual intelligence

Opportunity priority and exit context are unvalidated research heuristics, not profitable-edge
claims or execution instructions. No automatic pre-graduation USD market cap, calibrated entry
zone or maximum-chase price is available. Manual observations are user-reported and expire visibly;
market-cap changes are proxies, never P&L. Current liquidity and comparable prices are required
for after-cost estimates. Missing flow remains unavailable. An evicted manual-position mint gets
no additional polling and may remain DATA STALE. Curve history rewarms after restart.

Prospective outcomes have explicit gaps and bounded pending capacity; provider sampling is
irregular and selectively observes a lifecycle-ranked funnel. Such data has selection/coverage
bias and is not a population sample. Gross provider-price excursions are descriptive; costs may
be unknown and no approved evidence is created automatically. Manual journal records are external
self-reports, not reconciled fills. The local cash setting is not an automatically maintained ledger.
Research retention and the existing database cap can limit future coverage; monitor storage growth.

## Discovery availability

PumpPortal is optional and disabled by default. Configure SOLANA_WS_URL for standard Solana Pump log discovery. Without a connected source, no real launches can be observed and health reports unavailable. Supported canonical logs with targeted standard getTransaction identity recovery only for explicit truncations; no general outage backfill or guaranteed complete coverage. Creation metadata does not verify security or imply price. Missing migration logs do not imply graduation. Provider quotas and network restrictions still apply. See [on-chain discovery](providers/onchain-discovery.md).


## Pump TradeEvent coverage

No outage backfill, guaranteed provider delivery, or PumpSwap post-migration flow.
CURRENT describes observed continuous connection coverage, not cryptographic proof
that a provider omitted no logs. Exact-layout validation rejects older or future
TradeEvent layouts; unknown/default event quote mints are not guessed as SOL; default-key SOL conversion requires an independently verified cached curve; the zero-quote-amount legacy fallback also requires supported legacy instruction semantics. Only WSOL
and native USDC decimals are established. High-rate tokens that exhaust bounded
buffers remain partial. Decode gaps, dropped trades and reconnects reset clean
coverage; this may leave all candidates partial/unavailable on unstable public
WSS. Three samples establish a minimum evidence structure, not statistical power.
Timing/size clustering indicates possible coordination, never common ownership.
Strong flow neither verifies security nor proves profitability or trading edge.
Continuity is session-local; existing replay can report differences when original
transport coverage or asynchronous queue-loss context is not reproduced.


## Explicit log-truncation recovery

Standard getTransaction identifies affected tracked mints; it does not backfill
executed trade amounts, create/migration evidence or provider outages. Pending
recovery blocks CURRENT without prematurely destroying prior coverage. Confirmed
tracked impact still restarts that token's required clean window. Unresolved or
unsupported instructions/transactions and recovery overflow remain global gaps.
Legacy/v0/v1 compiled transaction messages are supported. Multi-hop curve-call identity is supported only through fully validated,
unambiguously associated canonical PumpSwap routes; ambiguous/missing parents remain global gaps. Missing inner-instruction metadata cannot prove completeness.
Standard RPC recovery consumes existing provider quota and may defer other work
under adaptive pressure. At most 32 recoveries, one request in flight, three attempts
and 10,000 dedup identities are retained; no raw transactions are stored. Queue lag,
20-second freshness, units, real tracked truncations and transport outages can still
prevent CURRENT. A preserved timer during pending recovery does not imply CURRENT.
The original 180-second standard and every strategy/security/economics gate remain.


The earlier 38 unsupported recoveries cannot be retrospectively subdivided from
aggregate counts. New runs record fixed instruction-subtype counters. Multi-hop
identity recovery covers only canonical curve PDAs in associated routes, not pool
trade flow or executed amounts. Missing CPI ancestry for inner routes, malformed
route shapes, unrelated unknown Pump instructions and transport loss remain
conservative global gaps. Successful recovery can preserve coverage but cannot
create samples, verified units, fresh observations, security or approved evidence.

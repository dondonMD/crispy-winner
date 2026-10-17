# Standard Solana Pump discovery

Verified against official documentation on 2026-10-17. This integration uses
[Solana logsSubscribe](https://solana.com/docs/rpc/websocket/logssubscribe), with
one `mentions` address, the Pump program
`6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`, and `confirmed` commitment.
There is no `transactionSubscribe`, paid trade stream, or transaction submission.

## Configuration

Set privately in the environment or ignored root `.env`:

```dotenv
SOLANA_RPC_URL=https://your-standard-solana-http-endpoint
SOLANA_WS_URL=wss://your-standard-solana-websocket-endpoint
PUMPPORTAL_ENABLED=false
```

For Helius, use its standard endpoint with your own key supplied locally:
`https://mainnet.helius-rpc.com/?api-key=<your-key>` and
`wss://mainnet.helius-rpc.com/?api-key=<your-key>`.
See [official Helius WebSocket documentation](https://www.helius.dev/docs/rpc/websocket).
Only the standard Solana method is used; account quotas and provider restrictions
still apply. No enhanced subscription or additional SDK is required. Any compatible
standard Solana WSS provider may be configured. HTTP and WSS must refer to mainnet.
URLs and credentials are never included in health responses or reconnect logs.
Do not put keys in tracked configuration.

Without `SOLANA_WS_URL`, on-chain discovery is disabled safely. Invalid WSS
configuration is reported UNAVAILABLE. PumpPortal defaults disabled; explicitly
set `PUMPPORTAL_ENABLED=true` only where available/permitted. Either connected
source satisfies the existing discovery-health requirement. With both down,
System Health and `/api/health` report unavailable/degraded. Existing candidates
and scheduler state survive reconnects. DEMO starts neither discovery source.

## Canonical event decoding

`backend/app/pump_events.json` contains the exact three event definitions and Shareholder type extracted
from the [official pinned Pump IDL](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/idl/pump.json).
The decoder reads Borsh fields through timestamp, plus migration's pool field.
Trailing reserves/features are deliberately unused. These events are:

- `CreateEvent`: discriminator `[27,114,169,77,222,235,99,118]`; name, symbol,
  URI, mint, bonding curve, user, creator and chain timestamp.
- `CompletePumpAmmMigrationEvent`: discriminator `[189,233,93,185,92,148,234,148]`;
  mint, bonding curve, chain timestamp and pool. Only this actual migration event
  authorizes a migration transition; curve completion does not.

Only successful transactions and successful Pump invocation frames qualify.
Failed nested invocations, unrelated programs, malformed/unbalanced/truncated
logs, invalid curve PDAs, or unknown layouts fail closed. The program-supplied
metadata strings are creation-time metadata, not security verification. No price,
USD market cap, liquidity, curve percentage or trade flow is inferred from creates.
Chain timestamp, confirmed commitment, slot, signature and source accompany the
normal `MarketEvent`. Existing event-age rules still reject delayed events.

## Bounds and delivery limitations

One WSS connection, one restored subscription per connection, 256 KiB maximum
message, 16 queued WSS frames, bounded invocation depth/log count/string lengths,
10,000 signature dedup entries. All decoded events in a successful transaction
are considered before signature dedup. Scanner mint dedup also prevents another
source creating the same candidate or overwriting its existing launch evidence.
Reconnect uses exponential delay with jitter, capped at 60 seconds; receiving
messages over a stable 60-second connection resets the attempt level. Ping every
20 seconds with 20-second timeout; receive timeout 90 seconds; cancellation closes
the socket. There is no catch-up/backfill: launches during outages may be missed.

Discovery has **zero HTTP enrichment calls**. It does not poll transactions,
metadata URIs, accounts or security. Logs without a complete supported event are
skipped. Providers that omit/truncate event logs cannot provide full discovery
coverage. Missing migration events likewise remain unavailable rather than
inferred. There is no expensive fallback queue or HTTP retry amplification.
The adaptive shared HTTP RPC controller and hot/security/background priorities
remain unchanged. New genuine candidates naturally cause the same existing
bounded lifecycle/security polling as candidates previously found by PumpPortal.

System Health reports connectivity, connection age, last successful WSS message,
messages, decoded creates/migrations, ignored events, decode errors, reconnects,
duplicate notifications and scanner duplicate launches. HTTP enrichment counters
remain zero by design; normal lifecycle HTTP requests retain shared RPC accounting.

## Free bonding-curve trade evidence

Official IDL commit: `639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22` (current official
main when inspected). Create/migration definitions remain unchanged. `TradeEvent`
discriminator: `[189,219,127,211,78,230,97,238]`. Its complete ordered field layout
is vendored verbatim in `backend/app/pump_events.json`, including the bounded
`Shareholder` vector. Unlike creation/migration prefix decoding, trades require
an exact complete supported layout, strict booleans, bounded UTF-8 strings,
nonzero amounts and trading identity, and a plausible chain timestamp.

Fields used: `mint`, `user`, `is_buy`, `token_amount`, `timestamp`, `quote_mint`,
`quote_amount`; `sol_amount`, `virtual_sol_reserves`, `virtual_token_reserves`,
`real_sol_reserves`, `real_token_reserves`, `virtual_quote_reserves` and
`real_quote_reserves` are retained as raw canonical evidence. All remaining
canonical fields are decoded/retained to validate the layout, including fees,
creator, instruction name, shareholders and holder rewards. Event creator does
not replace the token creator established by creation evidence. Reserve amounts
do not supply USD prices, liquidity or security conclusions.

Only explicit WSOL (`So11111111111111111111111111111111111111112`, 9 decimals)
and native USDC (`EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`, 6 decimals)
are allowlisted; `quote_amount` is divided by the corresponding power of ten.
Sources: [Solana native mint documentation](https://www.solana-program.com/docs/token),
[Solana balances and SOL decimals](https://platform.solana.com/docs/wallet-operations/balances),
[Circle's USDC integration reference](https://github.com/circlefin/skills/blob/master/plugins/circle/skills/use-usdc/SKILL.md),
and [official Pump v3 trade semantics](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/docs/instructions/TRADE_V3.md).
USDC is a quote asset, never silently USD. Unknown mint or missing explicit quote amount remains `currency=unknown`, zero
placeholder volume, invalid units. A default event quote is normalized to SOL ONLY
when an independently parsed, owner-verified curve from the EXISTING scheduled
curve batch establishes native SOL. Populated canonical `quote_amount` is used.
A narrower legacy fallback uses `sol_amount` only with that same independently
verified SOL pairing, zero `quote_amount`, and `ix_name` of `buy`, `sell` or
`buy_exact_sol_in`. Conversion uses nine decimals. The official
[BondingCurve quote documentation](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/docs/PUMP_PROGRAM_README.md)
and [buy account semantics](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/docs/instructions/BUY.md)
establish that default curve quote means native SOL. No account is fetched for
this decoder; missing cached verification stays unknown. Explicit conflicting
account/event quotes fail closed. No mint-decimals HTTP lookup is made. Invalid-unit
observations cannot produce CURRENT evidence.

Trades use the SAME single program-log subscription. An O(1) scanner dictionary
membership callback filters before submission; unrelated trades never enter the
queue, database or token buffers. Every successful transaction's event ordinal
joins its signature in the event identity, so multiple trades remain distinct.
The existing bounded 10,000-signature replay cache rejects repeated notifications;
the engine also retains its existing bounded/persisted event identities.

Create priority is 105, migration/security 110; tracked trades retain candidate
priority capped at 80. The existing queue bound remains. Drops distinguish trade
from critical/nontrade observations, and both rejected incoming trades and evicted
trades reset the affected token's clean window. Token buffer eviction of trades
inside 180 seconds also resets coverage. No global trade history is added.

Continuity requires connected transport, at least 180 clean seconds since the
latest subscription acknowledgement, decode gap, tracking start or token trade
loss; at least three actual samples, consistent valid units, and existing freshness
limits. Outages are unknown loss, never zero volume. A bounded 32-interval history
and last-disconnect/reconnect timestamps track transport continuity; reconnects
have no backfill. PARTIAL windows cannot satisfy Companion or core entry gates.
No samples/unknown units are UNAVAILABLE. Short clean windows with valid samples
are PARTIAL. Other feature windows expose their own coverage requirement.
Confirmed chain timestamps may lag local curve timestamps; trade observations
can enter their existing bounded time window without rewinding lifecycle time.

Health adds decoded/accepted/ignored/duplicate/invalid-unit trades, buy/sell
processed counts, separate drops, clean coverage and CURRENT/PARTIAL/UNAVAILABLE
candidate counts. Discovery/trade decoding directly causes zero HTTP requests.
Existing lifecycle, security cadence, Opportunity/Companion thresholds and all
post-graduation/economic/historical gates are unchanged. After migration, PumpSwap
trade events are not decoded by this Pump-program subscription; flow ages out.

## Scoped decode gaps and bounded diagnostics

TradeEvent's discriminator and 32-byte mint prefix are classified before parsing
its tail. Untracked mints use an O(1) scanner membership check and skip full Borsh
and tail base64 decoding, even when the unrelated tail is malformed. A lightweight
placeholder retains the supported-event ordinal within successful invocation
frames. Signature-plus-event-ordinal identity and bounded replay dedup remain.

A strict decode failure with a recoverable tracked mint invokes only that token's
trade-gap callback. It does not update the global decode-gap timestamp. Known
queue losses, stale trades and rolling-buffer losses also remain token-local.
Unknown/unrecoverable TradeEvent identity cannot safely exclude tracked mints:
that case remains a global gap. Invalid outer notifications, incomplete/invalid
invocation framing, subscription failure and disconnect remain global. In
particular, a truncated log tail can conceal additional tracked events; seeing an
untracked prefix earlier in that transaction does not prove complete coverage.
Create/migration schema and accepted-prefix semantics are unchanged.

Health uses fixed-cardinality counters: five event-type buckets, ten failure
categories and their 5-by-10 matrix, plus fixed framing/reset-reason counters.
Known event discriminators are static schema metadata; arbitrary discriminators,
wallets, exception text and payloads are never retained in diagnostic maps.
Framing distinguishes depth mismatch, unbalanced finish and unfinished invocations,
and counts the literal `Log truncated` marker separately. That marker also resets
global trade coverage when visible invocation frames happen to balance or no
visible event survives the truncation. Prefix-classification
and prefix-filter counters count examined logs, including logs whose invocation
later fails or whose notification replays. Full TradeEvent decode counters now
refer to tracked events in successful frames; untracked tails are not decoded.
This intentionally changes the interpretation of the old all-mints decoded count.

The 180-second observation requirement, 20-second configured freshness limit,
quote-unit checks, Companion/core gates and RPC cadence remain unchanged. A scoped
fix alone cannot establish CURRENT if genuine global framing/transport gaps keep
occurring. `smoke_observe.py` records peak/final coverage, whether CURRENT was ever
observed, bounded aggregate CURRENT examples, and overlapping blocker counts.

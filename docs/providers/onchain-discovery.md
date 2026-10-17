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

Ordinary discovery/trade decoding has **zero HTTP enrichment calls**. It does not
poll transactions, metadata URIs, accounts or security. Explicit truncations alone
use the bounded identity-recovery queue described below; missing supported events
are never synthesized. Providers that omit/truncate event logs cannot provide full discovery
coverage. Missing migration events likewise remain unavailable rather than
inferred. Recovery bounds and retries share the existing RPC limiter and pressure controller.
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
candidate counts. Ordinary discovery/trade decoding directly causes zero HTTP
requests; explicit truncation recovery is accounted separately.
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
and counts the literal `Log truncated` marker separately. Explicit truncations
with a valid signature now enter bounded identity recovery, including balanced
frames and notifications with no visible event. Other framing failures remain global. Prefix-classification
and prefix-filter counters count examined logs, including logs whose invocation
later fails or whose notification replays. Full TradeEvent decode counters now
refer to tracked events in successful frames; untracked tails are not decoded.
This intentionally changes the interpretation of the old all-mints decoded count.

The 180-second observation requirement, 20-second configured freshness limit,
quote-unit checks, Companion/core gates and RPC cadence remain unchanged. A scoped
fix alone cannot establish CURRENT if genuine global framing/transport gaps keep
occurring. `smoke_observe.py` records peak/final coverage, whether CURRENT was ever
observed, bounded aggregate CURRENT examples, and overlapping blocker counts.


## Targeted truncation recovery

Only a successful notification containing the exact `Log truncated` marker may
schedule standard [getTransaction](https://solana.com/docs/rpc/http/gettransaction).
Ordinary TradeEvents make zero HTTP requests. Recovery uses the existing
SOLANA_RPC_URL, confirmed commitment, JSON encoding and maxSupportedTransactionVersion=1.
It reads complete compiled outer and inner instructions, not meta.logMessages.
Version-0 keys resolve as static keys + loaded writable + loaded readonly addresses;
lookup counts and every account/program index are checked. Current
[standard v1 messages](https://solana.com/docs/core/transactions/versioned-transactions)
use inline keys, no lookup tables and a strictly bounded transactionConfig. The
[official JSON structures](https://solana.com/docs/rpc/json-structures) define the
same compiled-instruction shape; no binary v1 deserializer is needed. Missing CPI metadata,
unsupported versions, mismatched signatures/slots and malformed data fail closed.

`backend/app/pump_instructions.json` extracts discriminators and ordered account
names from the same official IDL commit
`639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22` (verified current 2026-10-17;
full IDL SHA-256 `7616681ea557975f9f623ac211080f22a93060781eaf4765b0a488d980997207`).
Supported identity layouts: buy, buy_exact_sol_in, buy_v2/v3,
buy_exact_quote_in_v2/v3, sell and sell_v2/v3. The canonical mint account is
position 2 for legacy instructions and base_mint position 1 for v2/v3.
Known nontrade instructions are distinguished using the pinned IDL.
Multi-hop curve calls now use the pinned PumpSwap route identity mapping below.
Unassociated/ambiguous calls and unknown Pump instructions remain unsupported/global.
Canonical inner Anchor event-emission calls use the
[official event-CPI tag](https://github.com/solana-foundation/anchor/blob/14cec14617f372b69403c6fe0c904e46a723ca3f/lang/src/event.rs),
known event discriminator and Pump event-authority PDA; they are not new trade
instructions. Instruction requested amounts are never converted into trade evidence.
No missing trade volumes or creations/migrations are reconstructed by recovery.

The queue holds at most 32 signatures, with one in-flight request, three attempts
at most and a 45-second pending-age limit checked between requests. A request may
finish after that limit by the existing bounded HTTP timeout. Null responses retry
with 2/4-second waits; provider cooldown can extend waits but never bypasses the
age limit. The worker shares the existing two-request/second limiter, concurrency
semaphore and adaptive 429/error backoff with monitoring. Signature dedup holds
at most 10,000 entries. Queue overflow immediately creates a global gap.
No transaction payload or wallet list is persisted.

Pending recovery blocks CURRENT for overlapping candidate feature windows and
immediately changes structured evidence to PARTIAL/UNAVAILABLE. System Health and
token coverage_state show `PENDING RECOVERY`; the previous clean-window start is
preserved. Only UNTRACKED_CONFIRMED clears pending with no gap. TRACKED_AFFECTED
creates local gaps for all affected currently tracked mints at the original
notification observation time. UNSUPPORTED_PUMP_TRADE, TRANSACTION_UNAVAILABLE,
TRANSACTION_FAILED and MALFORMED create global gaps. An intervening transport or
queue gap cannot be erased by a later untracked confirmation. A disconnect still
starts global coverage again. No general outage backfill is provided.

Health exposes actual recovery RPC requests/successful RPC responses/errors/429s,
classification counts, dedup, overflow, pending/peak/oldest age and local/global
recovery gaps. Successful RPC responses include temporary null results; classification
counts describe actual resolutions. Ordinary monitoring requests equal total RPC
requests minus recovery requests. The normal-trade HTTP delta remains zero;
explicit truncation recovery increases total HTTP demand and consumes provider quota.

Queue instrumentation preserves capacity and processing order: exact peak depth,
oldest source event/trade age, oldest queue residence, events/trades that were fresh
on arrival but exceeded the existing age limit before drain, cumulative accepted
and processed trade rates and at most 300 one-second depth samples. Already-stale
arrivals are counted by the existing rejection metric, not blamed on queue residence.
No 180-second continuity, 20-second freshness, quote units, strategy or lifecycle
threshold is relaxed. CURRENT remains observed coverage, not guaranteed delivery.


## Multi-hop recovery identity

`backend/app/pump_amm_recovery.json` vendors only the multi_hop_swap selector,
ordered fixed account names/addresses and argument types from
[official pump_amm.json](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/idl/pump_amm.json),
plus the hop-group specification from
[official MULTI_HOP_SWAP.md](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/docs/instructions/MULTI_HOP_SWAP.md).
Repository, commit, path and full IDL SHA-256 are recorded in the local schema.
The Pump instruction schema and normal event schemas are unchanged.

The PumpSwap selector is [43,100,73,19,233,246,111,148], with 16 fixed accounts
and five remaining accounts per hop: base, quote, venue, base vault, quote vault.
All keys are validated; only a venue equal to the Pump bonding-curve PDA derived
from [b"bonding-curve", base_mint] identifies a curve. Pool venues do not supply
Pump flow. No owner lookup, amount execution inference or additional HTTP request
is used. Recovery still runs only for explicit truncated notifications.

Association uses the original outer instruction index and CPI stackHeight ancestry.
Each curve call must descend from its nearest canonical route. With missing stack
heights, a sole outer route is still proven to contain its own inner-instruction
group; an inner route with unknown ancestry cannot be assumed to be the parent.
Multiple outer groups resolve independently; multiple inner routes require proven
ancestry. A sibling route or a route elsewhere in the transaction cannot justify a
call. Shared canonical user/global/config/program/event-authority accounts must
match. Route shape, literal program accounts, global-config PDA, exact instruction
length and curve-call Borsh byte-vector length are checked. Invalid routes are
MALFORMED; missing, mismatched or ambiguous parents remain UNSUPPORTED_PUMP_TRADE.
No partial route can clear pending coverage. All tracked curve mints in each
associated route are included, and pool base mints are excluded.

Fixed diagnostic buckets distinguish unsupported multi_hop_curve_swap,
unknown_discriminator and other (including unsupported event-CPI shape). They
count unsupported instructions, while the existing classifications count
transactions. Additional counters record curve calls observed, distinct associated
routes resolved, final multi-hop transaction classifications (untracked/tracked),
and unresolved calls/ambiguous subsets. Routes resolved and calls observed have
different units: one route can contain several curve calls. A transaction with an
otherwise resolved route and an unrelated unknown Pump instruction still fails
globally. Diagnostics never retain arbitrary discriminator keys, payloads or wallets.

Transport transitions retain at most 32 timestamp/state records. The OBSERVE probe
reports relative transition times, bounded queue samples and aggregate min/max
buyer breadth, flow ratio, whale share and samples drawn only from actual CURRENT
candidates. No samples means unavailable ranges, never fabricated zeros.
This adds no PumpSwap BuyEvent/SellEvent decoding, MarketEvents, strategy features,
wallet or transaction-submission capability. Existing 180-second continuity,
20-second freshness, units and all numerical gates remain unchanged.

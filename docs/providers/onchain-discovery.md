# Standard Solana Pump discovery

Verified against official documentation on 2026-10-16. This integration uses
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

`backend/app/pump_events.json` contains the exact two event definitions extracted
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

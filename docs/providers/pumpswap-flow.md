# Verified post-graduation PumpSwap flow

This read-only source uses standard Solana WSS, without PumpPortal or ordinary
trade HTTP requests. It supplies the existing MarketEvent/feature pipeline;
there is no trading or wallet functionality.

## Canonical source and executed amounts

The minimal complete BuyEvent/SellEvent layouts in
`backend/app/pump_amm_events.json` are copied from the official
[pump_amm IDL](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/idl/pump_amm.json),
commit `639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22`.
The source SHA256 is
`b7d8c57a4d9c4dd0109a9ab893052352333252d4eedced10ac091d4d66cab89b`.
The [trade-v2 documentation](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/docs/instructions/PUMP_SWAP_TRADE_V2.md)
confirms that v2 emits the same events and fee-recipient pubkeys may be default.
The [multi-hop documentation](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/docs/instructions/MULTI_HOP_SWAP.md)
remains pinned for identity recovery; that recovery path is unchanged.

Buy volume uses `user_quote_amount_in`; sell volume uses
`user_quote_amount_out`. These are the actual quote debit/credit at the user
boundary, including applicable fees. Both are consistently user cash flow;
`quote_amount_in`/`quote_amount_out` and actual base amounts must also be positive.
`max_quote_amount_in` and `min_quote_amount_out` are parsed for layout validation
but never used as executed volume. No price is derived from these amounts.
The strict decoder reads every canonical field, including signed i128 virtual
quote reserves, bools and bounded UTF-8 strings, and rejects trailing bytes.
Pool/user must be nondefault valid public keys; creator/fee keys may legitimately
be default. Creator identity comes from existing creation evidence, not the AMM
event's coin_creator field. Timestamp must be valid; the processing pipeline
retains the existing 20-second freshness limit.

Quote identity comes only from the independently verified on-chain pool:
WSOL (`So11111111111111111111111111111111111111112`) is 9 decimals/SOL;
USDC (`EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`) is 6 decimals/USDC.
Other quote mints produce unknown currency, unavailable units and no CURRENT
trade evidence. There is no USD conversion.

## Registry and subscriptions

The existing security inspector verifies the PumpSwap program owner, Pool
layout and base mint. Its report now retains the inspected pool address.
Confirmed migrated tokens in GRADUATED, POST_GRAD_OBSERVATION or
ENTRY_CANDIDATE can contribute independently verified pools to the registry.
A DEX Screener pair is only a discovery hint: it cannot enter without an
on-chain parse. Canonical migration pool hints also reach the existing security
scan, without adding a scan or changing RPC cadence. Security quality and flow
quality remain separate; strong flow cannot override missing security.

One additional standard WSS connection multiplexes at most 25 pool-address
mentions subscriptions. No global PumpSwap subscription is made. Selection
uses existing candidate priority and stable mint/pool ordering. Reconciliation
runs once per second; accepted notifications use an O(1) pool registry lookup.
Active and in-flight subscriptions share the 25-slot budget; retiring pools
release their slot after unsubscribe ACK. ACK deadlines are 15 seconds, socket
buffers bounded, and retries use bounded exponential jittered backoff.
Disconnect/shutdown closes coverage; reconnect restores eligible subscriptions
and waits for new ACKs. Signature/event ordinal/pool dedup retains at most
10,000 identities. Failed transaction/invocation events never supply flow.

## Epochs and continuity

Confirmed migration ends PRE-GRAD FLOW. Real-mode tokens start a fresh
POST-GRAD PUMPSWAP FLOW epoch; pre-grad events remain in bounded history but
cannot enter post-grad trade features. Late Pump trades cannot refresh post-grad
last-trade time. Restored sessions always re-warm their coverage and pool
verification. DEMO fixtures remain explicitly synthetic and unchanged.

Subscription ACK begins observation coverage. CURRENT requires at least 180
clean seconds after migration and ACK, at least three samples, consistent known
units, and fresh evidence within 20 seconds. All eligible verified pools for a
token must be covered: capacity loss never means zero trades. Pool-local
truncation, malformed events, identity conflicts, unsubscribe, queue loss,
stale processing or rolling-buffer loss invalidate the affected token. Entire
PumpSwap transport loss invalidates all covered tokens on that connection.
Pump discovery/recovery gaps do not reset post-grad continuity. Conversely,
PumpSwap loss cannot reset pre-grad continuity. Pool notifications containing
multiple pools' trade events fail closed on identity conflict; no partial
notification is accepted. There is no getTransaction fallback for pool logs.

Core, Opportunity and Companion thresholds, lifecycle gates, security gates,
economics and approved historical evidence requirements are unchanged.
CURRENT post-grad flow is necessary evidence, never permission by itself.

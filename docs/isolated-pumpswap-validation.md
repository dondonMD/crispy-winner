# Isolated PumpSwap acquisition validation

Run from the repository root with the existing private `SOLANA_RPC_URL` and
`SOLANA_WS_URL` configuration (the command loads local `.env`):

```bash
.venv/bin/python scripts/validate_pumpswap_flow.py \
  --pool <pool-address> --base-mint <expected-base-mint> --seconds 300 \
  --output data/observe/pumpswap-isolated-<UTC-timestamp>.json
```

The output path must not already exist. Duration is bounded to 1–600 seconds. A pool
hint from a prior migration is only a selection hint: the probe performs a fresh
standard `getAccountInfo` and calls production `parse_pool` before subscription.
That verifies the PumpSwap owner, canonical Pool discriminator/layout and expected
base mint. Pool, base, quote and both vault addresses must be nondefault valid
pubkeys; base and quote must differ. Pool identity verification does **not** establish
that its token passes security/concentration or is suitable for an entry.

Acquisition uses production `PumpSwapFlow` unchanged: the pinned official schema,
canonical successful invocation framing, pool mentions subscription, ACK handling,
bounded reconnect/backoff, quote semantics and signature/event-ordinal/pool dedup.
The schema provenance remains pump-fun/pump-public-docs commit
`639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22`, `idl/pump_amm.json`.

Production normalized volume is accepted only when the verified pool quote maps to
known units, `units_valid` is true, and executed raw amount agrees with the
normalized amount. Buys use `user_quote_amount_in`; sells use
`user_quote_amount_out`. WSOL uses SOL/9 decimals, USDC uses USDC/6 decimals; other
quotes fail closed. Max/min quote limits are never used. Totals accumulate integer
raw quote units and report decimal strings without USD conversion.

No engine, database, candidate, research store, strategy evaluator or paper account
is instantiated. The event sink retains counters, integer volume totals and at most
three examples containing only side, quote amount, timestamp, slot and pool. It
never retains or reports trader wallets or transaction payloads. Pool-specific gaps
are diagnostic counts only. No MarketEvent reaches RadarEngine or feature scoring.
The only ordinary HTTP request is pool verification; trade acquisition is WSS only.
Cancellation closes the production socket and joins the provider task.

The standalone probe never claims 180-second strategy CURRENT. An ACK plus a
canonical event proves acquisition/decoding only. The end-to-end milestone still
requires a normal tracked migration, verified safe eligible pool, selection, ACK,
clean 180-second post-grad coverage, valid/fresh samples and existing strategy gates.

## Live result: 2026-10-18

The [preserved wallet-free report](validation/pumpswap-isolated-20261018T205240Z.json)
is identical to the local report at
`data/observe/pumpswap-isolated-20261018T205240Z.json`, SHA256
`23e2741a754840a046d514f35505cef0b1cd74165d3454ee4bf994f395acbc17`.

The pool hint came from the previous recovered-migration handoff report. It was
freshly verified through confirmed `getAccountInfo` and the production parser:

- Pool: `Cz6WzWV8FsREtsin7TmRpqgm1BcETCgM8EQcA5X2QJDQ`
- Base mint: `GD3thpuWqREqzqpX72R5NfsnyBbUinow8UFEmTKpump`
- Quote: WSOL (`So11111111111111111111111111111111111111112`), SOL units, 9 decimals
- Canonical PumpSwap owner/layout and nondefault base/quote/vault keys verified.

In 300.001 seconds the production connection remained connected, with one
subscription request/ACK, 4,056 notifications, zero reconnects and zero transport
errors. It decoded 2,319 BuyEvents and 1,715 SellEvents; all 4,034 were accepted in
consistent known units. Duplicate count and invalid-unit count were zero.

The three decode failures were all explicit `Log truncated` notifications, producing
three diagnostic token-local gaps. Every other failure category was zero. The
missing transactions were not treated as zero trades and were not recovered over
HTTP by this pool-specific provider. Totals describe observed valid events only,
not complete flow for the interval.

Observed actual quote totals: 39.721077509 SOL bought / 12.387101408 SOL sold, from
`user_quote_amount_in` / `user_quote_amount_out` respectively. The first event
arrived after 1.262 seconds; final last-event age was 3.640 seconds. The report
contains exactly three wallet-free examples. It omits base amounts because the
production normalized MarketEvent does not supply executed base amounts.

Pool verification used one HTTP request. Ordinary trade HTTP delta was zero.
No engine, database, candidate, research or paper state was instantiated. Tests
trap engine construction/processing, exercise the production decoder/ACK path,
unknown quotes, wrong owner/layout/base identity, malformed amounts, bounded
examples, cancellation and reconnect replay deduplication. Live reconnect/replay
was not exercised because there were no disconnects.

All 502 backend tests and 39 frontend tests passed, along with Ruff, mypy (including
the script), TypeScript/production build, secret scan, locked-backend/frontend
dependency audits and diff checks. Existing frontend tests emitted their existing
duplicate-key warning without failures. No production decoder, recovery scheduler,
security, lifecycle, strategy, Companion or Opportunity logic changed.

This meets standalone acquisition validation. It does not establish safe-pool
strategy eligibility, post-grad CURRENT, profitability or a validated trading edge.
The normal migration-to-verified-eligible-pool-to-ACK-to-clean-CURRENT milestone
remains outstanding.

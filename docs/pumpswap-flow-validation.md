# Verified post-grad PumpSwap flow validation

Implementation follows the official Pump IDL/docs pin
`639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22`; provenance, complete event layouts,
executed user quote debit/credit semantics and coverage rules are documented in
[the provider reference](providers/pumpswap-flow.md).

## Deterministic validation

434 backend tests pass, including 32 new PumpSwap cases. Coverage includes
canonical buy/sell layouts and executed-volume fields; wallet/pool identity;
WSOL/USDC/unknown units; malformed/truncated/short discriminator/bool/trailing
layouts; failed invocation/transaction and wrong program; replay/multiple-event
identity; deterministic 25-slot capacity; duplicate subscribe prevention;
unsubscribe/ACK eligibility races; reconnect restoration; bounded rejection
backoff; migration epoch isolation; pre-epoch/pre-grad exclusion; three samples;
180-second clean coverage and unchanged 20-second freshness; creator selling;
existing core rejection gates; actual normalized buyer/flow features and zero
ordinary PumpSwap HTTP delta. All existing Pump discovery, truncation recovery,
Opportunity, Companion, economics and lifecycle tests remain in the full suite.

39 frontend tests pass, including post-grad health/capacity visibility.
Ruff, mypy (29 modules), TypeScript and production frontend build pass.
Backend and frontend dependency audits report no known vulnerabilities.
No dependencies, settings defaults or strategy thresholds changed.
The source/document secret scan and `git diff --check` pass.

The live probe uses an isolated temporary database and the configured Helius
standard HTTP/WSS endpoints, with PumpPortal disabled and
`trade_stream_enabled=false`. The added connection is pool-filtered; normal
PumpSwap trade ingestion has no HTTP path. Measurements include existing
monitoring/security HTTP and Pump truncation-recovery HTTP separately.

## Live Helius OBSERVE result

Final release implementation, 602.83 seconds on 2026-10-17 UTC
(2026-10-18 local): PumpPortal disabled, standard WSS only, isolated DB.
Two preliminary runs were stopped during final decoder/retry review and are
excluded from these measurements.

| Measurement | Final run |
| --- | ---: |
| Pump WSS messages / creates / migrations | 187,473 / 320 / 0 |
| Pump WSS reconnects | 0 |
| Pump tracked trades accepted / processed | 17,259 / 16,773 |
| Processed buys / sells (all pre-grad) | 8,846 / 7,927 |
| Pre-grad CURRENT / PARTIAL / UNAVAILABLE | 0 / 53 / 196 |
| Maximum Pump global / token clean seconds | 88.63 / 82.85 |
| Verified eligible PumpSwap pools, final / peak | 0 / 0 |
| PumpSwap subscribed pools, final / peak / capacity | 0 / 0 / 25 |
| PumpSwap ACKs / messages | 0 / 0 |
| PumpSwap BuyEvents / SellEvents / accepted / processed | 0 / 0 / 0 / 0 |
| PumpSwap reconnects / errors / decode failures / pool-local gaps | 0 / 0 / 0 / 0 |
| PumpSwap invalid-unit observations / duplicates | 0 / 0 |
| Post-grad candidates CURRENT / PARTIAL / UNAVAILABLE | 0 / 0 / 0 |
| Peak post-grad CURRENT / max clean seconds | 0 / 0 |
| Ordinary monitoring / Pump recovery / total HTTP RPC requests | 66 / 515 / 581 |
| RPC errors / 429 | 0 / 0 |
| Ordinary PumpSwap trade HTTP delta | 0 |
| Final / peak RSS MB | 200.4 / 200.4 |
| Mean / peak CPU, process percent | 64.29 / 116.6 |
| Final / exact peak queue | 12 / 571 |
| Final oldest event / trade age seconds | 7.19 / 7.19 |
| Events becoming stale while queued | 365 trades |
| Stale processing rejections | 471 trades |
| Overflow trade / critical drops | 0 / 0 |
| Companion ENTRY_CANDIDATE / WAIT / REJECT / TOO_LATE | 0 / 238 / 11 / 0 |
| Paper cash USD | 20 |

Opportunity counts: EARLY_OPPORTUNITY 0, DEVELOPING 164, PULLBACK_WATCH 2,
TOO_EXTENDED 0, AVOID 18, DATA_LIMITED 65.
No CURRENT post-grad candidates existed, so buyer, flow-ratio, whale-share,
buy/sell, sample-count and coverage aggregates for CURRENT post-grad candidates
are unavailable, not zero-valued flow estimates.

The PumpSwap socket connected successfully and remained connected, but this
window observed no canonical migration. Therefore it could not exercise a real
verified pool subscription ACK or real BuyEvent/SellEvent ingestion. Zero
post-grad status counts describe an empty candidate universe. The implementation
passes deterministic integration tests; real post-grad flow/CURRENT and active
pool resource load remain to be observed in a suitable migration window. This
is a live-verification limitation, not evidence that a migration occurred with
zero trades. No profitability or validated trading edge is established.

The accepted pre-grad foundation remained fail-closed under heavier observed
traffic. Pump recovery had 515 successful requests and 30 pending at the final
snapshot. Its 414 global gaps comprised 339 recovery-queue overflows, 74 bounded
transaction-unavailable expirations and one unsupported `other` subtype. No
transport gaps occurred. Multi-hop calls observed/resolved were 94/94, with no
unresolved or ambiguous multi-hop routes. No recovery behavior or queue
processing loop was redesigned in this patch.

Compared with the preceding 600-second milestone (156.6 MB peak RSS, 48.84% mean
CPU), this run reached 200.4 MB and 64.29%, alongside more Pump traffic
(187,473 versus 154,543 messages) and accepted trades (17,259 versus 11,288).
Those differences cannot be attributed to active PumpSwap ingestion: there
were no subscribed pools. RAM stayed below 500 MB. Active-pool overhead has not
been measured. The new provider has no ordinary trade HTTP call path, and the
deterministic normalized-event pipeline test independently verifies zero RPC
request delta while processing real-layout synthetic BuyEvent/SellEvent data.

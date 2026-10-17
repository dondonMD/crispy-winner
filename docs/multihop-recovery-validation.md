# Multi-hop truncation recovery validation

Continuation of `22be0c8bb5e66738d95df546319f6131ee730aff`.

Schema provenance: pump-fun/pump-public-docs commit
`639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22`, `idl/pump_amm.json` and
`docs/instructions/MULTI_HOP_SWAP.md`; Pump call account names from the same pinned
`idl/pump.json`. The new small pump_amm_recovery.json records repository, commit,
paths and full AMM IDL SHA-256
`b7d8c57a4d9c4dd0109a9ab893052352333252d4eedced10ac091d4d66cab89b`.
No third-party layout is used. Details and association rules are in
[the provider reference](providers/onchain-discovery.md#multi-hop-recovery-identity).

Mapping preserves the transaction outer-index/CPI hierarchy. Every Pump curve call
requires a canonical PumpSwap parent route, proven ancestry/grouping and matching
shared fixed accounts. Only route base mints with an exact Pump curve-PDA venue
can affect current tracked continuity. Multiple calls can belong to one route;
multiple routes must be distinguishable. Missing/ambiguous parents stay unsupported,
malformed shapes stay fail-closed. Normal nine buy/sell identity layouts, standard
legacy/v0/v1 handling, pending semantics and RPC pressure/cadence remain unchanged.
No HTTP owner queries, normal trade polling, PumpSwap flow features, executed amount
inference, wallet functionality, threshold or evidence-standard changes are added.

Counters are fixed-cardinality and aggregate only. Unknown discriminators never
become dictionary keys. The prior 38 unsupported transactions are not retrospectively
claimed to be one subtype. New live counts are collected separately.

A bounded preflight made two explicit-truncation getTransaction calls, zero errors,
and found one actual multi_hop_curve_swap correctly associated with one canonical
route and classified UNTRACKED_CONFIRMED. Preflight requests are excluded from the
main measured run. No raw transaction or wallet logs were retained.

Full validation and the at-least-600-second Helius OBSERVE result follow below.

## Validation

- Complete backend suite: 402 passed in 57.72 seconds (59 new multi-hop/diagnostic tests).
- Complete frontend suite: 38 passed, including System Health recovery presentation.
- Ruff and mypy: passed; 28 application source files checked by mypy.
- TypeScript and production Vite build: passed.
- Secret scan: passed, 118 source/document files; git diff --check passed.
- Backend pinned-lockfile and frontend dependency audits: no known vulnerabilities.
- No dependencies or endpoint/configuration changes.

Tests cover pool-to-curve and two-curve routes, exact tracked-mint sets, pool-only
routes, all-untracked routes, canonical PDA recognition, malformed fixed/remaining
accounts, bad Pubkeys/program accounts/data lengths, missing parents, unrelated
outer groups, sibling routes, ambiguous/missing inner ancestry, proven multiple
routes/calls, shared-account mismatches and impossible CPI stack jumps. Legacy,
v0 mixed loaded addresses and v1 messages are covered, as are all original nine
Pump trade layouts. Identity-only engine tests verify that recovery creates no
MarketEvents or feature observations. Existing tests retain the 180-second,
20-second, units, security, economics, history and strategy gates.

Diagnostic cardinality is fixed: three unsupported subtype buckets plus six
multi-hop counters, with at most 32 transport timestamp/state records. No raw
transaction, wallet list or arbitrary discriminator map is stored. Normal-path
trade HTTP remains zero; no per-hop owner lookup exists.

## Files changed

- `backend/app/pump_amm_recovery.py`, `backend/app/pump_amm_recovery.json`,
  `backend/app/truncation.py`, `backend/app/discovery.py`.
- `backend/tests/test_multihop_recovery.py`.
- `frontend/src/App.tsx`, `frontend/src/types.ts`,
  `frontend/src/components/Companion.test.tsx`.
- `scripts/smoke_observe.py`.
- `docs/providers/onchain-discovery.md`, `docs/operating-guide.md`,
  `docs/limitations.md`, `docs/truncation-recovery-validation.md`,
  `docs/multihop-recovery-validation.md`.


## 602.59-second Helius standard-WSS OBSERVE result

**The live criterion was met:** real CURRENT trade evidence was first observed at
263.24 seconds; peak simultaneous CURRENT count was one. No evidence standard,
unit/freshness check or strategy threshold was changed. Final evidence was no
longer CURRENT; later loss/lag remained fail-closed.

The probe used a fresh isolated temporary database, the existing Helius standard
HTTP/WSS endpoints, PUMPPORTAL_ENABLED=false and trade_stream_enabled=false. It ran
for 600 seconds plus report overhead. Main-run counters below exclude the two
preflight requests. No raw transaction or wallet list was retained.

| Recovery measurement | Result |
|---|---:|
| WSS messages / explicit truncations | 154,543 / 504 |
| Recovery RPC requests / successful RPC responses | 427 / 426 |
| Recovery errors / 429 | 0 / 0 |
| UNTRACKED_CONFIRMED / TRACKED_AFFECTED | 398 / 28 |
| UNSUPPORTED / UNAVAILABLE / FAILED / MALFORMED | 0 / 2 / 0 / 0 |
| Unsupported multi_hop_curve_swap / unknown discriminator / other | 0 / 0 / 0 |
| Multi-hop curve calls observed / associated routes resolved | 96 / 96 |
| Multi-hop transaction UNTRACKED_CONFIRMED / TRACKED_AFFECTED | 90 / 6 |
| Multi-hop unresolved / ambiguous calls | 0 / 0 |
| Recovery pending final / peak / oldest final age | 32 / 32 / 36.94 sec |
| Recovery queue overflows / duplicate signatures | 44 / 0 |
| Global continuity gaps | 48 |
| Global gap breakdown | 44 recovery overflows + 2 unavailable recoveries + 2 transport gaps |
| Token-local continuity gaps | 1,523: 931 stale + 564 rolling-buffer + 28 recovery |

All 504 truncations are accounted for: 426 resolved transaction identities,
two unavailable expirations, 44 backlog-overflow global gaps and 32 pending.
The 427th recovery request was still in flight at report capture: no HTTP error
was hidden, and pending coverage remained incomplete. No successful RPC null
response was required by the observed accounting. No unsupported route was
silently discarded. Six transactions containing resolved multi-hop routes were classified
TRACKED_AFFECTED. These counters describe the final transaction classification;
ordinary Pump trades can coexist in a transaction. The other 22 TRACKED_AFFECTED
transactions used existing normal Pump trade recovery. The previous 38 unsupported transactions are not retroactively
subtyped from this new sample.

| Continuity and evidence | Result |
|---|---:|
| CURRENT / PARTIAL / UNAVAILABLE final | 0 / 43 / 172 |
| Peak CURRENT / first observed CURRENT | 1 / 263.24 sec |
| Candidates ever observed at >=180 clean sec | 23 |
| Maximum global / token clean coverage | 245.49 / 245.49 sec |
| Tracked trades fully decoded / accepted / processed | 11,288 / 11,288 / 10,345 |
| Buys / sells processed | 5,347 / 4,998 |
| Stale processing trade rejections | 931 |
| CURRENT-only estimated independent buyer range | 7–7 |
| CURRENT-only flow-ratio range | 0.86069–0.91594 |
| CURRENT-only whale-share range | 54.27%–57.96% |
| CURRENT-only sample-count range | 100–106 |

The first qualifying aggregate example had 53 buys, 53 sells, seven estimated
independent buyers, flow ratio 0.91594, whale share 57.96%, and 181.46 seconds of
coverage. These are observed activity statistics, not ownership claims, profit
probabilities or entry instructions. CURRENT structure alone did not satisfy
strategy gates. No final candidate was CURRENT.

Retained bounded-event unit observations were 5,747 SOL, seven USDC and 3,016
unknown. They are not cumulative processed totals: old events/candidates can leave
bounded buffers. Invalid-unit accepted observations were 3,744. Units remained
unavailable when not independently established; route quote identities were never
converted into executed volume. Final overlapping blockers were 215 insufficient
continuity, 215 pending-recovery overlap, 172 invalid/mixed/unknown units, 186 stale,
and 146 insufficient samples (109 with no samples).

| Queue/providers/resources/product | Result |
|---|---:|
| Queue final / exact insertion peak | 13 / 761 |
| Final oldest event / trade source age | 7.54 / 7.54 sec |
| Final oldest queue residence | 2.44 sec |
| Maximum sampled oldest trade source age | 49.00 sec |
| Events / trades becoming stale while queued | 652 / 651 |
| Event-queue total / trade / critical overflow drops | 0 / 0 / 0 |
| Accepted / processed trade rate | 18.73 / 17.17 per sec |
| Ordinary monitoring / recovery / total Solana RPC | 53 / 427 / 480 |
| Total RPC errors / 429; final backoff level | 0 / 0; 0 |
| Normal-path trade HTTP requests | 0 |
| WSS reconnects | 2 |
| RSS final / sampled peak | 156.6 / 156.6 MB |
| Mean / sampled peak process CPU | 48.84% / 99.9% |
| Processed launches / final candidates / hot / background subset | 227 / 215 / 25 / 154 |
| Opportunity EARLY / DEVELOPING / PULLBACK / TOO_EXTENDED / AVOID / DATA_LIMITED | 1 / 106 / 1 / 0 / 36 / 71 |
| Companion WAIT / REJECT / ENTRY_CANDIDATE / TOO_LATE | 196 / 19 / 0 / 0 |
| Paper cash | $20 |

Trade conservation indicates 12 pending trades: 11,288 accepted = 10,345 processed
+ 931 stale rejected + 12 pending. The final 13-event queue therefore included one
other event. The sampled queue peak was 688; the insertion-time counter captured
the exact peak of 761. Queue source age includes chain/delivery delay as well as
queue residence. Stale-while-queued counts and processing rejection counts have
different scopes/timestamps and are reported independently.

The bounded 300-sample depth history retained its most recent portion. Excerpts
(seconds: depth): 167.7:1, 204.5:22, 242.6:14, 277.8:0, 312.1:6, 349.3:0,
395.8:12, 436.5:17, 497.0:15, 547.0:1, 599.2:19. No event-queue capacity was changed.

Detected transport/ACK timing relative to probe startup:

| Seconds | Transition |
|---:|---|
| 1.06 | CONNECTED |
| 45.86 | DISCONNECTED; global gap |
| 47.93 | CONNECTED |
| 294.13 | DISCONNECTED; global gap |
| 296.29 | CONNECTED |

These are detection and subscription-ACK times, not invented physical outage
starts. Both reconnects still reset continuity. The first uninterrupted interval
between reconnects lasted about 246 seconds and allowed the observed CURRENT
window. There is no outage backfill.

All 467 decoder framing errors were associated with explicit truncation; tracked
trade-tail and unknown-mint failures were zero. Every other fixed decoder failure
category was zero. Recovery handled those notifications rather than immediately
resetting everyone. Normal nine-instruction recovery remained active.

## Remaining limitation

The multi-hop unsupported blocker was removed for every observed case. The final
loss of CURRENT was caused by conservative recovery backlog safety: 44 overflow
resets and two pending-age expirations, alongside two real transport gaps. Queue
lag and high per-token activity also became material under this longer/higher
load: 651 trades became stale while queued and 564 bounded rolling-buffer gaps
were recorded. Final pending recovery blocked every candidate window. No gate,
capacity or processing-loop redesign was used to hide that loss.

Compared with the earlier 300.94-second run, ordinary monitoring was 53 requests
in 602.59 seconds versus 19 in 300.94; the polling configuration and pressure
formulas are unchanged. Recovery used 427 versus 168 requests, driven only by
explicit truncations. The route parser itself made zero additional requests.
Tracked acceptance increased from 2,526 to 11,288, and candidate count from 107 to
215. Mean CPU rose from 19.72% to 48.84%; RSS from 115.9 to 156.6 MB, still below
normal/soft memory targets. Different live loads do not isolate parser CPU cost.
There is no guaranteed sustained CURRENT availability, profitable-edge claim or
validated trading edge. Security, economics and historical evidence remain
separate conservative requirements.

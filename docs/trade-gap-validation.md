# Scoped Pump TradeEvent continuity validation

This patch preserves the pinned canonical schema, standard single Solana
`logsSubscribe`, Helius configuration, quote validation, 180-second clean window,
20-second freshness limit, bounded queues/buffers, RPC cadence, and all strategy,
Opportunity, Companion, security, economics and historical-evidence gates.
No PumpSwap integration, HTTP trade calls, paid stream or trading/wallet feature
is added.

## Diagnosis before behavioral changes

The existing ignored `data/observe-smoke.json` matched the supplied Helius run:
33,718 messages, 157 decoding errors, three reconnects. It retained only a total
error count, without categorized errors or raw failed notifications. Therefore
an exact retrospective category breakdown of those 157 errors cannot be
reconstructed. The report does not relabel them as untracked TradeEvent errors.

Bounded aggregate diagnostics were first installed with the original global-gap
behavior intact. A fresh 65-second run on the already-configured Helius endpoints
observed 5,925 messages, 1,335 fully decoded all-mint TradeEvents, one reconnect,
and **17 invocation-framing failures**. All 17 were notification-level errors;
TradeEvent/CreateEvent/migration tail-decode failures were zero. Truncated Borsh,
unsupported layout, invalid bool/string/pubkey/timestamp/value/encoding and other
categories were all zero. These are fresh observations, not exact classifications
of the historical 157 errors.

This finding matters: mint-scoping a known trade-tail failure does not justify
ignoring incomplete outer invocation logs. Those can conceal an additional
tracked trade whose mint is not visible. The final probe includes fixed framing
subcategories and correlation with the literal `Log truncated` marker.

## Scoped behavior and bounds

Only the discriminator and mint prefix are decoded for an untracked TradeEvent;
its tail is not decoded or counted as missing tracked evidence. Known tracked
mint tail failures call a token-local invalidator and never advance the global
decode-gap timestamp. Unknown/unrecoverable TradeEvent identity remains global.
Real disconnect/reconnect/subscription failures and invalid outer framing remain
global. Queue, stale and buffer losses remain local and observable; an older
buffer timestamp cannot rewind a newer local gap.

Diagnostic cardinality is fixed: five event types, ten reason categories, a
5-by-10 matrix, three static known discriminators, four framing details, seven
global reset reasons and four token-local reset reasons. No arbitrary keys,
wallets, exception messages or event payloads are retained in diagnostics.
Ordinal placeholders preserve distinct signature-plus-event-ordinal identities
when untracked tails are filtered; the existing 10,000-signature replay bound
remains. Current-prefix counters count examined log records, including records
whose outer frame is subsequently rejected. Full trade-decode counters now
exclude untracked tails and are not comparable to the old all-mint decode count.

## Validation

- Final full backend suite: 252 passed in 55.46 seconds. The prior 250-case run also passed.
- Scoped-gap diagnostics/regressions: 25 cases; the focused decoder/scoping suite
  passed all 66 cases; the broader focused
  decoder/core/Companion suite also passed (144 cases before the final timestamp
  regression was added).
- Frontend suite: 36 passed. No UI or TypeScript files changed.
- Ruff, mypy (`backend/app`), source/document secret scan and diff checks passed.
- No dependency changes; dependency audits were not required for this patch.

Tests cover bounded reason/type diagnostics, minimal prefix recovery despite a
bad base64 tail, no full decode for untracked mints, token-local strict failures,
continuity of the other tracked mint, conservative unknown identity and transport
loss, replay/ordinal safety, stale per-token loss, exact 179/180-second rebuild,
unchanged 20-second freshness, no HTTP trade requests and unchanged canonical
create/migration/unit behavior. Existing queue, core, Companion and Opportunity
regressions remain in the full suite.


## First scoped 240-second probe

The first scoped run used the existing Helius configuration and lasted 240.76
seconds. It did **not** meet the live CURRENT criterion. It observed 36,793 WSS
messages; 8,309 trade prefixes, 5,472 untracked prefixes filtered, and 2,837 tracked
trades strictly decoded/accepted. Tracked and unknown-mint decode failures were
both zero. The 126 decode errors were all notification-level invocation framing:
118 unfinished invocation stacks, four depth mismatches, four unbalanced finishes.
All 126 included the literal `Log truncated` marker. Every other decode category
and every event-tail failure type was zero in the observed/parsed records.

There were 131 marker-bearing notifications among records reaching the event decoder. Five had balanced visible frames
and therefore did not raise a parser error. The final code now also marks those (and marker-bearing no-event fast paths)
as global trade-coverage loss without changing existing create/migration decode
behavior; hidden events cannot be excluded just because visible frames balance.

Before that additional fail-closed guard, global resets were 128 (126 framing,
two transport), local resets 250 (22 stale, 228 bounded-buffer losses, zero tail
failures/queue losses). Peak clean WSS/token coverage was 27.13 seconds; final
snapshot WSS coverage 2.56 seconds. CURRENT/PARTIAL/UNAVAILABLE ended 0/11/81;
CURRENT was never observed. Other overlapping final blockers included 81 tokens
with invalid/mixed/unknown units, 43 with fewer than three samples and 70 with
stale/missing flow. All 92 were below required clean continuity.

Processed buys/sells were 1,526/1,289; retained observations included 1,861 SOL
and 726 unknown-unit samples (bounded buffers, not complete windows). Stale
processing rejections were 22. RPC calls 15, errors/429 zero; direct trade HTTP
calls and extra calls for 101 snapshots zero. RSS peak/final 115.3 MB, process CPU
mean 34.37%, sampled peak 93.6%, final 22.6%; sampled queue peak/final 28/0;
trade/critical drops 0/0. Workload was 92 candidates, hot 25/background 49; counts
and traffic differ from the original run, preventing a controlled CPU comparison.

Opportunity actions: DEVELOPING 63, PULLBACK_WATCH 1, AVOID 18, DATA_LIMITED 10;
EARLY_OPPORTUNITY/TOO_EXTENDED zero. Companion WAIT 76, REJECT 16, other actions
zero. Paper cash $20; no entry. One security scan completed. No profitability or
trading-edge claim is made.

## Exact changed files

- `backend/app/discovery.py`: fixed-size error diagnostics, minimal mint-prefix
  filter, strict tracked-tail decoding, ordinal placeholders, local/global gap
  dispatch and explicit log-truncation coverage guards.
- `backend/app/engine.py`: per-token invalidator, monotonic gap timestamps,
  fixed reset counters, reuse of local handling for queue/stale/buffer losses,
  and shared coverage calculation without changing its required duration.
- `backend/tests/test_trade_gap_scoping.py`: deterministic bounded-diagnostic,
  isolation, replay, transport/truncation and coverage-boundary regressions.
- `scripts/smoke_observe.py`: maximum/final coverage, observed CURRENT peak and
  bounded examples, reset totals and overlapping evidence blockers.
- `docs/providers/onchain-discovery.md`: scoped-gap behavior, counter semantics
  and conservative unknown-mint/truncated-notification cases.
- `docs/trade-gap-validation.md`: historical diagnostic limits, actual measured
  diagnosis, validation and live results.

## Final Helius verification: CURRENT acceptance NOT met

Configured duration 240 seconds; elapsed 243.83 seconds. Existing Helius standard
WSS/HTTP environment was loaded privately, without modifying configuration.
PumpPortal remained disabled and `trade_stream_enabled=false`. One Pump program
subscription, no HTTP trade polling and no wallet/trading functionality.

| Metric | Final measurement |
| --- | ---: |
| WSS messages / reconnects | 43,214 / 2 |
| TradeEvent prefixes classified | 9,244 |
| Untracked prefixes filtered without tail decode | 6,225 |
| Tracked trades fully decoded in successful frames / queue accepted | 3,017 / 3,017 |
| Tracked-tail decode failures / unknown-mint decode failures | 0 / 0 |
| Duplicates / invalid-unit tracked observations | 0 / 1,055 |
| Decoded creates / migrations | 73 / 0 |
| Launches processed / retained candidates | 71 / 71 |
| Hot / background candidates | 25 / 36 |
| Global continuity resets | 148 |
| Global reset reasons: framing / explicit balanced truncation / transport | 127 / 19 / 2 |
| Token-local resets: stale / decode / queue / buffer | 55 / 0 / 0 / 0 |
| CURRENT / PARTIAL / UNAVAILABLE | **0 / 8 / 63** |
| Maximum observed CURRENT candidates | **0** |
| Sampled peak clean WSS coverage | 42.22 seconds |
| Sampled peak candidate clean coverage | 29.93 seconds |
| Final snapshot clean WSS coverage | 0.018 seconds |
| Maximum token coverage computed after report snapshots | 0.66 seconds |
| Buy / sell observations processed | 1,438 / 1,144 |
| Retained SOL-unit / unknown-unit observations | 1,839 / 743 |
| Stale processing rejections / other processing rejections | 55 / 0 |
| RPC requests / errors / 429 | 19 / 0 / 0 |
| Last RPC latency | 318.1 ms |
| Direct trade HTTP requests / extra HTTP for 101 snapshots | **0 / 0** |
| RSS peak / final | 114.7 / 114.7 MB |
| Process CPU mean / sampled peak / final | 23.77% / 98.4% / 98.4% |
| Sampled queue peak / final pending | 380 / 380 |
| Trade / critical overflow drops | 0 / 0 |
| Security attempts / completed | 2 / 2 |
| Paper cash / entries | $20 / 0 |
| Database size / short-run extrapolated growth | 18.54 MB / 270.99 MB per hour |

All decoder reason categories:

| Failure category | Count |
| --- | ---: |
| Truncated Borsh payload | 0 |
| Unsupported layout / trailing bytes | 0 |
| Invalid bool | 0 |
| Invalid string | 0 |
| Invalid pubkey | 0 |
| Invalid timestamp / value | 0 |
| Invocation framing | **127** |
| Invalid encoding | 0 |
| Malformed outer notification | 0 |
| Other | 0 |

Failing type was `notification` for all 127. TradeEvent, CreateEvent,
CompletePumpAmmMigrationEvent and unknown-event error buckets were zero.
Framing details: **121 unfinished invocation stacks, 3 depth mismatches,
3 unbalanced finishes**. All 127 included the literal `Log truncated` marker;
none were unmarked framing errors. Another 19 marker-bearing notifications had
balanced visible frames, and correctly caused global coverage loss without being
misclassified as Borsh decoder failures. Total marker-bearing successful
notifications: 146. No marker-bearing no-visible-event fast path occurred in
this run; its conservative behavior has deterministic regression coverage.

Prefix counters include logs whose enclosing frames later fail: they are not a
claim of committed-trade evidence. Accepted trades reconcile as 2,582 processed
+ 55 stale rejections + 380 pending = 3,017. The 380 pending observations were
not processed before the isolated probe stopped and are not claimed as evidence
or hidden inside the zero overflow-drop count. A burst drove the final queue/CPU
sample high. The run does not establish steady-state burst-drain behavior.

Opportunity actions: EARLY_OPPORTUNITY 0, DEVELOPING 43, PULLBACK_WATCH 2,
TOO_EXTENDED 0, AVOID 10, DATA_LIMITED 16. Companion WAIT 61, REJECT 10,
ENTRY_CANDIDATE 0, TOO_LATE 0. No sufficient live CURRENT flow/buyer/whale examples
exist to report; no profitability or validated trading-edge claim is made.

### What prevented CURRENT

All **71 candidates lacked the required clean continuity**. The stream repeatedly
reported explicitly truncated invocation logs. An omitted tail may contain an
additional tracked-mint trade, so it cannot safely be attributed to only the
visible untracked mint. Those 146 truncations and two disconnects must remain
global under the requested safety rules. Seeing balanced visible frames does
not establish that no records were omitted. No 180-second clean observation
window was demonstrated.

Other overlapping final blockers: 63 candidates had unavailable/inconsistent
units, 31 had fewer than three samples (21 had none), and 68 had stale/missing
flow. These counts overlap and must not be added. The token-local stale resets
remain conservative. The earlier probe also observed bounded-buffer losses;
none occurred in this final run.

The historical 157 errors still cannot be exactly reconstructed. The fresh
full-decoder diagnostic and both 240-second probes consistently identify
invocation/log truncation as the observed global coverage blocker, rather than
tracked TradeEvent tail failures. This patch fixes known-mint scoping and adds
truthful diagnostics; it does **not** validate real CURRENT trade availability.
No safety threshold, freshness window or provider configuration was relaxed to
produce a successful-looking result.

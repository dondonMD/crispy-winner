# Explicit Pump log-truncation recovery validation

Historical report for `22be0c8`. See [multi-hop recovery follow-up](multihop-recovery-validation.md)
for the subsequent identity-only mapping and 600-second verification.

Verified 2026-10-17, following `f8c5935d88151a3e32624a79450336bccd4112b6`.

The earlier 243.83-second Helius run had 146 explicit truncations plus two
transport gaps, producing 148 global resets and no CURRENT candidates. The new
path recovers affected identities from complete standard getTransaction compiled
instructions, not truncated transaction logs or requested trade amounts.

Implementation and canonical sources are documented in
[the provider reference](providers/onchain-discovery.md#targeted-truncation-recovery).
Pump IDL remains pinned to `639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22`;
CreateEvent/TradeEvent/migration schemas, units, 180-second continuity, 20-second
freshness, security/economics/history/lifecycle gates and numerical strategy,
Opportunity and Companion thresholds are unchanged.

Recovery bounds: 32 pending, one HTTP request in flight, three attempts at most,
45-second pending age checked between bounded requests, 10,000 signature dedup
identities. Pending recovery blocks overlapping CURRENT decisions without erasing
prior clean starts. Only untracked confirmation clears without a gap. Tracked
impact is local at observation time; unsupported/unavailable/failed/malformed
transactions and queue overflow remain global. A separate transport gap is never
erased. No general trade polling or outage backfill exists.

Queue capacity, processing selection/order and freshness remain unchanged. New
bounded instrumentation measures exact peak depth, source event/trade ages,
queue residence, events/trades becoming stale while queued, accepted/processed
rates and at most 300 depth samples.

Validation:

- Complete backend suite: 343 passed (final v1 validation; 91 new recovery/queue regressions).
- Complete frontend suite: 37 passed, including pending-recovery presentation.
- Ruff and mypy (27 application source files): passed.
- TypeScript and production Vite build: passed.
- Source/document secret scan and git diff --check: passed.
- Backend pinned lockfile and frontend dependency audits: no known vulnerabilities.
- No dependencies, RPC endpoint configuration, optional PumpPortal defaults,
  strategy thresholds, wallet functionality or transaction submission added.

Synthetic tests cover all nine canonical trade instruction layouts in outer/inner
and legacy/v0 loaded-address combinations and current v1 inline accounts; multi-mint impact; canonical event-CPI;
unsupported/malformed/failed/unavailable transactions; signature/slot identity;
missing CPI/lookup metadata; pending threshold crossings and timer preservation;
transport gaps during recovery; bounded backlog/expiry/retry/429 accounting;
zero ordinary-path recovery HTTP and queue stale-age accounting. Existing complete
suites continue to cover units, security, economics, historical evidence and
unchanged lifecycle/Opportunity/Companion rules.

## Initial version diagnostic

The first 301.46-second probe used maxSupportedTransactionVersion=0 and did not
meet acceptance: 10 RPC errors, zero ordinary monitoring requests, 140 unavailable
recoveries plus 31 overflow gaps, nine still pending and no CURRENT evidence.
Shared backoff correctly prevented request amplification but also prevented cached
curve quote verification. The preserved result is an ignored local artifact.
A bounded structural diagnostic on an explicit truncation returned JSON-RPC
-32015 (unsupported transaction version); a separate explicit-truncation diagnostic
with standard maxSupportedTransactionVersion=1 succeeded and returned version 1.
These two diagnostic HTTP requests are outside the measured final run.

The corrected implementation supports current standard v1 JSON compiled
instructions, inline account keys and strict transactionConfig fields, preserving
legacy and v0 loaded-address support. Unsupported future versions and malformed v1
metadata fail closed. No enhanced subscription, endpoint/configuration change or
additional dependency was involved. The final complete suite includes v1 outer/
inner instructions for all nine trade variants and malformed config regressions.

The final isolated Helius run is recorded below.


## Final Helius standard-WSS OBSERVE result

300.94 seconds, isolated temporary database, PUMPPORTAL_ENABLED=false and
trade_stream_enabled=false. No endpoint/configuration changes. This is the final
corrected-code run; earlier version diagnostics are not included in its counters.

**Acceptance NOT met: no real CURRENT candidate was observed.**

| Measurement | Result |
|---|---:|
| WSS messages / reconnects | 73,637 / 2 |
| Decoded creates / migrations; processed launches | 110 / 0; 107 |
| Explicit truncations / recovery RPC requests | 168 / 168 |
| Successful recovery RPC responses / errors / 429 | 168 / 0 / 0 |
| UNTRACKED_CONFIRMED / TRACKED_AFFECTED | 126 / 4 |
| UNSUPPORTED_PUMP_TRADE | 38 |
| Unavailable / failed / malformed recovery classifications | 0 / 0 / 0 |
| Pending final / peak / oldest final age | 0 / 20 / 0 sec |
| Duplicate recovery signatures / overflow | 0 / 0 |
| Global resets | 40: 38 unsupported recoveries + 2 transport gaps |
| Token-local resets | 46: 4 recovery impacts + 42 stale trades |
| Prefix-classified / untracked prefix-filtered | 10,481 / 7,952 |
| Tracked fully decoded / accepted / processed | 2,526 / 2,526 / 2,483 |
| Stale rejected / pending trade | 42 / 1 |
| Buys / sells processed | 1,228 / 1,255 |
| Verified SOL observations processed / unknown-unit processed | 1,206 / 1,277 |
| Verified-unit accepted / invalid-unit accepted | 1,240 / 1,286 |
| CURRENT / PARTIAL / UNAVAILABLE final | 0 / 22 / 85 |
| Peak CURRENT / candidates observed at >=180 clean sec | 0 / 0 |
| Maximum global / token clean coverage | 42.16 / 42.16 sec |
| Final global / maximum token clean coverage | 15.65 / 16.55 sec |
| Candidate count / hot subset / background subset | 107 / 25 / 58 |
| Ordinary monitoring / recovery / total Solana RPC | 19 / 168 / 187 |
| Total RPC errors / 429; pressure level | 0 / 0; 0 |
| Normal-path trade HTTP requests | 0 |
| RSS final / measured peak | 115.9 / 115.9 MB |
| Process CPU mean / sampled peak / final | 19.72% / 84.3% / 16.4% |
| Queue final / exact peak | 1 / 46 |
| Final oldest event/trade age / queue residence | 18.69 sec / 0.91 sec |
| Maximum sampled oldest trade source age | 23.52 sec |
| Events / trades becoming stale while queued | 0 / 0 |
| Accepted / processed trade rate | 8.39 / 8.25 per sec |
| Trade / critical / total overflow drops | 0 / 0 / 0 |
| Opportunity DEVELOPING / AVOID / DATA_LIMITED | 67 / 24 / 16 |
| Opportunity EARLY / PULLBACK / TOO_EXTENDED | 0 / 0 / 0 |
| Companion WAIT / REJECT / ENTRY / TOO_LATE | 89 / 18 / 0 / 0 |
| Paper cash | $20 |

Trade conservation: 2,526 accepted = 2,483 processed + 42 stale rejections + one
pending. No events became stale while queued in this run; stale rejection remained
conservative and token-local. Queue capacity and processing order were unchanged.
Source age includes pre-enqueue delivery/chain-timestamp age, not just queue delay.
Candidate monitoring subsets do not include every lifecycle state.

Bounded depth sample excerpts (seconds: depth):
0.1:0, 32.1:0, 63.8:7, 98.3:1, 130.9:0, 163.5:2, 197.3:1, 230.3:7,
265.9:0, 300.1:0. Exact insertion peak was 46; one-second sampled peaks can be lower.

Decoder diagnostics: 157 invocation-framing errors, all associated with explicit
truncations; tracked-tail and unknown-mint failures were zero. All other fixed
failure categories were zero. The 157 framing errors did not themselves reset
coverage globally: complete-transaction recovery established impact instead.

The dominant remaining blocker is **unsupported Pump instruction impact**: 38
recoveries conservatively reset every token, plus two genuine transport resets.
No candidate accumulated 180 clean seconds. Actual tracked truncations also
correctly produced four local gaps. Final overlapping blockers: all 107 lacked
continuity; 85 lacked valid consistent units, 98 lacked fresh trade observations,
61 had fewer than three samples (50 had no samples). None was blocked by pending
recovery at final capture. Queue loss was zero and stale-while-queued was zero.
A post-run bounded diagnostic made one successful getTransaction request for an
explicit truncation and identified canonical multi_hop_curve_swap plus a normal
inner one-account event-CPI. That instruction has no direct mint/base_mint account
in the pinned IDL and remains unsupported here. This sample does not prove that
all 38 unsupported recoveries had the same subtype; per-instruction subtype counts
were not collected in the main run. An earlier auxiliary diagnostic lost its WSS
connection to keepalive timeout without yielding a subtype. Auxiliary diagnostics
are excluded from the final measured-session RPC totals. No dynamic remaining-
account indexes were guessed, and no PumpSwap integration was started.
No CURRENT flow/buyer/whale examples qualify for publication; these fields remain
unavailable rather than zero. No profitable-edge claim or real trade was made.

Compared with the previous 243.83-second run: global resets fell from 148 to 40
but maximum clean coverage remained about 42 seconds, insufficient for acceptance.
Ordinary monitoring remained 19 requests (0.063/sec here, versus 0.078/sec before).
Recovery explicitly added 168 standard RPC requests. Normal trade decoding added
zero HTTP requests. These are different live traffic samples, not a controlled
CPU benchmark; mean process CPU was 19.72% versus the prior reported 23.77%, with
115.9 MB RSS versus 114.7 MB. Both are below the normal laptop memory target.
No security, economics, historical evidence or strategy gate was relaxed.

## Files changed

- Backend: `backend/app/truncation.py`, `backend/app/pump_instructions.json`,
  `backend/app/discovery.py`, `backend/app/providers.py`, `backend/app/engine.py`,
  `backend/app/domain.py`.
- Tests: `backend/tests/test_truncation_recovery.py`,
  `backend/tests/test_trade_gap_scoping.py`,
  `frontend/src/components/Companion.test.tsx`.
- Visibility/probe: `frontend/src/App.tsx`, `frontend/src/types.ts`,
  `frontend/src/components/Companion.tsx`, `scripts/smoke_observe.py`.
- Documentation: `README.md`, `docs/providers/onchain-discovery.md`,
  `docs/operating-guide.md`, `docs/limitations.md`,
  `docs/opportunity-intelligence.md`, `docs/truncation-recovery-validation.md`.

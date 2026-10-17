# Standard Solana Pump trade evidence validation

Official IDL pinned to `639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22`, inspected
2026-10-17. All vendored definitions were compared to the official file;
existing CreateEvent and migration definitions remain identical.
See [schema, exact fields, units and continuity](providers/onchain-discovery.md).

## Initial fail-closed probe

A 240.5-second public-mainnet OBSERVE run used PumpPortal disabled and
`trade_stream_enabled=false`: 14,697 WSS messages, 30 creates, no migrations,
2,914 TradeEvents decoded, 509 tracked trades accepted, 2,405 untracked ignored,
zero duplicates, zero decode errors. All 509 accepted trades initially had unknown
units, so no current evidence was claimed. This prompted the independently
verified cached-curve path for legacy SOL; no polling was added.

The initial run processed 188 buys / 124 sells; remaining accepted observations
were subject to existing freshness/ordering/admission processing. It ended with
24 active/hot candidates, no background candidates, CURRENT/PARTIAL/UNAVAILABLE
counts 0/0/24. There were four reconnects and 17.3 seconds of clean coverage.
Twelve HTTP RPC requests, two 429/errors, final pressure level 2; zero requests
came from trade decoding, and 101 dashboard snapshots also caused zero requests.
RSS peak/final 105.9 MB; final CPU sample 3.9%; sampled queue peak/final 11/0;
critical/trade drops 0/0. Security attempts 2, completed 0. Opportunity counts:
EARLY_OPPORTUNITY 1, DEVELOPING 20, DATA_LIMITED 3; all others zero. Companion:
WAIT 24, ENTRY_CANDIDATE/REJECT/TOO_LATE zero. Paper cash $20.

This probe is evidence of decoding, filtering, bounds and conservative unit
handling, not proof of current flow. No flow-ratio or independent-buyer range is
reported from invalid-unit samples.

## Comparison limits

The accepted 30-minute monitoring baseline had 118 active candidates, approximately
146 MB RSS, 49 RPC requests, 8 RPC 429/errors, 20 WSS reconnects, 215,976 WSS messages,
353 creates and 8 migrations. The short probe has a different duration, candidate
population and traffic rate, so total requests, memory and CPU are not controlled
paired measurements. The architectural/testable HTTP delta attributable directly
to TradeEvent decoding is exactly zero; the existing lifecycle/security scheduler
still makes its own requests. No profitability or validated edge is claimed.


A second 240.31-second diagnostic probe decoded 2,620 trades, accepted 51 tracked
observations, and again kept all units unknown. Fifteen queued observations were
rejected by the existing 20-second freshness limit; 28 buys / 8 sells processed.
It used 10 HTTP requests (2 errors/429s), no trade HTTP calls, four reconnects,
1.64 seconds final clean coverage, 102.8 MB RSS, 6.38% mean process CPU, 49.8%
sampled peak CPU, queue peak/final 3/0 and no drops. Eighteen active candidates
had unavailable flow; Companion WAIT 17 / REJECT 1 / entries zero; paper cash $20.

A bounded wallet-free quote diagnostic then showed both default quote keys with
populated `quote_amount` and non-SOL quote mints with `sol_amount=0`. The decoder
was corrected to use populated canonical quote amounts for default-key events
ONLY after cached canonical curve data independently establishes native SOL.
This diagnostic confirms that current markets cannot all be treated as SOL.

## Validation

- Complete backend suite: 201 passed, 105.55 seconds.
- Focused decoder/continuity/queue/Companion/Opportunity/economics suite: 118 passed.
- Complete frontend suite: 36 passed across four files.
- Ruff (`backend scripts`), mypy (`backend/app`, the CI scope), TypeScript
  (`tsc --noEmit`), production Vite build, basic source/document secret scan,
  and `git diff --check` passed.
- Python locked dependency audit: no known vulnerabilities. npm audit: zero
  vulnerabilities. No dependencies were added or changed.
- Exact official schema comparison passed; existing CreateEvent/migration schemas
  preserved. No Opportunity/Companion/lifecycle configuration thresholds, RPC
  scheduler/cadence settings, security scans or DEMO fixtures were changed.
- Deterministic tests cover buys/sells, wallet/mint, units including USDC and
  verified default-key SOL, unknown/conflicting quotes, malformed/truncated/failed
  frames, untracked filtering, multi-event identity/replay, outage/rebuild,
  immediate gap invalidation, queue drops, creator sells, buyer breadth, flow ratio,
  whale share, unavailable display values and direct HTTP delta zero.

## Changed files

- `backend/app/pump_events.json`, `backend/app/discovery.py`: canonical schema,
  bounded decoding/filtering, quote normalization, dedup and transport continuity.
- `backend/app/domain.py`, `backend/app/engine.py`, `backend/app/features.py`:
  bounded loss accounting, cached verified quote identity, pipeline integration,
  evidence coverage/status, metrics and missing-unit handling.
- `backend/app/economics.py`, `backend/app/companion.py`,
  `backend/app/opportunity.py`: current continuity/structure requirements;
  numerical thresholds and economic/lifecycle/security/historical gates preserved.
- `frontend/src/App.tsx`, `frontend/src/components/DiscoveryHealth.tsx`,
  `frontend/src/types.ts`: health counts, coverage, reconnects and separate losses.
- `backend/tests/test_onchain_trades.py`, `scripts/smoke_observe.py`: deterministic
  synthetic wire tests and isolated aggregate real OBSERVE measurement.
- `README.md`, `docs/providers/onchain-discovery.md`, `docs/opportunity-intelligence.md`,
  `docs/operating-guide.md`, `docs/limitations.md`, `docs/pump-trade-validation.md`:
  schema provenance, operation, evidence terminology, limits and measured results.

## Final corrected live OBSERVE result

240.30 seconds, public mainnet standard Solana WSS only,
`PUMPPORTAL_ENABLED=false`, `trade_stream_enabled=false`, one program-log
subscription, no per-token subscriptions or HTTP trade polling.

| Metric | Measured result |
| --- | ---: |
| WSS messages | 30,345 |
| Creates / migrations decoded | 37 / 2 |
| TradeEvents decoded | 3,871 |
| Tracked trades accepted into queue | 424 |
| Untracked trades ignored | 3,447 |
| Duplicate trades / decode errors | 0 / 0 |
| Invalid-unit tracked observations | 125 |
| Verified-unit tracked observations | 299 |
| Buy / sell observations processed | 103 / 66 |
| Retained processed SOL-unit / unknown-unit observations | 81 / 88 |
| Stale trade processing rejections / other rejections | 253 / 0 |
| Trades pending at final snapshot/shutdown | 2 |
| WSS reconnects / final clean coverage | 2 / 83.46 seconds |
| Launches processed / scanner candidates retained | 18 / 19 |
| Hot / background / retained rejected candidates | 17 / 0 / 2 |
| CURRENT / PARTIAL / UNAVAILABLE trade candidates | 0 / 2 / 17 |
| HTTP RPC requests / 429 / errors | 8 / 1 / 1 |
| HTTP requests directly caused by TradeEvent decoding | **0** |
| Extra HTTP requests for 101 snapshots | 0 |
| Curve accounts checked / curve HTTP requests | 43 / 5 |
| Security attempts / completed | 1 / 0 |
| RPC pressure at end | level 1 BACKING OFF |
| RSS peak / final | 105.1 / 105.1 MB |
| Average process CPU / sampled peak / final CPU | 9.43% / 50.7% / 11.4% |
| Sampled queue peak / final | 5 / 2 |
| Critical queue drops / trade queue drops | 0 / 0 |
| Paper cash / entries | $20 / 0 |
| Database size / short-run extrapolated growth | 5.48 MB / 79.33 MB per hour |

Accepted trades reconcile exactly: 169 processed + 253 stale rejections + 2 still
queued = 424. The two queued observations were not claimed as processed; this
isolated probe stops with them pending. Stale rejections reset token continuity,
so they cannot silently count as a complete zero-trade interval. Known-unit
acceptance does not mean CURRENT evidence. The retained unit counts above are
bounded stored observations, not complete 180-second window statistics.

Opportunity actions: EARLY_OPPORTUNITY 0, DEVELOPING 16, PULLBACK_WATCH 0,
TOO_EXTENDED 0, AVOID 2, DATA_LIMITED 1. The initial probe had one
EARLY_OPPORTUNITY with trade evidence unavailable, confirming that real trade
availability is not forced into that action. Companion: WAIT 17, REJECT 2,
ENTRY_CANDIDATE 0, TOO_LATE 0. Security remained conservative and unverified.

There were no CURRENT windows, so no independent-buyer, flow-ratio or whale-share
ranges are presented as sufficient live evidence. Buy/sell, breadth, creator sell,
flow and whale semantics are verified deterministically from normalized canonical
wire examples; restoration of CURRENT after a clean window is deterministic-test
coverage, not a claim that the public endpoint achieved it in this run.

Relative to the accepted baseline (146 MB at 118 candidates), this run stayed below
500 MB with 19 retained candidates. It does not measure memory at baseline scale.
HTTP rate was 0.0333 requests/second versus baseline 0.0272; differing candidate
arrival, scan opportunities and run lengths prevent attributing this small total
rate difference to trade decoding. Direct trade HTTP delta is zero by both code
path and instrumented deterministic/live checks. Baseline CPU was not supplied;
the measured CPU values above do not establish a controlled CPU delta. Sampled
queue measurements can miss shorter bursts; no overflow was observed. Database
growth is a short-run extrapolation, subject to the existing retention/storage
guards, not a full-day measurement.

Remaining limits: provider omissions cannot be proven absent; no outage backfill;
public WSS reconnects and delayed confirmed logs can keep evidence partial or
unavailable indefinitely; unsupported quote assets/decimals and event layouts fail
closed; no PumpSwap trade decoding after migration; no completed security scan in
this run; no live CURRENT-flow demonstration or validated trading edge.

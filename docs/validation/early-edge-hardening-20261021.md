# Pre-cohort red team — 2026-10-21

**No real cohort, commit or push. Not ready to enroll while acquisition is blocked.**

Branch `research/prospective-early-entry-edge`; HEAD remains `2bebbf2863de21041fffca80fb99507356a815b6`. Only the isolated, previously uncommitted research files changed. Production strategy/security/economics/acquisition/decoders and the retired strict cohort/database were not modified.

## Methodology changes

See [the full hardened protocol](../early-entry-edge.md). Primary is USD 4 / minimum 10 seconds / 300 seconds from signal. Acquisition allowance is another 10 seconds, with the stricter request-start boundary. The 0.5/2/5-second variants consume the same captured stream and remain exploratory.

Controls are selected from exact-T candidates with the same readiness floor, exact quote/progress-band/age-band/security matching, then nearest progress/age/lexical tie breaks. Control mints are not reused within a session. Pairs and original roles are immutable across later crossover. Unmatched treatments remain counted and block strongest status.

Enrollment closes at first 100 unique treatment mint/session samples or 30 UTC days, earlier. Interim reporting is operational only. Closure and primary terminal accounting precede any statistical conclusion. Mint-level bootstrap preserves all sessions; pair comparisons merge mint clusters connected by immutable pair edges, retaining crossover dependence. No supporting comparison CI exists with fewer than two independent components.

Rent is recoverable capital, excluded from primary PnL and shown separately. The manual model reserves 1% per leg, network/priority costs for entry/sell/separate account close, and a failed-transaction reserve. Embedded SDK fees/impact are not charged twice. The zero-platform-fee direct-interface scenario remains an assumption requiring review. Full rent-non-recovery and protocol-only sensitivities are descriptive.

Automatic economic-zero classification is disabled. Unavailable outcomes remain in the denominator and block strongest status; candidate canonical proof requirements are documented, not guessed or implemented.

## Quote instrument

One confirmed getMultipleAccounts context supplies all pricing accounts; its slot cannot regress behind identity discovery or prior accepted context. Batch span <=5 seconds. Receipts include timing/boundary, identity/address list, contexts, state hashes, SDK pins, units, amounts, fee decomposition and USD references. Diagnostic-only pool receipts cannot enter outcomes.

Official SDK versions remain Pump 4.1.0 and PumpSwap 2.1.0. Exact source/compiled hashes and tarball integrity are in `backend/app/early_edge_sources.json`. Bundle SHA256:

`2b0c24a4842d301d9448270c1ce4697f5376bcd274b9e3d084a5661b46fd2fdb`.

The independent reference child receives no private environment/credentials and has a 15-second deadline. JSON integers are decimal strings, avoiding double-precision truncation. No wallet, instruction construction, signing or sending occurs.

## Concrete findings

1. Coinbase Exchange SOL-USD worked; USDC-USD returned HTTP 404 with `NotFound`. Before collection, the new research reference client was corrected to Kraken's documented public USDCUSD latest-trade endpoint, count=1. Publication/acquisition freshness remains <=20 seconds, cache/attempt interval 10 seconds, no peg assumption or fallback. A direct probe returned fresh valid references for both assets. This public FX observation never feeds Pump trade features.
2. Production pre-grad trade acquisition is currently failing closed. The final smoke saw **1,840 Pump TradeEvent unsupported-layout failures and zero accepted tracked trades**. All 113 tracked candidates lacked usable trade units. No decoder or threshold was changed. Exact byte-level cause is not established by these counters and needs separate acquisition review.
3. Temporary official-SDK reference dependencies have **16 advisories: 8 high, 8 moderate**. The project backend/frontend audits are clean. No SDK downgrade/force-fix was applied. The reference installation is outside project dependencies, executes quote helpers only, receives normalized bounded state and no credentials, and is time-bounded. These controls do not make the audit finding disappear; upstream/transitive exposure still needs review. Preserved audit: `data/early_edge/official-sdk-reference-audit-20261020.json`.
4. A later bounded recheck of older Pump mints correctly became unavailable as those states changed. Its source-bound preflight was BLOCKED rather than inventing quotes. Dynamic preflight must be repeated on current supported states before any later creation. USD preflight can also expire when a reference trade becomes stale; no freshness tolerance is extended.

## Final normal non-enrolling smoke

Preserved JSON: `data/early_edge/hardened-current-source-smoke-20261021.json`.

| Metric | Result |
| --- | --- |
| Runtime | 186.37 seconds; smoke only, not six hours |
| Launches accepted | 113; approximately 2,183/hour within this short window |
| Adequately observed eligible / qualifying EARLY | 0 / 0 |
| Potential controls / unmatched rate | Not estimable; no qualifying treatment |
| Quote attempts / successes | 16 / 12; 75% |
| Pump SDK comparisons | 6 exact, two mints, buy and sell |
| PumpSwap SDK comparisons | 6 exact, two independently verified pools, sell exits |
| Unavailable quotes | 4, retained in diagnostic denominator |
| Unexplained SDK parity mismatches | 0 |
| Usable USD quote observations | 12; no missing USD reference for those comparisons |
| Public USD reference requests / errors / 429 | 35 / 0 / 0 |
| Total Solana RPC HTTP requests / errors / 429 | 279 / 0 / 0 |
| Pump WSS messages / reconnects | 66,204 / 0 |
| Tracked Pump trades / unsupported TradeEvent layouts | 0 / 1,840 |
| Queue peak / oldest event / oldest trade at snapshot | 28 / 8.25s / 0s |
| Stale while queued | 0 |
| Peak RSS | 126.21 MB |
| Mean / peak Python-process CPU | 41.49% / 102.1%; SDK child CPU excluded |
| Resource/candidate-capacity pressure samples | 0 / 0 |
| Recovery overflow | 42; existing fail-closed limitation, scheduler unchanged |
| Real cohort / prospective treatment-control outcomes | None / 0 |

The bank/account-state comparisons prove local-port agreement with official SDK calculations at the captured states, not transaction inclusion or deployed-binary execution parity. They do not validate actual manual fills or alter strict PumpSwap event decoding.

A six-hour command is supplied in the protocol but was not run: known acquisition failures make a longer signal-yield estimate uninformative until reviewed. No N=100 completion-time estimate can be inferred from zero qualifying signals. Quote sampling is periodic and bounded, not a saturated 64-signal deadline-load test. Reference freshness, supported state coverage, residual monitoring differences and manual-interface costs still need longer operational assessment.

## Proposed manifest and synthetic smoke

Non-collectable proposal: `data/early_edge/manual-frozen-proposal-20261021.json`, ID `DRAFT-20261021-1403ede43c91`. Source hash:

`2b86fdd3cefcee8f253c66f4864e48c80bfcaa7ea692cbf3676b7322ccb8b931`.

It freezes 4/10/300, target 100, maximum 30 days, crowd 85, buyer marker at existing min_buyers=20, risk-set/readiness rules, costs, missingness, no backfill/stopping changes and bootstrap seed 20261020 with 10,000 resamples. `collectable=false`. No real creation command was executed.

Offline smoke: `data/early_edge/manual-final-offline-smoke-20261021.json`. Zero network requests/engine/live cohort; historical enrollment refused, pre-boundary requests rejected, restart data persisted, unfinished outcomes explicitly unavailable, report deterministic and INTERIM_OPERATIONAL_ONLY. One synthetic treatment/control pair remains fully accounted without pretending unavailable outcomes are zero.

## Validation

- Complete backend: **674 passed**, final unrestricted run 97.08 seconds, including **139 research tests** and 48 SDK golden vectors.
- Complete frontend: **39 passed**, five files. Existing duplicate React-key fixture warning remains.
- Ruff: passed. mypy: passed, 43 source files. TypeScript and production build: passed.
- Secret scan: passed. Backend/frontend dependency audits: no known vulnerabilities / zero vulnerabilities.
- Temporary SDK-reference audit: **not clean**, 16 findings as described above.
- Tracked diff and new-file whitespace checks: passed.

The restricted sandbox stalled the existing DEMO API test's asyncio-runner teardown after its assertion passed. It was interrupted, reproduced in isolation, and passed immediately outside the sandbox (1.27s). The complete suite then passed outside the sandbox. No production teardown code was changed.

Remaining weaknesses: acquisition must be fixed separately; reference dependency findings need review; fresh preflight/long-run USD availability is not guaranteed by a short probe; hypothetical trades do not change the realized future state stream; SDK agreement does not establish deployed execution behavior; exact-T matching/readiness does not eliminate selection or market correlation; mint-connected pairing can reduce effective sample size; no actual manual interface/fill study has occurred. None is resolved by changing strategy gates or declaring an edge.

## File inventory

All 18 files are new/uncommitted relative to the production base:

- `backend/app/early_edge.py`
- `backend/app/early_edge_design.py`
- `backend/app/early_edge_parity.py`
- `backend/app/early_edge_quotes.py`
- `backend/app/early_edge_report.py`
- `backend/app/early_edge_runtime.py`
- `backend/app/early_edge_sources.json`
- `backend/tests/fixtures/early_edge/sdk_quotes.json`
- `backend/tests/test_early_edge.py`
- `scripts/early_edge_cohort.py`
- `scripts/early_edge_diagnostic.py`
- `scripts/early_edge_golden.cjs`
- `scripts/early_edge_report.py`
- `scripts/early_edge_sdk_compare.cjs`
- `scripts/early_edge_smoke.py`
- `docs/early-entry-edge.md`
- `docs/validation/early-edge-review-20261020.md` (historical first draft)
- `docs/validation/early-edge-hardening-20261021.md`

# PumpSwap standard-PubSub filter investigation — 2026-10-20

Production remains frozen at `2bebbf2863de21041fffca80fb99507356a815b6`.
No acquisition fix was adopted, committed or pushed. The censored prospective
cohort was not opened or appended to; no new cohort was created.

## Finding

The historical ACK-with-zero-notifications failure was **not reproduced on two
freshly verified active-pool candidates**. Both pool and mint mentions delivered
notifications. Switching production subscriptions to mint mentions is therefore
not justified by this investigation.

An observed pool-filter notification was corroborated with getTransaction for
two v0 transactions whose pool was ALT-loaded writable and base mint ALT-loaded
readonly. Thus a blanket claim that this provider's standard mentions filters
exclude ALT-loaded pool addresses is contradicted by this bounded sample.
Legacy and v1 examples had both addresses static. These are **pool-mention
transaction samples**, not successfully decoded target-trade samples.

A separate reproducible blocker appeared after delivery: production parsing
rejected supported-discriminator payloads as `unsupported_layout`. No decoder
was relaxed or changed. The currently published official IDL and pinned IDL
have the same 40 BuyEvent / 33 SellEvent fields. The deployed payload discrepancy
requires separate canonical-layout investigation; its exact explanation is
not established here. No actual volumes, wallets or CURRENT evidence are inferred.

## Live comparisons

Every pool passed fresh production `parse_pool` ownership/discriminator/layout,
expected base mint, nondefault keys and quote relationship checks. All verified
quotes were WSOL. Each run used one standard WSS connection, separate request
IDs and returned subscription IDs, commitment `confirmed`.

| Run | Pool notifications | Mint notifications | Program notifications | Accepted target Buy / Sell | RPC requests |
| --- | ---: | ---: | ---: | --- | ---: |
| Original 9YUj, 120s + bounded fallback | 0 | 0 | 1000 | 0 / 0 per filter | 1 |
| HNB2… / 687h…, 120s + fallback | 2370 | 2376 | 1000 | 0 / 0 per filter | 1 |
| AscP… / EKos…, 120s + fallback | 88 | 88 | 1000 | 0 / 0 per filter | 1 |
| AscP…, 60s intermediate sample probe | 44 | 44 | not requested | 0 / 0 per filter | 4 |
| HNB2…, final 60s | 487 | 491 | not requested | 0 / 0 per filter | 4 |
| AscP…, final 60s | 43 | 43 | not requested | 0 / 0 per filter | 4 |

All six runs had one connection, zero reconnects and zero transport errors.
Each requested filter ACKed exactly once: 15 ACKs total. Optional program
fallbacks stopped at their 1000-message cap (before the configured 15-second
limit). Early runs aggregate pool/mint counts through that fallback window;
final reports also expose the comparison-window snapshot separately.

The intermediate sample report classified its three samples unavailable/malformed
because the diagnostic initially rejected the System Program's default-valued
key. That diagnostic-only check was corrected and regression-tested; final
reports supersede its address classification. No production parser changed.

Final HNB2… samples: one v1 static/static; two v0 ALT-writable/ALT-readonly.
Final AscP… samples: three legacy static/static. The final pool filters had
33 and 43 `unsupported_layout` failures respectively (same counts for their
mint filters). HNB2… also had one explicit truncation per filter. Payload-shape
counters, explicitly **unvalidated discriminator observations**, recorded
BuyEvent lengths 497–515 and 512 bytes, SellEvent lengths 449 bytes. These
counters are not valid trade samples or executed-economics evidence.

The original pool's fresh public DEX snapshot reported zero m5/h1 transactions.
That is consistent with inactivity but cannot prove it. Its new-window result
is `INCONCLUSIVE_NO_CONFIRMED_TARGET_ACTIVITY`; historical rolling counts were
not used as proof. The active-pool probes establish delivery but not accepted
canonical target events, so their event-activity classification remains
inconclusive. No provider limitation or complete acquisition fix is claimed.

## Isolation and bounds

`scripts/diagnose_pumpswap_filters.py` imports production pool verification and
`PumpSwapFlow.parse_logs`, and constructs only a SolanaProvider plus diagnostic
counters. It never constructs RadarEngine, a database, research, a cohort or a
paper account; it never emits MarketEvents into scoring. There is no trading.

Bounds: 1–600 second main window; optional program fallback 0–15 seconds and
1000 messages; 20,000 total notifications; WSS max message 256 KiB / queue 16;
4096 identities per dedup cache; three redacted examples per filter; eight ACK
identities per filter; three transaction sample requests plus one pool
verification per run. Production RPC limiter/backoff remains authoritative.
No raw transactions or wallets are retained. Signatures are hashed in reports.
Normal-path production trade HTTP delta is zero.

The six probes used **15 diagnostic Solana RPC requests** total, including all
verification and sample attempts. Two separate public DEX requests supplied
selection hints only. Official-source documentation downloads are not trade
requests. Program-wide subscription was diagnostic-only and was not adopted.

## Commands and preserved evidence

```sh
.venv/bin/python scripts/diagnose_pumpswap_filters.py \
  --pool <pool> --base-mint <expected-mint> --seconds 120 \
  --program-seconds 15 --output data/observe/<unique-report>.json
```

`--program-seconds` defaults to zero and is used only after the main window
produces no decoded target events. Reports never overwrite existing files.
All six redacted JSON reports are under `data/observe/pumpswap-filters-20261020-*`;
the timestamped consolidated `pumpswap-filter-investigation-*.json` contains
complete copies and request accounting. Reports are local artifacts, ignored
by git.

## Validation

Deterministic tests cover independent ACKs, production Buy/Sell parsing,
target/foreign/mixed events with original ordinals, same-subscription replay
and cross-filter dedup, reconnect/re-ACK, strict unknown-unit behavior,
truncation/malformed payloads, bounded memory and duration, legacy/v0/v1 key
placement, verified-pool requirement, secret-safe reporting, and engine/database
construction traps. A pre-existing future-timestamp test now computes its
future timestamp at test execution rather than collection; production freshness
is unchanged.

Final validation: **550 backend tests passed; 39 frontend tests passed**.
Ruff passed; mypy passed across 34 files (including the new diagnostic);
TypeScript and production build passed; secret scan passed across 155 files;
backend and frontend dependency audits found no known vulnerabilities.
`git diff --check` and whitespace checks on all new files passed.
The final targeted diagnostic suite contains 15 deterministic tests.

## Sources and remaining questions

[Official logsSubscribe contract](https://solana.com/docs/rpc/websocket/logssubscribe)
requires one mentioned address and returns an independent subscription ID.
[Official transaction JSON structures](https://solana.com/docs/rpc/json-structures)
distinguish message account keys from loaded addresses.
[Agave log collection](https://github.com/anza-xyz/agave/blob/master/runtime/src/bank.rs)
iterates `transaction.account_keys()` for mentions matching; that source alone
was not treated as proof of this provider's deployment.
[Official pinned PumpSwap IDL](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/idl/pump_amm.json)
remains the canonical schema baseline.

The historical delivery failure remains unexplained: these new windows cannot
recover its past delivery behavior. The live unsupported-layout discrepancy is
reproducible and should be resolved canonically before claiming restored
acquisition. Neither mint-filter replacement nor program-wide production flow
is supported by the evidence gathered here. Strategy/security/economics,
continuity/freshness, recovery scheduling and prospective statistics are untouched.

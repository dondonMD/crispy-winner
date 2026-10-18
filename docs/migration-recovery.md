# Truncation-only canonical migration recovery

The code-level lifecycle gap was confirmed: `transaction_impact()` recognised
`migrate` and `migrate_v2` from the pinned schema but discarded their identities.
It returned trade-impact classification only. A migration event hidden by
explicit `Log truncated` could therefore be absent from lifecycle processing.
This mechanism does not establish the cause of every missing migration in past
runs; live instruction counters provide that evidence prospectively.

## Canonical proof and bounds

The existing `pump_instructions.json` account-name lists and discriminators were
verified against the official
[Pump IDL at 639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/idl/pump.json).
Both migration instructions take no arguments. Recovery requires their exact
8-byte discriminator, complete named account layout, canonical Pump program,
nondefault mint/pool/quote keys, canonical PumpSwap program and correct Pump
bonding-curve PDA. Legacy `wsol_mint` must equal WSOL; v2 uses `quote_mint`.
The existing strict legacy/v0/v1 key resolution and transaction signature/slot/
success validation remain. No transaction logs are reparsed.

A successful transaction does not prove that an inner CPI whose error might
have been caught succeeded. Inner migration instructions are recognised and
counted, but cannot emit lifecycle evidence without execution-success proof.
They increment a separate bounded `recovered_migration_unproven_cpi` counter.
Top-level canonical migration instructions in successful transactions provide
lifecycle identity evidence. Independent on-chain pool verification remains
mandatory before PumpSwap subscription eligibility; recovered instruction
identity never grants trust to pool liquidity, economics or security.

Recovery stages identities until the complete transaction structure validates.
An unsupported trade can still require a global trade gap while a separately
proved migration supplies lifecycle evidence. Malformed transactions emit none.
Only currently tracked mints can emit; untracked identities are counted and
ignored. No extra candidate admission or arbitrary transaction polling is added.

## Time, lifecycle and identity

A valid `getTransaction.blockTime` is preferred. When absent, the confirmed
truncation notification's observation time is a conservative upper bound,
explicitly labelled as such. It is not presented as exact chain time. Invalid
provided block times fail closed instead of silently falling back. Recovery
retains the existing bounded pending lifetime/retries and the engine's existing
20-second event freshness check. Delayed recovery can consequently be observed
but rejected as stale; freshness is not relaxed. Post-grad coverage still starts
after processing and subscription ACK, never from backdated chain time.

Recovered MarketEvents carry mint, pool, quote mint, signature, slot, instruction
name/ordinal, official schema provenance and VERIFIED identity quality. They use
the existing engine migration processor, which records graduation and starts
the PumpSwap epoch. There is no migration-state implementation in recovery.
Visible decoding is unchanged. Both paths use `signature:migration:mint`;
distinct migrated mints in one signature remain distinct. Repeated successful
calls for the same mint cannot represent a second legitimate migration of its
same bonding curve. Submission and processing identities are bounded to 10,000.
Queue losses remain visible in the existing critical-drop metrics.

## Diagnostics

Fixed counters distinguish migrate/migrate_v2, tracked/untracked identities,
emitted/duplicate/invalid-layout/invalid-time/unproven-CPI observations and queue
rejection. A fixed-cardinality histogram, one bucket per pinned Pump instruction
name, counts structurally validated successful truncation-recovery transactions.
This retains aggregate counts only, never raw transactions or wallet lists.
Visible `CompletePumpAmmMigrationEvent` counts remain separate in discovery
health. No normal-path trade HTTP calls, PumpSwap decoder changes, acquisition
provider changes or strategy threshold changes are introduced.

Fresh verified recovered migration identity may arrive after a newer curve or
security observation because getTransaction is asynchronous. It is accepted
without rewinding `last_event`; the original 20-second age gate still runs first.
A regression tests both a two-second-old observation being accepted and a
21-second-old observation being rejected. Visible migration decoding and the
normal visible arrival-order path are unchanged.

## 300-second live diagnostic

The requested short test ran 303.17 seconds using the existing Helius endpoints,
PumpPortal disabled, with no arbitrary transaction queries or extra trade HTTP.

| Counter | Result |
| --- | ---: |
| Pump messages / decoded creates / admitted launches | 80,223 / 143 / 140 |
| Visible CompletePumpAmmMigrationEvents | 0 |
| Explicit log truncation notifications | 323 |
| recovered_migrate_instruction | 0 |
| recovered_migrate_v2_instruction | 1 |
| recovered_migration_tracked_mint | 1 |
| recovered_migration_untracked_mint | 0 |
| recovered_migration_emitted | 1 |
| recovered_migration_duplicate / invalid_layout | 0 / 0 |
| Invalid time / unproven inner CPI / queue rejection | 0 / 0 / 0 |
| Migration observations processed / rejected | 1 / 0 |
| Final GRADUATED / POST_GRAD_OBSERVATION / ENTRY_CANDIDATE | 0 / 0 / 0 |
| PumpSwap eligible verified / subscribed pools / ACKs | 0 / 0 / 0 |
| PumpSwap messages / BuyEvents / SellEvents / accepted trades | 0 / 0 / 0 / 0 |
| Post-grad CURRENT / PARTIAL / UNAVAILABLE | 0 / 0 / 1 |
| Recovery RPC requests / successful results | 210 / 209 |
| Monitoring RPC / total RPC | 29 / 239 |
| RPC errors / 429 | 0 / 0 |
| Normal-path Pump + PumpSwap trade HTTP delta | 0 |
| Pump / PumpSwap reconnects | 0 / 0 |
| Final / peak queue | 367 / 459 |
| Stale while queued / final oldest trade seconds | 44 / 67.52 |
| Trade / critical overflow drops | 0 / 0 |
| Peak RSS MB | 148.5 |
| Mean / peak CPU process percent | 65.4 / 104.6 |
| Security attempts / completed scans | 3 / 3 |
| Paper cash USD | 20 |

**Root cause confirmed in code and reproduced live:** a successful tracked
canonical migrate_v2 was recovered from an explicitly truncated transaction,
while the visible migration-event count remained zero. The new observation was
emitted and processed, and POST_GRAD_OBSERVATION appeared in the run's observed
states. The old identity-only recovery had no path to emit this lifecycle event.
This establishes one missed-event mechanism, not the complete retrospective
cause of all missing migrations in earlier runs.

At the final snapshot the migrated candidate was no longer in the subscription-
eligible lifecycle states. No independently verified eligible pool formed during
the diagnostic. The aggregate probe did not retain that candidate's final
rejection/expiry reason, so none is inferred here. Post-grad flow remained
UNAVAILABLE. No real PumpSwap flow or CURRENT window is claimed, and no gates
were bypassed to obtain a subscription.

The recovery histogram covers 209 structurally validated successful transactions
already fetched for explicit truncations. Nonzero canonical Pump instruction
buckets were: buy 6; buy_exact_quote_in_v2 18; buy_exact_quote_in_v3 12;
buy_exact_sol_in 5; buy_v2 14; buy_v3 22; close_user_volume_accumulator 20;
collect_creator_fee_v2 1; create_v2 20; distribute_creator_fees 1;
extend_account 3; init_user_volume_accumulator 17;
migrate_bonding_curve_creator 1; migrate_v2 1; multi_hop_curve_swap 27;
sell 1; sell_v2 28; sell_v3 6; sweep_creator_fee 1. All remaining pinned-name
buckets were zero. `migrate_bonding_curve_creator` is not classified as liquidity
migration. The two migration discriminators match the official pin exactly:
migrate `[155,234,231,146,236,158,162,30]`, migrate_v2
`[187,203,18,31,206,237,254,41]`. No extra histogram-sampling HTTP calls occurred.

The final arrival-order guard was added after this diagnostic and verified with
fresh/stale deterministic regressions; it does not alter instruction recovery,
HTTP behavior, pool verification, PumpSwap trade flow or strategy thresholds.
No further endurance run was performed. Prospective strategy evidence and an
actual post-grad CURRENT observation remain separate future validation work.

## Release validation

457 backend tests and 39 frontend tests pass. The backend suite includes 23 new
migration-recovery cases and all existing trade, multi-hop, PumpSwap, strategy,
Opportunity, Companion, security, lifecycle and economics tests. Ruff, mypy
(29 modules), TypeScript/production frontend build, source/document secret scan,
backend/frontend dependency audits and `git diff --check` pass. No dependency,
strategy threshold, 180-second continuity or 20-second freshness setting changed.
The seven changed files are `backend/app/truncation.py`, `backend/app/engine.py`,
`backend/tests/test_migration_recovery.py`, `scripts/smoke_observe.py`, this report,
`docs/providers/onchain-discovery.md` and `docs/limitations.md`.

# Recovered migration: lifecycle time versus acquisition freshness

The preserved 1,805.27-second run recovered and emitted three tracked canonical
migrations, but the engine rejected all three as stale. `event.ts` correctly
retained chain/block time; the generic 20-second event-age gate incorrectly used
that immutable occurrence time as the age of newly acquired recovery evidence.
The canonical identity-recovery mechanism remains accepted and unchanged.

## Two times, one narrow exception

`event.ts` remains the actual lifecycle timestamp, using getTransaction blockTime
or the existing labelled confirmed-notification observation upper bound when
blockTime is absent. `truncation_observed_at` remains the notification receipt
time. `recovery_verified_at` is captured only after successful transaction,
canonical instruction/layout/PDA identity and MarketEvent validation. It is the
acquisition time, not a replacement migration occurrence time.

Every `Recovered Pump instruction` migration must have VERIFIED data and identity
quality, canonical migrate/migrate_v2 name, matching pinned schema/program,
confirmed commitment and matching event/evidence mint and pool. It must also
match an immutable event digest registered by this recovery instance after
validation. Merely copying source strings, flags or timestamps cannot grant the
exception. The session-local proof cache is bounded to the existing 10,000
migration-dedup limit; it is not a pending recovery queue or a replay service.

All timestamps must be finite, non-future, real numeric times. Recovery must be
verified at or after truncation observation, and chain time must not exceed
verification time. Both limits apply independently:

- verification minus truncation observation: at most **45 seconds**;
- processing minus verification: at most the unchanged **20 seconds**.

A fresh recovery can therefore apply a 30- or 40-second-old migration occurrence.
An overlong recovery or an observation waiting more than 20 seconds after
verification still fails closed. Missing/partial/spoofed provenance fails even
when its chain timestamp looks fresh. Ordinary trades, market/security/curve
observations and visible migrations retain the original event-age rule. The
special out-of-order exception now requires the same complete acquisition proof.
No freshness setting or strategy threshold changes.

## History and current evidence

Graduation, graduation DB timestamps, the migration event journal and chain
provenance keep the actual occurrence time. The existing
`flow_epoch = max(processing_now, event.ts)` remains unchanged. Pool selection,
subscription ACK and the full 180-second clean window still have to occur.
No pre-grad samples, coverage, prices or liquidity become post-grad evidence.

For a recovered migration, current analysis, paper checks and prospective
signals/intelligence use processing time, so they cannot evaluate old prices or
security as if the clock were still at chain time. Collector observation and
migration/event history keep the original event. No post-grad security,
economics, historical approval, Opportunity or Companion gate is relaxed.

## Fixed diagnostics

Recovery health and OBSERVE reports expose:

- `recovered_migration_chain_age_accepted`: successfully processed recovered
  observations whose chain age exceeded 20 seconds; duplicates do not add to it.
- `recovered_migration_recovery_freshness_rejected`: verification is future or
  acquisition evidence is older than 20 seconds at processing.
- `recovered_migration_recovery_window_rejected`: invalid chronological order,
  future observation/chain time or recovery duration above 45 seconds.
- `recovered_migration_missing_freshness_provenance`: absent/invalid markers,
  malformed times or missing/mismatched session proof.

`recovered_migration_last_ages` retains one finite aggregate age sample: chain age
at processing, acquisition age at processing and recovery duration. No raw
transaction history is added. The probe distinguishes stale acquisition from
other migration rejection causes and reports new graduation, already-graduated
or lifecycle-ineligible application outcomes separately. An accepted lifecycle
observation does not reopen a rejected/expired token or guarantee a pool.

MAX_PENDING=32, MAX_ATTEMPTS=3, MAX_AGE=45, the single recovery worker, adaptive
RPC pressure and the explicit-truncation-only getTransaction path are unchanged.
No ordinary trade HTTP polling was introduced.

Deterministic regressions cover old chain/new acquisition time, exact lifetime
bounds, stale verification, spoofed and malformed provenance, future times,
ordinary/visible event freshness, immutable journal time, unchanged last-price/
liquidity timestamps, deduplication and zero pre-earned PumpSwap coverage.

## Release validation and 600-second OBSERVE

486 backend tests and 39 frontend tests pass, along with Ruff, mypy (30 modules),
TypeScript/production build, secret scan, backend/frontend dependency audits and
`git diff --check`. No dependencies or configuration defaults changed.

The Helius standard-WSS probe ran **602.72 seconds**, with PumpPortal disabled and
trade_stream_enabled=false. Its complete uniquely named report is preserved at
`data/observe/recovered-migration-freshness-20261018T200927Z.json`.
The [timestamped versioned aggregate report](validation/recovered-migration-freshness-20261018T200927Z.json)
contains the handoff record and the complete report's SHA256.

| Measurement | Result |
| --- | ---: |
| Pump messages / decoded creates / admitted launches | 154,645 / 278 / 248 |
| Visible migrations / explicit truncations | 0 / 398 |
| Recovered migrate / migrate_v2 | 0 / 4 |
| Tracked / untracked recovered migrations | 1 / 3 |
| Emitted / processed / newly recorded graduations | 1 / 1 / 1 |
| Migration stale / other rejections | 0 / 0 |
| recovered_migration_chain_age_accepted | 0 |
| recovered_migration_recovery_freshness_rejected | 0 |
| recovered_migration_recovery_window_rejected | 0 |
| recovered_migration_missing_freshness_provenance | 0 |
| Tracked chain age / acquisition age / duration, seconds | 4.583 / 0.042 / 0.726 |
| Retained handoff records / independently verified pools | 1 / 1 |
| Eligible / selected / ACKed pools | 0 / 0 / 0 |
| PumpSwap messages / BuyEvents / SellEvents / accepted trades | 0 / 0 / 0 / 0 |
| Maximum post-grad clean coverage / peak CURRENT | 0 / 0 |
| Final active post-grad CURRENT / PARTIAL / UNAVAILABLE | 0 / 0 / 0 |
| Recovery peak pending / overflow / global gaps | 32 / 27 / 29 |
| Final pending recovery | 0 |
| Recovery / ordinary monitoring / total HTTP RPC calls | 371 / 50 / 421 |
| Recovery and RPC errors / 429 | 0 / 0 |
| PumpSwap and Pump normal-path trade HTTP delta | 0 |
| Queue final / exact peak | 0 / 79 |
| Trade observations becoming stale while queued | 3 |
| Trade / critical overflow drops | 0 / 0 |
| Peak RSS MB / mean CPU / peak CPU process percent | 138.9 / 25.7 / 113.8 |
| Pump WSS / PumpSwap WSS reconnects | 5 / 0 |
| Companion ENTRY_CANDIDATE / WAIT / REJECT | 0 / 231 / 7 |
| Paper cash USD | 20 |

The migration entered the existing post-grad lifecycle and the normal security
workflow independently verified its pool. That security result then triggered
the unchanged **top_1_independent_pct and top_5_independent_pct concentration
rejection gates**. The token therefore became lifecycle-ineligible before
subscription, later expired, and was removed. The retained handoff ends at
NO_LONGER_TRACKED/EXPIRED with the exact rejection reasons. Its last flow status
was UNAVAILABLE. Final active post-grad evidence counts are zero because the
candidate is no longer tracked; these are not zero-flow estimates.

The tracked live recovery had only 4.583 seconds of chain age. Thus this run
confirms normal recovery/lifecycle/pool-inspection integration and no stale
migration rejection, but **does not empirically exercise the >20-second chain-age
acceptance branch**. That branch is verified deterministically at 30, 40 and 65
seconds, together with rejection of 46-second recovery and 21-second-old
verification. No PumpSwap trade-flow/CURRENT validation or trading edge is
claimed: no suitable eligible candidate reached a subscription.

Recovery pressure remains a separate limitation: the unchanged 32-entry queue
reached capacity and overflowed 27 times. Two other unsupported recovery cases
plus those overflows produced 29 recovery global gaps. No capacity/concurrency
increase or backpressure redesign was made in this patch.

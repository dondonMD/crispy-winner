# Post-grad PumpSwap handoff trace

This is session-local observability only. Strategy gates, lifecycle transitions,
security scan cadence, candidate admission, pool selection, subscriptions,
180-second continuity, 20-second freshness and PumpSwap trade decoding are unchanged.
No live endurance run is part of this change.

Read `health.postgrad_handoff` in the dashboard API or `postgrad_handoff` in the
OBSERVE probe report (`data/observe-smoke.json`). The trace preserves why a
migrated candidate left eligibility even after it is removed from the scanner.
There are no new HTTP calls or per-wallet logs. Public mint/pool identities and
the migration transaction signature identify the handoff; no wallet secrets or
endpoint URLs are included. DEMO records are explicitly marked simulated.

Each retained candidate includes:

- Migration source/signature/slot in its history, migration pool hint, graduation
  time, venue and post-grad epoch.
- Lifecycle state, core decision/reasons and bounded security failures/warnings.
- Security attempt and applied-result times. Attempt history records hint count
  and whether the migration hint is among the inspector's existing first two
  sorted account hints. Result-queued history distinguishes RPC completion from
  application of its queued security observation.
- Verified pool count, base-matching pool count, whether the migration pool was
  verified, eligible pools, selected pools and ACKed pools.
- Socket connection, clean coverage, sample count, units validity, trade age and
  actual trade-evidence status.

The primary stage distinguishes lifecycle exclusion, missing migration hint,
security not attempted/pending, pool not verified/incomplete identity, WSS loss,
selection pending/capacity, ACK pending, unknown quote units, coverage building,
insufficient samples, invalid trade units, stale trades and CURRENT evidence.
The accompanying facts can show several missing conditions at once. A trace
stage never supplies evidence to any decision or changes provider state.

Lifecycle transitions and migration/security observations are captured directly;
other status changes are sampled at most once per second when health is viewed.
Unchanged snapshots do not append history. The latest 100 candidate records each
retain at most 32 history entries; reasons are capped at 240 characters and each
security/decision reason list at eight items. `evicted_candidates` and
`trimmed_history_entries` expose retention loss. Counts describe the retained
trace, not every candidate ever observed. Restored candidates warm new traces;
prior sessions' trace memory is not replayed or persisted into strategy research.

Validation covers verification/selection/ACK blockers, no changes to policy or
RPC counts, exact rejection reason retention after removal, bounded history and
candidate retention, copied report output, and snapshot throttling.

Release checks: 461 backend tests, 39 frontend tests, Ruff, mypy (30 modules),
TypeScript/production build, source/document secret scan and `git diff --check`
passed. Dependencies and frontend source are unchanged. No live probe was run.

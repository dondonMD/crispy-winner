# Bounded per-token evidence receipts — 2026-10-25

**PRE_COHORT_READY=NO. No observation, provider connection, cohort or trading activity.** Baseline `bacdbd1e3aa941c5fe88f5abb288a323467e75fa`; branch `remediation/early-edge-evidence-readiness`. The preceding per-token investigation and all original receipts remain unchanged.

## Extension and bounds

The existing `evidence_runs` session row gains an optional `token_evidence` projection. No table, migration, event queue, worker, subscription or per-trade database write is added. Existing accounting fields, durable write acknowledgement and rollback semantics remain intact.

- Capture on the existing 30-second operational write, storage-stop receipt and final shutdown receipt. A session row is overwritten, not appended per sample.
- Select at most **12 tracked tokens**: manual positions first, then most recent source trade, lexical mint tie-break. This diagnostic selection never changes production ranking or monitoring selection.
- Scan at most **12 × 500 retained events** per projection. No additional rolling event buffer or wallet history is retained.
- Limit each section to **12,288 encoded bytes**, removing trailing token rows and recording `omitted_bytes`. `omitted_selection` records candidates outside the 12-token selection. Retired token-instance counts explicitly identify churn; retired instances are not kept in a side cache.
- The final receipt holds a detached **pre-shutdown LIVE** section and a **SHUTDOWN** section. Each has its own observation timestamp, inherited by all token rows. Optional data is trimmed further when the complete receipt exceeds a **57,344-byte soft target**; `omitted_record_budget` counts removed rows. If necessary a minimal omission marker replaces the projection. Essential fields are never truncated. The original **65,536-byte hard guard** remains: even a minimal marker cannot force an oversized essential receipt through it.
- New optional projections expire after **seven days**, replaced with an explicit EXPIRED marker. At most **32 session rows** are updated per existing maintenance pass. Core receipt fields, legacy rows without the new projection, paper history, cohorts, strategy versions and outcome records are not removed by this extension. Export diagnostics before expiry if longer forensic retention is needed.

## Meaning and unavailable information

Each selected token records mint, venue, tracking start, flow epoch, verified quote identity, last-trade age, clean coverage, existing engine classification/blockers, coverage-gap and buffer-loss watermarks. The retained 180-second window reports sample count, recognised SOL/USDC units, unknown/unrecognised units, mixed currencies and reason counts.

These are **retained-window counts**, not an assertion that evicted trades were observed completely. An unexpired buffer-loss watermark is explicit; a future-dated watermark makes active-window loss unknown rather than falsely absent. Cached feature sample/unit state and analysis timestamp are included separately from the freshly counted retained window. Diagnostics do not recompute features or replace the engine's decision.

The Pump acquisition path copies its existing unit-failure reason into unknown-unit event metadata. Known-unit events gain no extra field. No discriminator, layout, economic value or acceptance rule changes. Events from older recordings or other sources lacking that metadata count as `UNAVAILABLE`; reasons are never reverse-inferred. Window reason counts do not describe events already evicted or rejected.

Fixed per-token counters record all buffer trade evictions and existing reset reasons, split by LIVE/SHUTDOWN phase. The latest reset records both actual recording time and the timestamp used by existing gap accounting; these can differ for recovery. Latest stale rejection preserves source timestamp, freshness-check time and age. Acquisition time is explicitly null because it is not available here; queue-versus-source delay is not invented. Counters are scoped to the current token instance, reset on restoration, saturate at signed-64-bit maximum and flag saturation. No per-event diagnostic history is stored.

Global reset counts are split by phase; existing Pump reset-reason totals are also copied. Phase means whether shutdown has begun, not a guessed network cause. Thus a shutdown post-grad invalidation using the existing `decode` reason remains visible as SHUTDOWN without changing that core counter.

## Failure, shutdown and restart

Diagnostic hooks cannot interrupt real continuity invalidation. Hook errors are counted and make subsequent diagnostic sections PARTIAL. Projection errors yield UNAVAILABLE with explicit omission/error counts and no raw exception text. Invalid optional JSON becomes UNAVAILABLE_ENCODING. Database write failures still propagate; no success is acknowledged before commit and prior committed receipts survive rollback.

Before cancellation, shutdown captures the live view. After cancellation, unresolved-work accounting, coverage invalidation, checkpoint and client cleanup, the final existing write captures the shutdown view. This does not convert unresolved recovery into complete evidence. Restart preserves the prior durable receipt but starts new live counters and requires normal evidence re-warming.

A crash can lose diagnostic increments after the last committed operational cut. RUNNING plus the receipt's timestamp is the last durable view, **not a final-session accounting guarantee**. Seven-day retention and bounded selection also limit retrospective precision; neither limitation is hidden.

## Validation and overhead

Focused offline suite: **210 passed**, normal termination, 10.64 seconds. Coverage includes inclusive window membership, mixed/unknown units and exact reason branches, passive decision equivalence, deterministic selection, byte omissions, optional JSON failure, counter saturation, real invalidation despite diagnostic failure, committed-receipt rollback, bounded retention, shutdown and restart, plus existing adversarial truncation, buffer-loss, transaction, transport and feature regressions. Two initial synthetic zero-amount fixtures were correctly rejected by canonical validation; fixture inputs were corrected without weakening production validation.

Ruff passed on the five changed application modules and the new test module; mypy passed on the five application modules. Basic secret scan passed (262 source/document files), and `git diff --check` passed. Final preservation checks match all 15 initially hashed files and all seven frozen artifacts; the retired database size/mtime is unchanged. No full-suite, live, endurance or throughput run was performed.

Resource bounds: fixed small counter maps per active token (250 at current configuration), two sections at most 24 KiB encoded, no new event samples, and no extra normal operational write frequency. Conservative steady-state diagnostic allocation estimate is below 1 MiB; this is not a measured whole-process RSS guarantee. A maintenance batch can temporarily hold up to 32 existing receipt payloads (at most 2 MiB encoded, with additional Python-object overhead). Only failed-unit raw records gain a short reason field. A local 20-iteration projection-only check over 250 candidates and 6,000 retained events is recorded privately in `data/early_edge/per-token-receipts-20261025/component-cost.json`; it is synthetic component cost, not sustainable throughput or live market evidence.

## Exact files changed for this task

- `backend/app/token_receipts.py` — bounded passive projection and fixed counters.
- `backend/app/domain.py` — token-instance diagnostic state.
- `backend/app/discovery.py` — preserve existing unknown-unit reason.
- `backend/app/engine.py` — passive counter hooks, phase attribution and existing-write integration.
- `backend/app/db.py` — optional byte-budget trimming and diagnostic-only retention.
- `backend/tests/test_token_receipts.py` — deterministic isolated regressions.
- `backend/docs/bounded-token-evidence-receipts-20261025.md` — this report and synthetic example.

The five unrelated files and the pre-existing investigation report are preserved. No staging, commit, push or merge.

## Complete sanitized synthetic example

This is the new optional `token_evidence` field only; existing core receipt fields are unchanged and omitted from this example. Token identity and timestamps are controlled offline fixtures. No quote, real opportunity or CURRENT market evidence is claimed.

```json
{
  "version": 1,
  "at": 10000,
  "current": {
    "at": 10000,
    "phase": "LIVE",
    "selection": "manual_first_then_last_trade_then_mint",
    "tracked_tokens": 1,
    "retired_token_instances": 0,
    "token_limit": 12,
    "tokens": [
      {
        "mint": "SYNTHETIC-EXAMPLE",
        "venue": "PUMP",
        "tracking_start": 9820,
        "flow_epoch": null,
        "verified_quote_mint": "So11111111111111111111111111111111111111112",
        "retained_window": {
          "samples": 3,
          "recognised_units": 2,
          "unknown_or_unrecognised_units": 1,
          "mixed_currencies": true,
          "unit_failure_reasons": {
            "curve_not_verified": 1,
            "unsupported_quote": 0,
            "identity_conflict": 0,
            "unverified_quote_semantics": 0,
            "zero_executed_amount": 0,
            "UNAVAILABLE": 0
          }
        },
        "feature_samples": 3,
        "feature_units_valid": false,
        "feature_observed_at": 10000,
        "last_trade_age": 1,
        "clean_seconds": 0,
        "classification": "UNAVAILABLE",
        "blockers": {
          "no_samples": false,
          "unknown_or_mixed_units": true,
          "insufficient_samples": false,
          "incomplete_window": true,
          "transport_or_pool_unavailable": true,
          "stale_trade": false,
          "pending_recovery": false,
          "loss_watermark_unexpired": true,
          "clean_window_short": true
        },
        "coverage_gap_at": 0,
        "buffer_loss_at": 9990,
        "active_window_trade_lost": true,
        "counters": {
          "live_resets": {
            "buffer": 1
          },
          "last_reset": {
            "recorded_at": 10000,
            "gap_at": 10000,
            "reason": "buffer",
            "phase": "LIVE"
          }
        }
      }
    ],
    "omitted_selection": 0,
    "omitted_bytes": 0,
    "errors": 0,
    "status": "AVAILABLE",
    "counter_scope": "current_token_instance; not_restored",
    "global_resets": {
      "LIVE": 0,
      "SHUTDOWN": 0
    },
    "pump_reset_reasons": {
      "transport": 0,
      "shutdown": 0,
      "unknown_trade_identity": 0,
      "invocation_framing": 0,
      "outer_notification": 0,
      "event_decode": 0,
      "log_truncation": 0,
      "truncation_recovery": 0
    }
  },
  "pre_shutdown": null
}
```

Final component measurement: 4.498ms mean, 6.345ms maximum; section 12266 bytes, 12 rows, 238 selection omissions and 0 byte omissions. No network calls.

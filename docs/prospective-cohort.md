# Frozen prospective strategy cohort

This cohort measures the association between existing, unchanged research-eligible
signals and future **300-second after-cost net return**. It does not seek more
entries, approve holdout evidence or enable execution. Acquisition and strategy
thresholds remain frozen.

## Manifest and scope

Creation stores an immutable DB manifest: ID, UTC/Unix creation time, exact clean
Git HEAD, existing `conservative-…` strategy version, full SHA256 of every Settings
field including mode, combined code/config strategy hash, full config, all seven
horizons, latency, failed-transaction reserve, position semantics and existing
minimum sample count. No provider URL/key is stored. IDs use
`prospective-YYYYMMDD-<combined-strategy-hash>`.

The PRIMARY is always 300 seconds; 15/30/60/180/600/1800 are explicitly
SECONDARY_EXPLORATORY. Creation rejects a different horizon set. Reports cannot
choose another primary. Manifest hashing and SQLite triggers prohibit updates or
deletion, even before enrollment. New source/config/mode requires a new cohort,
never automatic migration. Private endpoint credentials remain outside Settings
and are not included in the report.

Only clean committed source can create or append. Startup and every signal/outcome
append compare exact Git SHA, strategy version, complete config and mode. Dirty
source or any drift refuses the transaction; the cohort runner exits if its monitor
fails. An existing research DB refuses a normal session without explicit cohort
selection. Other DBs remain retrospective unless explicitly enrolled; the report
cannot claim they represent unsampled market activity. Offline replay never
implicitly attaches the cohort.

## Inclusion and immutable observations

Every newly persisted OutcomeCollector signal with `eligible_research is true`,
matching version/mode and `signal timestamp > manifest.created_at` is enrolled
atomically with its source signal. There is no CURRENT-only, decision-only,
win-only, survival or outcome-availability filter. Historical rows are never
backfilled. The existing signal production cadence, eligibility and storage guards
remain unchanged. Storage/resource suppression is visible in session quality; the
cohort cannot reconstruct signals never produced by the monitoring system.

One token contributes one primary sample per engine session: its earliest eligible
signal. Repeats remain immutable descriptive records and are counted separately.
An out-of-order attempt to replace the first sample is refused. A missing earliest
outcome is never replaced by a later winning signal. Different sessions can contain
the same token; same-market/overlap dependence remains a warning.

The enrollment copy contains timestamp, mint/session columns, state, decision and
reasons, scores, 180-second features, security risk, price, liquidity, age, proposed
position, estimated costs, version, eligibility and mode. DB snapshots and outcome
rows are immutable. Pending snapshots are deep copied so later token mutations do
not leak into signal-time data. Cohort records/source signals survive normal
retention. Existing disk guards still apply; no paper/strategy history is deleted.

## One outcome implementation

The cohort observes the existing OutcomeCollector writes; it never computes an
entry/exit or a competing return. It preserves the next observed entry after frozen
latency, horizon-specific observed exit and delay, gross return, estimated
round-trip cost including failed transaction reserve, net return, MFE/MAE and
UNAVAILABLE_GAP/COSTS/NO_PRICE/CAPACITY. Economics and position-size assumptions
are unchanged: signal-time `viability.proposed_position_usd`, with the existing $4
fallback. Values are estimated returns, not actual executions.

Eligible pending work is persisted with the same 2,000-item collector bound. A
clean stop or crash/restart has no price backfill: OutcomeCollector marks unfinished
cohort horizons UNAVAILABLE_GAP rather than continuing an allegedly complete
window across downtime. Completed outcomes remain unchanged. Persisted terminal
horizons are subtracted on restart, preventing double counting. A crash between a
signal commit and pending persistence remains missing evidence, not a fabricated
outcome. No missed period is treated as zero price movement.

## Report and interpretation

The SQLite `mode=ro` report runs no migrations, writes no approvals and enables no
trading. For a fixed DB and `--as-of` timestamp it is deterministic. Enrollment and
outcome acquisition timestamps prevent later records appearing in an earlier
as-of report. It reports raw eligible signals, unique token/session samples,
excluded repeats, measured/unavailable/pending, coverage and all requested primary
statistics. Missing overdue ledger outcomes are labelled UNAVAILABLE_NOT_RECORDED,
not recomputed or assumed to have zero return. Pending samples also remain in the
conservative overall coverage denominator.

Means, variance and normal 95% CI use all measured primary samples. Medians use the
existing deterministic bounded reservoir (at most 5,000 values per metric), labelled
with its sample count. Profit factor uses positive/negative percentage-return sums,
not an executable portfolio. MFE/MAE are observed gross price excursions.

Statuses are INSUFFICIENT_SAMPLE, NEGATIVE_OR_INCONCLUSIVE, POSITIVE_DESCRIPTIVE or
PROSPECTIVE_EVIDENCE_CANDIDATE. A positive mean with CI crossing zero is inconclusive.
The strongest status requires the frozen `min_holdout_samples`, positive mean and
lower CI, and predeclared **100% measured primary coverage**. This deliberately
conservative requirement can prevent that status permanently after missing primary
outcomes; it must not be relaxed after results arrive. Even that label is only a
candidate for prospective statistical evidence, never approved edge or a trading
permission. Existing retrospective evaluate() and its chronological 50/25/25 analysis
remain separate, descriptive and unchanged.

Session-quality snapshots store bounded counters every 30 seconds and at shutdown:
recovery overflow/expiry, trade gaps, reconnects, RPC errors/429, stale queues/trades,
resource/storage pressure and sampled provider availability. Startup availability is
recorded separately from later outage samples. No degraded session is excluded.
Fixed coverage groups show measured/missing counts in degraded versus other sessions;
up to 200 detailed session rows are displayed, with truncation stated. Session
aggregates cannot prove exact gap overlap or missingness causality.

Every report warns about selection bias, survivorship risk, missing-outcome rate,
same-market correlation, overlapping token exposure, regime dependence, exploratory
multiple testing, normal-CI limitations, interim looks/optional stopping and no
guarantee of future returns. No automatic stopping/approval is performed.

## Daily commands

Run from the repository root. Use the same unchanged config and OBSERVE mode for
all commands. Private `.env` is loaded internally. The dedicated default DB is
`data/prospective.db`; do not delete it between sessions.

A. Create once on clean committed source (prints the manifest and cohort ID):

```bash
RADAR_MODE=OBSERVE .venv/bin/python scripts/prospective_cohort.py create --db data/prospective.db
```

Copy its `cohort_id` into a shell variable; this is operational metadata, not a
strategy setting:

```bash
COHORT_ID='prospective-YYYYMMDD-hash-from-create'
```

E. Before every run, detect drift; exit status is nonzero on any mismatch:

```bash
RADAR_MODE=OBSERVE .venv/bin/python scripts/prospective_cohort.py check --db data/prospective.db --cohort "$COHORT_ID"
```

B. Run the normal production OBSERVE engine, appending every eligible signal to
that cohort. Stop with Ctrl-C; unfinished windows become unavailable:

```bash
RADAR_MODE=OBSERVE PUMPPORTAL_ENABLED=false .venv/bin/python scripts/prospective_cohort.py run --db data/prospective.db --cohort "$COHORT_ID"
```

For a deliberately bounded session, add `--seconds N`. No wallets, signing, orders
or live execution exist. Do not change to PAPER inside an OBSERVE cohort; mode drift
is refused.

C. Check progress (read-only, including pending and missing evidence):

```bash
.venv/bin/python scripts/prospective_report.py --db data/prospective.db --cohort "$COHORT_ID"
```

D. Export the same primary report, with secondaries visibly exploratory:

```bash
.venv/bin/python scripts/prospective_report.py --db data/prospective.db --cohort "$COHORT_ID" > data/prospective-primary-report.json
```

For reproducible historical analysis, add `--as-of <Unix-timestamp>`. Read-only
reports remain available after source/config changes; append/check require the exact
frozen identity. No manual SQL editing or automatic cohort migration is supported.

Run one collector process per research DB and use the commands sequentially. A
restart closes persisted unfinished windows as gaps; opening another collector
against the same DB while one is active is not a supported parallel collection mode.

## Implementation validation

[Preserved deterministic results](validation/prospective-cohort-20261019.json):
535 complete backend tests, including 26 prospective tests, and 39 frontend tests
passed; Ruff, mypy, TypeScript/build, secret scan, dependency audits and diff checks
passed. Fixtures prove creation, future eligibility, immutable snapshots, drift
refusal, first-signal selection, exact collector after-cost reuse, 50% coverage for
one measured/one unavailable sample, restart gaps/persistence and read-only CLI
reporting. Synthetic fixtures are isolated from real research. No hour-long
engineering OBSERVE run was performed for this phase.

Session quality is captured before intentional shutdown cancels sockets, so planned
closure is not misreported as a provider outage. Unfinished outcome windows still
become gaps. An initial empty CLI smoke cohort exposed this metadata issue and was
preserved unchanged; the corrected implementation creates a new frozen cohort.

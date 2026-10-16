# Candidate expiry and adaptive polling

Root cause: `last_event` advances on every accepted event, including RPC curve/security observations.
The fixed five-minute expiry could therefore remove background candidates before the application
itself allowed their next adaptive lifecycle poll. `last_curve` tracks received curve evidence;
`last_curve_attempt` records scheduler attempts. None of those timestamps or evidence rules changed.

For a pre-graduation candidate still eligible for lifecycle monitoring, the expiry deadline is:

- Base deadline: last event (creation if none) + `candidate_inactivity_seconds` (default 300).
- Poll opportunity: last curve attempt (creation if never polled) + the **current** tier's effective
  interval, advanced to current provider Retry-After/global cooldown eligibility.
- Hot: also account for the global hot-batch cadence guard. Background: account for background
  backoff, batch cadence, heavy-pressure background-probe deferral, and the number of bounded
  oldest-first batches ahead of this token. Queue ranks use the scheduler's existing ordering.
- Deadline: the later of the base deadline and opportunity + `candidate_expiry_grace_seconds`
  (default 30), capped at last activity + `candidate_expiry_max_seconds` (default 7,200).
- Expire only after the deadline, when EXPIRED is a permitted transition and the candidate has
  neither an open paper position nor a pending paper entry. No execution logic was changed.

Example with no queue/cooldown delay: a background token last observed/attempted at time T with
720-second effective revisit remains until T+750 rather than disappearing at T+301. Healthy
background revisit 180 seconds normally leaves the original T+300 expiry unchanged. Current hot
membership uses hot timing, not background timing. Tier changes and provider recovery recalculate
the deadline immediately; no sticky per-token grace is stored.

Defaults are bounded configuration, not strategy threshold changes. The inactivity maximum must
be at least the base inactivity interval. The cap deliberately takes precedence if an outage,
Retry-After, custom batch configuration, or queue delay exceeds the allowance: this is a finite
monitoring opportunity budget, not an unlimited promise through arbitrary provider outages.
Events continue to refresh activity as before. Hard admission/eviction limits remain unchanged at
250 active / 25 hot by default, and can replace weaker candidates even during expiry deferral.

DEMO receives no RPC-related extension. Migrated candidates retain base inactivity timing where
EXPIRED is allowed; states requiring monitoring without an EXPIRED transition are no longer
silently deleted. Paper positions remain protected; pending entries now receive the same expiry
protection already used by deep-set selection. Pending exits alone receive no extra protection.

Health exposes `inactive_expirations` (session cumulative, excludes admission evictions) and
`expiry_deferred_for_poll` (current eligible inactive candidates retained for scheduled polls).
The OBSERVE probe also reports the peak sampled deferral gauge. No per-token log, state allocation,
extra network request, or polling/scheduling change was introduced. Queue ranks are computed once
per sweep in bounded temporary storage. UNKNOWN/STALE evidence and WAIT requirements are unchanged.

Deterministic tests cover healthy expiry, 301/400/500-second retention with 720-second revisit,
expiry after opportunity/grace, never-polled creation anchors, Retry-After/global/background
cooldowns, heavy background probe delay, finite retention during repeated outages, healthy
recovery, hot/NEAR timing and tier promotion, paper protection, DEMO, transition guards, queue
slots, admission eviction, defaults, configuration validation and monitor-loop integration.
Existing background fairness, lifecycle hysteresis, adaptive RPC and Companion tests are unchanged.

## Validation — 2026-10-16

- Complete backend suite: 119 passed in 84.89s, including 19 new deterministic expiry cases.
- Frontend: all 23 tests passed; TypeScript check and Vite production build passed.
- Ruff backend/scripts, mypy backend/app (19 source files), basic secret scan, and
  `git diff --check` passed.
- `pip-audit -r backend/requirements.lock --no-deps --disable-pip` and frontend `npm audit`:
  no known vulnerabilities. The existing exact lock still lacks artifact hashes; audit warnings
  about that limitation are unchanged. No dependency changed.
- Existing test assertions were not weakened or edited. RPC controller/provider code,
  lifecycle thresholds/hysteresis, Companion, economics, Strategy Lab and paper execution
  code were not changed. Configuration remains immutably versioned by the existing mechanism.

### Read-only OBSERVE probe

360.82 seconds, isolated temporary DB, default 250/25 limits, paid trade subscriptions disabled.

| Metric | Observed |
| --- | ---: |
| Real launches / final active | 69 / 69 |
| Hot / background | 25 / 44 |
| Background waiting | 0 |
| Oldest background attempt age | 220.9 seconds |
| Final effective hot / background revisit | 52.5 / 360 seconds |
| RPC adaptive level | 0 → 1 at 245.7 seconds |
| Final RPC state | BACKING OFF |
| Inactive expirations | 0 |
| Current / peak sampled expiry deferrals | 0 / 0 |
| Curve accounts checked / verified | 169 / 150 |
| Hot / background batches | 10 / 0 |
| Accounts per successful curve HTTP request | 16.9 |
| Total RPC HTTP requests / requests per second | 13 / 0.036 |
| HTTP 429 / total RPC errors | 1 / 1 |
| Security attempts / completed | 1 / 0 |
| Final / peak sampled queue depth | 0 / 18 |
| Dropped observations | 0 |
| Final / peak sampled RSS | 96.4 / 96.4 MB |
| Final sampled CPU | 3.8% |
| PumpPortal state / errors / reconnects | CURRENT / 0 / 0 |
| DEX state | NOT USED YET |
| SQLite + WAL | 5.3 MB |
| Paper cash / paid trade subscriptions | $20 / 0 |

All 69 Companion actions were WAIT; missing trade/security evidence did not establish safety.
101 snapshots generated no extra RPC requests. Background batches were zero in this probe: the
rotating hot set had supplied recent attempts and no background token was due at the final
snapshot under the effective 360-second revisit. A six-minute run exceeded the old inactivity
constant in elapsed wall time, but no candidate actually required an expiry deferral. Thus this
run verifies operational integration and observed resources, not the reported long-run starvation
scenario. The 720-second fairness, cap, recovery and expiration behaviors are established by
clock-controlled tests. A larger/longer live run is still needed to establish endurance behavior.
RPC rate limiting remains possible and the failed security scan completed no refresh.
The finite retention cap can expire candidates through an outage longer than the configured
budget; UNKNOWN/STALE remains truthful. Priority admission eviction remains independent of expiry.

Files changed: `backend/app/engine.py`, `backend/app/config.py`,
`backend/tests/test_candidate_expiry.py`, `frontend/src/App.tsx`, `frontend/src/types.ts`,
`scripts/smoke_observe.py`, and this document. No provider, domain, Companion, evaluation or
paper-execution implementation changed.

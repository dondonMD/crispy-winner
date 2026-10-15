# Adaptive Solana RPC pressure

Operational change only: Companion classification, lifecycle thresholds/hysteresis, economics,
trade evidence and paper execution are unchanged. Default limits remain 250 candidates / 25 hot.

All Solana failures raise a shared bounded pressure level (default maximum 4). HTTP 429 returns
to the scheduler after one HTTP attempt, including within security inspection. Numeric and HTTP-date
Retry-After are respected; valid provider delays are not truncated to the adaptive cooldown cap.
Other Solana failures also return after one attempt. Non-Solana bounded retry behavior is preserved.

At levels 0–4, hot intervals are 30 / 52.5 / 75 / 97.5 / 120 seconds. Security scan cadence and
per-token refresh interval, background revisit/batch cadence, and HTTP spacing scale by
1 / 2 / 4 / 8 / 16. Background polling additionally defers at levels 3–4, but permits bounded
oldest-first recovery probes so a lack of hot candidates cannot permanently block recovery.
A global hot-batch cadence guard prevents hot-set churn from issuing small batches every enrichment tick.
Existing background error backoff remains an additional guard. Scheduler checks skip waiting work;
HTTP calls are asynchronous and discovery/event processing run in separate tasks.

Recovery requires both 120 seconds without failure and at least 3 successful RPC results per
level removed. One success cannot clear pressure. Configurable settings: rpc_backoff_max_level,
rpc_interval_max_multiplier, rpc_cooldown_max_seconds, rpc_recovery_seconds,
rpc_recovery_successes. Unknown or expired security still fails closed; refresh TTL for decision
validity is unchanged, so throttling can increase WAIT decisions. Pressure can also make curve
evidence stale under existing freshness rules; these rules are deliberately unchanged.

System Health keeps cumulative errors and 429s, shows RATE LIMITED during Retry-After,
BACKING OFF during recovery, and CURRENT once connected and recovered. It exposes pressure level,
HTTP requests, next eligible RPC, last success, effective intervals, and curve accounts per
successful curve-batch HTTP request. The latter counts returned accounts, including unknown/null
accounts, excludes the cached global baseline and security requests, and is not a validity rate.

PumpPortal had an avoidable backoff reset on every successful handshake. It now resets only after
a 60-second stable connection. Reconnect delays remain capped at 60 seconds plus <1s jitter.
Connection-local subscription sets are cleared and discovery subscriptions are sent once per
connection. Historical reconnect counts alone cannot establish the cause of those disconnects.

Retention remains unchanged: monitor maintenance runs every 60 seconds, deletes raw/snapshot
records at their configured ages, and performs TRUNCATE WAL checkpointing. Paper history and
strategy versions are excluded. Retention tests verify deletion and preservation with WAL enabled.
SQLite reuses freed pages; retention need not shrink the main file. Optimize/VACUUM remains
available; busy readers may delay WAL truncation. No aggressive deletion or cap change was added.

Public endpoints remain shared and can rate limit or block traffic independently of this process.
See the official Solana RPC documentation: https://solana.com/docs/rpc and
https://solana.com/docs/rpc/http/getmultipleaccounts. Batching remains getMultipleAccounts with
locally derived PDAs, deduplicated bounded mint lists, and a reused five-minute global cache.
A short run cannot establish sustainability at the observed 228-candidate load.

## Validation — 2026-10-15

Final checks: 100 Python tests passed (79.15s), 23 frontend tests passed, Ruff,
Mypy (19 source files), TypeScript/Vite production build, basic secret scan and diff whitespace
checks passed. One sandbox full-suite rerun stalled and was interrupted; the complete unrestricted
rerun passed. Deterministic tests cover repeated 429 escalation, Retry-After >120s, single-attempt
429 handling, gradual time-and-success-gated recovery, security deferral, hot slowdown including
membership churn, bounded background recovery probes, cache reuse, deduplicated batches, and
PumpPortal reconnect backoff/stable reset. Existing Companion/WAIT, 250-candidate fair sweeps,
lifecycle regression/hysteresis, retention and DEMO replay tests remain green.

Two read-only probes used separate temporary databases, max deep 25, and no paid trade subscriptions.
The first preceded the global hot-batch cadence guard; the final run includes it. Both include the
adaptive controller, so neither is an unmodified baseline. Different market arrivals and endpoint
conditions prevent attributing every difference to code.

| Metric | Initial patch probe | Final patch probe |
| --- | ---: | ---: |
| Duration seconds | 181.11 | 181.07 |
| Real launches / active | 92 / 92 | 91 / 91 |
| Hot / background candidates | 25 / 67 | 25 / 66 |
| RPC HTTP requests | 32 | 9 |
| RPC requests/second | 0.1767 | 0.0497 |
| Curve accounts checked / verified | 135 / 129 | 109 / 105 |
| Successful curve HTTP requests | 26 | 6 |
| Curve accounts/successful curve HTTP request | 5.19 | 18.17 |
| Curve accounts/all RPC HTTP requests | 4.22 | 12.11 |
| Hot / background batches | 26 / 0 | 5 / 1 |
| HTTP 429 / total RPC errors | 2 / 2 | 1 / 1 |
| Adaptive levels observed | 0 → 1 (112s) → 2 (176s) | 0 → 1 (111s) |
| Final RPC status | RATE LIMITED | BACKING OFF |
| Effective hot / background revisit / security scan seconds | 75 / 720 / 120 | 52.5 / 360 / 60 |
| Oldest background attempt age seconds | 142.8 | 111.6 |
| Security attempts / completed | 2 / 0 | 1 / 0 |
| Final / peak sampled RSS MB | 96.5 / 96.5 | 96.4 / 96.4 |
| Final sampled CPU % | 3.9 | 7.5 |
| SQLite + WAL MB | 5.05 | 5.02 |
| Final / peak sampled queue | 0 / 10 | 0 / 25 |
| Dropped observations | 0 | 0 |
| PumpPortal errors / reconnects | 0 / 0 | 1 / 1 |
| Final PumpPortal state | CURRENT | CURRENT |
| DEX state | NOT USED YET | NOT USED YET |
| Paid trade subscriptions | 0 | 0 |
| Paper cash USD | 20 | 20 |

Final run: one oldest-first background batch covered 25 mints; no revisit was observed within
this short window. All 91 Companion actions were WAIT; 101 snapshot reads added zero RPC requests.
The failed security scan completed no refresh and did not establish safety. Successful requests
after the 429 left pressure elevated, as intended; complete recovery was tested deterministically,
not observed live. Public RPC still rate limits security analysis even at this low aggregate rate.

Compared with the user's earlier 1,386-error long session, this short run recorded one error with
no retry amplification. Durations/load differ (91 versus 228 candidates), so no comparable long-run
error reduction percentage or claim of a solved rate limit is justified. A sustained 250-candidate
run remains necessary. Final sampled memory/CPU are also not directly comparable to the longer run.

Measured startup-window DB growth extrapolated to 96.43 MB/hour (initial probe 97.19); this includes
startup allocations, WAL/checkpoint effects, and no records old enough for retention. It is not a
steady-state forecast or proof that the 1 GB cap can sustain any particular research duration.
Existing retention/checkpoint code and tests were verified; this probe cannot validate 24-hour raw
or 30-day snapshot aging in real time. No existing research database was modified by these probes.

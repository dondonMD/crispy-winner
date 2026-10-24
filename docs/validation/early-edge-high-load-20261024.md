# High-load processing diagnosis — 2026-10-24

Branch: remediation/early-edge-evidence-readiness. Starting source 0357de8672592055d1297801df473a992efc68f5. No live experiment or cohort; all new traffic is synthetic. Historical artifacts remain untouched. PRE_COHORT_READY remains NO.

## Protocol and baseline

Retain exactly 250 candidates, 200 warm observations/token, 60 seconds at 50 trades/s, 0.7 recoveries/s with mocked 150ms HTTP, production shared limiter, and unchanged 250ms consumer pacing. Corrected drain accounting includes detached in-processing work. The prior first stress had p99 5.444s, processed 2,980 and cancelled 20; the restored-pacing fresh baseline processed all 3,000 with p99 10.778s. Host conditions differ; report both, not a manufactured speedup. Fresh baseline elapsed 71.262s, CPU mean 89.487%, peak RSS 185.602MiB, no token-local reset, one intentional shutdown global reset. Inclusive analysis: 10,796 calls/33.132s; DB.add 6.247s; reserve_event 4.654s; refresh 7.167s. Stages overlap and must not be summed as exclusive CPU.

Instrumentation separates scheduled-to-application age, admitted-to-process wait (including detached batch wait), individual synchronous process duration, and producer scheduling lag. Fresh p99: 10.778s / 10.311s / 0.02267s / 1.203s respectively. Queue accumulation dominates latency; consumer throughput is constrained by CPU and synchronous SQLite/observer work, not a measured lock-contention bottleneck.

Artifacts are uniquely preserved under data/early_edge/controlled-validation-20261024/high-load-*.json. The first sandbox attempt was interrupted without a completed JSON; its initial profile remains an incomplete attempt, not a valid benchmark. Separate ten-second runtime profile is deliberately excluded from latency comparison: 500 trades, 19.672s total with profiler overhead. Of 19.151 profiled seconds, calculate_features consumed 9.642s inclusive, window_features 9.374s, repeated pressure-bin generator 1.095s self across 1,126,448 calls. Volatility work consumed 1.147s inclusive; 128 cached return tuples cannot retain the capacity working set. Repeated immutable config copies/readiness and synchronous per-event SQL are secondary costs, left unchanged here to avoid combining unvalidated semantic changes.

## Targeted exact optimizations

Each trade is assigned once to a half-open pressure bin using the same floating-point boundary expressions and bisect_right; per-bin original event order and Python sum semantics are preserved. No incremental float accumulator replaces Python's summation. Unknown units, freshness, wallet dependence and every output field remain unchanged. A frozen test-only full pre-change window function provides exact dictionary comparisons across all six windows, random samples, exact/adjacent floating boundaries, unknown units, empty windows and advancing clocks.

The exact-value volatility LRU is bounded to 1,536 entries, enough for six windows across 250 candidates. Its keys are immutable return tuples and its result is unchanged statistics.pstdev; it caches neither time-sensitive trade evidence nor decisions. Increased cache memory is measured in the repeated loads. No candidate/event/queue capacity changes. No analysis cadence, provider settings, gates, decoder or study policy changes. The failed no-idle optimization is not restored.

Performance results and final checks follow after comparable unprofiled repeats. No acceptance conclusion is preassigned.

## Unprofiled 50/s comparison

| Metric | Preserved stress (4a78535) | Fresh baseline (0357de8) | Optimized (317aac3) |
|---|---:|---:|---:|
| Input | 3,000 | 3,000 | 3,000 |
| Processed / cancelled | 2,980 / 20 | 3,000 / 0 | 3,000 / 0 |
| Elapsed incl. drain, seconds | 65.188 | 71.262 | 64.336 |
| Application age p50, seconds | 2.902 | 5.555 | 2.509 |
| Application age p95, seconds | 4.755 | 10.180 | 3.817 |
| Application age p99, seconds | 5.444 FAIL | 10.778 FAIL | **4.295 PASS** |
| Application age maximum, seconds | 5.606 | 11.058 | 4.614 |
| Actual queue wait p50 / p95 / p99, seconds | not instrumented | 5.139 / 9.866 / 10.311 | 2.129 / 3.225 / 3.709 |
| Individual process p99, milliseconds | recorded separately in JSON | 22.670 | 20.502 |
| Producer schedule lag p99, seconds | not instrumented | 1.203 | 1.040 |
| Mean CPU, one core percent | 88.45 | 89.49 | 88.40 |
| Peak RSS, MiB | 185.23 | 185.60 | 186.61 |
| Queue peak | 253 | 459 | 210 |
| Stale / overflow drops | 0 / 0 | 0 / 0 | 0 / 0 |
| Recovery completed / accepted | 42 / 42 | 42 / 42 | 42 / 42 |

Original stress cancelled detached processing at shutdown because of the old harness drain predicate; this defect was fixed before the fresh baseline and repeat. Both new runs have exact terminal reconciliation, 3,000 persisted, no pending/in-processing/shutdown remainder. Recovery peak pending 1, expiry/overflow zero in both; shared monitoring stand-in completed 13 and 12 requests respectively. All transport is mocked; no claim of real security progress. Both have one intentional global shutdown gap, zero token-local resets and zero observation pauses. Consumer batching (100), yields, ordering, freshness and idle interval remain unchanged.

At almost identical analysis call counts (10,796 versus 10,810), inclusive analysis time fell 33.132s -> 24.950s. SQL times did not improve (DB.add 6.247 -> 6.530s; reserve 4.654 -> 4.914s); database batching was therefore not secretly responsible. The narrow feature optimization reduced enough repeated work to avoid growing the backlog in this declared envelope. It is not a claim of unlimited throughput: 88.4% mean CPU and 4.295s p99 leave limited margin, and the 60-second stress does not establish hour-scale performance or adversarial burst capacity.

The volatility cache remains bounded but retains more return tuples; measured peak RSS increases ~1MiB in the stress comparison. Cache content is disposable, immutable-keyed and irrelevant to continuity validity. All existing loss paths remain fail closed. A larger cache is an optimization of an exact function, not an increase in retained event history or an approximation of buyer statistics.

## Nominal regression and acceptance

The exact 210-second, 15/s nominal protocol at source 317aac3 processed and persisted 3,150/3,150 trades (2,100 buys/1,050 sells) in 211.400s including drain/shutdown. Application ages p50/p95/p99/max: 0.632 / 1.158 / **1.367** / 1.653s. Queue-wait p99 1.262s; process-duration p99 24.338ms. Peak queue 25, stale/overflow zero, all terminal ledgers reconcile; 147/147 recoveries complete, peak pending 1, no expiry/overflow/shutdown remainder. Mean CPU 77.18%, peak RSS 187.20MiB; no token-local gap or observation pause, one intentional global shutdown gap. Earlier nominal p99 was 1.272s, so the new run is slightly slower but remains well within the identical five-second criterion. Do not claim a nominal speedup from this comparison.

**Declared synthetic high-load latency criterion: PASS** at 50/s for 60s, as well as nominal 15/s for 210s, without stale-while-queued events, drops or unexplained loss. The new source has no consumer-loop changes relative to 0357de8. Both successful runs retain every processed event and do not manufacture complete observations from missing inputs. No synthetic CURRENT or opportunity result is counted as real evidence.

Baseline instrumentation is reproducible: the recorded source is 0357de8, with the latency instrumentation later committed in eeb1a24. Its harness SHA differs only because `admitted = {}` subsequently received the mypy-only annotation `admitted: dict[str, float] = {}`; removing that annotation from the committed harness reproduces the baseline SHA exactly. Optimized runs use committed source 317aac3 and its recorded harness SHA. During timed measurements no competing validation workload or application source edit was launched; only this engineering report was drafted during the nominal run. Host/background-load variability remains uncontrolled and is why both historical and fresh baselines are shown.

Reproduction uses new unique paths (existing paths refuse overwrite):

```
.venv/bin/python scripts/validate_evidence_load.py --seconds 60 --rate 50 --output <new-stress>.json
.venv/bin/python scripts/validate_evidence_load.py --seconds 210 --rate 15 --output <new-nominal>.json
.venv/bin/python scripts/validate_evidence_load.py --seconds 10 --rate 50 --profile-runtime --output <new-profile>.json
```

The last command is profiling only and cannot be substituted for unprofiled latency acceptance. All commands default to the same 0.7 recovery/s, 200 warm events and mocked HTTP. Diagnostic sample storage is bounded by the 600-second/100-trade/s CLI ceilings; outstanding-event timestamps remain bounded even if a synthetic event is rejected or lost. Production memory/queue/storage capacities are unchanged.

## Remaining limits

* CPU remains close to one core's capacity (mean 88.4% at stress, sampled peak 101.2% including threads); the improvement does not remove periodic feature cost, synchronous SQLite writes or observational snapshot/config work. The 60-second load is not a guaranteed sustained maximum.
* No generic DB transaction batching, analysis decimation, periodic cadence change or decision cache was introduced. Those could alter failure atomicity or time-sensitive decisions and require separate evidence before implementation.
* The existing 500-event rolling buffer still fails closed on loss. This change does not prove complete 180-second evidence for arbitrarily busy individual tokens.
* Live provider transport, decoding load, genuine CURRENT, matched real controls, quote success during actual congestion, and hour-scale 1GiB storage viability are not established by normalized synthetic traffic.
* No six-hour run, live cohort, trading operation or automatic push was performed. **PRE_COHORT_READY remains NO**. A passing synthetic criterion does not authorize or substitute for a separately approved live readiness evaluation.

## Final regression/security results and commit boundaries

* Focused feature/replay/storage/shutdown suites: **25 passed** before the performance commit.
* Complete backend run: **750 passed, 1 skipped, 1 failed in 162.36s**. The sole failure was the older `test_volatility_cache_is_exact_and_bounded` asserting a hard-coded 128 entries. Its exact numerical-output assertion was retained; it now inserts 2,000 distinct keys and requires the documented 1,536-entry eviction bound, then clears the disposable cache. The affected remediation plus feature suites subsequently passed **18/18** (including that corrected case). No application code changed after the measured performance commit, and the other 750 full-suite passes are reused; a second complete suite was not run solely for this test-expectation correction. The opt-in skip remains unchanged.
* Complete frontend: **39 passed**; TypeScript `tsc --noEmit` and production Vite build passed.
* Ruff passed; mypy passed (43 source files including the benchmark); secret scan passed (198 source/document files); whitespace check passed.
* Backend installed dependency audit: no known vulnerabilities. Frontend audit: zero vulnerabilities. Dependency manifests/lockfiles are unchanged; the preceding requirements-resolved clean audit remains available in the same artifact directory.
* Seven frozen original evidence hashes, original smoke hash, and retired cohort database size/mtime were reverified unchanged. No historical result was rewritten. No new real-market acquisitions, prospective enrollment, paper mutation, SDK runtime dependency, decoder modification, live trade or push.

Local reviewable boundaries: `eeb1a24` adds only benchmark timing/runtime-profile instrumentation; `317aac3` adds the exact feature hot-path change, frozen test-only reference, parity/cache regressions and initial investigation document. The final follow-up changes only the legacy cache-bound regression and this completed report. Its SHA is provided in the final response. Source 317aac3 is the measured optimized application source; the follow-up does not change application code.

A structured metric/artifact-hash inventory is preserved locally as `data/early_edge/controlled-validation-20261024/high-load-validation-summary.json`. These diagnostic artifacts are intentionally outside the committed application tree, consistent with previous controlled-load reports. Failed and interrupted attempts remain retained and distinguished from completed unprofiled comparisons.

**Engineering conclusion:** the specified high-load synthetic acceptance criterion is now satisfied by the measured exact optimization, with nominal regression also passing. This closes the specific demonstrated processing-latency failure at this declared envelope, not every infrastructure or evidence-completeness risk. **PRE_COHORT_READY = NO.** No separately authorized live validation is started by this conclusion.

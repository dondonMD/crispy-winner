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

# Truncation recovery scheduling

Recovery is still restricted to successful Pump notifications explicitly containing
`Log truncated`. No ordinary transaction polling or additional trade HTTP path is
introduced. The accepted migration acquisition/chain-time validation is unchanged.

## Measured cause and change

A 120-second instrumentation-only single-worker Helius diagnostic recovered 89
transactions in one attempt, with 90 requests started and three pending at the
snapshot. Network latency was 0.419 s median / 1.228 s p95 / 1.908 s maximum;
provider admission wait was 0.000031 s median / 0.644 s p95 / 1.822 s maximum.
Serial RPC awaits plus the existing 100 ms worker pause therefore leave permitted
capacity unused during slow responses. Bursts and occasional monitoring contention
also contribute. There were no retries, errors or 429s in this diagnostic.

Two long-lived workers now overlap network waits. Each claims a signature before
any await; at most two claims exist, including provider admission wait. Claims
remain in the 32-entry pending bound and block CURRENT until resolved. Completion
is idempotent. Every exit, including cancellation, releases its claim. Shutdown
cancels and joins both workers. No task is created per transaction.

The existing shared FIFO semaphore (two slots), global start interval (healthy
0.5 seconds), adaptive pressure and cooldown remain authoritative. Monitoring and
security use that same semaphore and retain their place in its wait queue; recovery
has no private HTTP client or quota. A 429 still slows the shared provider.

MAX_PENDING remains 32, MAX_ATTEMPTS remains three, and MAX_AGE remains 45 seconds.
Expiry is checked before dispatch and after the RPC; a late response cannot restore
continuity. Overflow/expiry still produce conservative global gaps. Unknown
truncations retain the same scheduling eligibility as other accepted work.

## Bounded accounting

Health includes submitted/accepted/completed/overflow/expiry, terminal attempt
counts (zero for expiry without dispatch), first-attempt non-null results, pending
high-water, active claims and actual HTTP in-flight high-water. Existing RPC
successful-result and unavailable-classification counters remain separate.
Actual HTTP starts count monitoring/recovery calls while pending work exists.

Latency quantiles retain the latest 1,024 samples per fixed metric; extrema cover
the process lifetime. Queue wait ends at the first actual HTTP start, including
provider admission. RPC latency includes admission and HTTP; HTTP latency excludes
admission. Total latency runs from notification observation to terminal resolution,
including expiry. Cancellation is a measured RPC attempt but is not a completion.
Rolling 1/5/10-second maxima retain at most 8,192 timestamps per stream; saturation
is explicit, and maxima become lower bounds if this diagnostic bound is reached.
No identities or transactions are retained in these diagnostics.

The preliminary serial diagnostic measured queue wait to scheduler dispatch
(0.600 s median / 11.308 s p95 / 13.066 s maximum), before the final actual-HTTP
start hook was installed. Its queue quantiles must not be treated as identical to
the final metric; provider wait is reported separately for that run.

## Limits

Two workers cannot bypass provider rate limits or compensate for sustained arrivals
above shared service capacity. Finite bursts can still overflow; late/unavailable
transactions, unsupported instructions and real transport loss still require gaps.
A quiet live interval does not establish production burst tolerance or trading edge.

## Preserved 602.29-second validation

[Aggregate report](validation/recovery-pressure-20261018T203457Z.json) records the
baseline, preliminary serial diagnostic, final measurements, raw-file hashes and
quality checks. The full uniquely named report remains locally under
`data/observe/recovery-pressure-20261018T203457Z.json`.

| Metric | Accepted baseline | Two workers |
| --- | ---: | ---: |
| Duration (s) | 602.72 | 602.29 |
| Truncations | 398 | 284 |
| Arrivals/s | 0.660 | 0.472 |
| Recovery HTTP requests/s | 0.616 | 0.472 |
| Accepted / completed | not instrumented | 284 / 284 |
| Peak pending | 32 | 23 |
| Overflow | 27 (6.78%) | 0 (0%) |
| Expired / final pending | not instrumented / 0 | 0 / 0 |
| Recovery global gaps | 29 | 3 |
| RPC errors / 429 | 0 / 0 | 0 / 0 |

All 284 requests returned successfully on attempt one; no unavailable transactions.
The final rolling maximum arrival counts over 1/5/10 s were 11/20/26, versus
8/14/16 in the preliminary serial diagnostic. Completion maxima were 4/11/21.
Completion bursts can exceed the start rate over short intervals when overlapping
requests finish together; the shared start-rate limiter is unchanged.

Latency seconds (min / median / p95 / max):

| Measurement | Min | Median | p95 | Max |
| --- | ---: | ---: | ---: | ---: |
| Before first HTTP start | 0.001 | 0.396 | 16.857 | 21.455 |
| Total recovery | 0.222 | 1.063 | 17.685 | 22.550 |
| RPC including admission | 0.220 | 0.879 | 3.615 | 8.974 |
| Provider admission | 0.000019 | 0.134 | 2.275 | 6.163 |
| HTTP network/body | 0.218 | 0.620 | 1.486 | 3.350 |

Measured cause is a combination: the serial worker cannot overlap network waits,
truncations arrive in bursts, and ordinary monitoring/security contend for the
shared quota. Retries and rate-limit cooldowns were not contributors in these
observations. The two-worker run used both actual HTTP slots without changing the
limiter. Its average arrival rate was 28.6% lower than baseline; zero overflow alone
does not establish a causal improvement or capacity guarantee. Baseline burst and
latency distributions were not captured and cannot be retrospectively inferred.

Capacity stays 32. The observed peak of 23 used 71.9% of that bound, and maximum
terminal latency of 22.55 s used 50.1% of the 45 s lifetime. Total starts averaged
367/602.29 = 0.609/s, below the healthy 2/s provider ceiling, with significant tail
contention still visible. These measurements justify leaving capacity unchanged
for the observed workload; they do not guarantee tolerance of larger future bursts.
Increasing buffering without a sustained shared-service estimate would be unjustified.

Monitoring made 83 ordinary RPC calls; 27 started while recovery backlog existed.
There were 284 recovery starts during backlog. Seven of eight security scans
completed (the last was pending at shutdown). Maximum active claims and actual
HTTP requests were both two. No sample buffers saturated.

The three recovery global gaps were unsupported `other` instructions. Seventeen
recoveries caused token-local gaps. Three genuine WSS disconnects at 326.91,
415.43 and 482.84 s account for the other three global continuity resets; reconnects
occurred at 329.15, 417.83 and 486.13 s. Nothing treats these losses as zero flow.

Resource results: RSS final/peak 149.5 MB, process CPU mean/peak 39.56%/149.5%
(multicore percentages). Event queue final/peak 8/202; final oldest event and trade
age 5.85 s, maximum sampled oldest trade age 28.20 s. Seven events became stale
while queued (six trades); 652 trades were rejected as stale overall. Trade and
critical overflow drops were both zero. Normal-path trade HTTP delta remained zero.
Queue lag, freshness rejections and bounded event-buffer gaps remain separate
limitations; none were hidden by this scheduler change.

Five canonical migrate_v2 instructions included four tracked migrations, all emitted
and processed; no migration freshness rejection. Two retained candidates failed
existing concentration gates, one was awaiting security and one was no longer
tracked. Eligible/subscribed pools and PumpSwap messages remained zero. No live
PumpSwap flow validation is claimed. Opportunity actions: EARLY_OPPORTUNITY 1,
DEVELOPING 134, PULLBACK_WATCH 2, TOO_EXTENDED 0, AVOID 30, DATA_LIMITED 23.
Companion: WAIT 171, REJECT 19, ENTRY_CANDIDATE 0, TOO_LATE 0. Paper cash stayed $20.

Validation passed: 493 backend tests, 39 frontend tests, Ruff, mypy (31 modules),
TypeScript/production build, secret scan, backend requirements/lock and frontend
dependency audits, and git diff whitespace checks. Thresholds, recovery lifetime,
trade freshness, migration freshness validation and PumpSwap decoding are unchanged.

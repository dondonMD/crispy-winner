# Time-correlated persistence and capacity investigation — 2026-10-24

PRE_COHORT_READY=NO. Started clean on remediation/early-edge-evidence-readiness at 2ed1ffcdad8856a23f2431bc83ccffb6da35e550. Synthetic only; no live cohort, trading, six-hour test or push. Historical evidence and retired database remain unchanged.

## Existing 6.129s failure: diagnosis before any production modification

Read the preceding reproducibility report and all three optimized replay JSON files. No production change was made for this initial investigation. Preserved derived correlation: data/early_edge/capacity-20261024/failed-replay-correlation.json, with hashes of original reports.

The failed B2 begins like the passing runs, then gradually falls behind during seconds10–30. At about9s all have only14–34 uncommitted trades. By29.27s B2 has169 accepted-but-uncommitted trades, versus42 at29.91s for B1 and48 at29.86s for B3. At39.10s B2 still has167; at59.10s it has267. This count includes detached in-processing work: queue.depth alone omits it. The service deficit precedes the60s outcome-expiry burst at approximately51–59s.

B2 commit wall time in bins10–20/20–30 is3.232/3.328s, versus2.126/1.888s in B1 and2.044/2.077s in B3. The extra roughly2.4–2.5s is the same order as120–127 arrivals at50/s and the observed extra backlog; this is a correlation, not a full counterfactual proof because timers overlap and samples do not land at exact boundaries. CPU feature totals remain17.78–18.01s. Longest recorded B2 refresh=.634s and longest commit=.100s, not a single6s blocking operation. The p99 process duration is63.57ms, versus23.58/24.46ms in B1/B3; queue p99=5.477s supplies most application age. No stale/drop/duplicate or queue-reconciliation defect explains the difference.

WAL stays197,792 bytes until later growth to218,392 around53s, after the deficit already appeared. That growth is not evidence that a large late WAL caused the initial slowdown. Internal automatic checkpoints, retention worker timing and physical device service cannot be assigned to a particular transaction from the old aggregate traces. These are the specific telemetry gaps to close; there is no justification for a speculative production rewrite.

## Predeclared next measurements

Keep the existing project ext4 filesystem,250 candidates,200 warm events, queue1000, buffer500,20s freshness,250ms cadence, recovery0.7/s, burst envelope and mock providers. Run120s at30,40,50 trades/s, strictly serial processes including setup/cleanup. This is a short capacity bracket, NOT proof of indefinite sustainability. Observe committed progress/backlog trends rather than equating nominal arrival rate with service capacity. Preserve every result. A50/s failure blocks endurance even if a later favorable60s replay occurs.

Diagnostic-only additions: transaction-role counts/latency in existing10s bins, timing of existing retention/evaluation/outcome operations, and successful durable-completion age after process returns from persistence. No new timer, forced checkpoint, writer queue, network request or source-evidence change. Existing application-age metric remains processing-START age for comparability; durable completion is separately labelled. Thread-local roles distinguish raw-event and identity commits from maintenance/read-only calls. Diagnostic aggregation uses a short lock, never across application work or I/O. Text reads and stage/role histories are bounded. Instrumentation overhead must be measured and disclosed.

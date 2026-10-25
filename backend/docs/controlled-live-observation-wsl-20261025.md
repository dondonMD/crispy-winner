# Phase 3 WSL live-receipt audit — 2026-10-25

**CONTROLLED OBSERVATION PARTIAL. PRE_COHORT_READY=NO.** Offline audit only: no engine, provider connection, cohort, wallet, transaction or rerun. The earlier [blocked sandbox pre-flight](controlled-live-observation-20261025.md) remains unchanged and valid; these later WSL results do not rewrite it.

Labels: **CONFIRMED** = recorded values, checked arithmetic or inspected code; **INFERENCE** = supported interpretation without event-level proof; **UNRESOLVED** = not established by these receipts. Receipts are operator-supplied records, not an independent chain or endpoint attestation.

## Provenance

**CONFIRMED:** both sessions identify source54e2ef95ad256419808392109d383352b6a08fa1, matching this audit's starting HEAD on remediation/early-edge-evidence-readiness. Application/configuration and original smoke harness are unchanged relative to Phase2C baseline0fbe59f9ab73797247f8fba77af519853fca367d. The corrected WSL runner and all11 private files, including empty stderr logs, were hashed before analysis. No private files were changed.

- Strategy version computed from recorded Settings: conservative-40d1a51bfe22.
- Settings SHA256, UTF-8 sorted compact JSON: df6e618588ed4f45df34f28161e254cf9a510d39c68e37d6f15e36b5623ee9f6, identical for both sessions.
- OBSERVE;250 candidate capacity,25 deep,1,000 queue,500 rolling events;20s trade/market freshness;180s clean flow; security threshold60% curve/TTL300s/global scan interval30s; hot curve30s/background target180s. Limits were not raised.
- Original harness SHA256:46896e982171365ea6a73fca9be3d8cc4b08355e5848ee8d75593387322dda0f.
- 65s generated diagnostic overlay SHA256:9f16c3842936aca633a50d6f4d631f3633e8431807b68b81c29bdab309831fdf.
- 240s overlay SHA256:fb7f91a59a7e4809cefc932cdfd31d86ef6e750df6319a1e6c98936956f62610.
- Runner file SHA256:2b53508076f5d98474afdd89d772bbc41377955f0f899f952b735c19e7e6dadd.

Both overlay hashes were independently reproduced offline using only the runner's checked string-replacement helper, original source and respective output path. No generated harness was executed. Changes are diagnostic keyword forwarding, unique output paths, safety checks and shutdown/SQL receipts; per-run paths explain different overlay hashes, not configuration drift. This was not an untouched original harness invocation. Actual provider URLs/keys and full host/environment identity are absent from sanitized identity receipts; no independent claim about their exact values is possible.

Private source: data/early_edge/controlled-observe-wsl-20261025-aczwDa/{probe65,probe240}/identity.json, observe.json, shutdown.json, plus runner/stdout/stderr. Derived checks/hashes are retained separately under ignored data/early_edge/wsl-receipt-audit-20261025/. No token identifiers or wallet data are published here.

## Both observed sessions

|Measurement|65s probe|240s probe|
|---|---:|---:|
|Measured elapsed|65.09s|240.34s|
|Operator-reported process exit|0|0|
|Shutdown returned / SQLite quick_check|true / ok|true / ok|
|Processed launches / stale creates|11 /1|48 /1|
|Pump WSS messages / reconnects|13,174 /0|26,678 /2|
|Decoded/submitted trades|164|1,926|
|Processed AND SQL-persisted trades|145|1,730|
|Processed buys / sells|80 /65|925 /805|
|Trade stale rejections|19|196|
|Verified curve observations / curve events|5 /5|138 /151|
|Final active / deep / background|11 /10 /0|48 /25 /9|
|Security attempts / completions|0 /0|2 /2|
|Total RPC / recovery HTTP / ordinary RPC|64 /62 /2|164 /143 /21|
|RPC errors /429|0 /0|0 /0|
|Internal queue peak / sampled peak|9 /4|42 /32|
|Trade / critical overflow drops|0 /0|0 /0|
|Average process CPU / sampled peak, one-core basis|6.21% /25.4%|8.68% /55.5%|
|Peak RSS / reported SQLite allocation|100.1 /1.20MiB|110.6 /10.56MiB|
|CURRENT peak / maximum token clean coverage|0 /39.89s|0 /124.30s|
|Prospective cohort/enrollment/outcome rows|0 /0 /0|0 /0 /0|

**CONFIRMED:** row-kind counts match persisted accounting, no trade/critical overflow, no observation-pause gaps, resource/storage pressure flags false, approved_evidence=None, paper cash$20 and no paper-trade rows. Token-state/research records are ordinary descriptive observations, not prospective enrollment. No0 exit-code file is present independently of the operator statement; shutdown/SQLite success is independently in the saved receipts. Neither empty stderr nor successful cleanup proves complete market coverage.

## A. Transport and the124.3-second ceiling

**CONFIRMED:**240s report timeline, relative to the harness observation clock:

|Transition/window|Seconds|
|---|---:|
|First connected|1.21|
|Disconnect / reconnect|85.99 /88.14|
|Disconnect / reconnect|212.93 /215.05|
|Observation cut|240.34|
|Connected intervals|84.78;124.79;25.29|

The two outages last approximately2.15s and2.12s. No connected interval reaches180s. engine.trade_coverage_seconds uses connected_since, token tracking start and relevant gaps; therefore no pre-grad candidate could obtain180 continuous seconds in this session, regardless of its age. The sole migrated candidate had no eligible pool coverage, independently preventing post-grad CURRENT. The65s run was too short by design.

**INFERENCE:** once-per-second coverage sampling plausibly explains the.49s difference between longest connection124.79s and sampled maximum124.30s. Token creation/admission,196 local stale resets and6 recovery-local gaps can only shorten candidate windows further. They are not needed to explain the global ceiling.

**UNRESOLVED:** exact candidate birth/admission times, per-token reset timelines and which candidate achieved the maximum are not retained in these aggregate receipts. No attribution to a particular token is possible. The production socket loop catches several exception types and records DISCONNECTED without preserving exception/close code; both stderr files are empty. Network interruption, remote closure or keepalive/timeout are possibilities, not established causes. Truncated framing errors are handled inside receive and are not themselves proof of a socket disconnect. Do not blame Helius, host load, SQLite or malformed trade tails without additional evidence.

## B. Trade accounting, units and CURRENT blockers

**CONFIRMED:**240s exact terminal equation:

**1,926 fully decoded =1,926 submitted =1,926 queue-accepted =1,730 processed/persisted +196 stale.**

Incoming queue rejection, eviction, memory/SQL duplicate trade, untracked/venue terminal rejection, exception, shutdown-discarded trade, pending and in-processing trade counts are all0.925+805=1,730; independent SQL trade count=1,730. This is measured stale rejection, not an assumption that every difference is stale or an unexplained loss. Queue acceptance is not acceptance as current evidence. The65s equation is164=145 processed/persisted+19 stale.

All event kinds also reconcile:240s SQL raw events1,932=48 creates+1,730 trades+151 curves+2 security+1 migration. Total submitted2,129=1,932 processed+196 stale trades+1 stale create.65s SQL161=11 creates+145 trades+5 curves;181 submissions=161 processed+19 stale trades+1 stale create.

**Stale causality remains limited:** all recorded admission-to-SELECTION waits lie within the<=.5s histogram bound; largest consumer tick gap=.468s, max measured process call=.0203s. Only1 trade is recorded as becoming stale while queued in240s (0 in65s). That counter checks admission versus dequeue age; it does not cover later detached-batch waiting or give acquisition-to-arrival age. **INFERENCE:** sustained consumer backlog is not supported here; already old/near-stale input is plausible. **UNRESOLVED:** how many of196 were already stale at arrival versus crossed20s after admission/selection, whether transport replay caused them, and their exact ages. Maximum sampled oldest queued trade age26.38s is not their complete age distribution.

Unit failures and stage counters overlap, not additional lost trades.240s decoded invalid-unit observations414:413 curve_not_verified,1 unsupported_quote,0 identity conflicts. Retained processed trade observations total1,730:1,317 SOL/verified-curve and413 unknown/event. Unknown units were not converted to SOL/USD. No Pump unsupported-layout, invalid encoding/bool/pubkey/timestamp or tracked-tail decode failure was recorded in either session.

Prefix counters are earlier-stage diagnostics:240s5,749 classified versus3,822 filtered untracked+1,926 completed tracked decodes leaves1 prefix not represented in those downstream totals. Code stages/discards events with failed/incomplete invocation frames; the exact notification responsible cannot be identified without per-notification records. This is NOT an unexplained accepted-trade deficit or proof of a missing tracked trade.65s2,252=2,088 filtered+164 completed. Neither prefix count is a complete chain-wide trade count.

At240s cutoff:0 CURRENT,11 PARTIAL,37 UNAVAILABLE (pre-grad0/11/36 plus1 post-grad unavailable). Nonexclusive blocker counters:48 insufficient continuity;37 invalid/missing units;24 fewer than3 samples;18 no samples;34 stale/missing last trade;48 pending-recovery overlap;0 currently disconnected. Do not sum these as distinct candidates. The generic pending counter tests overlaps even for the post-grad token, whereas production applies Pump recovery overlap to pre-grad; it is not proof of a PumpSwap-specific gap. Ordinary Opportunity flow reports UNAVAILABLE unless CURRENT, so its48 unavailable-flow projections do not contradict the engine's11 PARTIAL candidates.

## C. Truncation recovery and shutdown

**CONFIRMED:**145 explicit truncation notifications=133 framing-with-truncation+12 balanced truncated notifications. No framing-without-truncation; detail counts5 depth mismatches+128 unfinished invocations. Discovery's135 errors combine133 framing diagnostics and2 transport errors; they are not135 independent transport failures. Recovery pending semantics prevented truncated logs from becoming complete evidence.

|240s recovery stage|Count|
|---|---:|
|Submitted /accepted /deduplicated /overflow|145 /145 /0 /0|
|Completed classifications|143=137 UNTRACKED_CONFIRMED+6 TRACKED_AFFECTED|
|Unsupported/unavailable/failed/malformed classifications|0|
|Recovery global gaps / local gap calls|0 /6|
|Pending / claimed worker at cutoff|2 /1|
|Oldest pending age|1.037s|
|HTTP requests /successful responses /errors /429|143 /143 /0 /0|
|Peak pending /expiry|6 /0|
|After shutdown|143 completed+2 shutdown-unresolved; pending/in-flight0; STOPPED INCOMPLETE|

A claimed worker is not necessarily an HTTP request already counted; it can be awaiting the shared limiter. Accepted signatures, worker claims, HTTP requests and completed classifications are different counters. All143 completed on the first attempt. Completed recovery latency median.463s/p952.431s/max2.856s; max age45s and workers2 remained unchanged. No capacity saturation/timeout/expiry failure was recorded for the last two. **INFERENCE:** they were ordinary cutoff-outstanding work. **UNRESOLVED:** their identities/contents/outcome and eventual availability; neither may be called harmless, untracked or recovered.

The65s result is also incomplete:66 accepted=61 UNTRACKED_CONFIRMED+5 pending, then5 shutdown-unresolved.62 HTTP requests/61 successful responses,2 claimed workers at cut; oldest pending4.683s, peak24, overflow/expiry/errors/429 all0. Its completed-recovery max latency11.573s is not an expiry. Post-stop accounting explicitly retains this unresolved work; no backfill or silent success conversion.

Engine local-reset counts202=196 stale+6 recovery calls; global resets2 correspond to the same two transport gaps reported by discovery, not another two to add.133 framing diagnostics and145 recoveries must not be added as unrelated continuity resets. Shutdown intentionally ends coverage and cannot be counted as an unexplained in-window outage.

## D. Security and monitoring fairness

**CONFIRMED:**138 of151 curve observations were verified;13 remained unverified, despite successful RPC responses. Exact invalid/missing-baseline/account causes are not recorded. Eight hot batches, no background batch; background waiting0 and oldest background poll age134.9s at cut, below the180s target. Zero background polls is not by itself proof of starvation.

Source engine.enrich_once requires deep membership, graduation OR verified/current curve>=60%, last security attempt due after300s, global30s interval, and RPC eligibility. REJECTED/EXPIRED tokens are excluded from deep selection.48 retained candidates is not48 scan-eligible candidates: final population14 REJECTED+25 deep+9 background. Of40 final known progress values,38 are below30%,1 is30–59%,1 is60–84%; freshness/membership further constrain eligibility. One canonical recovered migration was processed; independent pool verification succeeded, but concentration rejection left it lifecycle-ineligible for subscription. That is a preserved risk gate, not an acquisition failure.

Two scans completed and persisted; cached shutdown projections contain2 current-verified security views and46 UNKNOWN/STALE, not46 proven unsafe or time-stale tokens. Both attempts were within the hot set.21 ordinary RPC calls made progress alongside143 recovery requests; RPC errors/429 and backoff level0, resource pressure false. **INFERENCE:** the sparse threshold-eligible population is consistent with two scans; shared-RPC scheduling contributed some wait but no recorded pressure collapse. **UNRESOLVED:** exact eligible/due/deep sets at each scheduling opportunity, security completion times/raw reports and whether any eligible candidate was delayed unfairly. The receipts cannot prove that two scans were sufficient, nor that more were due.25 slots is a cap, not continuous service to every retained candidate.

## E. Opportunity Intelligence and PumpSwap

**CONFIRMED recorded classification counts:**26 DEVELOPING,1 PULLBACK_WATCH,14 AVOID,7 DATA_LIMITED;0 EARLY/TOO_EXTENDED, totaling48. The shutdown cache has35 CURRENT,9 STALE and4 UNKNOWN curve projections; all48 lack CURRENT trade flow and current provider market context. Only5 satisfy the existing net-progress>=4pp predicate and3 the persistence>=.75 predicate individually;0 satisfies the complete EARLY predicate in that stored projection. These overlapping predicate counts are not matched to future outcomes.

These are unvalidated attention/risk labels: DEVELOPING does not establish sustained breadth; PULLBACK_WATCH does not confirm renewed buying; AVOID records a risk/lifecycle blocker; DATA_LIMITED is not a failed-return classification. Creator-sell/concentration blockers exist, but no ownership or profitability conclusion follows.0 EARLY at the recorded cut is not proof there was never a transient EARLY during the session:252 ordinary opportunity signal/outcome records are counted, but their full transition payloads/timestamps are not preserved here. No valid EARLY throughput estimate or expected PnL can be calculated. Companion0 ENTRY/38 WAIT/10 REJECT is a separate mapping from the Opportunity labels.

One recovered tracked migration and two untracked migrations were identified in240s (visible migration events0). The migrated pool was independently verified but its candidate failed concentration gates: eligible/subscribed/ACK/messages/Buy/Sell all0; PumpSwap socket connected. **No PumpSwap event layout was exercised.** Compatibility remains UNVERIFIED for these sessions; the historical suffix issue remains unresolved, not newly confirmed or disproved. No authoritative new schema can be established from an absent payload. No entry fill, executable exit quote, after-cost result, approved evidence or paper trade was established.

## Conclusion and minimum next action

**CONFIRMED:** real launch/trade/curve acquisition, useful canonical-unit observations, independently recorded migration/pool verification, coherent terminal/SQL accounting, bounded resources and honest shutdown-unresolved classification. Successful process completion is not complete180s evidence.

**Ranked remaining blockers:**

1. No uninterrupted180s pre-grad window: recorded transport resets alone explain the ceiling. Disconnect cause is unrecorded; per-event source/acquisition/admission/start ages are insufficient to explain stale arrivals precisely.
2. Substantial unavailable/partial evidence: pending recovery, unknown curve quote verification, fresh/sample requirements and sparse monitoring/security readiness. Two cutoff recoveries remain unresolved, without a proven service failure.
3. No prospective signal/economic validation or fair-control/quote-deadline demonstration. Zero final EARLY is not proof of predictive failure, success or cohort throughput.
4. No live PumpSwap event compatibility proof; concentration exclusion correctly prevented subscription. The historical unsupported suffix must not be guessed away.

**Additional bounded non-trading observation is justified, not initiated.** Minimum next engineering/validation action before reconsidering Phase4: review bounded diagnostic capture of transport exception/close category and source-event→acquisition/admission→processing ages, plus time-stamped scan eligibility and unresolved recovery cutoff state; then obtain separate authorization for a bounded observation that actually demonstrates180s known-unit/fresh evidence with reconciled losses. Do not simply extend duration or reduce standards. Phase4 also needs the separately required quote/deadline, observation-fairness, matching and immutable protocol checks; one new CURRENT candidate alone would not approve enrollment or trading. No source fix or rerun is authorized/performed by this audit.

**Final Phase3 status: CONTROLLED OBSERVATION PARTIAL. PRE_COHORT_READY=NO.**

## Offline validation and preservation

Checked all event-disposition equations against terminal ledgers and saved SQL counts, recovery classification/pending/shutdown conservation, identical Settings hashes, original/generated harness hashes and normal shutdown/SQLite assertions. No SQLite database was opened, no full engine constructed and no saved harness executed. Source inspection covered discovery.receive/run, engine._process/trade_status/trade_coverage_seconds/enrich_once, PriorityBuffer counters, TruncationRecovery.step/resolve/close_pending, opportunity_view and the diagnostic snapshot boundaries.

All11 original private-file hashes, five pre-existing changes, prior blocked report, seven frozen evidence files and retired DB size/mtime remain unchanged. Derived aggregate checks live in a separate ignored audit directory. Source/document secret scan and link/whitespace checks passed. No backend/frontend suite, performance test, network call or live rerun was necessary for this documentation-only audit. No production code, architecture, decoder, threshold or approval control changed.

## Publication

Staging ONLY this report failed because Git metadata is read-only (.git/index.lock). No new commit/push or permission bypass occurred; HEAD remains54e2ef95ad256419808392109d383352b6a08fa1. Publish from a writable WSL terminal:

```bash
git switch remediation/early-edge-evidence-readiness
git add -- backend/docs/controlled-live-observation-wsl-20261025.md
git diff --cached --name-only
git diff --cached --check
git diff --cached
git commit -m "docs: audit controlled WSL observation receipts"
git push origin remediation/early-edge-evidence-readiness
```

Stage only this documentation file. Private receipts and all unrelated changes remain excluded. No main merge, cohort or Phase4 action follows.

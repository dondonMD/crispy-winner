# Required computation profiling and exact preparation reuse — 2026-10-25

PRE_COHORT_READY=NO. Starting HEAD766db221c6e7fe634e93e853ab07b8cc9d63a553. Four pre-existing diagnostic changes are hashed in initial-state.json and preserved untouched. No scheduling/cadence/batch/candidate/queue experiment, provider change, cohort or trading. New work begins with synchronous component profiling on fresh synthetic databases, not120s replays.

## Exclusive profiles and required work

Initial profile,250 candidates/200 warm events, no scheduler/provider task:
-1000 analyse calls:3.706s wall/3.705s CPU. cached_window_features6000 calls/.907s exclusive, raw window_features3280/.796s exclusive. Inclusive feature3.480s overlaps those children and must not be added. Static reuse already avoids2720 raw calls; window membership, half-window, persistence and freshness continue to change with time.
-8 forced refreshes:2.283s CPU.6000 opportunity_view calls/.150s exclusive/.620s inclusive;6000 config loads/1.256s inclusive, including .544s Pydantic deepcopy path. Serializer12000 calls/.190s exclusive; validators12000/.113s exclusive; file open6000/.158s exclusive; JSON encoding6000/.097s. These are separate self times; deep-copy parent/children must not be summed.
-500 real synchronous synthetic trade processes:7.066s wall/5.290s CPU.1000 real SQLite commits2.058s exclusive; feature raw2500 calls/.711s exclusive, cached3000/.406s exclusive. deep_mints500/.174s exclusive, with priority/sort children giving .612s inclusive. No new database optimization inferred from this profile.

A reproducible CLI, scripts/profile_evidence_computation.py, profiles those components and then audits input hashes in a SEPARATE untimed pass. Hashing does not distort reported function profile cost. No raw wallet/config/provider secrets are written; only hashes/aggregate counters. The first audit failed on an existing infinite grad_low sentinel; preserved output. Diagnostic hashes now distinguish nonfinite values internally without changing any business validation. Output metrics remain strict finite JSON. CLI import bootstrap was corrected for existing scripts/profile.py shadowing; static checks cover it.

Corrected profile audit: calculate_features1000 calls,750 unchanged underlying versions,250 exact same-time repeats,500 changed-time calls. Each horizon has only250 unchanged EFFECTIVE classifications; all500 advancing-time calls change membership/half-window/bin classes in this scenario, even where300/600 raw memberships repeat. This directly rejects skipping analysis merely for no new trade.1500 opportunity projections include500 exact repeats at the same resolved input/time, but750 changed times; safe projection reuse across observers would require a full mutation/time key not present today.1500 config parse-input calls share1499 unchanged source contents; the existing content parse cache is already doing that reuse. Every source read must remain for drift detection. Complete Token hashes here are conservative diagnostics, NOT production cache keys.

Analysis must still refresh continuity, score(age), security/lifecycle/economics decisions, state transitions and viability inputs. Post-raw callback work includes actual opportunity acquisition/transition and early-observer coverage, readiness, configuration drift checks and ranking. It cannot be dropped because a projection repeats. Evidence context references are already lossless/deduplicated; hashing an unchanged small context is not identified as a useful bottleneck. Observer timestamps may differ from the event time intentionally; no future/current-time substitution.

## Rejected component candidates

ABBA on real project filesystem, unprofiled:
- cheaper independent configuration copies:10000 loads each, original .732/.743s vs candidate .669/.712s. Whole20-refresh components original3.087/3.135s vs candidate3.098/2.937s. Small/inconsistent whole-component gain; NOT adopted. File reads/deep independence and future schema safety cannot be traded for a misleading cache.
- ranking reuse(empty-position synthetic case):4000 calls, original1.116/1.135s vs candidate1.051/1.008s. Small subset gain, and protected paper/pending-position ordering needs a larger key; NOT adopted. This prototype is not a general production-safe ranking cache.

## Proven reuse candidate and contract BEFORE implementation

The repeated work is event TYPE classification for every horizon: six horizons each scan all events for trades AND priced observations. This classification does not depend on now. The existing complete business-field fingerprint is already revalidated on every calculate_features call. Prepare two immutable ordered tuples ONCE for that fingerprint: all trades, all events with non-None price. Each horizon still filters those tuples against current now, including future timestamps and inclusive boundaries, and runs existing dynamic calculations.

Exact key remains(creator,flow_venue,flow_epoch, ordered tuples of ts/kind/side/wallet/repr(volume)/currency/price). Venue filtering happens BEFORE fingerprint/preparation as before. Invalidation on append, eviction, reorder, business-field/creator/venue/epoch mutation; existing private cache missing prepared inputs rebuilds once. Every call still verifies full fingerprint; no identity/length/last-trade shortcut. No now/health/security/decision is cached. Backward clocks and future-event entry use the original per-call filters. Source tuples hold Event references but their relevant fields are checked afresh; tuple containers are immutable. Newly added unrelated fields cannot silently affect existing feature formulas; consumed-field additions require fingerprint review as before.

Bounds: two extra input tuples, each <= already-bounded Token.events; six existing window slots; <=250 active candidates. No global cache or pending-write buffer. No scheduling, SQL, durability, callback, observer or audit-context operation moves. Standalone cached_window_features without prepared sources keeps its existing behavior. Feature dict/list copies remain independent; caller mutations cannot alter cached values. All score/decision/state/timestamp/accounting equivalence is required, not inferred from WAIT results.

Initial1000-call ABBA prepared-input component: unchanged evidence original1.503/1.149s vs candidate1.047/1.031s; new-trade original1.770/2.062s vs candidate1.863/1.706s (one regression, preserved). Repeat with intended immutable tuples,2000 calls: unchanged original2.486/2.327s vs candidate2.206/2.202s; new-trade original3.900/3.842s vs candidate3.785/3.785s. Exact outputs checked across250 tokens, both existing and appended evidence. Conservative adjacent savings~.063ms per unchanged analysis/~.028ms with new trades. At the prior ~16k periodic+6k trade analyses this suggests only~1–2 CPU-seconds/120s, NOT a demonstrated end-to-end throughput gain. Benefit is small but repeatable enough for this bounded, exactly equivalent preparation reuse; configuration/ranking proposals remain rejected.

Next: focused exact-boundary/mutation/venue/output/engine-record parity tests, component measurement of actual code. Only if those pass may unchanged fixed40/s and up to three fixed50/s120s validations proceed; stop at first qualification failure. No experimental idle option. Same project filesystem/input/durability/cadence; all failed results preserved. No600s unless three complete qualifying short passes; no six-hour or real cohort. PRE_COHORT_READY=NO.

Artifact root: data/early_edge/computation-20261025/ includes all profiles, candidate probes/results and the original audit failure. Synthetic component measurements are not real evidence or throughput acceptance.


## Actual-code result: candidate rejected and production restored

A temporary implementation added only private immutable trade/priced preparation tuples under the existing full fingerprint; all time filters/dynamics remained.29 focused cases passed6.33s, including exact floating boundaries/future entry/clock reversal, every business mutation, venue/epoch/creator/reorder/rolloff, six-slot bounds, legacy cache reconstruction, returned-list independence and standalone caller safety. Two DEMO engines were compared against uncached window_features through ticks0..301: identical features/scores/decisions/states/analysis/event timestamps/rankings, raw records/context references/signals/outcomes/state rows and paper/accounting state. Only independent session identifiers were normalized. One initial mutation fixture assigned the existing side value and failed its invalidation expectation; corrected, with original28pass/1fail output retained.

Actual-code ABBA vs exact HEAD feature module,2000 calls/mode:

|Condition|Original wall seconds(A1/A2)|Candidate wall seconds(B1/B2)|Assessment|
|---|---|---|---|
|Unchanged evidence|2.346 /2.378|2.321 /2.295|Only~1.1–3.5% gain|
|New trade per calculation|4.000 /3.986|3.894 /4.002|One~2.7% gain, one~.4% regression|

An earlier actual-code run overlapped focused tests; it is explicitly ineligible for performance qualification and remains preserved with implemented-overlap-note.json. The serial run above had no competing test/profile work. Prototype results, actual-code results, equality checks and all original source copies are retained. No favourable subset was selected to justify a replay.

This does NOT demonstrate a stable meaningful end-to-end benefit. The forecast~1–2 CPU-seconds/120s was never presented as measured throughput; the actual component results weakened it. Therefore the entire temporary backend/app/features.py change was restored BYTE-FOR-BYTE from the starting commit. Candidate code/diff and parity tests are preserved only in the local artifact directory, not installed as production or default tests. No runtime optimization, input-preparation cache or invalidation rule from that experiment is retained. Config/ranking prototypes also remain unadopted. No120s replay or600s followed because the component qualification condition failed.

## Required callback and evidence costs

In the500-trade initial profile, the post-raw Intelligence.observe wrapper is1.406s inclusive(.0066s self). Its children include ranking500 calls/.612s inclusive, coverage500/.406s, readiness500/.215s, signal_snapshot1000/.302s, pure projects1000/.174s, research.observe500/.051s and save_pending500/.032s. These nest; NEVER add their inclusive values. Research transition returns early for unchanged actions, and save_pending already skips byte-identical committed payloads; mutable pending/outcome/timestamp work cannot be removed just because prices or actions repeat.

Raw context construction scans current degradation/provider/resource state and creates a content-addressed lossless reference. Existing128-entry context cache already avoids repeated context writes, while raw event rows remain unique/durable. Neither an extra context cache nor deferred observer/financial publication is justified by this profile.

Time-dependent obligations: window membership and bins; score age; trade age and clean coverage; security TTL/provider health; lifecycle retreat/stale transitions; resource/financial state; observer's actual acquisition clock; config source reads. All remain exactly as they were. Opportunity projection duplicates are real in same-time refresh subpaths, but the other calls use a different observer time or manual/provider context. Reusing the earlier result across mutable callback state would need a complete key/recheck and independent result copies. No safe worthwhile implementation was demonstrated, and no callback was skipped/deferred.

## Retained diagnostic tool and reproduction

Retained files are scripts/profile_evidence_computation.py, backend/tests/test_computation_profile.py and this report ONLY. No pre-existing files are changed by this task at completion. The tool refuses cohort/PumpPortal selection and out-of-bounds work before creating output. New output directories are exclusive; failed runs are not overwritten.250 candidates max,500 warm events/token max,<=8 analysis passes,<=16 refreshes,<=2000 component trades. No scheduler/provider tasks start; HTTP is forbidden in the unit test. Real engine/client cleanup runs; no forced exit or worker suppression. Profiles retain self/call totals; input audits retain only aggregate counters/hashes with<=2500 previous slots, never wallet/raw payloads or private endpoints. Existing inf/NaN sentinels are distinguished in diagnostic hashes only; all output metrics remain finite strict JSON and no business validation is relaxed.

Example repeat command (choose a NEW output directory):

```
.venv/bin/python scripts/profile_evidence_computation.py --output data/early_edge/computation-profile-new
```

Small smoke/test command:

```
.venv/bin/python scripts/profile_evidence_computation.py --output data/early_edge/computation-small-new --candidates 2 --warm 12 --passes 1 --refreshes 1 --events 4
```

These are synchronous synthetic COMPONENTS, not provider observations, a scheduler experiment, throughput acceptance or prospective outcomes. Output includes source SHA plus exact implementation-file hashes; source metadata alone does not imply a clean checkout. All existing four uncommitted/untracked changes were preserved and recorded before this task. Final quality/preservation/publication outcome follows below.

**No safe worthwhile runtime optimization demonstrated. PRE_COHORT_READY=NO.** Repeated work exists, but some is already cached, some is time/state-required, and the tested reusable classification did not earn retention or expensive replay. Future work must show measured gains and full input/mutation equivalence first; this report does not authorize cadence/scheduler experiments, threshold changes, trading, a cohort or a long run.


## Final quality and preservation

The corrected reproducible CLI also profiled1000 analyses4.165s,8 refreshes2.515s and500 events7.205s. These cProfile-affected component totals vary with real clock/window state and are not performance acceptance trials. All raw/self/call tables and the separate2001-slot input audit are preserved. Diagnostic-key equality is NOT permission to memoize stateful callbacks.

**Full backend846 passed,1 skipped in161.61s, exit0** under the existing explicitly labelled bounded-cleanup diagnostic. Original Runner.close and real worker joins retained; not an unrestricted ordinary-runtime cleanup claim. No new shutdown workaround. Final post-revert focused18 passed2.91s; strengthened profiler HTTP-prohibition tests3 passed1.66s. Candidate parity suite previously29 passed6.33s, with one original28pass/1fixture-fail preserved. No candidate test was falsified to obtain a gain; the rejected candidate-specific tests now live only with its forensic artifacts.

Fresh frontend39 passed6.43s; TypeScript/production build passed(Vite3.88s). Full Ruff passed; mypy47 sources; source secret scan227 files; git diff --check passed. Backend/frontend dependency-audit attempts remain UNVERIFIED due PyPI/npm DNS failures, not clean audits. No dependency manifests, SDK packages or locks changed.

Production backend/app is byte-identical to starting766db22; the four pre-existing changes match their recorded initial hashes. Seven original frozen evidence hashes and retired database size/mtime checked again in preservation.json. No real/retired cohort or historical observation edited, no wallet/signing/sending/trading added. No scheduler/cadence/batch/limit change,120s replay,600s or six-hour experiment. PRE_COHORT_READY=NO.

Only proposed retained files: this report, scripts/profile_evidence_computation.py and backend/tests/test_computation_profile.py. Initial/corrected profiling failures, all component candidates including regressions and overlapped result, temporary implementation/patch, actual serial measurements and equivalence tests remain under data/early_edge/computation-20261025/. Commit/push status is recorded in the final receipt/response only after an actual result; existing commits are not a new publication of these files.


### Final publication outcome

Local HEAD remains766db221c6e7fe634e93e853ab07b8cc9d63a553. Staging ONLY the three new profiler/test/report files failed with read-only .git/index.lock. No new commit, no successful push and no force/main/merge action. Connected GitHub mutation is already known to require approval unavailable under this session policy; it was not retried as a filesystem workaround. The reviewed profiling-tools.patch preserves only these three new files, separate from the four untouched pre-existing changes and rejected optimization artifacts. No clean/new published SHA is claimed. PRE_COHORT_READY remains NO.

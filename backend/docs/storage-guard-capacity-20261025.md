# Storage guard hot-path validation — 2026-10-25

PRE_COHORT_READY=NO. Branch: remediation/early-edge-evidence-readiness. Starting published source: 41a810b5c61e5c047e783dbe14d740368ade51eb. The existing two durable transactions, post-commit proof, counterexample tests, observers, ordering and every evidence/risk gate remain intact. No transaction consolidation or publication re-audit is part of this task.

## Diagnosis before production edits

Fresh baseline: established 120s deterministic project-filesystem workload, 250 candidates, 50 trades/s, 200 warm events/token, existing bursts, recovery and mock quote traffic. 6,000/6,000 persisted, no loss; application p99 4.916s; queue p99 4.420s. Aligned scheduled-minus-durable deficits at 20..120s: 40,68,51,47,76,171,148,148,116,58,97. Slope +.649091 events/s, early-three mean 53, late-three 90.333: unchanged no-growth guard FAILS. No favorable replacement baseline. Commit total 12,112, commit wall 27.833s, trailing-sample p99 14.476ms; mean CPU 67.76%, RSS peak 210.30MiB. Baseline includes drain (122.561s), so committed rows/elapsed is not the offered 50/s.

Production profiling of 3,000 writable(connection=...) calls: .791s instrumented total, .494s inside size, .214s inside exec_driver_sql; 18,000 stat calls. File allocation was freshly checked on both main transaction paths, including an unconditional PRAGMA freelist_count even when allocated bytes alone prove ample budget. The earlier driver-SQL prototype remains rejected; commits are still the I/O floor.

Independent project-filesystem ABBA component probes retain 2,000 commits / 1,000 fixed writes each. Guard-only CPU: current 2.182/1.668s, candidate 1.489/1.575s. Combined guard + identical-file-set allocation CPU: current 2.413/1.858s, candidate 1.312/1.477s. Use conservative adjacent saving .380s/1,000 writes (~2.28 CPU-seconds/6,000), not the larger cold first comparison. Adjacent combined noncommit wall saves .364s/1,000; commit wall itself varies and is not claimed improved. Expected engine benefit is modest (~2% elapsed headroom), not proof of sustained capacity. Probes preceded production changes and are not research outcomes.

## Narrow change and correctness argument

Database.writable still measures live allocation each call and enforces the identical physical reserve first. Since SQLite free-page count is nonnegative, allocated < 70% for raw (85% for essential) proves the same logical result even with zero free pages. Only then may it omit the query; at/above the threshold it performs the existing freelist query on the supplied writer connection and retains all logical guard/censorship decisions. No cached file sizes/free counts, new limits, asynchronous acknowledgement or durability change.

Database.size uses os.scandir and the SAME fnmatch prefix pattern, regular-file and followed-symlink behavior as the old Path.glob sum. DirEntry avoids Path construction and duplicate stat work. Sidecars, matching backups, broken symlinks, directories and literal glob metacharacters are regression-tested. Metadata failures remain errors/fail closed, never assumed zero allocation.

Near-boundary semantic matrix covers fixed/small physical reserves, exact logical/physical boundaries +/-1 byte and multiple free-page counts, with identical legacy allow/censor/error results. Live-size rechecking and no caching are explicit tests. Existing rollback, lost-response proof, replay, SQLITE_BUSY, SIGKILL/cold restart, observer and feature/decision parity tests remain required. Two existing SQL-count assertions change only from two freelist queries to zero when allocation is provably low; transaction/checkout/INSERT counts remain unchanged.

## Predeclared validation plan

Fresh serial 120s 40/s regression, then up to three 120s 50/s trials on one frozen source/config/harness. Stop at FIRST failed 50/s gate. Unchanged p99 application and queue <5s, complete SQL/ledger reconciliation, no unacceptable stale/drops/pending work, recovery completion and real worker shutdown; unchanged aligned no-growth rule (OLS slope <=0 and final-three mean <= initial-three mean after20s warmup). No favorable sampled endpoints or discarded failures. Only consistent complete short-run passes can qualify one bounded 600s synthetic endurance run; no 30-minute or six-hour run.

Artifact root: data/early_edge/storage-fastpath-20261025/ (ignored local synthetic evidence). Frozen historical artifacts and retired cohort are not used as mutable test inputs. Final measured outcomes, quality results and publication status follow below.


## Frozen-overlay results (all synthetic)

Git staging failed with `.git/index.lock: Read-only file system`. No new commit or push exists. To avoid falsely labelling patched code as published HEAD, each driver receipt references the complete `source-overlay.json` file/hash inventory. Its base is 41a810b; the replay driver checks that every tracked/unignored source file and Git HEAD stay unchanged before/after each child. This is an explicitly uncommitted frozen overlay, not a clean committed source. Configuration/harness/source end checks also pass. Final engineering documentation is expanded only AFTER timed replays finish.

| Metric | Fresh baseline 50/s | Optimized 40/s | Optimized 50/s #1 | Optimized 50/s #2 |
|---|---:|---:|---:|---:|
| Declared input duration, s | 120 | 120 | 120 | 120 |
| Committed / submitted | 6,000/6,000 | 4,800/4,800 | 6,000/6,000 | 6,000/6,000 |
| Committed rows / elapsed incl drain, /s | 48.955 | 39.489 | 49.237 | 49.047 |
| Application p50 / p95 / p99, s | 2.133 / 4.322 / 4.916 | 1.074 / 1.738 / 2.273 | 1.519 / 2.248 / 2.501 | 1.599 / 2.346 / 2.548 |
| Durable p50 / p95 / p99, s | 2.143 / 4.334 / 4.925 | 1.085 / 1.748 / 2.280 | 1.530 / 2.258 / 2.508 | 1.609 / 2.356 / 2.557 |
| Queue-wait p99, s | 4.420 | 1.667 | 2.358 | 2.409 |
| Queue peak | 251 | 103 | 148 | 139 |
| Guard cumulative wall, s | 5.512 | 1.458 | 1.746 | 1.749 |
| Freelist queries | 12,078 | 0 | 0 | 0 |
| Total DBAPI commits | 12,112 | 9,742 | 12,111 | 12,112 |
| Commit cumulative wall, s | 27.833 | 23.105 | 26.064 | 25.876 |
| Commit p99, ms | 14.476 | 13.672 | 12.330 | 12.144 |
| Mean process CPU, % of one core | 67.76 | 67.90 | 68.19 | 68.89 |
| Peak RSS, MiB | 210.30 | 208.55 | 210.63 | 210.68 |
| Sampled WAL peak, bytes | 218,392 | 206,032 | 234,872 | 197,792 |
| Final DB before restart, bytes | 17,256,448 | 14,663,680 | 17,244,160 | 17,256,448 |
| Stale / dropped / pending trades | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| Gate result | FAIL growth | PASS regression | PASS | FAIL growth |

Guard time fell by ~68% in both target-rate repeats; no reduction of commit count, SQLite durability, allocation sampling frequency or risk/evidence thresholds. CPU totals and elapsed-through-drain throughput improve only modestly and remain variable. Do not attribute all p99 improvement to this patch or claim 50/s capacity from offered input rate alone. Commit quantiles are the last bounded 8,192 samples; cumulative counts/time cover all calls. Stage timers can nest and must not be added as exclusive CPU.

Both before/after runs use WAL, synchronous=NORMAL, busy_timeout=5000ms, autocheckpoint=32 and 4096-byte pages. Measured databases stayed below the unchanged 1GiB budget; near-guard censorship/rollback and pinned-reader WAL behavior are tested separately. WAL/SHM return to zero after clean shutdown.

### Exact aligned no-growth decision

Trial #1 deficits at20..120s: 66,75,47,68,62,39,55,67,39,37,43. Slope -.272727 events/s; early mean62.667, late39.667: passes.

Trial #2 deficits at20..120s: 44,66,44,57,60,67,69,45,77,41,75. Slope +.126364 events/s; early mean51.333, late64.333: fails. The mid/final deficits oscillate; this is not evidence of runaway backlog. It is still a failure of the unchanged qualification rule, and no favourable sampled endpoints replace it. Queue peak and p99 are lower than baseline in BOTH trials, but three consistent complete passes are NOT established.

The driver stopped at this first optimized failure. Trial #3, 600s and all longer tests were NOT run. Complete failure evidence remains alongside passes. No benchmark was discarded or rerun to obtain a favourable outcome.

### Durable and terminal reconciliation

Independent read-only SQL finds exactly one raw trade row, unique event ID and trade identity per submitted trade in every run. Additional 250 raw rows/run are create records. All event dispositions reconcile; no stale/incoming/evicted/critical drops or detached/pending trade work remains. Recovery 84/84 succeeds/run, no pending/overflow/expiry; normal process exit 0, zero remaining workers, cold-restart integrity ok. Each run records one intentional global shutdown reset and zero token-local resets. No raw omission/reclamation during these short tests. Cohort rows remain zero; synthetic decisions/evidence are not prospective observations.

The two-transaction design/counterexamples, exact post-commit proofs and callback/financial transaction behavior are unchanged. Existing restart semantics remain conservative: restored candidate windows empty and security requires refresh. This optimization does not repair or conceal the previously documented identity-only crash window.

## Regression, quality and publication

Initial focused run: one new fixture failed because a 1MB test budget's fixed 256KiB physical reserve was reached before its intended logical test boundary; 50 other cases passed. Corrected fixture to a 10MB budget, leaving production limits unchanged. Standalone new cases:5 passed. Final focused suite: **51 passed in12.50s**. Tests cover exact legacy decisions across boundaries/free counts, live allocation rechecks, matching-file-set equality including sidecars/symlinks/glob metacharacters, metadata failure rollback, existing transaction/replay/busy/crash/observer/parity/accounting and pinned-WAL/censorship cases.

Frontend **39 tests passed**; TypeScript/production build passed. Ruff passed; mypy45 sources passed; source secret scan217 files and git diff --check passed. Full backend and fresh audit outcomes are recorded after completion below. No new dependency or manifest/lockfile change.

Changes: backend/app/db.py (budget decision fast path and equivalent allocation measurement); backend/tests/test_storage_guard_fastpath.py (five regression cases); backend/tests/test_trade_hotpath.py and test_trade_writer_transactions.py (only low-allocation query-count expectations); this report. No engine, decoder, configuration, research/paper/strategy gate or financial behavior changed.

Publication remains blocked by read-only .git. No attempt was made to bypass filesystem permissions, synthesize alternate remote history, force-push or push uncommitted files. Published HEAD remains the user-provided41a810b; exact file hashes in the overlay and local evidence make this work reviewable, but do not substitute for a validated commit.

**PRE_COHORT_READY=NO. Sustained 50/s no-growth acceptance remains NOT ESTABLISHED.** The measured guard overhead reduction is worthwhile and regression-tested, but does not close the end-to-end capacity gap. Remaining limits are the unchanged two-commit I/O floor and finite-run timing/filesystem variability; their relative contribution to the residual13-event late-minus-early mean is not established. No threshold/criterion was relaxed. No real cohort, trading or long readiness run was started.


### Final quality and preservation receipt

Complete repository-root backend suite: **829 passed, 1 skipped in152.45s**, exit0, using the existing explicitly labelled bounded-cleanup diagnostic. Original Runner.close and real worker joins are retained; this does not claim an unconditional ordinary-runtime pass outside the known sandbox socketpair EPERM environment. No worker/cleanup application code was changed. Frontend39 passed in6.86s; TypeScript/build passed (Vite3.87s). Full Ruff, mypy45 sources, secret scan217 files and whitespace checks passed.

Fresh installed-backend dependency audit failed on PyPI DNS; frontend audit failed on npm registry DNS (EAI_AGAIN). Both are UNVERIFIED, not passing, and the failure outputs are retained. No dependencies or locks changed. Seven frozen evidence hashes match; retired database remains1,073,893,376 bytes / mtime_ns1792471574652367761. No prospective cohort was created or touched.

Exact benchmark identity is preserved: harness b961081bd30ffb547d0a2f208b4ec81e318d58b3179a572c1d9a1e6933c584ed; settings88165dc561fc75ab068452f62079ae275a03997c166512e2c3bd01266fe5d684. All50/s runs use workload3f426da15fc972ec62d5141b9e9317ce41ddf2546c3e4f552600553c23a3254d. No code/config/harness drift during runs; only this report changed after measurement. `comparison.json`, source-overlay inventory, gate/process receipts, probes, all run databases and quality outputs remain in the artifact root. SQL identity/raw/ledger reconciliation is independent of mere queue acceptance.

Final source remains an uncommitted reviewable overlay on published41a810b5c61e5c047e783dbe14d740368ade51eb. `.git/index.lock` creation failed (read-only filesystem); no new commit SHA exists and nothing new was pushed. Exactly three tracked modifications and two new files comprise the patch. A local `reviewable-uncommitted.patch` and final receipt preserve the complete proposed change without bypassing permissions. This publication limitation is separate from the remaining capacity criterion failure.

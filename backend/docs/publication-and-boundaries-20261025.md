# Public backup audit and transaction continuation — 2026-10-25

PRE_COHORT_READY=NO. Approved branch only: remediation/early-edge-evidence-readiness. Verified starting clean HEAD7bdab3024117366508fa498e9cddbea312bdca8b (the already validated successor of7a265da). Remote is the expected credential-free HTTPS URL for dondonMD/crispy-winner. No main push, branch merge, force push or history rewrite authorized or performed.

## Phase0: audit before publication

Audited EVERY commit/tree/blob reachable from starting HEAD, including deleted files:73 commits,511 unique text blobs,6,555,619 total blob bytes (largest139,122).38 commits were absent from locally cached remote refs. Pattern/path/magic scan found no credentials, credentialed URLs, known token patterns, wallet key material, tracked private databases, binary artifacts, data/log outputs or private-tool directories. Commit messages were also scanned. Only data/.gitkeep and logs/.gitkeep are tracked in those local-output trees. `.env.example` is a template, not an exemption from content scanning. SDK quote goldens and IDLs are source/test fixtures, not private research rows.

Manual publication review: engineering documents contain aggregate operational findings and references/hashes for ignored local evidence, not raw wallet lists, private database exports or per-signal research outcomes. The tracked prospective validation JSON is explicitly synthetic. No investigation branch was merged; only approved branch ancestry is in push scope. Public provider/program documentation and synthetic fixtures are not credentials. No scanner can prove all possible secret formats absent; limits/manual review are explicit. gitleaks/trufflehog are not installed; no unreviewed package was installed to substitute for the audit.

New scripts/audit_public_history.py preserves a reproducible, read-only bounded scan (<=2,000 commits,20,000 blobs,2MiB/blob,64MiB total) and emits only categories/locations/hashes, never matched values. Three tests prove detection of subsequently deleted secrets/databases, unsafe template contents and restricted paths. Source secret scan and ignore checks also pass. All reported matches would block publication; none were suppressed as false positives.

.gitignore had gaps for .env.* and SQLite variants. Added environment variants/private tool credentials, *.sqlite*, disposable profile/temp/log/coverage outputs, while retaining public .env.example.11 exact ignore checks passed. Existing tracked history had no sensitive file hidden by these changes; adding ignore rules is not history sanitization.

GitHub connector confirms repository is public, remote main still2bebbf2863de21041fffca80fb99507356a815b6; approved remediation ref absent (search empty and exact git-ref GET404). Local git ls-remote fails DNS resolution. Publication status below must be updated only from an actual push result; remote existence/main verification alone is NOT a backup.

### First authorized push result

After hardening commit5560b263d279da2e19d35ab130fc91e0188f1dc4, reran the full reachable-history audit:74 commits,515 blobs,6,566,909 bytes; no findings. Rechecked remote main via connector (unchanged) and exact remediation ref (404). Executed EXACT authorized `git push -u origin remediation/early-edge-evidence-readiness`: exit128, could not resolve github.com; no upload/branch creation. Remote approved-branch SHA is null, NOT the local SHA. The connector can read remote state, but its create_commit interface lacks original author/committer timestamps and cannot upload this exact local commit history. No alternate history/ref was synthesized as a substitute. Publication remains network-blocked, not successfully backed up.

## Phases1–3 continuation from already validated HEAD

Do not undo completed96e93a3: the current identity/raw Core adapters and exact post-commit read proofs already passed55 focused cases and817 backend tests/1 skipped (diagnostic cleanup). The current engine still has two commits/event with independently committed transitions, collector/financial records, context and opportunity writers between/after them. Migration0005 adds immutable context/reference receipts, not an event-wide transaction or foreign-key link between identity and raw records. OutcomeCollector and prospective on_record/persist_pending have distinct transaction ownership; routing just the initial two writes into one outer transaction does not route those intervening writes or roll back their memory.

Added real-SQLite counterexample tests (not production paths):
- An outer uncommitted identity INSERT causes an existing separate-Session negative-outcome write to hit SQLITE_BUSY; the outer identity rolls back. Test-only busy_timeout10, production5000 unchanged.
- Moving identity reservation after a durable negative outcome permits the same outcome to be appended again after restart. The early-reservation control suppresses replay and retains exactly one negative outcome. This demonstrates why neither naïve merge is safe; it does not claim that an eventual fully staged unit-of-work is impossible.

Relevant focused audit/boundary/current-writer tests:24 passed in6.01s. No production code, strategy/config, observers, SDK schema or freshness changes in this continuation.

Evaluated driver-level bound SQL within existing transactions on project ext4,500 pairs ABBA: current CPU1.278/.903s vs candidate1.082/.839s, same1000 commits, almost identical commit wall time within each adjacent pair. Saving7–15% of a low-level subset is small/variable and dwarfed by observed whole-run I/O variation; it does not establish sustained50/s. Direct driver binds also require preserving explicit Float conversion/type behavior. Candidate remains an ignored diagnostic only; NOT adopted into production. Avoid another speculative micro-optimization while the two-commit floor and cross-component rollback problem remain.

Next measurements use the SAME production source as7bdab30, fresh project-filesystem DBs, unchanged250 candidates/200 warm events/20s freshness/burst/recovery/cadence/durability. Reuse the predeclared120s40/50 driver and stop at first50/s failure; only three fully passing50s trials could qualify further review. Existing aligned no-growth guard (slope<=0 and late-three mean<=early-three after20s) stays fixed. All results, including failure, will be preserved;600s remains conditional and PRE_COHORT_READY remains NO.

### Publication recovery — 2026-10-25

GitHub DNS and remote connectivity were restored from the user's WSL terminal.
The audited development branch was successfully published using
`git push -u origin remediation/early-edge-evidence-readiness`.
Git confirmed creation of the remote branch and configured upstream tracking.
The earlier DNS-blocked push remains documented above as historical evidence.

This publication does not establish PRE_COHORT_READY.
PRE_COHORT_READY remains NO. No cohort or trading was initiated.

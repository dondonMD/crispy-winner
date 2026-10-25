# Evidence approval boundary correction — Phase 2A, 2026-10-25

PRE_COHORT_READY=NO. Source:1f222658cf894c5f02a9b50d5b4daa6427758366, remediation/early-edge-evidence-readiness. The serial architecture, thresholds, quote assumptions, schemas, transaction boundaries and historical research remain unchanged. No cohort, acquisition run, trading or performance experiment was started.

## Root cause and reproduced unsafe acceptance

[cli.main](../app/cli.py) previously handled freeze-evidence by calling [evaluation.evaluate](../app/evaluation.py), a retrospective chronological50/25/25 analysis. Positive validation/holdout status, no missing outcomes and no capacity flag permitted writing an ordinary Record(kind=evidence) containing version, mode and holdout. Those checks did not establish prospective enrollment, frozen protocol identity or independent approval.

[RadarEngine.__init__](../app/engine.py) then selected a stored evidence row using only matching strategy version and DEMO-versus-real class; OBSERVE/PAPER/MANUAL ASSIST were not exact mode matches. It assigned the supplied holdout to approved_evidence. analyse passed its expectancy to PositionSizer and its count/lower_ci to evaluate_candidate. Companion independently checked those numbers, but not their provenance. Thus positive retrospective or fabricated records could satisfy the statistical gate while leaving all other gates in place. This was an authorization defect, not evidence that any particular historical entry actually occurred.

A regression was written and executed BEFORE the fix. It inserted a synthetic positive retrospective record into a temporary SQLite database, stopped the engine normally, and restarted it. Expected approved_evidence=None failed: the engine loaded count200/lower_ci2/expectancy5. Preserved diagnostic: data/early_edge/approval-boundary-20261025/before-fix.txt, **1 failed in1.94s**. No actual cohort/database was used.

## Smallest safe correction

Only two production files change:

1. cli.py rejects freeze-evidence with argparse exit2 immediately after argument parsing, before dotenv/settings/engine construction, evaluation, output creation or any database write. The error directs users to descriptive evaluate and states that prospective approval needs a separately validated protocol/independent control. Keeping the old command as an explicit error is preferable to silently giving it a new authorization meaning.
2. engine.py no longer reads evidence records into approved_evidence at startup. It initializes to None regardless of legacy status, purported provenance, positive statistics, matching version/config, mode or APPROVED flag. No parser or boolean in an arbitrary record is a replacement authority. Both DEMO and real stored approval records are ignored; isolated pure DEMO fixtures remain unchanged.

The existing economic/gate behavior already fails closed: absent approved evidence gives no historical edge to PositionSizer, economically allowed position_size_usd=0, and the statistical WAIT. proposed_position_usd remains an estimate for research; it is not authorization. Hard risk rejections and MISSED can still take precedence when applicable. No concentration, maturity, momentum, freshness, cost or continuity gate changed.

There is currently **no enabled startup approval route**, even for an apparently complete prospective record. This deliberately does not implement a partial provenance validator. The system can safely distinguish stored unapproved research from authority by refusing the latter; it cannot yet certify a prospective result as eligible authorization. That remaining capability requires its own reviewed implementation.

## Approval contract

### A. Descriptive research

Retrospective evaluation, opportunity reports, strict prospective reports and early-edge reports remain research outputs. Positive mean, positive normal/bootstrapped intervals, HOLDOUT/APPROVED labels, statistical report status or stored rows independently grant no authority. Existing evaluate/replay/optimize behavior is retained. This patch does not relabel, edit, delete or migrate research rows.

### B. Future evidence eligible for consideration — required, not implemented

A future approval protocol must independently verify at least:

- **Identity:** immutable protocol/cohort ID and digest, enrollment source Git SHA and relevant source hashes, complete strategy/configuration/opportunity/quote/cost identity as applicable, exact mode and DEMO isolation. Any allowed source transition needs explicit compatibility review, never silent adoption of the current code hash.
- **Prospectivity:** manifest predates every enrolled signal; immutable signal-time snapshots, first-eligible token/session rules, no retrospective enrollment/backfill/future leakage, exact predeclared primary horizon/latency/notional, valid enrollment closure and matured primary outcomes. Historical split membership does not prove these boundaries.
- **Sample acceptance:** verify accepted sample criteria from source observations and immutable enrollment ledgers, not row totals. Deduplicate correlated repeats, preserve unmatched controls and negative outcomes, and validate strategy-specific quality requirements without excluding failed outcomes after seeing results.
- **Completeness/quality:** reconcile every enrollment through measured/economic outcome or explicit unavailable disposition; independently verify coverage denominator, pending work, gaps/provider/resource metadata, retention/storage-censorship receipts and integrity of referenced evidence. Missing or censored evidence cannot silently count as complete. An unsupported economic-zero claim is not a measured loss.
- **Statistical protocol:** retain current minimum sample, edge/sizing and positive lower-CI gates; honor the chosen protocol's independent validation/holdout requirements. Retrospective50/25/25 results remain descriptive. Early-edge's100/30-day,10s/300s/$4 paired mint-bootstrap protocol is a different signal population and cannot be promoted into strict post-grad approval. A successful early report does not validate the strict strategy.
- **Independent control:** explicit separately authorized review binds an auditable approval decision to the verified protocol/result/source identities. A caller-controlled flag, hash over untrusted input or arbitrary database record is insufficient. Authority distribution, revocation, corruption/tamper handling and startup revalidation need a defined trust root and negative tests before enabling consumption.

No combination of these conditions is automatically sufficient for guaranteed profitability. Report eligibility is distinct from approval, and approval would still not bypass current risk/economic/quality gates or enable live execution. No real prospective cohort is created to test this contract in Phase2A.

## Historical compatibility and scope

All old evidence/evaluation/signal/outcome/strategy rows remain inspectable and unchanged. The behavior change is solely that persisted approval data cannot authorize a new running engine. Frozen source experiments and the retired infrastructure-censored cohort are preserved; no backfill or upgrade of their evidentiary status occurs.

OutcomeCollector, ProspectiveCohort and the separate early-edge integrity/statistics code were inspected and remain unchanged. Their reporting/inclusion semantics do not become an approval route. Evaluation metrics and historical strategy versions are not rewritten.

Historical replay explicitly restores recorded context.evidence inside its own temporary offline engine/database. This is retained for faithful reproduction of old decisions, not a production startup loader or an approval writer. The pure evaluator and sizing functions still accept explicit numerical evidence as calculation inputs; tests and explicitly labelled DEMO fixtures can exercise all gates. They are not provenance-verification APIs. No public data-record deserialization now supplies those inputs as startup approval. This patch is not protection against arbitrary trusted Python code mutating the engine in memory.

All SQL writers, identity/raw-event commits, uncertain-commit proof, observer callbacks, financial journal and crash/replay mechanics are untouched. No write queue, new migration, new retention behavior or asynchronous approval process was introduced.

## Regression coverage

New [test_evidence_approval_boundary.py](../tests/test_evidence_approval_boundary.py) covers:

- Positive retrospective evidence rejected on real SQLite stop/restart while its row remains byte-equivalent through normal DB decoding.
-32 combinations of OBSERVE/PAPER/MANUAL ASSIST/DEMO with positive forged approval flags, purported verified prospective provenance, wrong strategy/config, DEMO/other-mode rows, missing outcomes, storage/recovery censorship and malformed holdout. All remain unapproved; no paper trades and default cash unchanged.
- Disabled CLI fails before engine construction, dotenv or evaluation/output. There is no secret/config/database side effect from the rejected command.
- Otherwise eligible synthetic candidate has zero economically allowed size, preserved proposed research size, WAIT and Companion WAIT without approval.
- Descriptive evaluate still writes only its evaluation/output and cannot approve even a positive result. This unit isolates CLI dispatch; actual engine/database behavior is exercised by restart regressions and the existing suite.

No positive persisted-approval fixture is provided because no authorization verifier exists. Positive coverage proves continued descriptive evaluation and existing pure gate/DEMO/replay behavior; it does not manufacture a legitimate cohort or an approval shortcut.

Initial post-fix focused result: **36 passed in6.00s**. Applicable complete-suite/static/frontend outcomes and publication status follow after completion. A printed assertion summary without normal process exit is not an unconditional full-suite pass.

## Preservation and remaining limitations

Initial receipt data/early_edge/approval-boundary-20261025/initial.json hashes all five pre-existing worktree files, the published ADR and Phase1 audit, plus seven original frozen evidence files. Retired database size/mtime is recorded without opening it for writes. No unrelated work is staged or edited.

This fix closes the known database-to-startup trust boundary by disabling approval consumption. It does not solve provider completeness, sustained processing capacity, PumpSwap undocumented layout, research sampling/quotes, cost-model validation or prospective statistical evidence. PRE_COHORT_READY remains NO. Phase2B/other audit findings are not started.

## Completed validation

- New boundary suite:36 passed6.00s. Original before-fix failure preserved separately, not overwritten.
- Complete backend under the EXISTING bounded-cleanup diagnostic: **882 passed,1 skipped in162.36s, exit0**. This runs the full collected suite, including observer/evaluation/replay/paper/writer/checkpoint/rollback/cold-restart regressions and the new36 cases. Official Node reference remains opt-in; ordinary tests use goldens.
- Ordinary `python -m pytest -q` invocation: **timeout300s, exit124**, stalled at roughly32%. This is not a clean full-suite pass and does not establish a new cause beyond the previously documented restrictive-runtime cleanup issue. The separate diagnostic retains original asyncio.Runner.close and real executor joins, supplying bounded loop-wakeup timers; no cleanup bypass/application runtime change was made. Its success is not unrestricted normal-runtime cleanup qualification.
- Frontend39 passed6.44s; TypeScript and production build passed(Vite3.85s), exit0. No frontend modification.
- Full Ruff backend/scripts passed; mypy42 application source files passed; basic secret scan230 source/document files passed; tracked and explicit new-file whitespace checks passed.
- Dependency audits remain **UNVERIFIED**: npm audit failed DNS(EAI_AGAIN); corrected installed-environment pip-audit failed PyPI DNS. An initial no-deps requirements attempt was invalid because requirements are ranges, and is preserved as a command failure, not an audit. No package manifest/lock/dependency was changed or installed.
- Five original worktree changes, published ADR/audit, seven frozen evidence hashes and retired DB size/mtime are rechecked. No historical DB was opened for writes; all new test DBs are isolated temporary synthetic data. No actual prospective cohort or outcome was created by this task.

**Result:** the identified persisted-research approval path is closed. Legitimate prospective approval is still unavailable, rather than inferred from a favourable report. Unrestricted ordinary backend cleanup and online dependency-audit completion remain separately unverified. PRE_COHORT_READY=NO. This ends Phase2A.

## Publication result

Staging ONLY the four tested Phase2A files failed: read-only .git/index.lock. No commit/push, permission workaround, main change or force action. HEAD remains1f222658cf894c5f02a9b50d5b4daa6427758366. The five pre-existing changes are unchanged and must remain outside the Phase2A commit.

From a writable WSL terminal, review and publish only this boundary correction:

```bash
git switch remediation/early-edge-evidence-readiness
git add -- backend/app/cli.py backend/app/engine.py backend/tests/test_evidence_approval_boundary.py backend/docs/evidence-approval-boundary-fix-20261025.md
git diff --cached --name-only
git diff --cached --check
git diff --cached
git commit -m "fix: disable unverified research evidence approval"
git push origin remediation/early-edge-evidence-readiness
```

Verify the staged list contains exactly those four files. No other audit phase is initiated.

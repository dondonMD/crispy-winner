# Quote receipt validator and attempt ledger — 2026-10-25

**Offline components implemented. No provider adapter activated, no pilot/cohort created. PRE_COHORT_READY=NO; Phase4 unauthorized.** Baseline `0a55bade72d3a88f5903299d7c18a513c45af94e`, remediation/early-edge-evidence-readiness.

## Exact scope

Four new files only:

- [early_edge_quote_receipts.py](../app/early_edge_quote_receipts.py): pure provider-neutral structural validation.
- [early_edge_attempts.py](../app/early_edge_attempts.py): separate append-only pilot attempt database.
- [test_quote_receipts_attempts.py](../tests/test_quote_receipts_attempts.py): deterministic synthetic/offline tests.
- This report.

No existing application, research, cohort, decoder, UI, strategy, cost assumption, security/freshness/continuity gate or approved_evidence code changed. These modules are not wired into normal monitoring or any outcome collector. There is no network client, wallet, signing, order or P&L generation. Existing strict and research paths remain separate.

## Receipt contract v1

`validate_receipt(payload, context, now)` compares an untrusted normalized receipt against a separately trusted request/identity Context. Strict frozen models bound fields, amounts and fee arrays; extra fields, unknown execution profiles and state-derived hypothetical quote types reject. Errors return fixed reasons, never raw validation/exception strings.

|Requirement|Implemented behavior|Offline evidence|
|---|---|---|
|Source identity|Exact provider/source-version/quote-version match; adapter, response and source evidence SHA256 references|Source mismatch and sensitive-text rejection tests|
|Actual times and validity|Request<=response<=validation time; provider quote timestamp within request/response, OR exact separately verified slot/context hash with acquisition within that interval; authoritative time expiry strictly after validation|Before-boundary, late, future/stale provider time, absent expiry and exact-context tests|
|Units and amounts|Nondefault canonical pubkeys; expected base/quote/decimals and exact input raw integer; only proven SOL/USDC quote units; positive u64 output and minimum output consistent with frozen slippage intent|Wrong units/amount, unknown quote and slippage tests|
|Direction/venue/lifecycle|Exact expected venue/address/direction; pre-grad Pump address must be canonical curve PDA; PumpSwap exits require independent pool context plus canonical migration evidence reference; migrated BUY unsupported in this protocol|Pump/PumpSwap buy/sell and missing migration tests|
|Route and supported conditions|Route explicitly available with evidence reference; only reviewed classic SPL/no freeze/hook/transfer-fee/restrictions profile in v1|No route, unknown conditions and hypothetical-quote rejection tests|
|Fees|Exactly eight unique components: protocol, creator, LP, platform, network, priority, transfer, rent. Explicit embedded/external/lockup/not-applicable/unavailable treatment; known amounts have mint/decimals and evidence; unavailable never becomes zero|Unknown cost makes route structurally valid but receipt economically unaccepted; missing/duplicate fee coverage rejects|
|Endpoints|BUY request at/after T+10, response/validation by T+20; SELL at/after signal-relative declared60/180/300/600/1800 horizon, by horizon+20. Already expired responses cannot qualify|Boundary/deadline and all-horizon tests|

Request input amount must be independently derived from the frozen USD4 intent/reference for BUY and the selected acquired quantity for SELL. Context binds USD-reference and cost-policy hashes; this validator does not authenticate those references or calculate currency conversion. The existing reviewed sizing/quote math is not replaced.

Fees have no invented defaults. NOT_APPLICABLE requires explicit zero plus evidence; only rent can be marked recoverable lockup. Missing known costs reject economic acceptance, with `route_valid=True` available to distinguish route delivery from cost completeness. No cost arithmetic is performed here, so embedded costs are not silently recharged. Frozen slippage/failure allowances and USD normalization remain separate measurement-policy requirements.

Success means **QUOTE_ACCEPTED**, never MEASURED, executed or profitable. Every Result has `outcome_authorized=False`. Structural validation cannot authenticate a provider or prove account facts merely because a caller supplies hashes or flags. A reviewed adapter must authenticate the source, inspect canonical identities/conditions independently, archive the referenced evidence and populate trusted Context. The expected source versions cannot be learned from the untrusted receipt itself.

## Durable attempt accounting

`AttemptLedger` creates only `ee_attempt_meta` and `ee_attempt_events` in a new isolated namespace. Foreign research/core/cohort DBs are refused before write/DDL. Protocol hash and event bound are immutable; drift refuses reopening. Linux/WSL advisory file locking permits one serial owner. SQLite WAL, synchronous FULL and explicit commit-before-return provide durable acknowledgement; no write transaction spans network work, no worker or asynchronous write queue exists.

Pilot integration contract (not activated here):

1. Call `begin` **before** eligibility/filtering, matching or provider work. Stable attempt, logical observation and evidence identifiers are SHA256 references, not arbitrary strings. Archive the immutable source snapshot/request evidence before referencing it; an unresolved evidence reference is not sufficient for a later economic evaluation.
2. Finish signal/control attempts as eligible, ineligible with a fixed risk/units/readiness/freshness/lifecycle reason, matched, unmatched or eligible-but-not-selected. Every considered control must be counted, not just the selected one.
3. Call `quote` for entry/exit attempts. It validates and atomically commits the terminal status plus bounded sanitized normalized receipt/Context when parsing succeeds. It also checks that receipt request time equals the durably recorded BEGIN time. Invalid raw payloads are not retained. Use explicit missing-receipt, timeout/rate-limit, cancellation or unsupported-condition reasons when no normal response exists.
4. Retries use new attempt IDs but the SAME logical endpoint key. That key must bind session, token, signal/pair, direction, latency and horizon. The ledger counts attempts separately from distinct logical observations. Only the first valid receipt per logical endpoint/stage is selected; a later better quote is stored as QUOTE_NOT_SELECTED. It cannot replace the first receipt or create an independent favorable sample.
5. Same-ID delivery produces an additional duplicate receipt, not another primary attempt/outcome. Identical parsed quote replay is ignored even after expiry; it never becomes a fresh quote. Conflicting content is recorded and raises. Malformed replay is explicitly UNVERIFIABLE, not falsely certified identical.
6. Graceful `shutdown(at)` terminally records outstanding work as CANCELLED. Reopening an unfinalized ledger records PROCESS_INTERRUPTION for pending attempts, with no resumption/backfill. Plain `close()` only releases resources; callers must use shutdown for a clean cutoff. Original terminal rows are never rewritten.

Each row has a previous-row hash and content hash, with UPDATE/DELETE rejection triggers. This detects accidental corruption/ordinary mutation; it is not cryptographic authentication against a hostile database administrator. State/outcome/cohort tables do not exist here. Direct public finish cannot manufacture QUOTE_ACCEPTED; the validated quote path is required, and still grants no outcome or approval.

Capacity is64 pending attempts. An excess attempt is first recorded, then terminally censored; its denominator remains. The immutable event ceiling defaults10,000 (maximum10,000), including duplicates. One slot is reserved for a censorship receipt; on reaching it the ledger records STORAGE_CENSORSHIP and stops. No retention/deletion or automatic new database is used. Outstanding attempts remain explicit in summary after censorship and must not be described as complete. Normalized quote/context storage is capped12KiB per row; malformed provider traffic is not archived. This is an event/record-size bound, not a guaranteed filesystem byte quota; a future pilot must retain existing storage monitoring. Physical disk failure can prevent writing even censorship: exceptions propagate without a success acknowledgement, and the caller must stop.

`summary` reports unique attempts, logical observations, terminal dispositions, pending attempts, duplicates/conflicts/unverifiable duplicates and censorship. For properly used IDs, terminal dispositions plus pending reconcile to unique attempts; repetitions do not inflate independent observations. Caller-owned source references, evidence completeness and session quality still require audit before any research inference.

## Validation and remaining compatibility requirements

- Combined targeted run: **92 passed in16.59s**, normal exit0, including existing research-contract, matched-control/deadline and approval-boundary regression tests.
- After final control-selection/malformed-replay and USDC cases: new component suite **40 passed in1.40s**, exit0. Counts overlap; they must not be added as independent tests. No unrelated full-system suite or performance experiment.
- Ruff passed; mypy44 application files passed. Secret, whitespace, link and preservation checks completed before delivery. No dependency additions, installations, frontend changes or live quote calls.
- Tests include known/unknown fees, expiry, missing response, missing route/units, source/venue/context mismatch, first-valid selection, late duplicate, immutable rows, insert failure rollback/retry, cold restart, actual child-process exit, single-owner lock, protocol drift, capacity/storage guard and foreign DB byte preservation. Missing/expired evidence never yields a measured return or approval.

**Remaining before any separately authorized pilot:** choose/review a read-only provider adapter; establish its real source/authentication and expiry semantics, exact-in/net-output/fee conventions, account/program compatibility and quote availability for both directions; prove its independent identity/conditions/USD-reference evidence and archive resolver; freeze the pilot protocol hash and stable ID construction; wire begin-before-filter accounting and explicit shutdown/storage failure handling into that isolated pilot. Slot-only expiry, Token2022/extensions and multihop/unrecognized venue profiles remain unsupported in v1, not guessed. Compatibility is UNVERIFIED, not implied by synthetic fixtures. No real cohort is authorized.

## Guarded publication

Five unrelated working-tree files, frozen originals, private receipts and retired database metadata are preserved. Ignored receipts: `data/early_edge/quote-contract-20261025/`. Git metadata remains read-only; no commit/push or bypass. In writable WSL, inspect before publishing only these four paths:

```bash
test "$(git branch --show-current)" = remediation/early-edge-evidence-readiness || exit 1
test "$(git rev-parse HEAD)" = 0a55bade72d3a88f5903299d7c18a513c45af94e || exit 1
if ! git diff --cached --quiet; then echo "Stop: unrelated staged changes exist"; exit 1; fi
git add -- backend/app/early_edge_quote_receipts.py backend/app/early_edge_attempts.py backend/tests/test_quote_receipts_attempts.py backend/docs/quote-receipt-attempt-ledger-20261025.md
git diff --cached --name-only
git diff --cached --check
git diff --cached
git commit -m "research: add quote receipt validator and attempt ledger"
git push origin remediation/early-edge-evidence-readiness
```

Verify exactly four staged paths; never stage private data or the unrelated five changes. No main merge or force-push. **Components validated offline; provider compatibility and prospective usefulness remain unproven. PRE_COHORT_READY=NO. Phase4 unauthorized.**

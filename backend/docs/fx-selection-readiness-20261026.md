# Fresh-cache/demand/fairness FX policy — release qualification

PRE_COHORT_READY=NO. Phase4 unauthorized. Operational readiness is not predictive profitability.

Implementation reviewed against published baseline `d2a76b7ccb8f25f418b976714906b9ad23837a42`, approved branch `remediation/early-edge-evidence-readiness`. The hardened rejection diagnostics were preserved, not reimplemented. The published design report was read before changes. This document freezes code/offline evidence; the exact resulting release SHA and any live result belong in Git and the ignored qualification receipts, not a self-referential SHA in this document.

## Policy contract

Version: **fx-fresh-demand-fair-1**. The existing hot acquisition now passes counts of the current RPC batch's validated states by quote, total<=25, to the existing UsdReference. This opt-in keyword preserves original behavior for existing callers without validated demand, including legacy two-product reference callers. No separate poller, queue, worker, connection, provider or quote support was added.

Per existing hot poll, select **at most one** SOL-USD or USDCUSD product:

1. Apply the exact existing `fx_value` predicate to cached references at actual selection time. Fresh cache is reused; neither acquisition nor publication time is extended.
2. A needed missing/stale product is eligible only after its original10s attempt interval, outside provider cooldown, and when existing limiter/concurrency state permits dispatch inside the existing2s budget. Public semaphore.locked() and the provider's own limiter deadline are used; no private library internals. With occupied provider slots or limiter wait>=2s, skip the round rather than spending fairness or opening another slot.
3. Among eligible products, prefer larger current validated-state demand. Ties use oldest product attempt, then fixed SOL-first order.
4. After an unserved product misses two eligible mixed rounds, force its selection on the next eligible mixed round. Miss counters are fixed to two products and bounded0..2. A single eligible product is selected directly.
5. Unneeded or genuinely fresh products reset their pending need/miss count. Cooldown, attempt-interval and limiter-budget ineligibility hold the counter without incrementing it; they cannot erase a prior fairness obligation. Wall-clock regression/nonfinite selection time makes no request and consumes no fairness round.

“Service” means selection for a bounded request attempt, **not** a guaranteed usable provider response. A stale publication, HTTP failure or cancellation remains an actual failed/unavailable acquisition. Attempt timestamps retain original semantics, including failed/cancelled attempts; no second request is made as an out-of-budget retry. Fairness guarantees selection opportunity only, not cache freshness for both products every round. State is bounded and process-local; a new engine session/cache starts a new fairness history, with no retrospective restoration or research backfill.

The original rate0.2 (5s pacing), concurrency2, retry_attempts=1,10s product interval, hot poll cadence/capacity and2s engine wait_for are unchanged. The real request still goes through HttpProvider's limiter and cooldown handling. Freshness is revalidated during `usd_mark()` and `PriceResearch.accept()`; a reference that expires after selection stays unavailable. Formula/version, timestamp/expiry semantics, canonical event payload, V2.1, security, strict CURRENT and approval predicates are unchanged.

## Diagnostics and provenance

Price diagnostics add `fx_selection`, null until a validated-demand policy round occurs, otherwise a bounded fixed-product snapshot:

- policy version; total and mixed-eligible rounds; clock rejections; last selected product;
- each product's last validated-state count, selected count, fresh reuse, budget/interval/cooldown/limiter skips, not-needed count, last selection status, and pending eligible-mixed misses0..2.

Actual request/refresh outcomes remain in the existing per-product FX counters (attempted, http_started/completed, usable, stale/schema/HTTP failure, cancellation) and reference timestamps/freshness. A selected product is not necessarily an HTTP completion or usable refresh. A zero counter is not evidence of improved coverage. Existing receipt48k,32 token/24 review/25 inflight/32 session and ledger16KiB/64MiB caps remain; no new write frequency was added. The new state is fixed cardinality, independent of mint population.

Both qualification and prospective manifests now freeze `fx_selection_policy_version`. Existing source/configuration SHA checks continue to bind the code and settings. The original1200s protocol and880s enrollment cutoff are unchanged. Old ledgers/marks/unavailable outcomes are never modified.

## Stronger short qualification

The existing corrected120s qualification framework is reused. In addition to its discovery, processing, durable SQL, ledger, queue, shutdown and source checks, it requires the reserve namespace to be present, snapshot available, reconciled, no invalid updates and zero calculation/aggregation/integrity failures. Observed FX selection must match this policy version and its two-product fairness bounds. A null selection means this live branch was not observed, not a demonstrated improvement.

The final report includes actual price acquisition/FX/selection diagnostics and zero open/pending paper-position checks. The fresh isolated DB and disabled approval boundary prevent an observational smoke from manipulating a real paper portfolio; existing paper-history data is not opened. No cohort, wallet or transaction path is introduced. No source edits may occur during qualification.

Single qualification command **only after selective publication, matching fetched origin and source preflight**:

```bash
cd /home/modisa/projects/crispy-winner
RELEASE_SHA='<full-published-SHA-containing-this-policy>'
RADAR_MODE=OBSERVE RADAR_CONFIG=config/conservative.yaml PUMPPORTAL_ENABLED=false \
  .venv/bin/python scripts/qualify_live_discovery.py --run \
  --expected-sha "$RELEASE_SHA" \
  --output "data/early_edge/fx-qualification-$(date -u +%Y%m%dT%H%M%SZ)"
```

No retry on failure. No old smoke harness. Preserve failed output. Record actual exit status, durable STOPPED/checkpoint, source identity and report checks.120 seconds cannot establish180-second strict CURRENT or predictive validity. No absence of USDC/unsupported states during a short sample proves that those paths work live.

## Offline validation

- Broad relevant backend/manual/security regression set: **598 passed,1 expected opt-in official Node SDK reference skip in29.74s**, normal exit. Ordinary pinned goldens ran; no SDK install or Node runtime oracle became an application dependency.
- After adding the conservative occupied-provider-slot guard, focused policy/pricing/diagnostic/qualification regressions: **185 passed in5.99s**. Final qualification checks after explicit paper-boundary reporting: **38 passed in1.50s**. These overlap the broad suite and are not additive independent test counts.
- Fairness is checked for every two-product split1..24 within a25-state batch over repeated31s rounds; no eligible product misses more than two mixed rounds. Fixed synthetic calls prove<=one request per original round, cooldown/10s/occupied-slot/limiter-budget skips, fresh reuse, SOL-only/USDC-only, deterministic ties, clock regression/nonfinite/future timestamps, HTTP429/500, slow/stale/invalid publication, cancellation and timeout.
- Actual adapter sequence under mocked HTTP is SOL,SOL,USDC,SOL for14:1 demand, four calls in four rounds. This differs from legacy LRU but is **not a recovered historical price result**. Existing design simulations remain descriptive, not production configuration.
- Isolated real-engine tests compare legacy/new selection for both quotes: accepted mark values/provenance/timestamps/expiry, one committed mark each, classifications, features, decisions and event accounting remain identical with the same successful reference inputs. Missing or expired references stay unavailable, never economic losses.
- Frontend: **62 tests passed across7 files**. Production build passed, including TypeScript noEmit,37 modules transformed. No UI source changes.
- Ruff/mypy, secret/whitespace, preserved artifacts and exact diff are checked before publication. No broad performance/endurance study was run. Initial lint-only unused test imports were removed; no remaining failure is concealed.

## Dashboard/manual-use verification and limits

Existing Opportunity, FOMO Companion, token-detail intelligence, Manual Positions and System Health views were inspected and exercised by existing offline tests; compiled assets build. Token Intelligence is a detail panel, not a new separate navigation item. Research-only/speculative labels, timestamps/freshness, lifecycle, security/unknown risks, observed buyer flow, monitoring degradation, missing liquidity/prices and non-executable cost-estimate warnings remain. Copy-mint/FOMO links and manual journal workflow already exist; no BUY NOW, wallet or execution feature was added.

A real provider-connected OBSERVE startup is not proved by offline tests or a frontend build. Its actual status must be reported separately after publication/preflight and the one qualification. While any release guard is blocked, do not claim the live dashboard is qualified. Helius configuration is checked privately for presence, never printed.

After review/qualification, run manual-use OBSERVE with a separate persistent database (protects original radar.db and frozen studies). Build the frontend first; ensure no other engine is running. The following is an **operator command**, not a service started by this document:

```bash
cd /home/modisa/projects/crispy-winner
npm --prefix frontend run build
RADAR_MODE=OBSERVE RADAR_CONFIG=config/conservative.yaml PUMPPORTAL_ENABLED=false \
.venv/bin/python - <<'PY'
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv('.env')
assert not any(v for k,v in os.environ.items() if 'COHORT' in k.upper())
from backend.app.config import load_settings
from backend.app.main import create_app
import uvicorn
settings = load_settings()
assert settings.mode == 'OBSERVE'
path = Path('data/manual-observe/companion.db')
path.parent.mkdir(parents=True, exist_ok=True)
uvicorn.run(create_app(settings, path), host='127.0.0.1', port=8765,
            access_log=False, timeout_graceful_shutdown=5)
PY
```

Open `http://127.0.0.1:8765`. This new journal starts empty; it does not silently import or overwrite previous manual positions. User-entered fills are local records, not verified transactions. Evidence gaps/stale/security unknown remain warnings/WAIT, not safety assurances. Ctrl+C uses the existing real engine cleanup; never kill a server merely to manufacture a clean qualification.

## Independent20-minute study — prepare only, do not launch

Only after the120s qualification passes, review this separate command with the **same complete qualified published SHA** and policy version:

```bash
RADAR_MODE=OBSERVE RADAR_CONFIG=config/conservative.yaml PUMPPORTAL_ENABLED=false \
.venv/bin/python scripts/signal_quality_pilot.py --run \
  --expected-sha "$RELEASE_SHA" \
  --output "data/early_edge/signal-quality-fx-v1-$(date -u +%Y%m%dT%H%M%SZ)"
```

Stop for review before running it. Do not resume/append/merge the original October26 pilot. Changed FX selection changes missingness and which tokens have measured marks, so comparisons are descriptive, not controlled evidence of better prediction. Count unique mints and token/class units separately; retain STALE/risk/neutral/unpriced classes and full baseline/matured/censored denominators at15/30/60/180/300s. Report only supported gross reserve-implied movement. No mark is an executable manual entry/exit; route availability, real fees/slippage/failures and after-cost profitability remain unvalidated. No strategy approval/evidence freeze follows from either pilot. PRE_COHORT_READY=NO.

## Intended publication boundary

Only the scheduler module, existing FX adapter/engine/diagnostics integration, two existing harness provenance/qualification files, focused tests and this document are intended. Preserve all six unrelated dirty files and historical receipts. Publication/remote SHA and any environmental blocker are reported by the agent separately; no force push/main merge or source-integrity bypass is permitted. If publication/preflight fails, **no live qualification may start**.

## Actual release checkpoint

Git refused creation of `.git/index.lock` because Git metadata is mounted read-only. Nothing was staged, committed or pushed. HEAD and the cached origin ref remain `d2a76b7ccb8f25f418b976714906b9ad23837a42`; the cached ref is not a new network verification. Source preflight correctly refused unpublished changes before engine/database creation. Loopback binding separately returned EPERM in this environment.

The ignored checkpoint is `data/early_edge/fx-release-review-20261026/report.json`. Zero live qualifications and zero long studies were started. Live FX refresh outcomes and coverage improvement are UNAVAILABLE; provider-connected dashboard startup is UNVERIFIED. Offline validation does not establish live qualification or prospective readiness.

Publish from a writable WSL terminal after reviewing only the nine intended files:

```bash
cd /home/modisa/projects/crispy-winner
set -e
[ "$(git branch --show-current)" = remediation/early-edge-evidence-readiness ]
[ "$(git rev-parse HEAD)" = d2a76b7ccb8f25f418b976714906b9ad23837a42 ]
[ -z "$(git diff --cached --name-only)" ]
git fetch origin remediation/early-edge-evidence-readiness
[ "$(git rev-parse origin/remediation/early-edge-evidence-readiness)" = "$(git rev-parse HEAD)" ]
.venv/bin/python scripts/check_secrets.py
git diff --check
git add -- backend/app/fx_selection.py backend/app/early_edge_runtime.py \
  backend/app/engine.py backend/app/price_diagnostics.py \
  scripts/signal_quality_pilot.py scripts/qualify_live_discovery.py \
  backend/tests/test_fx_selection.py backend/tests/test_live_discovery_qualification.py \
  backend/docs/fx-selection-readiness-20261026.md
git diff --cached --stat
git diff --cached --check
git diff --cached
```

Stop and review the complete staged diff before the following separate publication step. Never include the six unrelated files or force-push:

```bash
git commit -m "fix: select fresh FX references with bounded demand fairness"
git push origin HEAD:remediation/early-edge-evidence-readiness
git fetch origin remediation/early-edge-evidence-readiness
RELEASE_SHA=$(git rev-parse HEAD)
[ "$RELEASE_SHA" = "$(git rev-parse origin/remediation/early-edge-evidence-readiness)" ]
printf 'Published source: %s\n' "$RELEASE_SHA"
```

Only then may the single qualification above run, subject to its existing source/configuration/process guards. The twenty-minute study remains prepared only, requiring review after qualification passes. PRE_COHORT_READY=NO.

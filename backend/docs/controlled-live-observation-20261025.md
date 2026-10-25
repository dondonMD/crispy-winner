# Controlled real-market observation — Phase 3, 2026-10-25

**Operational finding: CONTROLLED OBSERVATION BLOCKED.**

**PRE_COHORT_READY=NO.** No live monitor,65s observation,240s observation, prospective cohort, trade, wallet connection, transaction simulation/submission,600s endurance or six-hour experiment was started. This is a preserved pre-flight failure, not a failed market strategy or evidence of an inactive market. Do not replace unavailable metrics with zero observations.

## Source and environment

- Branch: remediation/early-edge-evidence-readiness.
- HEAD:0fbe59f9ab73797247f8fba77af519853fca367d, Phase2C `fix: reject unbracketed break-even estimates`.
- Local origin/remediation/early-edge-evidence-readiness tracking SHA matches HEAD. Publication is accepted from the supplied completed milestone and local tracking ref; no fresh GitHub fetch could establish current remote state in this network-restricted environment.
- Phase2A unverified approval consumption remains disabled; Phase2B required nondefault pool identity check and Phase2C root-bracketing correction are present. Published serial architecture unchanged.
- Five pre-existing diagnostic files are still modified/untracked. Therefore the WHOLE working tree is not clean. Production backend/app and config have no diff against HEAD; the existing unrelated changes were hashed and untouched, not misrepresented as part of the frozen runtime.
- Python3.13.16; WSL2 kernel6.18.54.1-microsoft-standard-WSL2;4 physical/8 logical visible CPUs;11,435,442,176 bytes visible RAM. Pre-flight free project space1,010,592,292,864 bytes; temporary space5,444,763,648 bytes. These are environment snapshots, NOT measured live CPU/RSS/storage growth.

Pre-flight receipts under ignored data/early_edge/controlled-live-20261025/: preflight.json, network.json, environment.json, harness-check.json and recipe-check.json. They contain only sanitized configuration types, hashes and aggregate/error classifications. No credentials or provider URLs are printed here. The local fallback recipe is not a live result or a new production implementation.

## Pre-flight results

|Check|Result|
|---|---|
|Expected Phase2C source/branch|PASS; HEAD and local tracking ref match.|
|Application/configuration drift|No production/config diff; exact source/config hashes captured before investigation and rechecked.|
|Five unrelated changes|Preserved by initial/final content hashes; no staging of them.|
|Competing monitor|None identified among visible process arguments for the known OBSERVE/diagnostic/uvicorn patterns. No command lines, endpoints or secrets printed. This does not inspect every possible Windows process or monitor outside the visible process namespace.|
|Helius configuration|.env exists; SOLANA_RPC_URL is present as HTTPS, SOLANA_WS_URL as WSS; both configured host types are Helius. Values never printed, copied into public documentation or committed.|
|Paid/collectable mode|RADAR_COHORT empty; PUMPPORTAL_ENABLED not enabled. Intended harness mode OBSERVE, trade_stream_enabled=False; standard logsSubscribe and existing bounded RPC only.|
|Wallet/trading capabilities|No new capability; OBSERVE does not request paper entries, and Phase2A supplies no approved evidence. No signing/sending/wallet API enabled.|
|Existing databases|No engine/database writer constructed. Retired database size/mtime and seven frozen evidence hashes match. Existing data/observe-smoke.json, if present, was hashed and not overwritten.|
|Network|BLOCKED: both configured hosts fail resolver pre-flight with socket.gaierror errno−3(EAI_AGAIN).|

## Commands actually executed and measured failure

Read-only Git status/branch/log/tracking checks and source inspection of scripts/smoke_observe.py, engine startup/process/stop/accounting and provider environment handling were performed. A sanitized Python pre-flight read dotenv configuration, compared source/evidence hashes and enumerated visible monitor candidates without printing command arguments or private values.

A separate bounded resolver command used `timeout 15 .venv/bin/python` and socket.getaddrinfo against each configured hostname. Only these results were retained:

|Configured endpoint type|Result|Measured resolver elapsed,s|
|---|---|---:|
|Helius HTTPS RPC|gaierror errno−3; no resolved address|.0022|
|Helius WSS|gaierror errno−3; no resolved address|.0001|

Combined resolver elapsed=.0024s, process exit0 because errors were explicitly captured into the failure receipt. **HTTP requests0; websocket connections0; engine starts0.** This is not a65s probe or an RPC error returned by Helius. It demonstrates local DNS unavailability at this attempt, not provider downtime or a bad API key. No alternate endpoint was invented, substituted or used to evade restrictions.

The65s probe was NOT started because its configured providers could not be resolved. The240s probe was NOT started because the prerequisite short live result does not exist. No timer was reset or extended, and no second engine was launched.

## Existing harness issue found before execution

The current smoke harness assigns a counted_process(event,now=None) callback, while production drain_events calls process(...,queued=True). Direct invocation would raise TypeError before the real process method and corrupt the diagnostic's event-disposition accounting. A smoke report from that uncorrected adapter must not be accepted as market evidence.

No tracked harness or production code is changed in Phase3. The WSL recipe below transparently forwards **kwargs through that diagnostic callback, redirects the hard-coded data/observe-smoke.json output to a new private directory, and records terminal accounting/quality around normal shutdown. It adds read-only safety checks at the existing sample point, not a scheduler/capacity/strategy change. These adaptations and the resulting source hash are explicit; do not describe this as an untouched harness execution.

Offline verification here: patched callback forwards queued=True exactly once to its supplied synthetic original function; complete recipe and generated harness parse/compile. No engine, network or database was constructed by those checks. This does not validate live behavior of the recipe; its first execution must retain errors and real exit status. The original tracked harness and its source hash remain unchanged.

## Observation results — unavailable

|Requested measurement|Result|
|---|---|
|Actual observation duration|NOT RUN; no65s/240s market window. Only.0024s DNS pre-flight measured.|
|Launches/duplicates/admitted/active/deep|UNVERIFIED; not observed zeros.|
|Pump notifications/canonical accepted/processed/durable trades|UNVERIFIED. No connection made.|
|Verified curves/lifecycle/usable recent trade tokens|UNVERIFIED.|
|>=180s clean/CURRENT/independent buyers/flow|UNVERIFIED.65s alone could not establish180s even if it had run.|
|Security successful/unknown/stale reports|UNVERIFIED. No scan requested.|
|Provider RPC failures/429/reconnect/recovery|UNVERIFIED operationally; two DNS-resolution failures, no provider request or reconnect sequence.|
|Opportunity classifications / EARLY and missing-evidence reasons|UNVERIFIED. No actual candidate or opportunity surfaced.|
|Entry/exit prices, executable quotes or after-cost outcomes|NOT ESTABLISHED. This acquisition harness does not itself prove verified-state execution economics.|
|Queue/drops/CPU/RSS/storage growth/durable reconciliation|NOT MEASURED live. Do not report a clean zero-loss run from no engine.|
|Migrations/PumpSwap eligible/subscribed/ACK/Buy/Sell/gaps|UNVERIFIED, not evidence of compatibility or incompatibility.|

For a later surfaced EARLY, inspect actual verified progression/history; independent canonical trade units and CURRENT coverage; current verified security versus unknown; market provenance/freshness; hard risks/disagreement; and missing entry/exit/economic evidence. A curve-only HIGH/EARLY research attention classification is not a buy. Strict ENTRY_CANDIDATE approval remains disabled; any unexpected approved entry is a stop-and-investigate condition, not success.

## PumpSwap finding

No PumpSwap traffic was acquired here. The preserved historical unexplained8-byte suffix remains **BLOCKED pending authoritative layout**, with no new claim about current deployment. No authoritative new layout was established in this phase; there is no fresh failed payload to explain. The exact-consumption decoder, discriminator/units/pool routing/ordinal dedup and fail-closed gaps are unchanged. No tolerant-tail decoder, DEX-count flow substitute or paid subscription was introduced.

A future affected notification must preserve sanitized structural metadata, relevant verified identity/provenance and original ordinal in ignored evidence. Ordinary health failure categories alone do not establish tail semantics. Do not promote an unsupported quote/event to CURRENT. If authoritative source does not explain the complete bytes, stop decoder remediation and report BLOCKED; this document supplies no permission to guess fields.

## Exact writable-WSL continuation recipe — NOT executed here

Run from the same project checkout in an unrestricted writable WSL terminal. First verify no separate UI/backend/live monitor is running outside this process namespace. Keep stdout/stderr and token-level receipts private under ignored data; do not paste them into a public issue or commit them. Commands do not print endpoints. Do NOT source .env into shell tracing or enable set-x.

The recipe enforces unchanged production/config relative to the Phase2C baseline, default conservative settings, no cohort/PumpPortal and one visible monitor. A documentation-only later commit is acceptable; any production/config drift blocks. It uses the existing temporary DB (removed by its normal context manager), never radar.db/prospective.db, and saves independent post-stop SQL counts before removal. The supplied recipe is diagnostic-only, not a source edit or live observation already performed.

```bash
cd /home/modisa/projects/crispy-winner
umask 077
RUN_ROOT=$(mktemp -d data/early_edge/controlled-observe-wsl-20261025-XXXXXX)
cat > "$RUN_ROOT/run-smoke.py" <<'PY'
"""WSL-only recipe; NOT executed in the blocked sandbox. No tracked source edit."""
import asyncio
from contextlib import closing
import sqlite3
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil
from dotenv import load_dotenv

root = Path.cwd()
base = "0fbe59f9ab73797247f8fba77af519853fca367d"
seconds = int(sys.argv[1])
assert seconds in (65, 240), "Only the declared observation durations are allowed"
assert subprocess.check_output(["git", "branch", "--show-current"], text=True).strip() == "remediation/early-edge-evidence-readiness"
assert not subprocess.check_output(["git", "diff", base, "--name-only", "--", "backend/app", "config"], text=True).strip(), "Production/configuration drift"
for proc in psutil.process_iter(["pid", "cmdline"]):
    try:
        args = proc.info["cmdline"] or []
        names = {Path(arg).name for arg in args}
        if proc.pid != os.getpid() and (names.intersection({"smoke_observe.py", "run-smoke.py", "early_edge_diagnostic.py", "verify_observe.py", "uvicorn"}) or any(a.startswith("backend.app.main:") for a in args)):
            raise RuntimeError("Competing monitor candidate; inspect sanitized PID separately")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        continue
load_dotenv(root / ".env", override=False)
assert not os.getenv("RADAR_COHORT"), "Cohort selection forbidden"
assert os.getenv("PUMPPORTAL_ENABLED", "false").lower() in ("", "false", "0"), "PumpPortal forbidden"
assert os.getenv("SOLANA_RPC_URL") and os.getenv("SOLANA_WS_URL"), "Configured endpoints required"
os.environ["RADAR_MODE"] = "OBSERVE"
sys.path.insert(0, str(root))
from backend.app.config import Settings, load_settings
assert Settings(mode="OBSERVE", trade_stream_enabled=False, max_deep=25) == load_settings(), "Harness defaults differ from configured conservative settings"
out = Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=False)
script = root / "scripts/smoke_observe.py"
source = script.read_text()
def replace_once(old, new):
    global source
    assert source.count(old) == 1, "Harness changed; re-review recipe"
    source = source.replace(old, new)
replace_once("def counted_process(event, now=None):", "def counted_process(event, now=None, **kwargs):")
replace_once("accepted = original_process(event, now)", "accepted = original_process(event, now, **kwargs)")
replace_once('Path("data/observe-smoke.json")', f"Path({str(out / 'observe.json')!r})")
# Read-only checks at an existing sample point; no new cadence or provider call.
replace_once("                sample_now = time.time()", '''                sample_now = time.time()
                ledger = engine.accounting.snapshot(engine.queue)
                if (not all(row["reconciled"] for row in ledger["events"].values())
                        or engine.queue.dropped_critical or engine.storage_stopped
                        or engine.metrics.get("resource_pressure") or engine.metrics.get("storage_full")):
                    raise RuntimeError("Serious accounting/resource condition; preserve receipt and stop")''')
# Final receipts include rejected/evicted/pending work and quality, not just heap size.
replace_once("            await engine.stop()", f'''            before = None
            stopped = False
            try:
                before = json.loads(json.dumps(dict(
                accounting=engine.accounting.snapshot(engine.queue),
                recovery=engine.recovery.snapshot(), discovery=engine.onchain.health,
                rpc=engine.rpc.health, pumpswap=engine.pumpswap.health,
                opportunities=engine.intelligence.results, metrics=engine.metrics,
                persistence=engine.db.persistence_snapshot(),
                approved_evidence=engine.approved_evidence), allow_nan=False))
            finally:
                try:
                    await engine.stop()
                    stopped = True
                finally:
                    with closing(sqlite3.connect(f"file:{{engine.db.path}}?mode=ro", uri=True)) as conn:
                        sql_counts = dict(conn.execute("SELECT kind,COUNT(*) FROM records GROUP BY kind"))
                        sql_events = dict(conn.execute("SELECT json_extract(payload,'$.event.kind'),COUNT(*) FROM records WHERE kind='event' GROUP BY 1"))
                        quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
                        prospective_counts = {{name: conn.execute("SELECT COUNT(*) FROM " + name).fetchone()[0]
                            for name in ("prospective_cohorts", "prospective_enrollments", "prospective_outcomes")}}
                    Path({str(out / 'shutdown.json')!r}).write_text(json.dumps(dict(
                        before=before, shutdown_returned=stopped,
                        after_accounting=engine.accounting.snapshot(engine.queue),
                        after_recovery=engine.recovery.snapshot(), cohort_created=False,
                        sql_records=sql_counts, sql_event_kinds=sql_events,
                        quick_check=quick_check, prospective_counts=prospective_counts), indent=2, allow_nan=False))''')
meta = dict(source_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            production_baseline=base, requested_seconds=seconds, max_deep=25,
            original_harness_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
            diagnostic_overlay_sha256=hashlib.sha256(source.encode()).hexdigest(),
            settings=Settings(mode="OBSERVE").model_dump(), started_at=time.time(),
            production_modified=False, cohort_created=False)
(out / "identity.json").write_text(json.dumps(meta, indent=2))
namespace = {"__name__": "isolated_observe", "__file__": str(script),
             "closing": closing, "sqlite3": sqlite3}
exec(compile(source, str(script), "exec"), namespace)
asyncio.run(namespace["main"](seconds, 25))
assert not subprocess.check_output(["git", "diff", base, "--name-only", "--", "backend/app", "config"], text=True).strip(), "Source/config drift during run"
PY
timeout 110 .venv/bin/python "$RUN_ROOT/run-smoke.py" 65 "$RUN_ROOT/probe65" > "$RUN_ROOT/probe65.stdout.json" 2> "$RUN_ROOT/probe65.stderr.log"
```

Check the actual exit status before executing any further command. timeout exit124, exception, absent observe.json/shutdown.json, failed quick_check, unexplained accounting discrepancy, unexpected approval, critical/trade loss, storage censoring or unsafe resource condition is NOT a successful short probe. Preserve the entire private directory and STOP; do not rerun to replace a failure.

Review probe65/observe.json and probe65/shutdown.json locally. Require actual discovery delivery/creates, accepted AND processed canonical trades with usable known units, verified curve observations, no unexplained failed/undurable/disappeared events, all terminal ledger rows reconciled, no critical/trade overflow, no lingering processing after stop, clean shutdown/DB check, prospective table counts0 and approved_evidence=None. Record DNS/provider/429/reconnect/recovery errors even if eventually resolved. Any pending recovery/queued work before stop must have an explicit final disposition; post-stop zero pending alone is insufficient.

Only if that65s result meets acceptable connectivity/accounting/health, execute the conditionally authorized240s run using a NEW temporary database/output child (no continuation of65s coverage):

```bash
timeout 300 .venv/bin/python "$RUN_ROOT/run-smoke.py" 240 "$RUN_ROOT/probe240" > "$RUN_ROOT/probe240.stdout.json" 2> "$RUN_ROOT/probe240.stderr.log"
```

This is a conditional operator step, not an automatic script branch. Do not execute it after a failed/partial unexplained short probe. Runtime must be measured from the produced receipt, not assumed equal to timeout. The subprocess timeout is a safety ceiling covering startup/shutdown; it does not extend the market observation timer. No600s, six-hour or cohort follows.

Interpret CURRENT only if the existing clean180s/sample/freshness/units conditions actually pass in that independent240s window. Reconcile submitted/accepted/filtered/rejected/evicted/pending/processing/persisted/shutdown categories; do not add overlapping counters or call admitted trades durable. Any shutdown_unprocessed remains missing evidence. Exclude intentional shutdown coverage invalidation from transport failure counts while preserving both in receipts.

Review opportunity snapshots and dominant missing-evidence reasons from shutdown.before.opportunities, aggregate only for publication. The recipe records final classifications but is not a comprehensive timestamped history of every transient EARLY; do not claim otherwise. Acquisition receipts do not supply missing executable entry/exit prices or positive net outcomes. If migrations/eligible pools do not occur, PumpSwap runtime compatibility stays unverified. If unsupported traffic occurs, preserve failure counts and obtain bounded byte-level diagnostics before any authoritative-schema conclusion; do not change production to pass the run.

## Engineering and research readiness

**Further non-trading observation:** locally blocked by networking in this environment. A corrected, auditable diagnostic invocation can be attempted through the explicit WSL recipe, preserving all failures and the conditional65→240 sequence. No real-market reliability qualification is claimed from static checks.

**Before Phase4 prospective research:** obtain qualifying bounded live receipts on a frozen source/config; demonstrate actual canonical delivery/units/currentness and coherent accounting; quantify monitoring/security fairness and missingness; validate quote/deadline/interface-cost instruments under their separate contract; resolve relevant unsupported layout blockers without guessing; retain unavailable/negative outcomes and independent approval restrictions. Prior sustained-capacity, censored-data, unmatched-control and quote-coverage limitations are not repaired by a DNS pre-flight or by eventual short connectivity. A future Phase4 requires separate authorization; none is initiated here.

**Final finding: CONTROLLED OBSERVATION BLOCKED. PRE_COHORT_READY=NO.**

## Focused checks and publication

No production change was needed or made. New work is this documentation plus ignored local pre-flight/recipe receipts. Existing runtime/backend/frontend tests were not rerun for a DNS-blocked documentation task; Phase2C's906-pass/1-skip bounded-cleanup result is historical, not a new live qualification.

Focused offline checks passed: source/config/pre-existing/frozen hashes; retired DB stat and original smoke report unchanged; original smoke source unchanged; diagnostic callback keyword forwarding; recipe and generated harness compilation; explicit whitespace and source/document secret scan. An initial naive document-link check misread a Python subscript call in the code fence as a Markdown link; fence-aware checking corrects that checker false positive. No live result is inferred from these checks.

Staging ONLY this document failed: Git could not create .git/index.lock on the read-only filesystem. No commit, push, force action or permission bypass occurred. HEAD remains0fbe59f9ab73797247f8fba77af519853fca367d. From a writable WSL terminal, publish only the non-sensitive report:

```bash
git switch remediation/early-edge-evidence-readiness
git add -- backend/docs/controlled-live-observation-20261025.md
git diff --cached --name-only
git diff --cached --check
git diff --cached
git commit -m "docs: record blocked controlled live observation"
git push origin remediation/early-edge-evidence-readiness
```

Verify the staged list contains ONLY this report. Keep all local receipts, token details, .env and unrelated work out of the commit. Publication does not authorize Phase4 or a cohort. **CONTROLLED OBSERVATION BLOCKED; PRE_COHORT_READY=NO.**

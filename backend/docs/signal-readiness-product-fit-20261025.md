# Signal readiness and product-fit decision — 2026-10-25

**Recommendation: CONDITIONAL GO for a separately governed pre-graduation research path; NO-GO for trusted buy signals or Phase4 activation. PRE_COHORT_READY=NO.** Retain the serial architecture and strict strategy. No code, configuration, cohort or live collection changes accompany this decision.

Source `caa996138a66440c0a3e5f232b699782f1f3554c`, branch `remediation/early-edge-evidence-readiness`. Evidence: frozen identity, observation and shutdown receipts under ignored `data/early_edge/final-phase3-reliability-20261025-P2KqV0/probe240/`. Scope is recorded aggregates and code inspection; no new diagnostics or experiments. Token-level records remain private.

## What genuinely works now

The240.63s OBSERVE session recorded40,817 discovery messages,80 processed launches,3,850 processed trades (2,189 buys/1,661 sells),148 verified curve observations and two processed migrations. Trade stale rejections and queue trade/critical drops were zero. Recovery288/288 completed, overflow/pending/global recovery gaps zero, with two tracked-local recovery effects. SQLite check and shutdown accounting passed; prospective tables remained empty and approved evidence remained None.

This window had no reconnect or ping-timeout failure. Peak CURRENT candidates2, first CURRENT207.63s, maximum clean token coverage237.93s; final evidence counts1 CURRENT/14 PARTIAL/65 UNAVAILABLE. Thus genuine CURRENT acquisition is possible with current infrastructure. This does not establish indefinite provider reliability or explain earlier timeout causes. Pump unsupported-layout failures were zero;262 framing failures still occurred. PumpSwap eligible/subscribed/ACK/event counts were zero: this window cannot resolve its preserved suffix incompatibility.

The system can discover launches, track verified curve progression, display scoped canonical trades and estimated independent buyers when units/coverage qualify, identify some security/concentration failures and provide explainable research attention. These are useful monitoring capabilities, not demonstrated predictive value.

## Two different products inside the existing design

|Path|Actual evidence/decision contract|Product fit|
|---|---|---|
|[Opportunity Intelligence](../app/opportunity.py), `curve_dynamics` / `opportunity_view`|EARLY requires current curve evidence, at least3 observations/60s, net progression>=4pp, persistence>=0.75, increasing progression, retreat<=3pp, and current security OR at least4 observations/120s. Reject/expired state, hard failure, observed creator selling or disagreement blocks it. CURRENT trade flow and fresh USD market data improve evidence grade but are not required to assign EARLY.|Can surface earlier research attention; not an executable-entry signal. Curve progression is not price appreciation, and unknown security is not safety.|
|[Core engine](../app/engine.py), `analyse`, and [economics](../app/economics.py), `evaluate_candidate`|Confirmed graduation, post-grad wait60s, independently verified pool, current price/liquidity/security, clean CURRENT flow, buyer/maturity/momentum gates, stabilization/renewed buying, no chase/risk rejection, viable after-cost size and approved evidence.|Intentionally selects later post-graduation setups. It cannot identify an approved pre-graduation purchase by design.|

The Opportunity display predicate itself is broader than the frozen early-entry experiment: it does not independently impose “no graduation and curve<85.” The separate [early_edge.py](../app/early_edge.py) `signal_snapshot` does impose those constraints, canonical units and observation readiness. A UI label must not be substituted for that study's enrollment contract.

The180s CURRENT requirement needs actual continuously covered trade evidence; migration starts a fresh post-grad flow epoch. The60s post-grad wait can overlap that coverage, so these are not automatically additive waits. Nonetheless the core is intrinsically unsuitable for launch-time/pre-graduation entries. Lowering continuity to produce more labels would answer a different question with weaker evidence. The earlier research path can be evaluated separately using its frozen10s manual latency, rather than pretending the core is an early-entry system.

## Approval-dependent gates: impossible while approval is None

1. `RadarEngine.analyse` derives historical edge exclusively from `approved_evidence`; retrospective dashboard holdout is descriptive, not authorization.
2. `PositionSizer.size(..., historical_edge_pct=None)` adds “No validated out-of-sample after-cost edge,” sets economically_viable false and allowed position size zero, even if a hypothetical proposed size/cost scenario exists.
3. `evaluate_candidate(..., evidence=None)` always adds “Insufficient positive holdout evidence,” alongside nonviability. ALLOW_PAPER_ENTRY is impossible. Hard risks can still yield REJECT, and chase can yield MISSED; absence of approval does not force every result to be WAIT.
4. The engine can transition POST_GRAD_OBSERVATION to ENTRY_CANDIDATE only on ALLOW_PAPER_ENTRY. [Companion](../app/companion.py) also requires positive approved sample/CI evidence, economically viable positive size and the core decision. Its ENTRY_CANDIDATE is therefore impossible too.
5. [PaperAccount.request_entry](../app/paper.py) requires PAPER/DEMO mode and ALLOW_PAPER_ENTRY; OBSERVE never requests an executable position. Manual journal entries are separate records, not a bypass granting approval.

Phase2A intentionally disables the unverified approval route; a historical row labelled APPROVED cannot repair this. Missing statistical approval is distinct from missing market inputs and from an actual risk rejection.

## Why information is missing

|Limitation|Code/evidence and interpretation|
|---|---|
|Quote units|[Discovery.receive](../app/discovery.py) supports proven SOL/USDC semantics; legacy default quote requires verified curve identity. Receipts count1,049 curve-not-verified and4 unsupported-quote events. These are acquisition-stage counts, not unique tokens. Later verification does not retroactively turn earlier unknown units into valid flow. This is deliberate fail-closed behavior interacting with bounded observation timing; no new defect is proven.|
|Security|[Engine.enrich_once](../app/engine.py) limits scans to the deep set and graduation or fresh curve>=60, with30s global scan interval,300s per-token retry/TTL and shared RPC protections.3 scans completed;77 final Opportunity views UNKNOWN/STALE versus3 CURRENT. Unknown is neither safe nor unsafe; the receipts do not prove all77 were due or starved. This later-lifecycle selection intentionally leaves many early tokens unverified.|
|USD price/liquidity|Engine market enrichment sends only graduated deep candidates to [DexScreener.markets](../app/providers.py), which selects PumpSwap pairs. Pre-grad launches are not supplied executable USD prices by this route. All80 final views lacked current market price/cap; all80 core views lacked current price/liquidity. One successful DEX HTTP request proves connectivity, not a usable pair/quote. Provider marks expire at20s and are not executable reserve quotes.|
|Continuity/breadth|Most tokens have insufficient age, recent samples, verified units or local clean coverage: final nonexclusive blocker counts include59 continuity,65 units,38 samples and66 stale/missing last-trade. One CURRENT token does not make the other tokens complete. Truncated transaction recovery cannot guarantee unobserved chain-wide delivery.|
|Post-grad compatibility|No eligible PumpSwap subscription exercised the known unexplained event suffix. This remains a separate blocked/unverified acquisition dependency for later outcomes, not a failure established by zero events in this window.|

These receipts do not establish a new software defect. Intentional coverage scope/readiness rules explain substantial absence; provider truncation/incomplete delivery and historical disconnects are real operational limitations with incomplete causal attribution. No evidence justifies blaming every missing value on Helius or changing providers. The serial architecture has demonstrated low-load usefulness, not unbounded capacity or fair complete monitoring of every launch.

## What the rankings establish—and minimum evidence still missing

Final Opportunity views:51 DEVELOPING,25 AVOID,4 DATA LIMITED,0 EARLY. Companion:56 WAIT,24 REJECT,0 ENTRY_CANDIDATE. These are different predicates, not contradictory performance measurements. At snapshot time75 curves were current,16 had>=3 observations/60s history, only3 had net progression>=4pp. Marginal counts do not prove which individual EARLY predicate failed; zero final EARLY does not establish zero signals throughout the run or an hourly opportunity rate. AVOID may include hard risks or lifecycle/decision exclusions; it is not a realized losing trade. WAIT/DATA LIMITED are not negative returns.

Profitability cannot be evaluated without immutable qualifying pre-grad signal snapshots and contemporaneous eligible non-EARLY controls; first valid executable state after the frozen manual latency; supported units and contemporaneous USD reference; correctly versioned buy/sell quote math and relevant fees/restrictions; horizon exits across any migration; realistic interface/network/reserve costs; and complete outcome/missingness accounting. Snapshot math is not guaranteed execution or proven sellability. Existing core cost estimates and provider USD marks do not supply this evidence. This session supplies no complete paired after-cost evaluation or validated predictive test. The retired infrastructure-censored cohort cannot be reused as that evidence.

## Decision and single next milestone

**The architecture can support the objective as bounded observational research, but the current strict strategy cannot satisfy pre-graduation product intent by design.** Continue the existing core only for its explicit later-entry purpose. For early manual decisions, review and qualify the already separate frozen pre-graduation research instrument; do not redesign or relax the strict core, and do not activate a cohort now. Stop evidence collection if current authoritative quote/state compatibility cannot be established.

**Single highest-value next milestone: establish an independently reviewable pre-graduation signal-to-exit measurement contract.** Before separately authorizing collection, demonstrate that the existing research instrument can preserve the exact signal/control snapshot and produce a coherent, timestamped T+10 entry and300s exit quote receipt under authoritative current math, including migration handling, all costs and explicit unavailable outcomes. Unsupported execution conditions must remain unavailable; no guessed PumpSwap tail is required or accepted. This is a prerequisite for evaluating the hypothesis, not proof of it and not authorization to run Phase4.

**CONDITIONAL GO for research instrument qualification; NO-GO for trusted buying recommendations.** The technical ability to observe some current activity is demonstrated. Superior after-cost early-entry outcomes are not. PRE_COHORT_READY=NO.

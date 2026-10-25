# Market-data reliability — Phase 2B, 2026-10-25

**PRE_COHORT_READY=NO.** Starting HEAD a35d5c8002968e1fc3b6495b7f8d00efacda9301, remediation/early-edge-evidence-readiness. Phase2A approval consumption remains disabled. The published serial architecture is retained. No monitor, live provider request, trade, actual cohort, endurance or six-hour experiment was started. Synthetic unit/integration fixtures are not real-market observations.

## Assessment

The existing adapters have substantial deterministic coverage for source scope, supported layouts, units, identity, freshness, deduplication and known coverage loss. One reproducible pool-account identity validation defect was found and corrected after failing tests: required default mint/vault keys could previously enter parse_pool's ostensibly verified result. No evidence links that gap to the historical8-byte PumpSwap event suffix or previous operational overload.

Current **wire compatibility is conditional**: the bundled Pump TradeEvent layout has authoritative provenance and accepted historical live evidence; it was not freshly compared to current deployed traffic here. The known unexplained PumpSwap extension remains fail-closed and unresolved. Fixture compatibility is not a current-provider delivery guarantee. Tests passing do not establish chain-wide discovery, complete trading history or readiness to collect prospective research.

## End-to-end source/evidence trace

|Boundary|Implementation and preserved identity/time|Verification and limitations|
|---|---|---|
|Pump launch|[discovery.py](../app/discovery.py): OnchainPumpDiscovery.run/receive, decode_event. Confirmed canonical Pump logs subscription/ACK; program invocation stack; successful transaction and invocation; event mint/curve PDA, signature/slot and ordinal retained. Launch metadata is distinct from observed market price/cap.|Malformed/failed/foreign invocations provide no valid event. Replay dedup is bounded. Create/migration decoding intentionally validates stable identity prefixes, not the full TradeEvent-tail contract. Discovery before admission and historical launches not seen this session are not backfilled.|
|Pump trades|Same adapter: minimal TradeEvent mint prefix filters untracked traffic, preserving ordinal placeholders. Tracked events require the exact full schema, finite supported values, nondefault user/mint and successful canonical invocation. MarketEvent carries source=Solana WSS, signature, event ordinal, slot and canonical trade fields.|Not instruction slippage/max/min reconstructed volumes. Known executed quote_amount, or explicitly supported legacy sol_amount with independently verified SOL curve semantics, supplies native quote volume. No fabricated USD trade price. Unsupported tracked tail causes token gap; unrecoverable identity conservatively causes global gap.|
|Quote units|Event quote_mint is reconciled with independently parsed curve quote where required; only WSOL9→SOL and USDC6→USDC are recognized. Unknown/conflicting/zero executed semantics yield unknown units and no usable volume.|Unknown is not converted to SOL/USD; mixed/unknown units invalidate feature-volume evidence. Numeric zero in an unknown-unit diagnostic is not observed zero buyer flow. Token amounts are not quote amounts.|
|Curve observation|[providers.py](../app/providers.py): curve_progress_batch; [onchain.py](../app/onchain.py): parse_curve/parse_global/curve_progress. Canonical owner/discriminator, reserve/supply/invariant checks and independently derived PDA; global baseline cached at most300s; incompatible progress unavailable. Engine poll timestamp is acquisition time.|Progress is token reserve depletion, not price gain. Complete flag is not confirmed migration. Current curve cache does not supply old missing trades or a full historical curve. Batch progress reports do not expose all pricing-slot receipt guarantees of the separate research quote oracle.|
|Visible/recovered migration|Discovery validates canonical visible migration identity. [truncation.py](../app/truncation.py): migration_identity, transaction_impact, migration_freshness_error. Canonical named account layouts, Pump/PumpSwap/PDA identity, succeeded transaction, tracked membership and session-bound recovered-event digest.|Recovered migration requires complete verified provenance, not a source string or arbitrary VERIFIED flag. Inner migration with unproved CPI success is not invented. Recovery preserves chain time and separate acquisition freshness under45s recovery/20s application bounds.|
|Independent pool verification|SolanaProvider.inspect obtains suggested pool accounts and calls parse_pool: owner, discriminator, minimum stable layout, expected base mint; now required mint/vault identities must also be nondefault. DEX pair/migration hint alone is not verified_pools.|Prefix identity proof is not a full initialized-pool/exit-liquidity guarantee. Creator fee recipient may legitimately be default. Vault identity strings alone do not prove current token balances/authorities; that stronger check belongs to the research oracle. Unknown nondefault quote assets remain unknown units.|
|PumpSwap acquisition|[pumpswap.py](../app/pumpswap.py): selection/reconcile/handle/parse_logs. At most25 verified pool subscriptions on one standard connection; distinct subscription ACKs, current registry agreement, canonical successful invocation and full BuyEvent/SellEvent decoding; only matching event.pool accepted.|Complete valid foreign events ignored; unknown/malformed foreign payload is not filtered away. Signature+original ordinal+pool dedup persists across reconnect. Actual user_quote_amount_in/out only; no max/min amounts, global trade feed or normal-path getTransaction requests.|
|Engine admission/processing|[engine.py](../app/engine.py): submit/_process/drain_events. Source label, mint, signature, event time and evidence survive normalization; tracked/venue/pool/epoch filters before mutation, actual processing-time freshness in queued drain, memory/SQL idempotency and explicit terminal accounting.|Priority selection then chronological timestamp/sequence order WITHIN the bounded selected batch; no global slot-order guarantee across all arrivals. Canonical late trades have an explicit out-of-order exception, not a guarantee that RPC and WSS arrive in chain order. Source strings are internal adapter labels, not cryptographic authorization. No external raw MarketEvent injection API was found in main.py.|
|Features/classification|[features.py](../app/features.py): calculate_features/window_features; engine.refresh_trade_continuity/trade_status. Six time windows, observed counts/quote flow/wallet heuristic, venue/epoch filtering and fresh continuity enrichment;180s clean coverage,>=3 samples and20s freshness remain.|Feature math can exist for incomplete windows, but CURRENT requires continuity/units/sample/freshness checks. Raw ratios are not a probability or approved entry. Known quote volumes are not USD without separate conversion.|
|Opportunity/core consumers|[opportunity.py](../app/opportunity.py): separate lifecycle freshness and unvalidated research action; [economics.py](../app/economics.py)/[companion.py](../app/companion.py): strict market/flow/security/currentness, risk and approval gates.|EARLY can be lifecycle-only, with missing flow/security declared; this is intended research behavior, not fabricated CURRENT or a buy. Core requires complete post-grad gates and remains unapproved after Phase2A. Manual market context is not canonical buyer flow or research fill evidence.|

## Time, ordering and continuity invariants

- MarketEvent validates finite/nonnegative timestamp/volume, positive optional price/cap and nonnegative liquidity. Adapters validate their own program/layout and timestamps; engine queued processing uses a newly read application clock for every event. Direct process calls without now follow existing event-time/replay semantics; they are not a real-time acquisition-freshness certificate.
- Source event timestamp, RPC acquisition time, recovery observation/verification time and processing/durable completion are different concepts. Recovered lifecycle age exception remains confined to session-verified migrate/migrate_v2; it grants no old post-grad coverage, market price or samples.
- Trade/market/security freshness is20s in the strict decision inputs except the existing security TTL300s. Curve-current checks use their existing lifecycle policy; Opportunity's configured curve freshness180s is not a relaxed trade freshness window. Stale or future-currentness failures are not fresh evidence.
- Migration records real graduation time, starts flow_epoch=max(now,event.ts), clears last_trade and changes venue. Pre-grad Pump trades cannot supply post-grad flow. PumpSwap subscription ACK starts pool coverage; absent ACK, unsubscribe, registry change or transport loss prevents complete relevant coverage.
- Pump transport/unknown event loss is global for pre-grad coverage; tracked decode/stale/queue/buffer losses are local where identity is known. PumpSwap pool-specific truncation/decoding is local; shared disconnect gaps all subscribed pools. Recovery pending blocks CURRENT, untracked-confirmed resolution preserves previous coverage, tracked recovery identifies affected mints without fabricating executed economics. Overflow/expiry/unresolved classifications fail closed.
- PriorityBuffer tracks rejected incoming and accepted-then-evicted events separately. Detached remainder cancellation/shutdown is explicit; heap depth alone is not pending-work accounting. Rolling500-event eviction within180s, observation pauses, clock reversal and resource trims invalidate relevant continuity. Durable row count alone cannot establish evidence completeness.
- Standard confirmed PubSub cannot independently prove delivery of every relevant transaction. ACK, healthy connection or no detected gap is not cryptographic completeness or chain-wide coverage. CURRENT is the implementation's conditional observed-evidence standard, not a guarantee against undetectable provider omission or later reorganization.

## Reproduced defect and minimal correction

### Before

parse_pool verified owner/discriminator and expected base mint but did not reject default base_mint, quote_mint, base_account or quote_account. A byte-valid Pubkey is not necessarily a usable nondefault identity. A default base matching a caller's default mint or a matching real base with default quote/vaults was accepted. This could let malformed account data appear in security.verified_pools; it did not by itself defeat unit, coverage or strict approval gates.

New test_market_data_reliability.py was run against the original source first: **4 failed,1 passed in.62s**. Each default required identity failed the expected rejection assertion. The valid unknown-quote/default-optional-creator case passed. Original result is retained at data/early_edge/market-data-20261025/before-fix.txt.

### After

parse_pool derives the four required keys once and rejects any default value before returning verified identity. Existing expected-mint mismatch and owner/discriminator/layout checks remain. Optional creator_fee_recipient is deliberately NOT included in this required set; valid zero-creator-fee pools remain supported. Nondefault unfamiliar quote mints are not assigned arbitrary decimals or rejected as malicious; downstream units remain unavailable.

No event decoder/schema, quote calculation, capacity, scheduling, transaction/acknowledgement or risk/freshness setting changes. Existing test_onchain valid virtual-reserve fixture now supplies nondefault quote/vault keys instead of relying on zero-filled placeholders. The nine new cases include a production SolanaProvider.inspect integration using fixture RPC responses: malformed pool data must not enter verified_pools. Unknown/missing curve remains unavailable. No HTTP request or engine is used by those new fixtures.

This is a software validation correction, not a claim of a reproduced real-market default-key pool, a historical failure root cause or complete pool sellability proof.

## Schema compatibility and provenance

Read-only schema metadata/hashes are recorded in data/early_edge/market-data-20261025/schemas.json. No schema file changed, no third-party decoder was substituted and no official package was installed.

|Bundled source|Supported contract|Current evidence status|
|---|---|---|
|pump_events.json / Pump TradeEvent|36 fields, discriminator bddb7fd34ee661ee, final quote_transfer_fee:u64; official @pump-fun/pump-sdk4.2.0, gitHead4eea7389c1142d1313d08d468de6672ed4545573, src/idl/pump.json SHA256 c53b8f5d39887afd27cc40a256527a421c2d91b64a9014dc4952a261f4f36a01.|Strict canonical fixtures pass, opaque extra bytes and old incomplete layouts reject. Historical live acceptance in preserved SDK audit. No fresh deployment/provider compatibility claim.|
|pump_amm_events.json / PumpSwap|Official pump-public-docs639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22, Buy40/Sell33 fields; final creator_fee_unclaimed:u64; discriminators67f4521f2cf57777 /3e2f370aa503dc2a.|Documented fixtures pass; preserved investigation reported live extra8 bytes. Their meaning remains unresolved here; affected traffic BLOCKED. Fixture success does not supersede that finding.|
|pump_instructions.json and pump_amm_recovery.json|Pinned official instruction accounts/discriminators, named mint/pool resolution and canonical multi-hop route PDA association.|Recovery tests cover supported legacy/v0/v1 forms, loaded addresses, outer/inner association and conservative ambiguity. New unsupported layouts/instructions remain unresolved/global; no universal future-version support is claimed.|

Bundled-file SHA256s:

- pump_events.json:5566d6bb9b36330e8296f824ab8a881508fece9549c9273bb9fa0eb57f3fe97d
- pump_amm_events.json:27c5169a9c334a2819e05901aecdb94f0108e3bc9459cf80a70c57d63a275615
- pump_instructions.json:9a14644024a411ab141102e675ff1e091ab79e2b271c745c835f97f09e8659f5
- pump_amm_recovery.json:214a58d3224949ba3a1abd7d764f9872f71307c6017e98604b3c90c56d8b3b90

These identify local bundles, not the full upstream IDL tarballs. The Pump event pin4.2.0 is distinct from research quote SDK pins; do not infer PumpSwap event suffix meaning or current quote parity from it. Existing canonical create/migration prefix layouts have their original provenance.

## Failure-validation matrix

Inspected actual adapters/engine/feature code and executed the focused suites listed below. Tests use synthetic databases/providers; they cannot prove live provider completeness.

|Requirement|Executed coverage / outcome|
|---|---|
|Unsupported layouts fail closed|test_pump_trade_schema_audit: official420 exact extension, no_opaque_tail, documented_old_layout/truncation, failed scopes; test_pumpswap_flow: tail/bool/framing/short payload and wrong program. No unknown-tail acceptance.|
|Unknown units never become SOL/USD|test_onchain_trades: quote_units_fail_closed, legacy_SOL_requires_verified_curve, conflicting_verified_quote, explicit amounts; test_pumpswap_routing: unknown_units/category bounds. Native known SOL/USDC units remain separate from USD.|
|Reconnect/missing events invalidate coverage|test_onchain_discovery reconnect/resubscribe; test_onchain_trades continuity_outage/queue_gap/immediate invalidation; test_pumpswap_flow transport disconnect/local truncation and reconnect/dedup.|
|Truncation/ambiguity cannot manufacture CURRENT|test_truncation_recovery pending block/global unresolved, transport during pending, unavailable; test_multihop_recovery ambiguous routes/loaded keys; test_recovery_pressure overflow/expiry/claims; no recovered amounts used as executed flow.|
|Unverified migration/pool fail closed|test_migration_recovery identity/PDA/program/layout/failed transaction and inner CPI restrictions; test_migration_freshness fake/partial/source-only proof rejects. New default-key parser and inspect integration; pool is independently parsed rather than trusting a migration hint.|
|Stale evidence unavailable|test_migration_freshness ordinary_stale_event_rules_unchanged and post-grad epoch; test_evidence_remediation actual-time dequeue and observation pause; full economics/Companion/security/Opportunity tests cover their existing TTLs. Market, security and trade currentness are not interchangeable.|
|Dropped events cannot preserve eligibility|test_evidence_remediation reject/evict accounting, cancelled batch remainder, stale dequeue, resource trim, bounded overload; test_onchain_trades queue drop/degrade/unknown display. No decrease of quality standards to retain entry.|
|Correct PumpSwap pool/epoch/ordinal|test_pumpswap_flow verified registry/capacity/ACK/epoch/new clean window/late Pump rejection; test_pumpswap_routing matching/foreign/mixed notifications, original ordinals, registry mutation and replay dedup.|
|Buyer-flow semantics|test_onchain_trades normalized_breadth_flow_whale_creator and PumpSwap actual user_quote fields pipeline. Independent-buyer count is a synchrony/size-discounted wallet estimate, not proof of beneficial ownership; partial data cannot prove crowd absence.|

Focused command covered15 test modules: market_data_reliability, onchain, onchain_discovery, onchain_trades, pump_trade_schema_audit, pumpswap_flow, pumpswap_routing, pumpswap_diagnostic, truncation_recovery, multihop_recovery, migration_recovery, migration_freshness, recovery_pressure, discovery_security and evidence_remediation. **342 passed in30.63s, exit0**. No live decoder failure rate or new CURRENT observation is reported.

## Operational blockers, ranked

1. **Known schema incompatibility — post-grad buyer flow:** preserved live PumpSwap suffix failure is a genuine acquisition blocker; strict rejection is correct. It is separate from pool filter delivery (historical zero-notification failure was not reproduced on later probes) and from the newly corrected default-key validation. Authoritative complete layout plus separately authorized fresh validation is required; no guessed tail or aggregate-count substitute.
2. **Incomplete timely processing — shared operational evidence:** finite50/s growth failures, previous stale/dropped/censored periods and limited serial service margin remain as described by the published ADR. No new capacity measurement or optimization here. Even successful decode/admission cannot prove timely processed/durable evidence.
3. **Observation coverage and readiness — early signal population:** hot/background monitoring and prioritized security scans do not ensure equally frequent current observations for250 candidates. Canonical units may be unavailable before independent curve verification. That limits fair early/control opportunities; it is not permission to assume SOL or lower observation requirements.
4. **Transport truncation/recovery — provider constraint plus bounded capacity:** Log truncated is legitimate standard-RPC behavior; recovery cannot reconstruct every hidden trade's economics. Genuine transport loss, unsupported recovery, overflow/expiry still gap continuity. Those losses must remain measured and fail closed. Silent PubSub omissions cannot be ruled out solely by connection health.
5. **Stale/partial independent context:** DEX caches/20s market freshness, security TTL and sequential inspection slots, source disagreement and unknown liquidity remain constraints. A single price source with no detected disagreement is not independent agreement. Curve-only EARLY does not prove broad buyers, no creator-linked selling or current executable entry/exit price.
6. **Residual model/evidence limitations:** wallet-independence heuristic, top20 owner concentration proxy, current executable quote coverage, missing matched controls and prospective after-cost predictive value remain unresolved. These are not fixed by this pool parser change; further audit phases require separate authorization.

Known provider/market constraints (truncated logs, eventual confirmed transaction availability, reorg risk, unsupported quote assets, no honest activity in a bounded window) are distinguished from software defects. No software patch can make absent observations complete. The default-key parser gap was reproducible software behavior; host contention, current provider delivery, new schema changes and all hypothetical missed opportunities were not newly established causes in Phase2B.

## Readiness for controlled real-market observation

**Local deterministic reliability: improved and tested. Live observation readiness: conditional, not exercised.** A separately authorized, bounded, non-enrolling pre-grad diagnostic could assess current wire compatibility, acquisition/processing/censorship counters, quote units, event age, continuity and safe shutdown on a frozen clean source/config. It would need explicit stop conditions for unknown layouts, source/identity conflicts or unaccounted loss; an ACK/no-error count alone would not qualify it. No such run is authorized or started by this document.

Trusted post-grad flow remains blocked for affected unexplained layouts. No new cohort, repeat endurance experiment, source/settings change, risk relaxation or trading follows automatically. Phase2A remains fail closed: descriptive reports or arbitrary evidence rows cannot approve strict startup entry. Existing strict CURRENT requirements are180 clean seconds,>=3 samples, consistent known units, current relevant transport/pool and20s trade freshness; this report creates no exceptions.

## Scope, preservation and quality

Only production change: backend/app/onchain.py parse_pool required-key rejection. Direct tests: new backend/tests/test_market_data_reliability.py and corrected valid fixture in backend/tests/test_onchain.py. This report is the fourth Phase2B file. Full event decoder consumption, financial fields, ordinal dedup, callback ordering, persistence/rollback and storage semantics are untouched.

Initial receipt data/early_edge/market-data-20261025/initial.json records HEAD, five existing worktree hashes, unchanged architecture ADR, seven original frozen hashes and retired DB size/mtime. No frozen source/result or retired data is edited. Full-suite/static/frontend results and actual publication outcome follow after completion. No synthetic test match, trade or cohort is presented as real prospective evidence.

### Completed validation

- Before-fix regression:4 failed/1 passed,.62s, preserved separately. After-fix focused market-data/recovery suite:342 passed30.63s, exit0.
- Complete backend: **891 passed,1 skipped in167.93s, exit0**, using the existing bounded-cleanup diagnostic. Original asyncio.Runner.close and real worker joins remain; the diagnostic only supplies bounded loop wakeups. This is not unrestricted ordinary-runtime cleanup qualification. Phase2A's ordinary300s/exit124 stall remains documented; it was not needlessly repeated for this change. No new application shutdown workaround.
- Frontend39 passed5.54s; TypeScript/production build passed(Vite3.61s), exit0. No frontend change.
- Full Ruff backend/scripts and mypy42 application sources passed. Basic source/document secret scan passed; final tracked/new-file whitespace, link and preservation checks passed. No packages installed or dependency/lock manifests changed. Previously DNS-blocked online dependency audits remain UNVERIFIED; no new clean audit is claimed.
- Phase2A startup approval-negative regressions, financial/observer/replay/transaction/crash/shutdown tests are included in the complete suite. No test result is promoted to real CURRENT, live compatibility or economic evidence.

**Phase2B conclusion:** a minimal independently verified pool-identity check was strengthened; established failure semantics pass deterministic validation. Current live compatibility/completeness and broader readiness remain conditional/unverified. PRE_COHORT_READY=NO. Stop here; Phase2C and collection have not begun.

### Publication outcome

Staging only the four tested Phase2B files failed because Git metadata is read-only (.git/index.lock). No commit/push, API mutation or permissions workaround. HEAD remains a35d5c8002968e1fc3b6495b7f8d00efacda9301. All five pre-existing working-tree changes remain untouched.

Publish from a writable WSL terminal after reviewing the exact staged scope:

```bash
git switch remediation/early-edge-evidence-readiness
git add -- backend/app/onchain.py backend/tests/test_onchain.py backend/tests/test_market_data_reliability.py backend/docs/market-data-reliability-20261025.md
git diff --cached --name-only
git diff --cached --check
git diff --cached
git commit -m "fix: reject default verified pool identities"
git push origin remediation/early-edge-evidence-readiness
```

Stage ONLY those four files. No main push, force push or merge. No later phase or real-market run is authorized by publication.

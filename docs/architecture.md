# Architecture

Modular Python monolith, SQLAlchemy 2 / SQLite WAL and React compiled by Vite. FastAPI serves static assets and SSE snapshots; server-to-browser delivery needs no bidirectional WebSocket state. One Python process on loopback. No wallet or execution API.

Providers → bounded priority queue → token state/funnel → rolling features → security/holder reports → scores → central fail-closed risk gate → delayed paper fills → persistent outcomes. Market source provenance and freshness remain separate from analytical scores. Free sources produce observation, not invented wallet-level features.

Bounded candidates (250), deep set (25), event windows (500/token), dedup cache and response sizes. Persistent events are retained 24h; snapshots 30d; outcomes/signals 90d. Paper history, strategies and evaluation summaries are protected. Maintenance deletes eligible records, checkpoints WAL, and only explicit optimize vacuums. Database at cap blocks new expendable writes.

Signal snapshots are immutable and identify mode, session and strategy hash. Outcomes use later observed prices, with missing horizons marked unavailable rather than forward filled. Evaluation uses a chronological holdout and sample counts. Replay consumes recorded normalized events chronologically without remote requests.

## Two-tier free observation

Discovery admits bounded candidates without requiring trade events. `deep_mints()` ranks lifecycle
state, meaningful verified curve progress, then launch recency. Early low-progress tokens yield
to new auditions; protected paper positions remain prioritised.
At most one hot lightweight batch per enrichment iteration samples due members of that deep set.
A second, slower tier samples remaining active non-rejected/non-expired pre-grad candidates,
oldest attempt first (discovery time if never polled). New arrivals cannot jump the waiting line.
Never-polled background candidates are immediately eligible; previously checked ones wait 180
seconds. At most 25 background curves are checked per 30-second batch interval. The shared
strict parsers/global cache and RPC limiter apply to both tiers. No per-event RPC fan-out.
Curve PDAs are derived locally rather than trusting a launch-supplied address. Global data joins
the same request when the 300-second cache expires. Strict owner/discriminator/reserve/supply
parsers and current-global compatibility checks return UNKNOWN on failure. Failed observations
clear previous progress. Curve completion alone never sets graduation; the separately subscribed
migration event remains the authoritative lifecycle transition. Pool security remains separately
verified on-chain after migration.

WATCHING → MATURING can use fresh verified 30% curve progress; MATURING → NEAR_GRADUATION
uses 85%. NEAR_GRADUATION retains its label down to 75%, then legitimately returns to MATURING;
a later rise to 85% re-enters. Unknown/stale curve evidence also removes the near label, with
a distinct reason rather than claiming verified selling. MATURING returns to WATCHING if
meaningful curve/activity evidence is no longer current. These observational transitions do
not alter quality scores or entry gates. Migration still overrides pre-grad lifecycle.
Full security/holder/creator scans require migration or fresh verified 60% progress, run within the
same deep set, and are globally limited to one scan per 30 seconds with per-token security TTL.
Security attempts and successful report timestamps are separate; failed refreshes become UNKNOWN.
DEX market polling only receives graduated deep mints, with its existing bounded cache/limiter.

Lightweight curve events are recorded for chronological replay. Launch metadata remains an
unverified launch-time snapshot (`launch_metadata`); no USD price, current reserve, or entry
quality is inferred. HTTP health tracks attempts, requests, successes, errors and cooldowns.
Unavailable buyer/flow fields and trade-dependent score components are null in dashboard/detail
APIs and history charts; internal conservative scoring retains observed counts, never asserting a
verified buyer census. An explicit missing-trade-stream entry gate prevents accidental promotion.

Background work follows hot polling and selective security work, and is paused during resource/
storage pressure or RPC cooldown. Any new RPC errors delay background work by 60/120/240
seconds (capped at 300); successful background recovery probes reduce that backoff level.
Background requests have one HTTP attempt, not a retry burst. Retry-After remains honoured by
all RPC work, and hot polling resumes before background when permitted. Backoff never enlarges
batches/concurrency. Full security eligibility remains exclusively within the hot/deep set.

Session peak curve progress is an in-memory historical maximum, separate from current progress;
it resets on restart. Restored pre-grad lifecycle labels reset to WATCHING until new evidence.
Curve events include hot/background provenance and remain replayable. Health reports logical
hot/background batches, actual curve HTTP request starts (including retries), attempted/returned
curve-account counts, verified observations, background size/due count, oldest attempt age and
background backoff deadline. These scheduler counters reset each process session and are bounded.

## FOMO Companion

`backend/app/companion.py` is a pure, typed presentation layer over Token and the core decision. It maps WAIT, REJECT and MISSED to WAIT, REJECT and TOO LATE. A stored ALLOW_PAPER_ENTRY is revalidated using the unchanged `evaluate_candidate()` and the engine's frozen approved evidence, provider health and resource-pressure context. Additional structured checks require positive finite position size, current security/trade/market evidence and economics. Unknown, stale or inconsistent evidence fails closed; no frontend threshold strategy or English-reason parsing determines entry.

`token_view()` supplies identical companion results to dashboard/SSE and token detail. No new endpoints, acquisition tasks, RPC/DEX requests, trade subscriptions, strategy settings or state transitions are introduced. Attention derives from current lifecycle and freshness; session peak is descriptive only. Existing two-second SSE snapshots update the queue and detail decision; the existing single selected-token detail request supplies technical history. Evicted tokens lose their current detail panel. Entry alerts also require a current backend companion entry result.

React cards show action text, attention, current/peak curve, evidence quality, blockers and existing economics. Local clipboard access is the only new browser integration. Development-only DOM tests use [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/) and [Vitest's jsdom environment](https://vitest.dev/guide/environment.html); production retains React/CSS without a new framework.

DEMO-only `companion_examples()` creates four synthetic core-evaluated UI snapshots outside engine.tokens, the outcome collector and paper account. Real snapshots return no examples and never inherit fixture evidence. Bounded active/hot/background monitoring and public RPC backoff are unchanged.

## Opportunity and external manual positions

The scanner now publishes an independent unvalidated research projection. Existing VERIFIED
curve events append at most 32 compact timestamp/progress pairs per token. Pure Opportunity and
Exit modules consume these observations; they never call providers, alter lifecycle/core decisions,
or feed paper entries/approved evidence. An independent research config/version leaves core
strategy identity unchanged. Manual USD market observations stay outside Token/core evidence.

A local journal uses the same SQLite WAL database, with Alembic 0003 tables for bounded open
manual-position state and bounded prospective research work. Immutable research/mark/open/close
records use distinct namespaces. Projections refresh at most once per second; SSE reads cached
results, without SQL scans or extra RPC. Manual positions do not alter scanner admission or poll
priority. Opportunity and Manual Positions are additional React pages, not replacements for
Companion, Entry Candidates, paper research or System Health. See
[Opportunity Intelligence](opportunity-intelligence.md) for exact heuristics and limitations.

## Provider-independent discovery

Discovery providers conform to a shared health/run interface and submit ordinary MarketEvents. Standard Solana WSS Pump create/migration logs feed the existing bounded queue; optional PumpPortal uses the same path. Cross-source create deduplication happens before token mutation. Either connected discovery source satisfies the existing discovery-health gate; absence of all sources reports degraded health. No classification/threshold changes or HTTP discovery enrichment. See [provider design and limitations](providers/onchain-discovery.md).

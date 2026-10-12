# Architecture

Modular Python monolith, SQLAlchemy 2 / SQLite WAL and React compiled by Vite. FastAPI serves static assets and SSE snapshots; server-to-browser delivery needs no bidirectional WebSocket state. One Python process on loopback. No wallet or execution API.

Providers → bounded priority queue → token state/funnel → rolling features → security/holder reports → scores → central fail-closed risk gate → delayed paper fills → persistent outcomes. Market source provenance and freshness remain separate from analytical scores. Free sources produce observation, not invented wallet-level features.

Bounded candidates (250), deep set (25), event windows (500/token), dedup cache and response sizes. Persistent events are retained 24h; snapshots 30d; outcomes/signals 90d. Paper history, strategies and evaluation summaries are protected. Maintenance deletes eligible records, checkpoints WAL, and only explicit optimize vacuums. Database at cap blocks new expendable writes.

Signal snapshots are immutable and identify mode, session and strategy hash. Outcomes use later observed prices, with missing horizons marked unavailable rather than forward filled. Evaluation uses a chronological holdout and sample counts. Replay consumes recorded normalized events chronologically without remote requests.

## Two-tier free observation

Discovery admits bounded candidates without requiring trade events. `deep_mints()` ranks lifecycle
state, meaningful verified curve progress, then launch recency. Early low-progress tokens yield
to new auditions; protected paper positions remain prioritised.
At most one lightweight batch per enrichment iteration samples due members of that deep set.
Curve PDAs are derived locally rather than trusting a launch-supplied address. Global data joins
the same request when the 300-second cache expires. Strict owner/discriminator/reserve/supply
parsers and current-global compatibility checks return UNKNOWN on failure. Failed observations
clear previous progress. Curve completion alone never sets graduation; the separately subscribed
migration event remains the authoritative lifecycle transition. Pool security remains separately
verified on-chain after migration.

WATCHING → MATURING can use fresh verified 30% curve progress; MATURING → NEAR_GRADUATION
uses 85%. These configurable observational thresholds do not alter quality scores or entry gates.
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

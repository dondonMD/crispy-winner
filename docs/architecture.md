# Architecture

Modular Python monolith, SQLAlchemy 2 / SQLite WAL and React compiled by Vite. FastAPI serves static assets and SSE snapshots; server-to-browser delivery needs no bidirectional WebSocket state. One Python process on loopback. No wallet or execution API.

Providers → bounded priority queue → token state/funnel → rolling features → security/holder reports → scores → central fail-closed risk gate → delayed paper fills → persistent outcomes. Market source provenance and freshness remain separate from analytical scores. Free sources produce observation, not invented wallet-level features.

Bounded candidates (250), deep set (25), event windows (500/token), dedup cache and response sizes. Persistent events are retained 24h; snapshots 30d; outcomes/signals 90d. Paper history, strategies and evaluation summaries are protected. Maintenance deletes eligible records, checkpoints WAL, and only explicit optimize vacuums. Database at cap blocks new expendable writes.

Signal snapshots are immutable and identify mode, session and strategy hash. Outcomes use later observed prices, with missing horizons marked unavailable rather than forward filled. Evaluation uses a chronological holdout and sample counts. Replay consumes recorded normalized events chronologically without remote requests.

# Operating guide

Start DEMO to inspect all twelve scenario families offline. SIMULATED DATA is prominent and stored in data/demo.db. Approximately 90 seconds after launch, migration scenarios begin; developing, dumps and recovery become visible over the next minutes. No synthetic evidence calibrates the real strategy. Absence of entries is expected while historical evidence is insufficient.

OBSERVE is the default: outbound public APIs only, no wallet. The Radar prioritizes candidates rather than every chain launch. Open a token for risk reasons, individual costs and charts. Unknown/stale information is visible. System Health includes provider connectivity, rate-limit state in the API, RAM/CPU, queue drops and storage warnings.

For optional trade observations, set PUMPPORTAL_API_KEY privately and trade_stream_enabled: true in YAML, after reviewing provider charges. This is a data-provider credential; no wallet secret is requested by this application. Never paste keys into a tracked file. You can instead supply SOLANA_RPC_URL for an optional Helius/custom standard RPC endpoint.

PAPER uses real data and the durable $20 ledger. It will not force trades. Use evaluate before interpreting scores. A strategy must have sufficiently many complete first-eligible signal outcomes and positive later validation/holdout evidence. `freeze-evidence` explicitly records the current historical result for that strategy version, then restart to load it. Read methodology limitations first. This is research approval for simulated entries, not permission to trade real money.

MANUAL ASSIST displays the same strict decisions and venue links. Any actual purchase is performed independently by the user; the application never submits a transaction.

Stop with Ctrl+C before manual database optimization or updates. Back up data/radar.db after shutdown (or use SQLite backup tooling including WAL consistently). Paper history and strategy summaries are protected. Never edit database balances to make performance look positive.

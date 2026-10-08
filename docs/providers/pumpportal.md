# pumpportal

Verified: 2026-10-08 (documentation, not service SLA).

Purpose: Discovery, migration; optional metered trades

Official documentation: https://pumpportal.fun/data-api/real-time/

Endpoints/features: wss://pumpportal.fun/api/data; subscribeNewToken, subscribeMigration, subscribeTokenTrade

Authentication / free vs paid: Free creation/migration. Trades cost 0.01 SOL/10,000 events; linked funded account and API key required. Trade subscriptions disabled by default.

Rate limits: One WebSocket only; bounded reconnect/backoff. No published numerical discovery quota assumed.

Limitations / fallback: Third party, no guaranteed delivery. Missing trade breadth prevents entry. Reconnect resubscribes only bounded candidates.

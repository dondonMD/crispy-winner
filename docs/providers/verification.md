# Live verification — 2026-10-08

Read-only `python scripts/smoke_providers.py`; no key, paid subscription or transaction. Result:

```json
{
  "PumpPortal": {
    "connected": true,
    "new_tokens": 19,
    "observed_field_names": [
      "bondingCurveKey",
      "initialBuy",
      "is_mayhem_mode",
      "marketCapSol",
      "message",
      "mint",
      "name",
      "pool",
      "signature",
      "solAmount",
      "symbol",
      "traderPublicKey",
      "txType",
      "uri",
      "vSolInBondingCurve",
      "vTokensInBondingCurve"
    ]
  },
  "Solana RPC": {
    "connected": true
  },
  "DEX Screener": {
    "connected": true,
    "matching_pumpswap_markets": 0
  }
}
```

DEX connectivity succeeded; the WSOL query had no matching PumpSwap base market. This is not evidence that graduation or funded trades were observed. Launch payload field names are an empirical observation, not an assumed stable schema. Unknown/missing fields remain unavailable.

Full OBSERVE pipeline probe in an isolated database:

```json
{
  "mode": "OBSERVE",
  "simulated": false,
  "candidate_count": 14,
  "processed_events": 14,
  "pump_connected": true,
  "sources": [
    "PumpPortal"
  ],
  "decisions": [
    "WAIT"
  ],
  "paper_cash": 20,
  "paid_stream_enabled": false
}
```

All real candidates waited; no synthetic data or paper spending occurred.

## Provider-independent discovery — 2026-10-16

Read-only OBSERVE, isolated temporary SQLite database, standard public mainnet
`wss://api.mainnet-beta.solana.com`, public HTTP RPC. No Helius endpoint/key was
configured, so Helius connectivity was **not** verified. PumpPortal was disabled,
paid trade stream false, no wallet or transactions. Duration 90.9 seconds.

| Measurement | Result |
|---|---|
| Real creates decoded / processed launches | 68 / 65 |
| Authoritative migrations decoded | 1 |
| Active / hot / background | 65 / 25 / 40 |
| WSS messages / ignored | 41956 / 41887 |
| Decode errors / reconnects / duplicates | 0 / 0 / 0 |
| Discovery HTTP / enrichment attempts | 0 / 0 |
| Monitoring HTTP requests / requests per second | 5 / 0.055 |
| RPC 429s / total errors / final pressure | 1 / 1 / BACKING OFF level 1 |
| Verified curve accounts / curve HTTP requests | 35 / 2 |
| Curve accounts per curve HTTP request | 17.5 |
| Hot / background / security effective seconds | 52.5 / 360 / 60 |
| Background batches / oldest background attempt age | 0 / 75.0s |
| RSS / sampled CPU | 112.8 MB / 13.9% |
| Queue / peak queue / drops | 3 / 3 / 0 |
| Companion WAIT / ENTRY CANDIDATE | 65 / 0 |
| Paper cash / trade subscriptions | $20 / 0 |
| DEX state / requests | CURRENT / 3 |

Opportunity counts: DEVELOPING 30, DATA LIMITED 35, all other actions zero.
Evidence: LIMITED — LIFECYCLE UNKNOWN 35; LIMITED — NO TRADE FLOW, SECURITY UNKNOWN,
MARKET UNKNOWN 30. All 65 candidates reported trade flow unavailable.
Three observations were still queued at snapshot time; decoded creates and
processed launch counts are deliberately reported separately. No inactivity
expirations or adaptive-expiry deferrals occurred in this short run.

The migration event exercised existing post-grad processing; DEX was genuinely
used. One security refresh attempted and did not complete. The 429 remains
visible; existing shared backoff increased to level 1. Discovery itself adds no
HTTP calls, but discovering candidates naturally activates existing bounded
monitoring. This is not a controlled comparison of HTTP error rates or proof of
long-run provider capacity. No new profitability/edge claim is supported.

Validation: 177 backend tests, 36 frontend tests, Ruff, mypy (26 modules),
TypeScript/production build, secret scan (106 files), git diff whitespace checks,
frontend audit and backend pinned-lockfile vulnerability audit passed. No
dependencies were added. The backend audit used `pip-audit --disable-pip --no-deps
-r backend/requirements.lock` against the complete pinned lockfile.

DEMO: 12 synthetic scanner candidates, four original Companion actions, $20,
zero RPC requests/drops, 90.8 MB RSS. Separate synthetic 250/25 load: 8,000 bounded
history points, 94.41 MB RSS (+5.46 MB), 58.47 ms opportunity refresh, 23.29 ms
snapshot, zero snapshot SQL SELECTs, RPC requests or real research signals.

Coverage limitations: no outage backfill, no HTTP transaction fallback for
missing event logs, no Helius-specific live verification, and no endurance or
full-funnel real load claim from this 90-second session.

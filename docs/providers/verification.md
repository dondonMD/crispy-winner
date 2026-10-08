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

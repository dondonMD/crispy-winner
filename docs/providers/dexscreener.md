# dexscreener

Verified: 2026-10-08 (documentation, not service SLA).

Purpose: Post-graduation price and liquidity

Official documentation: https://docs.dexscreener.com/api/reference

Endpoints/features: GET /tokens/v1/solana/{addresses}

Authentication / free vs paid: Public no key, free.

Rate limits: Up to 30 addresses per batch; market endpoints 300 requests/minute; application uses at most 12/minute.

Limitations / fallback: Delayed/indexed data; aggregated tx counts cannot establish independent buyers. Failure leaves price stale, blocks entries.

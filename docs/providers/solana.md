# solana

Verified: 2026-10-08 (documentation, not service SLA).

Purpose: Mint authorities, extensions and largest holders

Official documentation: https://solana.com/docs/rpc/http

Endpoints/features: getAccountInfo, getTokenSupply, getTokenLargestAccounts, getMultipleAccounts, getSignaturesForAddress, getTransaction; logsSubscribe fallback research https://solana.com/docs/rpc/websocket

Authentication / free vs paid: Public RPC free with service limits; custom RPC optional.

Rate limits: Application 2 requests/second, concurrency 2, bounded retries; public limits may vary.

Limitations / fallback: Largest accounts only, not full holder census. Owner grouping required; unknown program accounts not assumed independent. Timeout blocks security clearance.

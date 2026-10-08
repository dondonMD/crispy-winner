# Research — 2026-10-08

Provider references are in providers/. Current PumpPortal trades are metered, unlike discovery/migration; free baseline must not pretend to know independent buyer flow. Pump supports Token-2022 creation and dynamic canonical-pool fees. USD and SOL paired curves exist; SOL-denominated event values must never be silently interpreted as USD. RPC logsSubscribe can flag Pump activity, but transaction decoding and RPC fan-out for every launch is unsuitable for the free laptop baseline; no fabricated fallback decoder is shipped.

Empirical hypotheses: breadth and persistence may be more useful than raw volume; coordinated timing/size patterns reduce estimated buyer independence but cannot establish ownership. Papers https://arxiv.org/abs/2602.14860 and https://arxiv.org/abs/2607.02795 are research leads, not profitability evidence. Runtime scoring is interpretable and uncalibrated; no paper coefficients are claimed as validated. Graduation is not a buy signal.

Fees reference https://pump.fun/docs/fees: bonding curve total currently 1.25%; canonical PumpSwap schedule varies. Default estimator uses conservative 1.25% per side plus separately configured network, platform, slippage and impact assumptions. No exact execution quote is promised.

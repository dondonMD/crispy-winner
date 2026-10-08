# Known limitations

- No profitability claim, wallet, autonomous live trading, private key, manipulation, front-running or private order flow.
- Free discovery/migrations work without a key in the verified probe. Wallet-level trade streams are now metered by PumpPortal and explicitly opt-in; no free substitute for buyer breadth is invented. Without them real entries normally stay WAIT.
- The default RPC is public and may throttle. DEX data is indexed, not tick-accurate. Receive timestamps do not establish on-chain event age or guarantee low latency. Market gaps make outcomes unavailable.
- The probe verified 19 launch events, RPC supply and DEX connectivity; it did not claim a live graduation was witnessed or validate the funded trade stream. Those paths have deterministic fixtures/tests. No funded account was supplied.
- Creator identity is provider-reported, not cryptographically linked ownership. Current creator fee recipients can change. Recent creator history is bounded to observed launches, not exhaustive.
- Largest-account distribution is limited to top 20, grouped by wallet; concentration across many smaller accounts may escape detection. Program exclusions require known addresses/verified pools. No full holder census.
- Timing/size clustering is intentionally conservative and can false-positive. Funding-source/transfer-graph clustering is not implemented; RPC fan-out would be substantial.
- Current-global curve progress applies only when supply and invariant offsets match. Historical global changes may still affect its interpretation; graduation is separately evidenced.
- USD prices exist primarily after graduation via DEX. No SOL amount is silently converted into USD. Curve-native prices are not displayed as dollar prices.
- Costs approximate balanced-pool impact, configurable fees and slippage. No route-specific quote, priority fee forecast, Token-2022 execution simulation or virtual-reserve quote is promised.
- Research mean intervals understate dependence; no production edge is validated. Frozen evidence requires data collection and explicit command, not automatic learning. Offline logistic regression, walk-forward tuning experiments and latency sweeps are future research improvements.
- Replay is limited by 24-hour raw retention and may report mismatches for sessions with incomplete recordings or unrecorded asynchronous expiry/resource trimming. It never labels a mismatch successful.
- One compact indexed record journal replaces dozens of nearly identical v1 tables. Alembic evolves it; event identities have a separate indexed table. This keeps migrations/querying small but does not provide full relational foreign-key analytics.
- A protected history alone can exceed the soft database limit. It is never deleted automatically; new expendable writes stop and maintenance requires user decisions.
- Windows setup scripts are provided; this build was tested on Linux/WSL, not a Windows desktop. No browser screenshot or visual browser automation was used. The production dashboard build and served assets were checked.

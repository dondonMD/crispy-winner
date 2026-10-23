# Exact Pump TradeEvent schema 4.2.0

The bundled CreateEvent/migration schemas retain official public-docs commit
639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22. Only TradeEvent advances to the
Pump-maintained @pump-fun/pump-sdk **4.2.0**, src/idl/pump.json.

- Published gitHead: 4eea7389c1142d1313d08d468de6672ed4545573.
- Full official IDL SHA256: c53b8f5d39887afd27cc40a256527a421c2d91b64a9014dc4952a261f4f36a01.
- Tarball integrity: sha512-3G1efTG8ihxejyso67wwc7EJGUzEI+xbQCJArqlc/unfPEEWiv+u51OqSG3cDOunRxwhTZEb81gMmrZSf9rsSA==.
- Official namespace linked by the Pump public README; unchanged npm maintainers;
  registry signatures and downloaded tarball integrity verified.
- Exact schema difference: append **quote_transfer_fee: u64** after
  creator_fee_unclaimed; all preceding 35 ordered fields are identical.
- Discriminator: **bddb7fd34ee661ee**. Full-consumption validation remains mandatory.

[Official SDK artifact](https://www.npmjs.com/package/@pump-fun/pump-sdk/v/4.2.0).
The public-docs IDL remains at 35 fields; the stale on-chain Anchor IDL has 34.
Program upgrade slot458921440 was 2026-10-19T17:47:02Z, after the public-docs pin.

The previous 60-second investigation reproduced2224 payloads with exactly8
trailing bytes under the35-field layout. A subsequent strict36-field live probe
accepted thousands of trades without layout failures. Unknown quote units remain
unavailable. Neither financial-field normalization nor units/gap/freshness gates
were changed. No opaque tail or old-event zero-padding compatibility was added.

Final pre-freeze corroboration, 2026-10-23: **12 successful finalized transactions,
5 slots (460398857..460398861),9 mints,6 BUY/6 SELL, all canonical SOL units**.
Each event consumed36 fields with zero trailing bytes, including the final u64;
canonical Pump buy/sell instruction named mint/user accounts, direction and ix_name
matched exactly. Eighteen bounded transaction lookups included six ambiguous
instruction mappings excluded from corroboration; no raw transactions or wallets
were retained. Report: data/early_edge/cross-slot-20261023.json (local redacted).
Diagnostic scripts never instantiate the engine or submit MarketEvents.

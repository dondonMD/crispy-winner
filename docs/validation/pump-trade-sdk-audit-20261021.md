# Pump TradeEvent and isolated SDK reference investigation — 2026-10-21

Production base remains `2bebbf2863de21041fffca80fb99507356a815b6` on `research/prospective-early-entry-edge`. All work remains uncommitted. No cohort was created. No thresholds, economic assumptions, recovery rules, PumpSwap decoder, paper approval or execution behavior were changed.

## Root cause and exact diagnostic branch

The old 1,840 failures were aggregated as `unsupported_layout`; their payloads were not retained, so it is not possible to retroactively reclassify each of those exact payloads. A fresh bounded 60-second read-only diagnostic reproduced **2,224 KNOWN_DISCRIMINATOR_TRAILING_BYTES** failures. Every one parsed all 35 bundled fields, ending with `creator_fee_unclaimed`, with **exactly 8 bytes remaining**. Pump discriminator: `bddb7fd34ee661ee`. This is a **new extension**, not the historical creator_fee_unclaimed addition.

The diagnostic invokes the production acceptance decoder where appropriate and walks the exact bundled field definitions for rejection metadata only. It emits no MarketEvents, imports no RadarEngine/Study/database/paper code and never accepts a prefix as flow. It bounds duration (120s), messages (100,000), websocket queue (16), payload size, layout histogram (64 + OTHER), examples (24), signatures/finalized lookups (12), and strings/vectors. Wallets/full payloads/transactions/provider URLs are not persisted. Signatures exist in memory only; reports hash them. Errors at the CLI boundary are category-only.

| Raw bytes | Consumed bytes | Remaining | Count |
|---:|---:|---:|---:|
|391|383|8|963|
|390|382|8|466|
|405|397|8|586|
|403|395|8|42|
|401|393|8|118|
|424|416|8|3|
|439|431|8|20|
|459|451|8|3|
|425|417|8|20|
|473|465|8|3|

RAW_TOO_SHORT, FIELD_BOUNDARY_FAILURE, FIELD_TYPE_UNSUPPORTED, INVALID_BOOL, INVALID_STRING, INVALID_PUBKEY, INVALID_TIMESTAMP and UNKNOWN_OTHER: **0** in this capture. INVOCATION_FRAMING: **39 notifications**, separately counted, not mislabeled as TradeEvent field failures. There were 10,300 WSS messages. A prior attempted run failed on transaction-version lookup and produced no retained report; it is not counted as a successful validation. The completed run used maxSupportedTransactionVersion=1.

Bounded tail examples and finalized sample all had unsigned LE u64=0, signed LE i64=0; SHA256 `af5570f5a1810b7af78caf4bc70a660f0df51e42baf91d4de5b2328de0e83dfc`. The one hash/value was constant across sampled pools/mints and both directions; this does not establish constancy in all traffic. Correlations are **UNDEFINED_ZERO_VARIANCE**. No nontrivial EXACT_MATCH against fees/reserves/state was established. No historical before/after payload dataset or independent post-transaction state equality study was performed. We did not assign semantics statistically.

## Deployment and authoritative sources

Upgradeable loader: `BPFLoaderUpgradeab1e11111111111111111111111`.
ProgramData: `B5MvUwXdiW1NMM6QFFD3ssPKBujD4zMohncbM73Z2BQu`.
Latest upgrade slot **458921440**, block time **2026-10-19T17:47:02Z**.
Public upgrade authority: `7gZufwwAo17y5kg8FMyJy2phgpvv9RSdzWtdXiWHjFr8`.
Program account executable and ProgramData enum/owner validated through finalized standard RPC.

Public docs main is still commit `639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22`, timestamp **2026-10-13T15:37:48Z**. Thus **DEPLOYED_PUMP_SCHEMA_AHEAD_OF_PUBLIC_SPEC** applies to the public GitHub IDL. Timing alone is not the field proof.

| Source | Exact identity | TradeEvent fields | Terminal field | Full IDL SHA256 |
|---|---|---:|---|---|
| Public docs pinned/current main | 639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22 / idl/pump.json |35|creator_fee_unclaimed|7616681ea557975f9f623ac211080f22a93060781eaf4765b0a488d980997207|
| Official npm Pump SDK |4.1.0 / gitHead b1a02a5ca87b4a7f3715a3cb921e503e1c2b3a66|35|creator_fee_unclaimed|7616681ea557975f9f623ac211080f22a93060781eaf4765b0a488d980997207|
| Official npm Pump SDK, current latest |**4.2.0** / gitHead **4eea7389c1142d1313d08d468de6672ed4545573**, published 2026-10-19T14:28:23.056Z|**36**|**quote_transfer_fee: u64**|**c53b8f5d39887afd27cc40a256527a421c2d91b64a9014dc4952a261f4f36a01**|
| On-chain historical Anchor IDL |AYgC53tU5BbP2NAnv5nConJxAdpQZctvmZK88pu69xRs|34|holder_rewards|ec3618ee8538826982b4f1fdb6487998596344c0cf8e38d336b5842dd1f46b6a|

The public Pump-maintained README explicitly links the official `@pump-fun/pump-sdk` npm namespace. Registry maintainers for 4.1.0 and 4.2.0 match (`oussama-baton`, `security-baton`); repository metadata points to pump-fun/pump-sdk. Both registry ECDSA signatures verified against npm signing keys, and downloaded tarball SHA512 matches registry integrity. These verify registry distribution integrity; they are not a claim of an independent source-code/security audit. The source repository URL returned 404; gitHead is published package metadata, not a separately retrieved GitHub commit. No lifecycle/package code from 4.2.0 was executed: only the tarball IDL was read.

4.2.0 integrity: `sha512-3G1efTG8ihxejyso67wwc7EJGUzEI+xbQCJArqlc/unfPEEWiv+u51OqSG3cDOunRxwhTZEb81gMmrZSf9rsSA==`.
4.1.0 integrity: `sha512-bjxHqUFgC6mcltooQZBbfIrmNBXeiCQNXGhEFPGaOSOCG47vuos153uAbIRL4dESa+6IaVodYUvIMWvgm9DV1w==`.
The new TradeEvent field is the **only difference in its ordered layout**; all preceding 35 field definitions match exactly. The final ordered fields are quote_mint, quote_amount, virtual_quote_reserves, real_quote_reserves, holder_rewards_bps, holder_rewards, creator_fee_unclaimed, quote_transfer_fee. **Authoritative explanation found: YES**, via the official SDK artifact. No separate newer Pump-maintained release note was established; GitHub main remains the older release.

Anchor derivation was checked against Anchor 0.31.1 source: find_program_address([]) then create_with_seed(base,"anchor:idl",program). The program-owned account was length-checked, canonical authority/vector header parsed and zlib-decompressed with a 1MiB bound. Raw account SHA256: `5a8e78dd38e8887c6dab8fadafdca9bd80575cd3b2e7c0257fab88c2caf7f5a9`. IDL authority `92gWFZMpGhWzVq5tjBnJxF9VnFwE3ydB2idJp9z2D9Nr` differs from the current upgrade authority; it is not treated as proof of the latest deployed interface. The IDL is stale and does not explain the extension.

The successor canonical Program Metadata mechanism was checked using official source commit `db537a3af463a1bbd8da8ee88b8c5fa154c02641`: seeds [program bytes, fixed-width 16-byte UTF8 "idl"] under `ProgM6JCCvbYkfKqJYHePx4xxSUSqJp7rh8Lyv7nk7S`. Correct canonical address `A6Y3keWVgXiJcWXYhGYYEauYaepb9NzrF6PChVeKdDoj` was absent at finalized context 459499557. An initial short-seed derivation was corrected after inspecting the official encoder; its negative result is not used. Third-party/non-canonical metadata would not authorize production acceptance.

## Bounded finalized sample and business-field matrix

Twelve distinct successful finalized v0 transactions, eight mint hashes, six BUY/six SELL, one canonical Pump TradeEvent each, complete successful invocation framing. Each event mint/user appears in account keys and exactly one Pump instruction's account list; each event token amount equals a parsed SPL transfer amount in its single-trade transaction. Exact original event ordinals are retained, never renumbered. **All 12 selected transactions fell in slot 459498344**. The requested cross-slot finalized sample was therefore not achieved. No more distinct getTransaction samples were taken, preserving the cap. This is an explicit forensic limitation, not a multi-slot proof. Current strict accepted-trade validation spans subsequent live slots.

The diagnostic did not persist arbitrary ix_name text: six SELL names were `sell`, three BUY names `buy`, three were OTHER. A complete independent named-account/discriminator/CPI-transfer attribution for all twelve was not retained. Do not describe an event-name/prefix inference as a proven instruction family. No instruction slippage/max/min argument is used as executed volume.

| Business field | Current schema classification | Independent corroboration in bounded sample |
|---|---|---|
| Mint | AUTHORITATIVELY_DECODED (SDK4.2.0 full layout) | INDEPENDENTLY_CORROBORATED address in message/Pump instruction; exact named-role mapping not retained |
| User/wallet | AUTHORITATIVELY_DECODED | Address appears in same Pump instruction, but named-role/CPI attribution remains AMBIGUOUS |
| Direction | AUTHORITATIVELY_DECODED is_buy | AMBIGUOUS independent instruction discriminator mapping; known ix-name categories reported only |
| Token amount | AUTHORITATIVELY_DECODED | EXACT_MATCH to SPL transfer amount 12/12; not asserted to be full scoped mint/destination attribution |
| Executed quote amount | AUTHORITATIVELY_DECODED existing quote/sol amount fields | AMBIGUOUS for independent native SOL attribution; no global balance delta reused |
| Quote mint/units | Canonical event plus existing independently verified curve semantics, known WSOL9/USDC6 only | UNAVAILABLE independent sample receipt; production normalization still fails unknown/conflicting units closed |
| Timestamp | AUTHORITATIVELY_DECODED | Independent blockTime equality not retained; UNAVAILABLE |

The initial diagnostic rejected tails and never submitted prefix values. The authoritative schema, not the limited corroboration matrix, authorizes the update. No research-only relaxed profile was implemented. If the schema had remained unexplained, these limitations would not justify production acceptance.

## Secondary community evidence (non-authoritative)

`nirholas/pump-fun-sdk`, pinned commit `f5bf85b2682cd1df6f839bcdefd6378604d14019`, dated 2026-10-11T01:45:13Z, src/sdk.ts: TradeEvent padding list [0,8,24,80,100,116] documents historical missing creator_fee_unclaimed/holder-reward/quote/etc fields. decodeWithTrailingDefaults appends zero defaults for older events and delegates to Anchor types.decode without a full-consumption check. Anchor's layout.decode returns the decoded prefix; the wrapper does not reject opaque trailing data. This is historical compatibility/tolerance, not evidence for the October19 field. Its terminal schema was creator_fee_unclaimed; the later official 35-field IDL explains that historical eight-byte case, not this new 36-field extension. It mirrors/uses Pump sources but supplies no new Pump-maintained provenance for quote_transfer_fee. No community behavior was copied.

## Minimal production change

Only tracked production file changed: `backend/app/pump_events.json` (**+17/-1 lines**): append exactly `quote_transfer_fee:u64` and pin official artifact provenance. Decoder code, full-consumption check, discriminators, invocation-success checks, known quote units, financial fields, event ordinals, dedup and all gap/freshness rules are unchanged. Create/migration schemas retain their original pin. Old 35-field wire payloads are now incomplete under this explicitly selected 36-field current layout and fail closed; no zero-padding or opaque-tail compatibility was introduced. Historical fixtures are not silently interpreted as new live events. No PumpSwap event decoding was changed.

The Python quote port/golden reference remains deliberately pinned to Pump4.1.0/PumpSwap2.1.0; the data-only event schema pin is independent. This task does not silently upgrade quote math/cost assumptions. Unknown quote assets/transfer-fee semantics still cannot become valid units.

## SDK security and runtime isolation

See [the complete 16-node security disposition](early-edge-sdk-security-20261021.md), including vulnerable ranges, paths, loaded status, root patches and exposure. The eight distinct root GHSA advisories remain visible; no forced SDK downgrade hides them. No high vulnerable operation was reached in the bounded quote-path trace, although affected high packages are imported. BN.js moderate arithmetic is reached. OS isolation is mandatory, not a claim that upstream vulnerabilities are repaired.

Actual namespace probe: only loopback interface; external socket returned ENETUNREACH; host home and project absent; env keys LANG/NODE_PATH/PATH plus namespace-generated PWD. No HTTP request or transaction was sent by the reference child. Forty-eight official golden outputs reproduced exactly twice with vector digest `2502cb2c489fb16971dd188e073dba44cc6bbfdc31bab016b222790d3f732e63`. Every vector now pins package/version/integrity, source hashes, input hash, expected outputs and generator version/hash. Ordinary backend tests do not require or auto-run the SDK; the optional local reference test is skipped unless explicitly requested.

No @pump-fun SDK entries exist in application package.json/package-lock or backend requirements. The old retired cohort DB remains 1,073,893,376 bytes, mtime 2026-10-20 06:46:14.652367761 +0200. No cohort, historical enrollment or prospective outcome was written. No commit/push occurred.

## Initial short resolved-schema smoke

`data/early_edge/pump-schema-resolved-smoke-20261021.json`: 307.93s, 69,123 WSS messages, 96 launches, **5,188 tracked trades accepted**, **zero tracked TradeEvent decode failures / zero unsupported layouts**. Invalid units 1,473 remain unavailable (not converted). Nine exact SDK state comparisons (two Pump mints and two verified PumpSwap pools across available observations), three QuoteUnavailable, zero parity mismatch. This is quote-state parity, not PumpSwap event decoding. No collectable cohort or prospective outcome exists.

RSS peak141.52MB; mean Python CPU47.27%, peak100.1%. Queue peak186; last sampled depth162; oldest trade19.45s; stale while queued19; no capacity/resource-pressure samples. Recovery accepted235/completed213, overflow87, expired33, global gaps120; no unsupported Pump trade recovery types; RPC240/errors0/4290. Recovery root requests health field is a legacy zero counter and is not reported as proof of zero recovery HTTP; recovery_requests_with_backlog=194. Existing fail-closed recovery/scheduling was not changed. Concurrent test/diagnostic load makes these resource/latency figures unsuitable for an acquisition capacity claim. CURRENT was not explicitly sampled in this first report, so no CURRENT claim is made.

No EARLY signal was observed; control match rate and time-to-N=100 cannot be estimated from this smoke. This is operational observation only. Normal Python-only follow-up and final checks are recorded below.


## Python-only short smoke (no Node or SDK tree required)

`data/early_edge/pump-python-only-smoke-20261021.json`: **307.86s**, 83,529 WSS messages, 110 launches. **5,768 tracked accepted trades** (3,014 buy / 2,754 sell); processed 2,900 buy / 2,619 sell. **4,132 verified SOL observations across 57 mint hashes**; 1,636 unknown-unit observations remain unavailable. No USDC trade observation was recorded in this bounded run. Zero tracked TradeEvent decode failures, zero unexplained layout failures, zero WSS reconnects. Only global reset was shutdown; recovery global gaps0, accepted188/completed181, overflow0/expiry0. No recovery capacity/scheduling adjustment was made; traffic/resource variation prevents attributing the lower pressure to this patch.

Sampled pre-shutdown evidence reached **CURRENT2 / PARTIAL19 / UNAVAILABLE74**, with **maximum sampled clean coverage271.51s**. This is the last 30-second sample, not an invented exact-at-shutdown count; shutdown correctly ends connection coverage. Peak sampled CURRENT=2. No 180-second requirement or 20-second freshness rule was changed. These are pre-grad candidates only; no PumpSwap event milestone is claimed.

Python quotes succeeded9/12, three QuoteUnavailable; SDK comparison **disabled**, parity result **null** (not a parity pass). Separate opt-in smoke above and the 48-vector verifier supply the zero-mismatch evidence. Ordinary monitor+recovery+quote Solana RPC231, errors0/4290; recovery requests-with-backlog182 (a subset, not a substitute for total). No ordinary-trade HTTP fallback was added. Public USD reference requests55/errors0. RSS peak152.57MB, mean/peak Python CPU51.78%/99.4%; no capacity/resource-pressure samples. Last queue-depth sample279 (also peak); oldest trade24.48s, max queue wait12.56s, stale-while-queued counter0. Older event timestamps and queued application age remain distinct; the 20-second application rejection gate is unchanged. Outstanding events are not misreported as processed trades.

Adequately observed eligible tokens1 (11.69/hour naive short-window extrapolation); EARLY signals0; no stable throughput estimate or time-to-N100 inference is available. No collectable cohort and zero prospective treatment/control outcomes in both smokes. The six-hour study was not run. Both reports bind their startup source/config hashes; diagnostic/report/test hardening continued during this task, so neither report is presented as a current final-source cohort-creation attestation. No real cohort was authorized or created.

## Validation and files

Final validation results are appended after the complete suite finishes. Earlier complete suite:690 passed/1 opt-in skipped; frontend39 passed; TypeScript/build passed; Ruff passed; mypy46 sources passed; production dependency audits0; 48-vector isolated reference reproduced exactly. Existing frontend duplicate-key warning remains unchanged. Additional isolation/receipt diagnostics were tested separately (21 passed). No claim of profitability, strategy edge or research approval follows.

Changed in this task: tracked `backend/app/pump_events.json`; already-untracked `backend/app/early_edge_parity.py`, `backend/tests/fixtures/early_edge/sdk_quotes.json`, `backend/tests/test_early_edge.py`, `scripts/early_edge_diagnostic.py`, `scripts/early_edge_golden.cjs`, `scripts/early_edge_sdk_compare.cjs`, `docs/early-entry-edge.md`; newly added `scripts/pump_trade_forensics.py`, `scripts/pump_authority_audit.py`, `scripts/early_edge_reference.py`, `backend/tests/test_pump_trade_schema_audit.py`, this report and `docs/validation/early-edge-sdk-security-20261021.md`. Other previously untracked early-edge implementation files were preserved. Local redacted JSON reports live under `data/early_edge/` and are ignored by git.

Remaining limitations: the twelve finalized samples are single-slot; independent instruction-scoped business-field attribution is incomplete and cannot authorize a relaxed profile; unknown units still fail closed; SDK advisories remain upstream; host/kernel and namespace availability remain trust/portability requirements; resource and acquisition gaps remain possible; short-window zero-EARLY observation cannot estimate research throughput. PumpSwap event extension remains unresolved and untouched. No real cohort creation should be inferred from this acquisition/security result.

## Source links

- [Pinned official Pump documentation](https://github.com/pump-fun/pump-public-docs/tree/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22)
- [Official Pump SDK4.2.0](https://www.npmjs.com/package/@pump-fun/pump-sdk/v/4.2.0), [registry artifact metadata](https://registry.npmjs.org/@pump-fun%2fpump-sdk/4.2.0)
- [Anchor canonical IDL derivation](https://github.com/coral-xyz/anchor/blob/v0.31.1/ts/packages/anchor/src/idl.ts)
- [Official canonical PMP derivation](https://github.com/solana-program/program-metadata/blob/db537a3af463a1bbd8da8ee88b8c5fa154c02641/clients/js/src/generated/pdas/canonical.ts), [fixed16 seed codec](https://github.com/solana-program/program-metadata/blob/db537a3af463a1bbd8da8ee88b8c5fa154c02641/clients/js/src/generated/types/seed.ts)
- [Community decoder, non-authoritative](https://github.com/nirholas/pump-fun-sdk/blob/f5bf85b2682cd1df6f839bcdefd6378604d14019/src/sdk.ts)


Reference reproducibility also preserves `backend/tests/fixtures/early_edge/reference_lock.json` as explicitly isolated test data. The opt-in verifier refuses a missing/changed lock before reading SDK artifacts. This is not a production dependency manifest and no application setup/runtime command installs it. The direct and nested dependency versions/integrities are reproducible without resolving latest versions. See the security report for disposable npm-ci recreation instructions.


Final validation: **695 backend passed, 1 explicitly opt-in SDK test skipped** (99.01s); **39 frontend passed**; Ruff passed; mypy **46 source files** passed; TypeScript and production build passed; secret scan **177 source/document files** passed; backend dependency audit **0**, frontend dependency audit **0**; temporary reference audit remains **16 affected nodes (8 high/8 moderate)**; git diff --check and explicit whitespace scan of all untracked files passed. Twenty-two dedicated new schema/forensic/security tests passed; all 48 pinned SDK quote vectors reproduced exactly in the isolated verifier. Frontend emitted its existing duplicate React key warning; no frontend source changed.

Old bundled minimal schema SHA256: `182d1c2f7d3383a113d9da93edf73abfbef076b93b949218d60cac81c0ca0707`; updated minimal schema SHA256: `5566d6bb9b36330e8296f824ab8a881508fece9549c9273bb9fa0eb57f3fe97d`. The full official SDK IDL hash is separately pinned above and must not be confused with the extracted minimal schema hash.

Final git scope: **one tracked production file, +17/-1; 25 untracked research/test/document files including the original 18**. The seven newly added files are the three diagnostic/reference scripts, dedicated schema-audit test, reference-only lock fixture and two investigation documents. No cohort created. No commit. No push. HEAD remains `2bebbf2863de21041fffca80fb99507356a815b6`.

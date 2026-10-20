# PumpSwap deployed schema authority investigation — 2026-10-20

**Classification: DEPLOYED_SCHEMA_AHEAD_OF_PUBLIC_SPEC.**

**Authoritative explanation of the extra eight bytes: NO. Production changed: NO.**
Upgrade chronology supports public-spec lag; it does not identify a new field,
prove where that field belongs, or authorize accepting a partially understood
payload. No production patch, new cohort, commit or push was made.

## A. Executable and deployment metadata

Four standard confirmed RPC requests fetched the executable Program account,
the ProgramData metadata header (45-byte slice), block time, and the two
canonical IDL locations. No ELF download or broad transaction scan was used.

| Property | Observed value |
| --- | --- |
| Program | `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA` |
| Executable | true |
| Loader | Upgradeable Loader v3: `BPFLoaderUpgradeab1e11111111111111111111111` |
| ProgramData | `6naEzKeUuFh1Jeeu51NXQgr5qkXgXtc9WKNct4xynVJc` |
| Latest deployment/upgrade slot | **458921517** |
| Slot block time | **2026-10-19 17:47:20 UTC** |
| Public upgrade authority | `7gZufwwAo17y5kg8FMyJy2phgpvv9RSdzWtdXiWHjFr8` |
| RPC context slot for Program | 459237916 |
| Public docs commit | `639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22` |
| Commit author/committer UTC | **2026-10-13 15:37:48 UTC** |

The deployment is **6 days, 2 hours, 9 minutes, 32 seconds after** that public
commit. The Program state's ProgramData pointer also matched the canonical
loader PDA. Owners, executable flags, loader state tags and authority option
were checked, rather than interpreting arbitrary account bytes.

[Official loader state](https://docs.rs/solana-loader-v3-interface/latest/solana_loader_v3_interface/state/enum.UpgradeableLoaderState.html)
and [official deployment semantics](https://solana.com/docs/core/programs/program-deployment).

## B. Official npm artifact

Package: **`@pump-fun/pump-swap-sdk@2.1.0`**. Registry-reported gitHead:
`0bc59090bbd0b8d6c27b8df72d52e30bfc069c3b` (artifact metadata, not independently
verified as a publicly accessible source revision).

Registry tarball integrity, verified against downloaded bytes:

```text
sha512-O0ulb5In/pMzxpcWIkzU17N27HQNZhGGof4fhgXZUkRj/vDbrZsDrViNoouhR52bvtfRf61e/bSvEg/h+35ueA==
```

Tarball SHA256:
`1ef56832347f06653acf154d8e2072f1bfc9343f0e6c203cf4517bb1948e8865`.
Registry SHA1 was also verified. All 95 tar entries were inspected with path,
member-count and expanded-size bounds; only regular files were copied to a
local temporary inspection directory. No install, lifecycle script or SDK
code was executed.

The package JSON IDL is `src/idl/pump_amm.json`, SHA256:
`b7d8c57a4d9c4dd0109a9ab893052352333252d4eedced10ac091d4d66cab89b`.
It is **byte-identical** to the public-docs IDL. BuyEvent has 40 fields and
SellEvent has 33. Both end at `creator_fee_unclaimed: u64`; neither defines a
field after it. Both match the bundled minimal schema's discriminators and
ordered event fields exactly. The minimal subset file itself has a different
file hash because it contains only selected events/provenance.

Relevant bundled declarations and runtime copies:

- Source JSON: `src/idl/pump_amm.json`.
- Source helper: `src/types/pump_amm.ts`.
- Generated helpers: `dist/pump_amm-D1Mp6mIm.d.ts` and `.d.mts`.
- Exported types: `dist/index.d.ts` and `.d.mts`.
- Ten compiled embedded IDLs: `dist/index.js`, `dist/esm/index.js`, and
  `dist/{sdk,esm/sdk}/{offlinePumpAmm,onlinePumpAmm,pumpAmmAdmin,util}.js`.
- Runtime factory: `src/sdk/util.ts:getPumpAmmProgram`, constructing Anchor
  `Program` from the bundled JSON; dependency `@coral-xyz/anchor: ^0.31.1`.

A pure-data TypeScript AST walk compared all ten embedded JavaScript IDL
objects to the official source JSON. All matched. No `eval` or SDK execution
was used. The inventory records hashes of every matching runtime/type artifact.
The package has no separate custom event decoder establishing another field.
Its included event tests use Anchor's coder and describe compatibility with
shorter historical logs; that does not document the observed extra bytes.

[Official package](https://www.npmjs.com/package/@pump-fun/pump-swap-sdk/v/2.1.0),
[official Pump SDK links](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/README.md).

## C. On-chain IDL: present, validated, stale

The official SDK's Anchor dependency identifies the applicable legacy mechanism.
Anchor 0.31 derives an empty-seed program signer PDA, then uses
`create_with_seed(base, "anchor:idl", program)`. The result is:

`5fLnXNNoZcZt9Qku6HARM3un3Ttm2cGsR7gN9Zp1R7h3`.

At RPC context slot 459237923 this account existed, was non-executable and was
owned by the PumpSwap program. Its discriminator matched
`SHA256("internal:IdlAccount")[:8]`. The canonical authority pubkey + u32 data
length header was validated, followed by bounded zlib decompression. The
JSON's embedded program address matched PumpSwap. Decompressed IDL SHA256:

`e16ac8008908911575241a25cad33bed8d2da2153f0d726790065fd467b90ff4`.

The exact decompressed JSON was saved locally as
`data/observe/pumpswap-onchain-idl-20261020.json`; its hash was rechecked.
It has **34 Buy fields / 27 Sell fields**, both ending at `buyback_fee`.
It lacks all six later public fields: `virtual_quote_reserves`, `can_boost`,
`base_supply`, `holder_rewards_bps`, `holder_rewards`, `creator_fee_unclaimed`.
It supplies no additional field and cannot explain the live remainder.

The successor program-metadata canonical `idl` location was independently
checked: `EB4BfHDFEUqTmRsUGqUusgk7B37LT9GyG8TTqM6eS1jN` was absent at the same
context slot. Its derivation used `[program, UTF8("idl") padded to 16 bytes]`
under `ProgM6JCCvbYkfKqJYHePx4xxSUSqJp7rh8Lyv7nk7S`, following the official
canonical PDA and fixed Seed codecs. No noncanonical third-party IDL was trusted.

Thus the result is **VALIDATED_ONCHAIN_IDL_STALE**, not NO_ONCHAIN_IDL. Absence
of the successor account alone was not used to claim global IDL absence.

[Anchor 0.31 IDL derivation/header](https://github.com/solana-foundation/anchor/blob/v0.31.1/lang/src/idl.rs),
[Anchor client derivation](https://github.com/solana-foundation/anchor/blob/v0.31.1/ts/packages/anchor/src/idl.ts),
[canonical metadata PDA](https://github.com/solana-program/program-metadata/blob/main/clients/js/src/generated/pdas/canonical.ts),
[fixed Seed codec](https://github.com/solana-program/program-metadata/blob/main/clients/js/src/generated/types/seed.ts).

## D. Final eight bytes: descriptive observations only

Two freshly verified WSOL pools were observed for 30 seconds each. They yielded
184 target payload observations, all still rejected by production full-consumption
validation. The diagnostic names no semantic field and accepts no trades.

| Pool | Buy / Sell observations | Unsigned LE u64 range | Signed LE i64 range | Tail variation |
| --- | --- | --- | --- | --- |
| HNB2… / 687h… | 9 / 3 | 0–0 | 0–0 | none observed |
| AscP… / EKos… | 146 / 26 | 0–0 | 0–0 | none observed |

Every retained example has trailing-byte SHA256:
`af5570f5a1810b7af78caf4bc70a660f0df51e42baf91d4de5b2328de0e83dfc`.
This matches the retained hash examples from the preceding investigation. Old
hashes were not treated as raw payloads; the integer views came from fresh bytes.

Arrival-order comparisons within each pool found 11 and 171 equal consecutive
pairs, zero changes. This is observed arrival order, not a claim about execution
order within a slot. One explicit truncation on HNB2… and two foreign failures
(one per pool) were excluded from target-value analysis. The sample is bounded
and is not a complete flow window or a CURRENT claim.

**EXACT_MATCH** numeric equality occurred with `holder_rewards` in 184/184
observations; all these comparisons were zero equals zero, with zero nonzero
matches. There were 0/184 equalities for `creator_fee_unclaimed`, `buyback_fee`,
`protocol_fee`, `coin_creator_fee` or `base_supply`, using the documented-prefix
interpretation. **CORRELATION** was not estimable: a constant tail has zero
variance. These comparisons provide no semantic authorization.

Independent post-transaction corroboration used one Buy and one Sell transaction
per pool. Pool vault identity came from production `parse_pool`; resolved static
and loaded keys mapped those vaults to `meta.postTokenBalances`. None of the
eight exact post-transaction base/quote vault balances equalled the tail value.
This was descriptive equality testing, never a volume reconstruction.

A later confirmed pool snapshot per pool was decoded only for documented numeric
prefix fields from the official SDK Pool schema. None of `lp_supply`,
`virtual_quote_reserves`, `protocol_fees` or `creator_fees` equalled the last
observed zero tail. Snapshot slots are recorded and requested at/after the last
observed slot; these are **later snapshots**, not guaranteed immediate
post-transaction pool account states. Numeric equality/inequality is not a causal
or field-identity claim.

Requests: 4 deployment/IDL RPC + 4 per tail probe = **12 diagnostic RPC**.
No HTTP-per-trade production path was introduced. Pools ACKed once each; no
trades entered an engine, strategy, cohort or paper account.

## E. Community implementations — NON-AUTHORITATIVE

| Repository / commit | Inspected behavior | Additional field identified? |
| --- | --- | --- |
| `pinax-network/substreams-solana-idls` / `aed8bcb1fb61950554df0eab0e4d8f7989aebfe1` | `unpack_trade_event_minimal` reads a stable leading subset and ignores suffixes; separate full Borsh API uses strict deserialization | No |
| `0xfnzero/sol-parser-sdk` / `589f1079af8f56b824b4657b16511166eceebf65` | `parse_trade_tail` reads `creator_fee_unclaimed` at tail offset 73, accepts lengths >=81 without requiring exact consumption | No |
| `nirholas/pump-swap-sdk` / `250861bbac73da3f9f58de8f03f9a86f96d5fe3f` | Community mirror IDL equals official npm/public JSON; generic Anchor-based handling | No |

The first parser explicitly describes append-only tolerance. The second accepts
bytes beyond its last known field. Neither inspected tail handler cites an
authoritative Pump explanation for these extra eight bytes. The mirror points
to the official npm artifact, which was inspected directly and has no extra
field. None of these implementations establishes a production schema change.
No community behavior or wallet/trading code was copied into CRISPY WINNER.

[Pinax source](https://github.com/pinax-network/substreams-solana-idls/blob/aed8bcb1fb61950554df0eab0e4d8f7989aebfe1/src/pumpswap/events.rs),
[sol-parser source](https://github.com/0xfnzero/sol-parser-sdk/blob/589f1079af8f56b824b4657b16511166eceebf65/src/logs/pump_amm.rs),
[community mirror](https://github.com/nirholas/pump-swap-sdk/blob/250861bbac73da3f9f58de8f03f9a86f96d5fe3f/src/idl/pump_amm.json).

## Artifacts, files and validation

Timestamped consolidated report:
`data/observe/pumpswap-schema-authority-20261020T130540Z.json`.
Public artifact snapshots, hashes, tarball, pure-data AST inspector and source
excerpts are in `data/observe/pumpswap-authority-sources-20261020T130540Z/`.
Deployment report and two descriptive reports are under `data/observe/`.
No provider URLs, raw trade payloads, user wallets or complete transactions are
retained in these diagnostics. The on-chain IDL is public interface data.

This phase adds `scripts/inspect_pumpswap_program.py`,
`scripts/describe_pumpswap_tail.py`, `backend/tests/test_pumpswap_authority.py`
and this document. The pre-existing diagnostic `scripts/diagnose_pumpswap_layout.py`
gains an opt-in descriptive view, off by default. All prior uncommitted work is
preserved. There is no diff in `backend/app` or `frontend/src`.

Validation: **576 backend tests / 39 frontend tests passed**. Ruff, mypy
(37 files, explicit package bases), TypeScript/production build and dependency
audits passed; audits found no known vulnerabilities. Secret/whitespace checks
are completed for the final document. The 13 new deterministic tests cover loader
identity, canonical IDL derivation and bounded decompression, unsigned/signed
views, unchanged rejection, constant-value statistics and isolated state-free
bounded tail probing. No dependencies were added.

Production HEAD remains `2bebbf2863de21041fffca80fb99507356a815b6`.
**Stop for review: the authoritative layout is still unavailable.**

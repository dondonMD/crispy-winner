# PumpSwap byte-layout investigation — 2026-10-20

**Status: FAIL_CLOSED_PENDING_AUTHORITATIVE_SCHEMA.** Production HEAD remains
`2bebbf2863de21041fffca80fb99507356a815b6`. No production decoder, schema,
subscription filter, strategy gate or cohort was changed. No acquisition fix
was committed or pushed. No end-to-end OBSERVE probe was run: accepting these
payloads is not yet justified.

## Exact failure

The failure is the production `decode_event` full-consumption check:

```python
if offset != len(raw):
    raise DecodeFailure("unsupported_layout")
```

Fresh successful PumpSwap invocation payloads consumed all 40 BuyEvent or all
33 SellEvent fields according to the bundled schema, then retained bytes.
This is **KNOWN_DISCRIMINATOR_TRAILING_BYTES**, not the encoded-string bound,
unsupported field type, or an earlier field boundary failure.

| Event | Discriminator hex | Observed raw lengths in range runs | Consumed offsets | Remaining bytes |
| --- | --- | --- | --- | --- |
| BuyEvent | `67f4521f2cf57777` | 500, 512, 515 | 492, 504, 507 respectively | 8 |
| SellEvent | `3e2f370aa503dc2a` | 449 | 441 | 8 |

Buy length differences follow the observed string lengths of known-safe
`ix_name` values (`buy_v2`, `buy_exact_quote_in`, `buy_exact_quote_in_v2`).
The report contains each sampled field's name/type/start/end/consumed count,
expected/parsed field counts, discriminator, payload length/hash and trailing
byte count/hash. It contains no wallet values or complete payloads.

All range-instrumented failures (89 observations) leave eight bytes. Examples
from both initial runs also leave eight bytes. One sampled remainder SHA256 is
`af5570f5a1810b7af78caf4bc70a660f0df51e42baf91d4de5b2328de0e83dfc`.
Its meaning is **unknown**. A complete parse according to the old schema does
not establish that every field retains its old semantics in the deployed
layout. In particular, this investigation does not prove a new field was
appended rather than some other layout discrepancy. No economics are accepted.

## Live evidence

All pools were freshly verified through production `parse_pool`, including
canonical PumpSwap ownership/layout, expected base mint and valid nondefault
pool/mint/vault keys. Both quotes are WSOL. Subscription semantics remain
pool-address mentions at confirmed commitment.

| Run | Notifications | Target Buy failures | Target Sell failures | Foreign Buy failures | RPC requests |
| --- | ---: | ---: | ---: | ---: | ---: |
| HNB2… / 687h…, 60s | 201 | 6 | 11 | 1 | 3 |
| AscP… / EKos…, 60s | 169 | 149 | 20 | 0 | 3 |
| HNB2…, 30s ranges | 103 | 4 | 3 | 0 | 3 |
| AscP…, 30s ranges | 82 | 73 | 9 | 0 | 3 |
| Total observations | 555 | 232 | 43 | 1 | 12 |

Each run ACKed once, with zero transport errors, framing failures or explicit
truncations. Accepted production trade events remain **zero**. All 276 observed
failures were in the trailing-byte branch; all other branch counters were zero.
The totals are diagnostic observations across probes, not an independent-trade
or research sample count.

Target/foreign classification uses only the valid decoded `pool` prefix from
a successful canonical PumpSwap invocation, compared with the independently
verified target. No notification is counted as a trade by itself. There were
zero identity-not-provable and zero foreign Sell observations. The foreign
Buy is kept distinct; it does not explain away target failures.

Eight small confirmed getTransaction samples (Buy and Sell on each run) matched
notification signature/slot and exact ordinal/payload SHA256. Production
invocation staging again identified the data as emitted in successful canonical
PumpSwap frames. Every sampled payload reproduced the same field offsets and
remainder. Ordinals count Program data lines throughout the complete transaction,
so they identify the exact data line without renumbering foreign events.
Raw signatures were transient lookup keys and cleared after use. No raw
transactions or complete log payloads were persisted.

## Schema provenance and authoritative search

Repository: `pump-fun/pump-public-docs`.
Pinned **and current HEAD**: `639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22`.
Canonical file: `idl/pump_amm.json`.

| File | SHA256 |
| --- | --- |
| Bundled `backend/app/pump_amm_events.json` | `27c5169a9c334a2819e05901aecdb94f0108e3bc9459cf80a70c57d63a275615` |
| Exact pinned upstream JSON | `b7d8c57a4d9c4dd0109a9ab893052352333252d4eedced10ac091d4d66cab89b` |
| Fresh current upstream JSON | `b7d8c57a4d9c4dd0109a9ab893052352333252d4eedced10ac091d4d66cab89b` |
| Official `idl/pump_amm.ts` helper | `0a2937ba78b3fa58c4dbc53527c32c51aec5ca91efcede89c2fcd284a8def352` |

Bundled and public JSON event names, discriminators and all field names/order/
types match: BuyEvent 40, SellEvent 33. The public JSON files are byte-identical.
The TypeScript helper has the same fields after camelCase normalization and
labels itself a type helper, not the actual IDL. **Schema diff: none.** These
schemas do not explain the unconsumed bytes in the live samples.

The bounded official IDL history check examined these eight commits:

| Commit | Buy / Sell fields |
| --- | --- |
| `8cda1fa30ea658b20909d8aedf002047119388d2` | 40 / 33 |
| `e0687ae9b7e064a0f54efc7297c65eecfbba3a8f` | 39 / 32 |
| `2c22246b670812e2392e5f94b9543f500d6c9e15` | 37 / 30 |
| `3c6721a67c0b206b39130b454c8ba22a83ce972e` | 34 / 27 |
| `82dacacf15ca93dc0444ab38714f2226210a0a3d` | 32 / 25 |
| `f0ef005c386adeeb783c27fdcc4ddd9d49b255c5` | 30 / 23 |
| `7d7abd77403f0646ea17468d7cb6e66b33dbc3ed` | 30 / 23 |
| `864c072f4c331354288232e73b88ae849215ce7b` | 30 / 23 |

Complete field definitions and per-file hashes for this bounded history are
preserved in the public-schema artifacts. No published official releases were
returned. No authoritative alternate layout explaining the remainder was found;
this is a bounded search, not proof no such information exists elsewhere.

[Official pinned JSON](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/idl/pump_amm.json),
[official helper](https://github.com/pump-fun/pump-public-docs/blob/639b87fb45c3adeffa6f7c4a1bf0cb85e392bf22/idl/pump_amm.ts),
[official IDL history](https://github.com/pump-fun/pump-public-docs/commits/main/idl/pump_amm.json).

## Diagnostic isolation and operation

```sh
.venv/bin/python scripts/diagnose_pumpswap_layout.py \
  --pool <verified-pool-candidate> --base-mint <expected-base-mint> \
  --seconds 60 --output data/observe/<unique-layout-report>.json
```

The diagnostic traces the actual production decoder's locals with a synchronous,
scoped Python tracing hook. It does not implement another Borsh decoder. The hook
and temporary diagnostic wrapper are restored in `finally`; nothing is patched
in production files. Failure markers pass only through diagnostic invocation
staging, never through MarketEvent or RadarEngine. Failed CPI frames are discarded
by the existing production framing parser.

Bounds: 1–300 seconds, 10,000 notifications, 256 KiB WSS messages / queue 16,
4096 dedup identities, three redacted examples/transient signatures, at most
three transaction requests plus one pool verification per run. Branch, event,
identity, safe instruction-name and min/max counters have fixed cardinality.
There is no HTTP-per-trade production behavior. No engine/database/cohort/paper
state is constructed. The old prospective cohort remains untouched.

Redacted reports: `data/observe/pumpswap-layout-20261020-{pool1,pool2,ranges1,ranges2}.json`.
The timestamped `pumpswap-layout-investigation-*.json` consolidates the reports,
hashes, exact upstream commit and stop classification. Public source snapshots
are in `data/observe/pumpswap-layout-schemas-20261020/`. These local artifacts
are ignored by git; no transaction payloads are stored there.

## Tests and stopping decision

Tests retain old canonical Buy/Sell fixtures and prove trailing garbage,
truncated fields and malformed strings still fail closed. They cover all exact
layout branches, field offsets, safe string classification, target/foreign
identity, failed invocation exclusion, bounded dedup, production mixed-pool
routing, unknown units, decoder restoration, and engine/database isolation.
The existing acquisition tests continue to protect freshness, units and dedup.

Without an authoritative explanation, accepting or skipping eight bytes would
be a guessed decoder change. **Production is unchanged and work stops for review.**
No new cohort, no relaxed CURRENT requirement, no strategy change, no commit
and no push. Validation: 563 backend tests and 39 frontend tests passed;
Ruff, mypy (35 files including both diagnostics), TypeScript/production build,
secret scan (158 files), dependency audits and whitespace checks passed.
The layout-specific deterministic suite has 13 tests.

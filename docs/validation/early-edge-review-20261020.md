> Historical first-draft validation. Superseded by the manual-latency hardening protocol and its validation report; no cohort was enrolled under this draft.

# EARLY study implementation validation — 2026-10-20

Review only. No live cohort creation, no real OBSERVE collection, no commit or push.

Base HEAD: `2bebbf2863de21041fffca80fb99507356a815b6`.
Branch: `research/prospective-early-entry-edge`.
Production source files and the retired prospective database were not modified. The retired database retained its original 2026-10-20 06:46:14 +0200 modification time. Tests use temporary databases. The offline smoke creates and removes its own explicitly synthetic temporary database.

## Results

| Check | Result |
| --- | --- |
| Complete backend `pytest -q` | 653 passed, 173.42 seconds |
| New EARLY tests included above | 118 passed, including 48 official-SDK vectors |
| Complete frontend Vitest | 39 passed in 5 files |
| TypeScript and Vite production build | Passed |
| Ruff `check backend scripts` | Passed |
| mypy app plus new Python scripts | Passed, 40 source files |
| Secret scan | Passed, 164 source/document files before this report |
| Backend dependency audit | No known vulnerabilities |
| Frontend dependency audit | 0 vulnerabilities |
| Existing tracked `git diff --check` and new-file whitespace inspection | Passed |
| Official artifact integrity and individual pinned source SHA256 checks | All matched |

The existing frontend Opportunity fixture emits a duplicate React-key warning; the tests pass. No frontend code changed.

## Synthetic smoke

Preserved report: `data/early_edge/synthetic-smoke-20261020T222100Z.json` (local ignored research artifact).

- No engine, live cohort, paper state or network requests.
- Historical enrollments: 0; a historical attempt was refused.
- Pre-latency entries: 0; a pre-boundary request with a later response was rejected as a fill.
- EARLY/control enrollments: 1/1, explicitly synthetic.
- Primary EARLY measured: 1; control unavailable: 1 after interruption.
- Terminal primary accounting: 100%; numerical coverage: 50%.
- Restart persisted immutable signals and receipts; unfinished outcomes were censored without backfill.
- Repeated report calls were identical; status INSUFFICIENT_SAMPLE.
- Runtime 1.88 seconds, peak RSS 55,848 KB, CPU 100% for this brief CPU-bound offline process. These are **not** live acquisition performance results.

## Draft for review

`data/early_edge/design-review-20261020T222100Z.json` is non-collectable, not a live cohort. Draft ID `DRAFT-20261020-64e68ff1f846`; opportunity version `opportunity-v1-ebe5d5f68265`.

Canonical manifest SHA256: `f00b58b5857a5d002916c119111eadf3d311d3c80dd45122dc5bf97403f0c20b`.
Source bundle SHA256 (`early_edge_sources.json`): `bb117a403bc729c57de6b19d2144ec0c6512aea7f71ccbf0bc0bab70642e4458`.
Frozen draft source hash: `bce26bce0e50f53c7e2431540da8579b0c45e85df34d534cf7fba785d751c4f4`.

The draft pins USD 4, 500ms, 300s primary, 60/180/600/1800 exploratory, existing 85% crowd boundary, 100 numerical primary EARLY samples minimum, 10,000 mint-cluster resamples, seed 20261020. Real collection requires later review, clean committed source and a newly created manifest. This draft cannot silently become that manifest.

## Review limitations

Read [the protocol](../early-entry-edge.md) before collection. SDK outputs are authoritative reference math, not confirmation of deployed execution parity or realistic fill availability. No live quote/load diagnostic was run. Canonical proof rules for automatic ECONOMIC_ZERO_EXIT are not supplied by missing/zero SDK quotes. Market correlation, observational confounding, optional stopping, bounded sampling delays and infrastructure censoring remain methodological limitations. Missingness blocks strongest status. Nothing changes paper or live approval.

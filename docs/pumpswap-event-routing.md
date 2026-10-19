# PumpSwap transaction-wide notification routing

The accepted 3603.01-second normal OBSERVE result established the complete
migration → verified eligible pool → selection → ACK → post-grad trades → 180 clean
seconds → CURRENT path. No redesign or threshold change is needed.

## Diagnosis

In the accepted implementation, the only source of `DecodeFailure("pool_identity")`
was the `any(decoded.pool != subscribed_pool)` check after complete successful log
parsing. Thus the reported 32 failures necessarily contained at least one decoded
valid foreign-pool event. The previous aggregates did not count matching events:
they cannot establish how many were mixed versus foreign-only notifications. No
raw transactions were preserved for retrospective classification. They must not
all be claimed to be mixed transactions.

A deterministic complete transaction reproduces the defect against the accepted
handler: Pool A Buy at ordinal 2 and Pool B Sell at ordinal 4 under subscription A
produces zero accepted events, one pool_identity failure and one gap. A pool
mentions subscription receives transaction-wide logs, so a valid foreign event is
not itself contradictory identity evidence for A.

## Narrow correction

Production parsing still validates the complete notification before submission.
Only then does the handler select events matching the subscribed pool, retaining
their original transaction ordinals. A and B subscriptions receiving the same
transaction each accept only their own events. Existing signature + ordinal + pool
identity and bounded replay dedup are unchanged.

A complete foreign-only notification is counted and ignored: no invented trade,
no zero-flow observation and no continuity reset. Empty decoded event sets also
submit nothing. Malformed supported events, unknown identities before full decode,
explicit truncation, framing/encoding/timestamp/pubkey failure and transport or
subscription loss retain conservative handling. Registry disagreement after parsing
is a TRUE_IDENTITY_FAILURE, rejects all observations and ends that pool's coverage.

Unknown matching quote units remain `currency=unknown`, `units_valid=false` and
unavailable for CURRENT. A local gap makes incompleteness explicit. No decimals
are guessed, discovered over HTTP or converted to USD.

## Bounded diagnostics

Fixed counters classify nonempty completely decoded notifications as MATCH_ONLY,
MIXED_POOLS or FOREIGN_ONLY, with TRUE_IDENTITY_FAILURE reserved for a registry
conflict. Counters also expose mixed notifications, foreign events ignored,
foreign-only notifications, actual identity failures and the number of complete
notifications the old foreign-event check would have rejected. They count received
notifications, including replay; accepted-event counters remain deduplicated.

Only three redacted examples are retained, each with at most 32 original ordinal /
side pairs, total/matching/foreign counts, subscribed pool and a truncated SHA256
signature hash. No wallets, raw signatures, logs or transactions are retained.
Quote diagnostics have exactly three categories: WSOL, USDC and OTHER. OTHER does
not identify a mint or imply known decimals. The historical 103 invalid-unit
observations necessarily fell outside the existing WSOL/USDC quote map: that was
the only branch incrementing invalid_units. Their category is therefore OTHER;
individual asset identities/decimals were not retained and must not be inferred.
New observations count this explicitly without expanding quote support.

## Unchanged boundaries

No change to recovery workers, MAX_PENDING/MAX_AGE/MAX_ATTEMPTS, migration freshness,
PumpSwap capacity, security/concentration limits, 20-second freshness, 180-second
continuity, post-grad timing, buyers, maturity/momentum, economics, holdouts, paper
or trading behavior. The user-reported 60-minute recovery pressure (365 overflow,
7 expiry, 392 recovery global gaps) remains a separate high-load limitation.

## Deterministic validation and test stability

Routing regressions exercise A Buy ordinal 2 / B Sell ordinal 4 with one or both
subscriptions, foreign-only and matching-only notifications, malformed foreign
payloads, explicit truncation, registry changes during parsing, reconnect replay,
unknown-unit gaps and fixed diagnostic/example bounds. The accepted handler was
also executed directly from accepted commit e62b043 against the synthetic complete A/B fixture
to reproduce the original failure before relying on the revised assertions.

The complete backend suite exposed an unrelated wall-clock assumption in the
recovery metrics saturation test: a slow host could take longer than its ten-second
rolling window. That test now freezes only the metrics module's clock. Recovery
production code, measurements and scheduling are untouched. The complete suite
passes 509 tests. Frontend 39 tests, Ruff, mypy, TypeScript/build, secret scanning,
locked backend/frontend audits and whitespace checks also pass.

## Preserved live validation: 2026-10-19

[Combined bounded report](validation/pumpswap-routing-20261019T193400Z.json)
contains the normal OBSERVE result, a separate diagnostic result, raw-report paths
and SHA256 hashes. Full normal report:
`data/observe/pumpswap-routing-20261019T193400Z.json`.

Normal OBSERVE ran 604.98 seconds and processed two migration observations. No pool
became eligible/selected/subscribed; ACKs, messages, BuyEvents, SellEvents, accepted
trades, truncations, mixed notifications, ignored foreign events, foreign-only
notifications, true identity failures and pool-local gaps were all zero. New
pool_identity failures were zero, versus the earlier run's 32, but **there was no
pool traffic, so this is not evidence of a live improvement**. Peak eligible and
subscribed pools were also zero. Maximum clean post-grad coverage was zero; no
post-grad CURRENT formed. The accepted 3603-second production milestone remains
valid and is not being re-evaluated by this short run.

A separate 300.002-second engine-isolated probe freshly verified the previously
observed pool and received one ACK, but the pool produced no notifications. Its
zero routing counts are also unexercised. No extra pool was forced through normal
security or lifecycle eligibility. Supplemental verification used one HTTP request;
normal-path trade HTTP delta remained zero in both runs.

There were no new invalid-unit observations. Historical 103 invalid units are
provably category OTHER from the old counter branch, without identifying their
asset symbols or decimals. Unknown units remain unavailable; no quote support was
expanded.

Normal-run recovery submitted 423, accepted/completed 393/393, overflowed 30 and
expired zero, with 30 recovery global gaps and zero errors/429s. This is the separate
high-load limitation; workers and capacity were not changed. RSS ended at 130.3 MB,
mean process CPU was 26.37%, final queue was empty, and trade/critical queue overflow
drops were zero. New multi-pool routing still awaits a naturally exposed live case;
deterministic tests prove the correction and fail-closed boundaries in this patch.

At the final bounded handoff snapshot, one migration was at POOL_NOT_VERIFIED and
one was NO_LONGER_TRACKED. These observations explain the lack of eligible pool
exposure; they do not justify changing verification or lifecycle rules.

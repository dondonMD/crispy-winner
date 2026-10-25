"""Bounded passive diagnostics. Never used by strategy, scoring or continuity gates."""
import json
import time

TOKEN_LIMIT = 12
SECTION_BYTES = 12288
RETENTION_DAYS = 7
REASONS = ('curve_not_verified', 'unsupported_quote', 'identity_conflict',
           'unverified_quote_semantics', 'zero_executed_amount')
RESET_REASONS = ('decode', 'stale', 'queue', 'buffer', 'recovery', 'processing', 'resource')
MAX_COUNT = (1 << 63) - 1


def increment(counts, key):
    old = counts.get(key, 0)
    counts[key] = min(MAX_COUNT, old + 1)
    if old >= MAX_COUNT:
        counts['counter_saturated'] = True


def reset(token, reason, at, shutdown):
    data = token.operational_evidence
    phase = 'shutdown_resets' if shutdown else 'live_resets'
    increment(data.setdefault(phase, {}), reason if reason in RESET_REASONS else 'decode')
    data['last_reset'] = {'recorded_at': time.time(), 'gap_at': at,
                          'reason': reason if reason in RESET_REASONS else 'decode',
                          'phase': 'SHUTDOWN' if shutdown else 'LIVE'}


def stale(token, source_ts, processed_at):
    token.operational_evidence["last_stale"] = dict(source_ts=source_ts, processed_at=processed_at,
                                                   age=processed_at - source_ts, acquired_at=None)


def section(engine, now, phase):
    """Read-only projection, no feature recomputation or token mutation."""
    manual = set(engine.manual_mints())
    selected = sorted(engine.tokens.values(), key=lambda t: (t.mint not in manual, -t.last_trade, t.mint))
    result = dict(at=now, phase=phase, selection='manual_first_then_last_trade_then_mint',
                  tracked_tokens=len(selected), retired_token_instances=engine.token_diagnostic_retired,
                  token_limit=TOKEN_LIMIT, tokens=[],
                  omitted_selection=max(0, len(selected) - TOKEN_LIMIT), omitted_bytes=0,
                  errors=engine.token_diagnostic_errors,
                  status='PARTIAL' if engine.token_diagnostic_errors else 'AVAILABLE',
                  counter_scope='current_token_instance; not_restored',
                  global_resets=dict(engine.token_diagnostic_global),
                  pump_reset_reasons=dict(engine.onchain.health['global_reset_reasons']))
    for token in selected[:TOKEN_LIMIT]:
        trades = [e for e in token.events if e.kind == 'trade' and 0 <= now - e.ts <= 180]
        known = sum(e.currency in ('SOL', 'USDC') for e in trades)
        currencies = {e.currency for e in trades}
        failures = dict.fromkeys((*REASONS, 'UNAVAILABLE'), 0)
        for event in trades:
            if event.currency not in ('SOL', 'USDC'):
                reason = event.evidence.get('unit_failure_reason')
                failures[reason if reason in REASONS else 'UNAVAILABLE'] += 1
        features = token.features.get('180', {})
        loss = token.buffer_loss_at
        blockers = engine.trade_evidence_blockers(token, now)
        blockers['loss_watermark_unexpired'] = loss is not None and now - loss <= 180
        clean = engine.trade_coverage_seconds(token, now)
        blockers['clean_window_short'] = clean < 180
        row = dict(mint=token.mint, venue=token.flow_venue, tracking_start=token.trade_tracking_since or None,
                   flow_epoch=token.flow_epoch or None, verified_quote_mint=token.verified_quote_mint or None,
                   retained_window=dict(samples=len(trades), recognised_units=known,
                       unknown_or_unrecognised_units=len(trades) - known,
                       mixed_currencies=len(currencies) > 1, unit_failure_reasons=failures),
                   feature_samples=features.get('samples'), feature_units_valid=features.get('units_valid'),
                   feature_observed_at=token.last_analysis or None,
                   last_trade_age=now - token.last_trade if token.last_trade else None,
                   clean_seconds=clean, classification=engine.trade_status(token, now), blockers=blockers,
                   coverage_gap_at=token.postgrad_gap if token.flow_venue == "PUMPSWAP" else token.trade_gap,
                   buffer_loss_at=loss,
                   active_window_trade_lost=(None if loss is not None and loss > now
                                             else loss is not None and now - loss <= 180),
                   counters=token.operational_evidence)
        # Detach from mutable counters before recording a pre-shutdown view.
        row = json.loads(json.dumps(row, allow_nan=False))
        result['tokens'].append(row)
    while len(json.dumps(result, allow_nan=False).encode()) > SECTION_BYTES and result['tokens']:
        result['tokens'].pop()
        result['omitted_bytes'] += 1
    return result

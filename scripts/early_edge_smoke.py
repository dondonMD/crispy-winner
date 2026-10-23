"""Offline synthetic smoke only. Creates no live cohort, engine, paper or wallet state."""

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import Settings
from backend.app.domain import Token, State, MarketEvent
from backend.app.early_edge import Study, IntegrityError, canonical, manifest, signal_snapshot
from backend.app.early_edge_quotes import WSOL, USDC, StateObservation
from backend.app.early_edge_report import report
from backend.app.opportunity import load_intelligence_settings


def smoke():
    now = 10000.0
    settings = Settings(mode="OBSERVE")
    references = {
        m: dict(
            source="Coinbase Exchange public ticker" if m == WSOL else "Kraken public recent trades",
            product=p,
            usd=v,
            acquired_at=now,
            published_at=now,
        )
        for m, p, v in ((WSOL, "SOL-USD", 150), (USDC, "USDCUSD", 1))
    }

    def snapshot(mint, action):
        t = Token(mint, "SYNTHETIC ONLY", "SYNTH", now - 240)
        t.state = State.MATURING
        t.last_curve, t.curve_progress, t.verified_quote_mint = now, 48, WSOL
        t.curve_history = deque([(now - 180, 30), (now - 120, 36), (now - 60, 42), (now, 48)], maxlen=32)
        t.security = dict(hard_failures=[], data_quality="VERIFIED")
        t.last_security = now
        t.features = {"180": dict(units_valid=True, currency="SOL", creator_sell_volume=0)}
        t.events.append(
            MarketEvent(
                mint=mint,
                kind="trade",
                source="Solana WSS",
                ts=now,
                event_id="SYNTHETIC",
                side="buy",
                currency="SOL",
                volume=0.1,
                evidence=dict(units_valid=True, quote_mint=WSOL, canonical_trade={}),
            )
        )
        view = dict(
            action=action,
            research_version=load_intelligence_settings().version,
            dynamics={"freshness": "CURRENT"},
        )
        return signal_snapshot(t, view, now, settings, references)

    fixture = json.loads(Path("backend/tests/fixtures/early_edge/sdk_quotes.json").read_text())["vectors"][0][
        "state"
    ]
    with tempfile.TemporaryDirectory(prefix="early-edge-synthetic-") as temp:
        path = Path(temp) / "synthetic.db"
        study = Study(
            path, settings, manifest(settings, now - 2, draft=False, synthetic=True), synthetic=True
        )
        study.begin(now - 1)
        early = snapshot(WSOL, "EARLY_OPPORTUNITY")
        historical = dict(early, timestamp=now - 3)
        try:
            study.enroll(historical, now)
        except IntegrityError:
            historical_refused = True
        else:
            raise AssertionError("Historical enrollment accepted")
        study.enroll(early, now, controls=[snapshot(USDC, "DEVELOPING")])
        obs = StateObservation(
            WSOL,
            now + 9.99,
            now + 10.1,
            123,
            canonical(fixture),
            2039280,
            tuple(hashlib.sha256(f"SYNTHETIC-{i}".encode()).hexdigest() for i in range(7)),
        )
        study.observe_state(obs, references, now + 10.1)
        assert study.db.execute("SELECT count(*) FROM ee_entries").fetchone()[0] == 0
        from dataclasses import replace

        study.observe_state(
            replace(obs, requested_at=now + 10, acquired_at=now + 10.2), references, now + 10.2
        )
        study.observe_state(
            replace(obs, mint=USDC, requested_at=now + 10, acquired_at=now + 10.3), references, now + 10.3
        )
        late_refs = {m: dict(r, acquired_at=now + 300, published_at=now + 300) for m, r in references.items()}
        study.observe_state(replace(obs, requested_at=now + 300, acquired_at=now + 300), late_refs, now + 300)
        assert (
            study.db.execute("SELECT status FROM ee_outcomes WHERE horizon=300").fetchone()[0] == "MEASURED"
        )
        # Control primary exit is still pending; interruption explicitly censors it.
        study.db.close()  # deliberate synthetic interruption
        restarted = Study(path, settings, synthetic=True)
        restarted.begin(now + 301)
        restarted.close(now + 302)
        result = report(path)
        assert result == report(path)
        assert result["primary_accounting_fraction"] == 1
        assert result["primary_unavailable"] == 1
        assert result["horizons"] is None and result["status"] == "INTERIM_OPERATIONAL_ONLY"
        return dict(
            synthetic=True,
            live_cohort_created=False,
            engine_created=False,
            network_requests=0,
            historical_enrollments=0,
            historical_refused=historical_refused,
            pre_latency_entries=0,
            restart_persisted=True,
            interruption_explicit=True,
            report_deterministic=True,
            enrollment=result["primary_unique_token_session_by_arm"],
            primary_unavailable=result["primary_unavailable"],
            primary_coverage=result["primary_outcome_coverage"],
            status=result["status"],
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = smoke()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as f:
            json.dump(result, f, indent=2, allow_nan=False)
            f.write("\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

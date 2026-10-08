import hashlib
import json
import math
import statistics
from collections import defaultdict
from backend.app.domain import MarketEvent


def strategy_version(settings):
    # Mode is provenance, not a strategy threshold; simulation never calibrates real decisions.
    config = settings.model_dump(exclude={"mode"})
    digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
    return "conservative-" + digest, config


class OutcomeCollector:
    def __init__(self, db, settings, estimator, session):
        self.db, self.settings, self.estimator, self.session = db, settings, estimator, session
        self.pending: dict = {}

    def signal(self, token, now, version):
        if token.price is None:
            return None
        costs = self.estimator.estimate(token.viability.get("proposed_position_usd", 4), token.liquidity)
        snapshot = {
            "timestamp": now,
            "price": token.price,
            "liquidity": token.liquidity,
            "features": token.features["180"],
            "scores": token.scores,
            "security_risk": token.security["risk_score"],
            "decision": token.decision,
            "strategy_version": version,
            "mode": self.settings.mode,
            "state": token.state.value,
            "age": now - token.created,
            "costs": costs,
            "position_usd": token.viability.get("proposed_position_usd", 4),
            "eligible_research": token.decision.get("research_eligible", False),
        }
        signal_id = self.db.add("signal", snapshot, token.mint, self.session, now)
        if len(self.pending) >= 2000:
            # Keep memory bounded; omitted follow-up is explicitly missing, never a winning sample.
            oldest = next(iter(self.pending))
            self.db.add(
                "outcome",
                {"signal_id": oldest, "status": "UNAVAILABLE_CAPACITY", "mode": self.settings.mode},
                session=self.session,
                ts=now,
            )
            del self.pending[oldest]
        self.pending[signal_id] = {
            "mint": token.mint,
            "signal": snapshot,
            "remaining": set(self.settings.horizons),
            "due": now + self.settings.latency_ms / 1000,
            "entry": None,
            "min": None,
            "max": None,
        }
        return signal_id

    def observe(self, token, event):
        if event.price is None:
            return
        for signal_id, pending in list(self.pending.items()):
            if pending["mint"] != token.mint:
                continue
            signal = pending["signal"]
            if event.ts < pending["due"]:
                continue
            # Next observable price after latency; outcomes never use a future price at signal time.
            if pending["entry"] is None:
                pending["entry"] = event.price
                pending["min"] = event.price
                pending["max"] = event.price
            pending["min"] = min(pending["min"], event.price)
            pending["max"] = max(pending["max"], event.price)
            for horizon in sorted(pending["remaining"]):
                if event.ts < signal["timestamp"] + horizon:
                    continue
                pending["remaining"].remove(horizon)
                delay = event.ts - (signal["timestamp"] + horizon)
                if delay > self.settings.max_data_age_seconds:
                    result = {"status": "UNAVAILABLE_GAP"}
                else:
                    gross = 100 * (event.price / pending["entry"] - 1)
                    # Use both entry and exit liquidity; adverse liquidity change must affect exits.
                    entry = self.estimator.side(signal["position_usd"], signal["liquidity"])
                    exit = self.estimator.side(signal["position_usd"] * (1 + gross / 100), event.liquidity)
                    if entry is None or exit is None:
                        result = {"status": "UNAVAILABLE_COSTS"}
                    else:
                        cost = sum(v for side in [entry, exit] for k, v in side.items() if k.endswith("_usd"))
                        cost += self.settings.failed_tx_reserve_usd
                        net = gross - 100 * cost / signal["position_usd"]
                        result = {
                            "status": "MEASURED",
                            "gross_return_pct": gross,
                            "net_return_pct": net,
                            "entry_observed": pending["entry"],
                            "exit_observed": event.price,
                            "signal_price": signal["price"],
                            "latency_ms": self.settings.latency_ms,
                            "round_trip_cost_usd": cost,
                            "mfe_pct": 100 * (pending["max"] / pending["entry"] - 1),
                            "mae_pct": 100 * (pending["min"] / pending["entry"] - 1),
                            "observed_delay_seconds": delay,
                        }
                self.db.add(
                    "outcome",
                    {
                        "signal_id": signal_id,
                        "horizon": horizon,
                        "mode": signal["mode"],
                        "strategy_version": signal["strategy_version"],
                        "signal_ts": signal["timestamp"],
                        "scores": signal["scores"],
                        "security_risk": signal["security_risk"],
                        "liquidity": signal["liquidity"],
                        "age": signal["age"],
                        "state": signal["state"],
                        "eligible_research": signal["eligible_research"],
                        "decision": signal["decision"]["decision"],
                        **result,
                    },
                    token.mint,
                    self.session,
                    event.ts,
                )
            if not pending["remaining"]:
                del self.pending[signal_id]

    def expire(self, now):
        for signal_id, p in list(self.pending.items()):
            if (
                now
                > p["signal"]["timestamp"] + max(self.settings.horizons) + self.settings.max_data_age_seconds
            ):
                for horizon in p["remaining"]:
                    self.db.add(
                        "outcome",
                        {
                            "signal_id": signal_id,
                            "horizon": horizon,
                            "status": "UNAVAILABLE_NO_PRICE",
                            "mode": p["signal"]["mode"],
                            "strategy_version": p["signal"]["strategy_version"],
                        },
                        p["mint"],
                        self.session,
                        now,
                    )
                del self.pending[signal_id]


class Summary:
    def __init__(self, minimum=100):
        self.count = 0
        self.total = 0.0
        self.squared = 0.0
        self.wins = 0
        self.positive = 0.0
        self.negative = 0.0
        self.equity = 0.0
        self.peak = 0.0
        self.max_drawdown = 0.0
        self.minimum = minimum
        # Bounded deterministic sample used for medians, explicitly labelled.
        self.sample: list[float] = []

    def add(self, value):
        self.count += 1
        self.total += value
        self.squared += value * value
        self.wins += value > 0
        if value > 0:
            self.positive += value
        else:
            self.negative -= value
        self.equity += value
        self.peak = max(self.peak, self.equity)
        self.max_drawdown = max(self.max_drawdown, self.peak - self.equity)
        if len(self.sample) < 5000:
            self.sample.append(value)
        else:
            # Deterministic reservoir, constant memory; not last-N bias.
            index = int(hashlib.sha256(str(self.count).encode()).hexdigest()[:8], 16) % self.count
            if index < 5000:
                self.sample[index] = value

    def result(self):
        n = self.count
        mean = self.total / n if n else None
        variance = max(0, (self.squared - self.total * self.total / n) / (n - 1)) if n > 1 else 0
        margin = 1.96 * math.sqrt(variance / n) if n > 1 else None
        lower = mean - margin if mean is not None and margin is not None else None
        upper = mean + margin if mean is not None and margin is not None else None
        status = (
            "INSUFFICIENT DATA"
            if n < self.minimum
            else (
                "POSITIVE EXPECTANCY OBSERVED"
                if lower is not None and lower > 0
                else ("NEGATIVE EXPECTANCY OBSERVED" if upper is not None and upper < 0 else "MIXED")
            )
        )
        winners = [x for x in self.sample if x > 0]
        losers = [x for x in self.sample if x <= 0]
        return {
            "count": n,
            "expectancy_net_pct": mean,
            "win_rate_pct": 100 * self.wins / n if n else None,
            "loss_rate_pct": 100 * (n - self.wins) / n if n else None,
            "profit_factor": self.positive / self.negative if self.negative else None,
            "median_winner_pct": statistics.median(winners) if winners else None,
            "median_loser_pct": statistics.median(losers) if losers else None,
            "median_net_pct": statistics.median(self.sample) if self.sample else None,
            "median_sample_count": len(self.sample),
            "lower_ci": lower,
            "upper_ci": upper,
            "status": status,
            "max_drawdown_sum_pct": self.max_drawdown,
            "ci_method": "Normal mean interval; dependent overlapping signals invalidate naive confidence",
        }


def evaluate(db, settings, mode="real", version=None, horizon=300, now=None):
    """Streaming chronological train/validation/holdout. One token per session per horizon.

    Correlated repeat alerts are deduplicated before evidence is counted. Time split is
    descriptive, not a tuned model. Real paper/observe/manual share real provenance.
    """
    import time

    now = time.time() if now is None else now

    selected: dict[int, int] = {}
    seen: set[tuple[str, str]] = set()
    capacity_limited = False
    for signal in db.iterate("signal"):
        if (signal.get("mode") == "DEMO") != (mode == "demo") or (
            version and signal.get("strategy_version") != version
        ):
            continue
        if (
            not signal.get("eligible_research")
            or signal["ts"] + horizon + settings.max_data_age_seconds > now
        ):
            continue
        key = (signal["session"], signal["mint"])
        if key in seen:
            continue
        if len(seen) >= 100000:
            capacity_limited = True
            break
        seen.add(key)
        selected[signal["id"]] = len(selected)

    def rows():
        measured: set[int] = set()
        for row in db.iterate("outcome"):
            signal_id = row.get("signal_id")
            if signal_id not in selected or signal_id in measured or row.get("horizon") != horizon:
                continue
            if row.get("status") != "MEASURED" or row["ts"] > now:
                continue
            measured.add(signal_id)
            yield row

    count = sum(1 for _ in rows())
    boundaries = (int(len(selected) * 0.5), int(len(selected) * 0.75))
    groups = {
        name: Summary(settings.min_holdout_samples) for name in ["calibration", "validation", "holdout"]
    }
    buckets: dict[str, Summary] = defaultdict(lambda: Summary(settings.min_holdout_samples))
    entries = Summary(settings.min_holdout_samples)
    for row in rows():
        i = selected[row["signal_id"]]
        split = "calibration" if i < boundaries[0] else "validation" if i < boundaries[1] else "holdout"
        groups[split].add(row["net_return_pct"])
        if split == "holdout":
            for label, value in [
                ("momentum", row["scores"]["momentum"]),
                ("maturity", row["scores"]["maturity"]),
                ("risk", row.get("security_risk", 100)),
            ]:
                buckets[f"{label} {int(value // 10) * 10}–{int(value // 10) * 10 + 9}"].add(
                    row["net_return_pct"]
                )
            liquidity = row.get("liquidity") or 0
            buckets["liquidity " + ("≥10k" if liquidity >= 10000 else "<10k")].add(row["net_return_pct"])
            buckets["age " + ("≥10m" if row.get("age", 0) >= 600 else "<10m")].add(row["net_return_pct"])
            buckets["state " + row.get("state", "UNKNOWN")].add(row["net_return_pct"])
            if row.get("decision") == "ALLOW_PAPER_ENTRY":
                entries.add(row["net_return_pct"])
    return {
        "sample_count": count,
        "eligible_due_signals": len(selected),
        "missing_outcomes": len(selected) - count,
        "coverage_pct": 100 * count / len(selected) if selected else None,
        "capacity_limited": capacity_limited,
        "horizon": horizon,
        "mode": mode,
        "strategy_version": version,
        "splits": {k: v.result() for k, v in groups.items()},
        "holdout": groups["holdout"].result(),
        "buckets": {k: v.result() for k, v in buckets.items()},
        "entry_precision": entries.result(),
        "no_trade_net_return_pct": 0,
        "warnings": [
            "Small samples",
            "Selection and survivorship bias",
            "Multiple testing",
            "Changing market regimes",
            "Overlapping market exposure",
            "Holdout is descriptive; production edge approval requires frozen prospective cohort",
        ],
    }


def replay(db, session):
    """Chronological replay through the same scoring, risk, state and paper pipeline.

    Uses an isolated temporary database, startup context, and recorded contemporaneous
    provider/resource states. No external requests and no later outcome lookup.
    """
    import tempfile
    from pathlib import Path
    from collections import deque
    from backend.app.engine import RadarEngine
    from backend.app.config import Settings
    from backend.app.domain import Token, State

    contexts = db.rows("session_context", session=session, limit=1)
    if not contexts:
        return {
            "session": session,
            "events_replayed": 0,
            "scores_match": None,
            "decisions_match": None,
            "limitation": "Session lacks replay context or is beyond retention",
        }
    context = contexts[0]
    count = 0
    score_mismatches = 0
    decision_mismatches = 0
    state_mismatches = 0
    with tempfile.TemporaryDirectory() as directory:
        engine = RadarEngine(Settings(**context["settings"]), Path(directory) / "replay.db", offline=True)
        engine.paper.state = context["paper_state"]
        engine.approved_evidence = context.get("evidence")
        for t in context["initial_tokens"]:
            token = Token(t["mint"], t["name"], t["symbol"], t["created"], t["creator"])
            token.state = State(t["state"])
            token.graduation = t["graduation"]
            token.grad_high = t["grad_high"]
            token.grad_low = t["grad_low"] if t["grad_low"] is not None else math.inf
            token.events = deque(maxlen=engine.settings.max_events)
            engine.tokens[token.mint] = token
        for row in db.iterate("event", session=session):
            event = MarketEvent.model_validate(row["event"])
            before = row.get("context_before", {})
            engine.metrics.update(
                resource_pressure=before.get("resource_pressure", False),
                storage_full=before.get("storage_full", False),
            )
            for name, health in [
                ("pump", engine.pump.health),
                ("rpc", engine.rpc.health),
                ("dex", engine.dex.health),
            ]:
                health["connected"] = before.get("providers_connected", {}).get(name, False)
            for mint in before.get("degraded", {}):
                if mint in engine.tokens:
                    engine.tokens[mint].degraded = True
            engine.process(event, event.ts)
            count += 1
            replayed = engine.tokens.get(event.mint)
            if replayed is None:
                state_mismatches += 1
                continue
            if any(
                abs(replayed.scores[k] - row["scores_after"][k]) > 0.11
                for k in ["maturity", "momentum", "chase"]
            ):
                score_mismatches += 1
            decision_mismatches += replayed.decision["decision"] != row.get(
                "decision_after"
            ) or replayed.decision["reasons"] != row.get("reasons_after")
            state_mismatches += replayed.state.value != row.get("state_after")
        engine.db.engine.dispose()
    return {
        "session": session,
        "events_replayed": count,
        "scores_match": count > 0 and score_mismatches == 0,
        "decisions_match": count > 0 and decision_mismatches == 0,
        "states_match": count > 0 and state_mismatches == 0,
        "score_mismatches": score_mismatches,
        "decision_mismatches": decision_mismatches,
        "state_mismatches": state_mismatches,
        "no_network": True,
        "no_lookahead": True,
        "limitation": "Raw events expire after 24h; partial sessions cannot prove exact reproducibility",
    }

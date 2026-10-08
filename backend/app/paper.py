import json
import uuid
from backend.app.db import Record


class PaperAccount:
    """Append-only, atomic account/trade journal. Demo has a separate account namespace."""

    def __init__(self, db, settings, estimator):
        self.db, self.settings, self.estimator = db, settings, estimator
        self.key = "demo" if settings.mode == "DEMO" else "real"
        rows = db.rows("paper_account", mint=self.key, limit=1)
        self.state = (
            rows[-1]["state"]
            if rows
            else {
                "starting_balance": settings.account_usd,
                "cash": settings.account_usd,
                "peak": settings.account_usd,
                "positions": {},
                "pending": {},
                "realized_net_pnl": 0.0,
                "gross_pnl": 0.0,
                "estimated_fees": 0.0,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "winning_total": 0.0,
                "losing_total": 0.0,
                "max_drawdown_pct": 0.0,
            }
        )
        self.committed_state = json.loads(json.dumps(self.state))
        if not rows:
            self.persist()

    def persist(self, trade=None, ts=None):
        # Account and trade either both commit or neither commits.
        import time

        now = time.time() if ts is None else ts
        try:
            with self.db.sessions.begin() as session:
                session.add(
                    Record(
                        kind="paper_account",
                        mint=self.key,
                        ts=now,
                        session="",
                        payload=json.dumps({"state": self.state}, allow_nan=False),
                    )
                )
                if trade:
                    session.add(
                        Record(
                            kind="paper_trade",
                            mint=self.key,
                            ts=now,
                            session="",
                            payload=json.dumps(trade, allow_nan=False),
                        )
                    )
        except Exception:
            self.state = json.loads(json.dumps(self.committed_state))
            raise
        self.committed_state = json.loads(json.dumps(self.state))

    def request_entry(self, token, now, strategy_version):
        if self.settings.mode not in ["PAPER", "DEMO"] or token.decision["decision"] != "ALLOW_PAPER_ENTRY":
            return False
        if token.mint in self.state["positions"] or token.mint in self.state["pending"]:
            return False
        if len(self.state["positions"]) + len(self.state["pending"]) >= self.settings.max_open_positions:
            return False
        size = token.viability["position_size_usd"]
        costs = self.estimator.estimate(size, token.liquidity)
        if not costs or size + costs["entry_cost_usd"] > self.state["cash"] or not token.price:
            return False
        self.state["pending"][token.mint] = {
            "action": "entry",
            "requested": now,
            "due": now + self.settings.latency_ms / 1000,
            "signal_price": token.price,
            "size": size,
            "strategy_version": strategy_version,
            "id": str(uuid.uuid4()),
        }
        self.persist(ts=now)
        return True

    def observe(self, token, observed_at):
        """Fill only using a new observable price after latency, never last displayed price."""
        mint = token.mint
        pending = self.state["pending"].get(mint)
        if pending and observed_at >= pending["due"]:
            if token.last_price < pending["due"] or token.price is None:
                return
            if pending["action"] == "entry":
                if token.decision["decision"] != "ALLOW_PAPER_ENTRY":
                    del self.state["pending"][mint]
                    self.persist(ts=observed_at)
                    return
                costs = self.estimator.estimate(pending["size"], token.liquidity)
                if not costs or pending["size"] + costs["entry_cost_usd"] > self.state["cash"]:
                    del self.state["pending"][mint]
                    self.persist(ts=observed_at)
                    return
                # Embedded slippage/impact increases fill price. Fees debit cash separately.
                entry = costs["entry"]
                adverse = (entry["slippage_usd"] + entry["price_impact_usd"]) / pending["size"]
                fill = token.price * (1 + adverse)
                fees = (
                    sum(
                        v
                        for k, v in entry.items()
                        if k.endswith("_usd") and k not in ["slippage_usd", "price_impact_usd"]
                    )
                    + self.settings.failed_tx_reserve_usd / 2
                )
                debit = pending["size"] + fees
                self.state["cash"] -= debit
                position = {
                    **pending,
                    "opened": observed_at,
                    "entry_fill": fill,
                    "entry_observed": token.price,
                    "quantity": pending["size"] / fill,
                    "entry_fees": fees,
                    "entry_debit": debit,
                    "latency_ms": self.settings.latency_ms,
                    "signal_fill_difference_pct": 100 * (fill / pending["signal_price"] - 1),
                }
                self.state["positions"][mint] = position
                self.state["estimated_fees"] += fees
                del self.state["pending"][mint]
                self.persist({"action": "ENTRY", "token_mint": mint, **position}, ts=observed_at)
            else:
                position = self.state["positions"][mint]
                mark = position["quantity"] * token.price
                exit_cost = self.estimator.side(mark, token.liquidity)
                if exit_cost is None:
                    return  # unknown exitability cannot magically liquidate a position
                embedded = exit_cost["slippage_usd"] + exit_cost["price_impact_usd"]
                fill = token.price * (1 - embedded / mark)
                fees = (
                    sum(
                        v
                        for k, v in exit_cost.items()
                        if k.endswith("_usd") and k not in ["slippage_usd", "price_impact_usd"]
                    )
                    + self.settings.failed_tx_reserve_usd / 2
                )
                proceeds = position["quantity"] * fill - fees
                pnl = proceeds - position["entry_debit"]
                gross = position["quantity"] * token.price - position["size"]
                self.state["cash"] += proceeds
                self.state["gross_pnl"] += gross
                self.state["realized_net_pnl"] += pnl
                self.state["estimated_fees"] += fees
                self.state["trades"] += 1
                self.state["wins" if pnl > 0 else "losses"] += 1
                self.state["winning_total" if pnl > 0 else "losing_total"] += abs(pnl)
                self.state["peak"] = max(self.state["peak"], self.state["cash"])
                drawdown = 100 * (1 - self.state["cash"] / self.state["peak"])
                self.state["max_drawdown_pct"] = max(self.state["max_drawdown_pct"], drawdown)
                trade = {
                    "action": "EXIT",
                    "token_mint": mint,
                    "position_id": position["id"],
                    "reason": pending["reason"],
                    "fill_price": fill,
                    "observed_price": token.price,
                    "entry_fill": position["entry_fill"],
                    "signal_price": position["signal_price"],
                    "entry_cost_usd": position["entry_fees"],
                    "exit_cost_usd": fees,
                    "net_pnl_usd": pnl,
                    "gross_pnl_usd": gross,
                    "proceeds_usd": proceeds,
                    "strategy_version": position["strategy_version"],
                    "latency_ms": self.settings.latency_ms,
                }
                del self.state["positions"][mint]
                del self.state["pending"][mint]
                self.persist(trade, ts=observed_at)
        position = self.state["positions"].get(mint)
        if position and mint not in self.state["pending"] and token.price:
            move = 100 * (token.price / position["entry_fill"] - 1)
            reason = None
            if token.decision["decision"] == "REJECT":
                reason = "Risk rejection"
            elif move <= -self.settings.stop_loss_pct:
                reason = "Stop loss"
            elif move >= self.settings.take_profit_pct:
                reason = "Take profit"
            elif observed_at - position["opened"] >= self.settings.max_hold_seconds:
                reason = "Maximum holding time"
            if reason:
                self.state["pending"][mint] = {
                    "action": "exit",
                    "reason": reason,
                    "requested": observed_at,
                    "due": observed_at + self.settings.latency_ms / 1000,
                }
                self.persist(ts=observed_at)

    def expire_pending(self, now):
        expired = [
            mint
            for mint, p in self.state["pending"].items()
            if p["action"] == "entry" and now - p["requested"] > 30
        ]
        if expired:
            for mint in expired:
                del self.state["pending"][mint]
            self.persist(ts=now)

    def summary(self, tokens):
        marked = 0.0
        stale = []
        for mint, p in self.state["positions"].items():
            token = tokens.get(mint)
            if token and token.price:
                value = p["quantity"] * token.price
                costs = self.estimator.side(value, token.liquidity)
                marked += (
                    max(0, value - sum(v for k, v in costs.items() if k.endswith("_usd"))) if costs else 0
                )
                if token.degraded:
                    stale.append(mint)
            else:
                stale.append(mint)
        state = self.state
        return {
            **state,
            "equity_estimate": state["cash"] + marked,
            "unpriced_positions": stale,
            "no_trade_baseline": state["starting_balance"],
            "profit_factor": state["winning_total"] / state["losing_total"]
            if state["losing_total"]
            else None,
            "expectancy_usd": state["realized_net_pnl"] / state["trades"] if state["trades"] else None,
            "average_winner": state["winning_total"] / state["wins"] if state["wins"] else None,
            "average_loser": state["losing_total"] / state["losses"] if state["losses"] else None,
            "mode_namespace": self.key,
            "validation": "UNVALIDATED",
        }

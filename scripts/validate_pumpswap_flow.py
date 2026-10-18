"""Isolated read-only acquisition probe; never creates an engine or a database."""
import argparse
import asyncio
from decimal import Decimal
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.onchain import parse_pool
from backend.app.providers import SolanaProvider
from backend.app.pumpswap import PumpSwapFlow, QUOTES, VerifiedPool, key


async def verify_pool(rpc, address, base_mint):
    key(address)
    key(base_mint)
    account = await rpc.rpc("getAccountInfo", [address, {"encoding": "base64", "commitment": "confirmed"}])
    parsed = parse_pool(account.get("value"), base_mint)
    for field in ("base_mint", "quote_mint", "base_account", "quote_account"):
        key(parsed[field])
    if parsed["base_mint"] == parsed["quote_mint"]:
        raise ValueError("Invalid pool mint relationship")
    return VerifiedPool(address, parsed["base_mint"], parsed["quote_mint"])


class Observations:
    """Fixed counters and at most three wallet-free examples; no retained events."""
    def __init__(self, pool):
        self.pool = pool
        self.started = time.monotonic()
        self.counts = {"buy": 0, "sell": 0}
        self.raw = {"buy": 0, "sell": 0}
        self.examples = []
        self.first = None
        self.last = None
        self.rejected = 0
        self.gaps = 0

    def gap(self, mint, **kwargs):
        self.gaps += 1

    def submit(self, event):
        currency, decimals = QUOTES.get(self.pool.quote_mint, ("unknown", 0))
        raw = event.evidence.get("executed_quote_raw")
        if (currency == "unknown" or event.currency != currency or event.kind != "trade"
                or event.mint != self.pool.mint or event.side not in self.counts
                or event.evidence.get("pool") != self.pool.address
                or event.evidence.get("quote_mint") != self.pool.quote_mint
                or event.evidence.get("units_valid") is not True
                or type(raw) is not int or raw <= 0 or not math.isfinite(event.volume)
                or event.volume != raw / 10 ** decimals):
            self.rejected += 1
            return False
        self.counts[event.side] += 1
        self.raw[event.side] += raw
        if self.first is None:
            self.first = time.monotonic() - self.started
        self.last = event.ts
        if len(self.examples) < 3:
            self.examples.append({"side": event.side, "quote_amount": event.volume,
                "timestamp": event.ts, "slot": event.evidence.get("slot"), "pool": self.pool.address})
        return True

    def snapshot(self):
        currency, decimals = QUOTES.get(self.pool.quote_mint, ("unknown", 0))
        return {"currency": currency, "buy_count": self.counts["buy"], "sell_count": self.counts["sell"],
            "sample_count": sum(self.counts.values()), "first_event_elapsed_seconds": self.first,
            "last_event_age_seconds": None if self.last is None else max(0, time.time() - self.last),
            "total_actual_quote_buy_volume": str(Decimal(self.raw["buy"]) / 10 ** decimals),
            "total_actual_quote_sell_volume": str(Decimal(self.raw["sell"]) / 10 ** decimals),
            "rejected_observations": self.rejected, "local_gaps": self.gaps, "examples": self.examples}


async def diagnose(pool, base_mint, seconds=300, rpc=None, url=None):
    if not 1 <= seconds <= 600:
        raise ValueError("Duration must be 1..600 seconds")
    own_rpc = rpc is None
    rpc = SolanaProvider() if rpc is None else rpc
    task = None
    try:
        record = await verify_pool(rpc, pool, base_mint)
        observations = Observations(record)
        flow = PumpSwapFlow(observations.submit, lambda: [record], observations.gap, url)
        if not flow.health["enabled"]:
            raise ValueError("Standard WSS configuration required")
        requests_before = rpc.health["requests"]
        task = asyncio.create_task(flow.run())
        await asyncio.sleep(seconds)
        # Capture transport before cancellation closes the connection.
        health = dict(flow.health)
        aggregates = observations.snapshot()
        return {"diagnostic_only": True, "strategy_current_claimed": False,
            "pool": record.address, "base_mint": record.mint, "quote_mint": record.quote_mint,
            "ownership_layout_verified": True, "runtime_seconds": time.monotonic() - observations.started,
            "transport": health, "subscription_requested": flow.sequence > 0,
            "subscription_ack": health["acks"] > 0, "observations": aggregates,
            "executed_volume_fields": {"buy": "user_quote_amount_in", "sell": "user_quote_amount_out"},
            "verification_http_requests": requests_before,
            "normal_path_trade_http_delta": rpc.health["requests"] - requests_before,
            "isolation": "No RadarEngine, database, strategy, research or paper account instantiated"}
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if own_rpc:
            await rpc.close()


def main():
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", required=True)
    parser.add_argument("--base-mint", required=True, help="Expected base mint, checked by production pool parser")
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a unique timestamped path")
    try:
        report = asyncio.run(diagnose(args.pool, args.base_mint, args.seconds))
    except Exception as exc:
        # Never print exception messages: network exceptions may contain private URLs.
        print(json.dumps({"diagnostic_only": True, "error_type": type(exc).__name__,
                          "ownership_layout_verified": False}), file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        json.dump(report, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

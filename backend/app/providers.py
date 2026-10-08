import asyncio
import json
import logging
import os
import random
import time
from typing import Any
from collections import OrderedDict
from urllib.parse import urlencode

import httpx
import websockets
from pydantic import ValidationError
from solders.pubkey import Pubkey
from backend.app.domain import MarketEvent

log = logging.getLogger(__name__)
PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


class AsyncRateLimiter:
    def __init__(self, requests_per_second=2, concurrency=2):
        self.interval = 1 / requests_per_second
        self.lock = asyncio.Lock()
        self.semaphore = asyncio.Semaphore(concurrency)
        self.next_request = 0.0

    async def wait(self):
        async with self.lock:
            delay = max(0, self.next_request - time.monotonic())
            if delay:
                await asyncio.sleep(delay)
            self.next_request = time.monotonic() + self.interval


class HttpProvider:
    def __init__(self, name, rate=2, client=None):
        self.name = name
        self.client = client or httpx.AsyncClient(timeout=12, follow_redirects=False)
        self.limiter = AsyncRateLimiter(rate)
        self.health: dict[str, Any] = {
            "connected": False,
            "last_success": 0,
            "last_event": 0,
            "latency_ms": None,
            "errors": 0,
            "reconnects": 0,
            "rate_limited_until": 0,
        }

    async def request(self, method, url, **kwargs):
        for attempt in range(3):
            async with self.limiter.semaphore:
                await self.limiter.wait()
                started = time.monotonic()
                try:
                    async with self.client.stream(method, url, **kwargs) as response:
                        if response.status_code == 429:
                            try:
                                delay = min(120, max(1, float(response.headers.get("Retry-After", "2"))))
                            except ValueError:
                                from email.utils import parsedate_to_datetime

                                try:
                                    delay = min(
                                        120,
                                        max(
                                            1,
                                            parsedate_to_datetime(response.headers["Retry-After"]).timestamp()
                                            - time.time(),
                                        ),
                                    )
                                except (KeyError, ValueError, TypeError):
                                    delay = 2
                            self.health["rate_limited_until"] = time.time() + delay
                            self.health["errors"] += 1
                        else:
                            response.raise_for_status()
                            chunks = bytearray()
                            async for chunk in response.aiter_bytes():
                                chunks.extend(chunk)
                                if len(chunks) > 2_000_000:
                                    raise ValueError("Provider response exceeds 2MB")
                            data = json.loads(chunks)
                            self.health.update(
                                connected=True,
                                last_success=time.time(),
                                latency_ms=round((time.monotonic() - started) * 1000, 1),
                            )
                            return data
                except (httpx.HTTPError, ValueError) as exc:
                    self.health["errors"] += 1
                    # Avoid URLs in logs: optional keys live in URL query strings.
                    log.warning("%s request failed: %s", self.name, type(exc).__name__)
                    delay = 2**attempt + random.random()
            self.health["connected"] = False
            if attempt < 2:
                await asyncio.sleep(delay)
        raise RuntimeError(f"{self.name} unavailable after bounded retries")

    async def close(self):
        await self.client.aclose()


class SolanaProvider(HttpProvider):
    def __init__(self, client=None):
        super().__init__("Solana RPC", 2, client)
        self.url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
        self.global_cache = None
        self.global_cached_at = 0.0

    async def rpc(self, method, params):
        data = await self.request(
            "POST", self.url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        )
        if "error" in data or "result" not in data:
            self.health["connected"] = False
            raise ValueError("RPC returned an error or missing result")
        return data["result"]

    async def inspect(self, mint, creator="", known_accounts=None):
        Pubkey.from_string(mint)  # reject malformed addresses before network requests
        account = await self.rpc(
            "getAccountInfo", [mint, {"encoding": "jsonParsed", "commitment": "confirmed"}]
        )
        supply = await self.rpc("getTokenSupply", [mint, {"commitment": "confirmed"}])
        largest = await self.rpc("getTokenLargestAccounts", [mint, {"commitment": "confirmed"}])
        accounts = largest.get("value", [])[:20]
        details = (
            await self.rpc(
                "getMultipleAccounts",
                [[a["address"] for a in accounts], {"encoding": "jsonParsed", "commitment": "confirmed"}],
            )
            if accounts
            else {"value": []}
        )
        curve, _ = Pubkey.find_program_address(
            [b"bonding-curve", bytes(Pubkey.from_string(mint))], Pubkey.from_string(PUMP_PROGRAM)
        )
        excluded = {str(curve), "11111111111111111111111111111111"}
        verified_pools = []
        from backend.app.onchain import parse_pool

        for pair in sorted(known_accounts or [])[:2]:
            pool = await self.rpc("getAccountInfo", [pair, {"encoding": "base64", "commitment": "confirmed"}])
            try:
                parsed_pool = parse_pool(pool.get("value"), mint)
            except ValueError:
                continue
            excluded.update({pair, parsed_pool["base_account"], parsed_pool["quote_account"]})
            verified_pools.append(parsed_pool)

        from backend.app.security import analyse_security

        report = analyse_security(
            account.get("value"),
            supply.get("value"),
            accounts,
            details.get("value", []),
            creator,
            excluded,
            time.time(),
            mint=mint,
        )
        report["verified_pools"] = verified_pools
        if creator:
            Pubkey.from_string(creator)
            owned = await self.rpc(
                "getTokenAccountsByOwner",
                [creator, {"mint": mint}, {"encoding": "jsonParsed", "commitment": "confirmed"}],
            )
            owned_accounts = owned.get("value", [])
            total = int(supply.get("value", {}).get("amount", 0))
            if len(owned_accounts) <= 1000 and total > 0:
                creator_balance = sum(
                    int(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"])
                    for a in owned_accounts
                )
                report["creator_pct"] = 100 * creator_balance / total
                report["creator_holdings_quality"] = "DIRECT_OWNER_ACCOUNTS"
            else:
                report["creator_pct"] = None

        curve_data = await self.rpc(
            "getAccountInfo", [str(curve), {"encoding": "base64", "commitment": "confirmed"}]
        )
        from backend.app.onchain import parse_curve, parse_global, curve_progress

        try:
            report["bonding_curve"] = parse_curve(curve_data.get("value"))
            if self.global_cache is None or time.time() - self.global_cached_at > 300:
                global_address, _ = Pubkey.find_program_address([b"global"], Pubkey.from_string(PUMP_PROGRAM))
                global_data = await self.rpc(
                    "getAccountInfo", [str(global_address), {"encoding": "base64", "commitment": "confirmed"}]
                )
                self.global_cache = parse_global(global_data.get("value"))
                self.global_cached_at = time.time()
            report["curve_progress"] = curve_progress(report["bonding_curve"], self.global_cache)
            report["observations"].append(
                "Curve progress uses current global baseline only if supply/invariant match; completion is not migration"
            )
        except ValueError:
            report["bonding_curve"] = None
        return report


class DexScreenerProvider(HttpProvider):
    def __init__(self, client=None):
        super().__init__("DEX Screener", 0.2, client)
        self.cache: OrderedDict = OrderedDict()
        self.batch_lock = asyncio.Lock()

    async def markets(self, mints):
        if not mints:
            return []
        async with self.batch_lock:
            now = time.time()
            needed = [m for m in mints[:30] if m not in self.cache or now - self.cache[m][0] > 15]
            if needed:
                for mint in needed:
                    Pubkey.from_string(mint)
                data = await self.request(
                    "GET", "https://api.dexscreener.com/tokens/v1/solana/" + ",".join(needed)
                )
                if not isinstance(data, list):
                    raise ValueError("Invalid DEX response")
                for mint in needed:
                    pairs = [
                        p
                        for p in data
                        if p.get("chainId") == "solana"
                        and p.get("baseToken", {}).get("address") == mint
                        and p.get("dexId") == "pumpswap"
                    ]
                    pair = max(pairs, key=lambda p: p.get("liquidity", {}).get("usd") or 0, default=None)
                    self.cache[mint] = (now, pair)
                    self.cache.move_to_end(mint)
                while len(self.cache) > 250:
                    self.cache.popitem(last=False)
            result = []
            for mint in mints[:30]:
                observed, pair = self.cache.get(mint, (0, None))
                if not pair or not pair.get("priceUsd"):
                    continue
                try:
                    result.append(
                        MarketEvent(
                            mint=mint,
                            ts=observed,
                            source="DEX Screener",
                            kind="market",
                            event_id=f"dex:{mint}:{observed}",
                            price=float(pair["priceUsd"]),
                            liquidity=pair.get("liquidity", {}).get("usd"),
                            market_cap=pair.get("marketCap") or pair.get("fdv"),
                            currency="USD",
                            pair=pair["pairAddress"],
                            evidence={"txns": pair.get("txns", {}), "venue": "pumpswap"},
                        )
                    )
                except (ValidationError, KeyError, TypeError, ValueError):
                    self.health["errors"] += 1
            return result


class PumpPortalProvider:
    def __init__(self, settings, submit, candidates, require_key=True):
        self.settings, self.submit, self.candidates = settings, submit, candidates
        self.health: dict[str, Any] = {
            "connected": False,
            "last_success": 0,
            "last_event": 0,
            "errors": 0,
            "reconnects": 0,
            "trade_events": 0,
            "estimated_metered_sol": 0,
        }
        self.key = os.getenv("PUMPPORTAL_API_KEY", "")
        if require_key and settings.trade_stream_enabled and not self.key:
            raise ValueError("Trade stream explicitly enabled but PUMPPORTAL_API_KEY missing")
        self.subscribed = set()

    def normalize(self, payload, now=None):
        now = time.time() if now is None else now
        kind = {"create": "create", "buy": "trade", "sell": "trade", "migration": "migration"}.get(
            payload.get("txType")
        )
        if kind is None or not payload.get("mint"):
            return None
        Pubkey.from_string(payload["mint"])
        signature = payload.get("signature", "")
        # Without a transaction identity, trades cannot be safely deduplicated.
        if kind == "trade" and not signature:
            return None
        return MarketEvent(
            mint=payload["mint"],
            ts=now,
            source="PumpPortal",
            kind=kind,
            event_id=f"{signature or payload['mint']}:{payload['txType']}",
            signature=signature,
            name=str(payload.get("name", ""))[:100],
            symbol=str(payload.get("symbol", ""))[:30],
            creator=payload.get("traderPublicKey", "") if kind == "create" else "",
            wallet=payload.get("traderPublicKey", ""),
            side=payload["txType"] if kind == "trade" else "",
            volume=abs(float(payload.get("solAmount") or 0)),
            currency="unknown",
        )

    async def run(self):
        attempt = 0
        while True:
            try:
                uri = "wss://pumpportal.fun/api/data"
                if self.key:
                    uri += "?" + urlencode({"api-key": self.key})
                async with websockets.connect(
                    uri, max_size=100000, max_queue=16, open_timeout=15, ping_interval=20, ping_timeout=20
                ) as ws:
                    self.health.update(connected=True, last_success=time.time())
                    await ws.send(json.dumps({"method": "subscribeNewToken"}))
                    await ws.send(json.dumps({"method": "subscribeMigration"}))
                    self.subscribed = set()
                    attempt = 0
                    while True:
                        if self.settings.trade_stream_enabled:
                            target = set(self.candidates())
                            for method, keys in [
                                ("unsubscribeTokenTrade", self.subscribed - target),
                                ("subscribeTokenTrade", target - self.subscribed),
                            ]:
                                if keys:
                                    await ws.send(json.dumps({"method": method, "keys": sorted(keys)}))
                            self.subscribed = target
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=5)
                        except TimeoutError:
                            continue
                        try:
                            payload = json.loads(message)
                            if not isinstance(payload, dict):
                                raise ValueError("invalid payload")
                            event = self.normalize(payload)
                            if event:
                                self.health["last_event"] = time.time()
                                if event.kind == "trade":
                                    self.health["trade_events"] += 1
                                    self.health["estimated_metered_sol"] = (
                                        self.health["trade_events"] * 0.01 / 10000
                                    )
                                self.submit(event)
                        except (ValidationError, ValueError, TypeError, KeyError):
                            self.health["errors"] += 1
            except (OSError, websockets.WebSocketException, TimeoutError):
                self.health.update(
                    connected=False,
                    errors=self.health["errors"] + 1,
                    reconnects=self.health["reconnects"] + 1,
                )
                self.subscribed.clear()
                await asyncio.sleep(min(60, 2 ** min(attempt, 6)) + random.random())
                attempt += 1

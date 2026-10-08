"""Read-only connectivity probe. No keys printed, trades subscribed or transactions submitted."""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import Settings
from backend.app.providers import PumpPortalProvider, SolanaProvider, DexScreenerProvider
import websockets


async def main():
    results = {}
    provider = PumpPortalProvider(Settings(), lambda e: None, lambda: [])
    try:
        async with websockets.connect(
            "wss://pumpportal.fun/api/data", open_timeout=12, max_size=100000
        ) as ws:
            await ws.send(json.dumps({"method": "subscribeNewToken"}))
            await ws.send(json.dumps({"method": "subscribeMigration"}))
            start = time.monotonic()
            discovered = 0
            schemas = set()
            while time.monotonic() - start < 25:
                try:
                    payload = json.loads(await asyncio.wait_for(ws.recv(), 5))
                except TimeoutError:
                    continue
                if isinstance(payload, dict):
                    schemas.update(payload.keys())
                    event = provider.normalize(payload)
                    discovered += bool(event and event.kind == "create")
            results["PumpPortal"] = {
                "connected": True,
                "new_tokens": discovered,
                "observed_field_names": sorted(schemas),
            }
    except Exception as exc:
        results["PumpPortal"] = {"connected": False, "error_type": type(exc).__name__}
    rpc = SolanaProvider()
    dex = DexScreenerProvider()
    try:
        result = await rpc.rpc("getTokenSupply", ["So11111111111111111111111111111111111111112"])
        results["Solana RPC"] = {"connected": bool(result.get("value"))}
    except Exception as exc:
        results["Solana RPC"] = {"connected": False, "error_type": type(exc).__name__}
    try:
        events = await dex.markets(["So11111111111111111111111111111111111111112"])
        results["DEX Screener"] = {
            "connected": dex.health["connected"],
            "matching_pumpswap_markets": len(events),
        }
    except Exception as exc:
        results["DEX Screener"] = {"connected": False, "error_type": type(exc).__name__}
    await rpc.close()
    await dex.close()
    path = Path("data/provider-smoke.json")
    path.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


asyncio.run(main())

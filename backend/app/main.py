import asyncio
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from backend.app.config import ROOT, load_settings
from backend.app.engine import RadarEngine
from backend.app.logging_setup import setup_logging
from backend.app.manual import (
    MarketInput,
    OpenPositionInput,
    ClosePositionInput,
    CashInput,
    EconomicsInput,
    manual_economics,
)
import time


def create_app(settings=None, db_path=None):
    @asynccontextmanager
    async def lifespan(app):
        load_dotenv(ROOT / ".env")
        engine = RadarEngine(settings or load_settings(), db_path)
        app.state.engine = engine
        await engine.start()
        try:
            yield
        finally:
            await engine.stop()

    app = FastAPI(title="CRISPY WINNER — Graduation Radar", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        return JSONResponse(
            {
                "detail": [
                    {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                    for error in exc.errors()
                ]
            },
            status_code=422,
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def local_security(request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in ["127.0.0.1", "localhost", "testserver"]:
            return JSONResponse({"detail": "Local host required"}, status_code=403)
        if request.method == "POST":
            origin = request.headers.get("origin")
            allowed = {
                "http://127.0.0.1:8765",
                "http://localhost:8765",
                "http://127.0.0.1:5173",
                "http://localhost:5173",
            }
            allowed.add("http://" + request.headers.get("host", ""))
            if (origin is not None and origin not in allowed) or request.headers.get(
                "sec-fetch-site"
            ) == "cross-site":
                return JSONResponse({"detail": "Local same-origin journal requests only"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "JSON required"}, status_code=415)
            try:
                length = int(request.headers.get("content-length", "-1"))
            except ValueError:
                length = -1
            if not 0 <= length <= 16384:
                return JSONResponse(
                    {"detail": "A bounded JSON request of at most 16KB is required"}, status_code=413
                )
            if app.state.engine.metrics.get("storage_full"):
                return JSONResponse({"detail": "Storage cap reached; journal writes paused"}, status_code=507)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' http://127.0.0.1:8765; frame-ancestors 'none'"
        )
        return response

    @app.get("/api/health")
    async def health():
        e = app.state.engine
        return {
            "status": "degraded" if e.metrics.get("resource_pressure") or (
                e.settings.mode != "DEMO" and not e.discovery_connected()
            ) else "ok",
            "mode": e.settings.mode,
            "session": e.session,
            "running": e.running,
            "monitor_running": any(t.get_name() == "monitor" and not t.done() for t in e.tasks),
        }

    @app.get("/api/dashboard")
    async def dashboard():
        return app.state.engine.snapshot()

    @app.get("/api/tokens/{mint}")
    async def detail(mint: str):
        if len(mint) > 64:
            raise HTTPException(400, "Invalid mint")
        engine = app.state.engine
        token = engine.tokens.get(mint)
        if not token:
            raise HTTPException(404, "Token not actively monitored")
        import time

        return engine.token_view(token, time.time(), detail=True)

    @app.get("/api/opportunities")
    async def opportunities():
        return app.state.engine.intelligence.opportunities()

    @app.get("/api/opportunities/{mint}")
    async def opportunity_detail(mint: str):
        value = app.state.engine.intelligence.results.get(mint)
        if value is None:
            raise HTTPException(404, "Token no longer actively monitored")
        return {"mint": mint, **value}

    @app.post("/api/manual-account")
    async def manual_account(value: CashInput):
        return app.state.engine.intelligence.journal.set_cash(value, time.time())

    @app.post("/api/manual-economics")
    async def economics(value: EconomicsInput):
        e = app.state.engine
        return manual_economics(
            e.settings, e.intelligence.journal.cash, value.amount_usd, e.tokens.get(value.mint), time.time()
        )

    @app.post("/api/manual-market-context")
    async def manual_context(value: MarketInput):
        intelligence = app.state.engine.intelligence
        result = intelligence.journal.observe_market(value, time.time())
        intelligence.refresh(time.time(), force=True)
        return result

    @app.get("/api/manual-positions")
    async def manual_positions():
        i = app.state.engine.intelligence
        return {**i.manual_view(), "closed": i.journal.closed()}

    @app.post("/api/manual-positions")
    async def open_manual_position(value: OpenPositionInput):
        try:
            return app.state.engine.intelligence.open_position(value)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/manual-positions/{identity}/mark")
    async def manual_mark(identity: str, value: MarketInput):
        i = app.state.engine.intelligence
        position = i.journal.positions.get(identity)
        if not position or position["mint"] != value.mint:
            raise HTTPException(404, "Open position/mint not found")
        i.journal.observe_market(value, time.time())
        i.refresh_positions(time.time())
        return i.exit_results[identity]

    @app.post("/api/manual-positions/{identity}/close")
    async def close_manual_position(identity: str, value: ClosePositionInput):
        i = app.state.engine.intelligence
        try:
            result = i.journal.close(identity, value, time.time())
        except KeyError:
            raise HTTPException(404, "Open position not found") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        i.refresh_positions(time.time())
        return result

    @app.get("/api/paper/trades")
    async def paper_trades():
        engine = app.state.engine
        return engine.db.rows("paper_trade", mint=engine.paper.key, limit=200)

    @app.get("/api/sessions")
    async def sessions():
        return app.state.engine.db.rows("session", limit=100)

    @app.get("/api/evaluation")
    async def evaluation(horizon: int = 300):
        engine = app.state.engine
        if horizon not in engine.settings.horizons:
            raise HTTPException(400, "Unsupported configured horizon")
        from backend.app.evaluation import evaluate

        return await asyncio.to_thread(
            evaluate,
            engine.db,
            engine.settings,
            "demo" if engine.settings.mode == "DEMO" else "real",
            engine.version,
            horizon,
        )

    @app.get("/api/events")
    async def stream(request: Request):
        async def snapshots():
            while not await request.is_disconnected():
                yield "data: " + json.dumps(app.state.engine.snapshot(), allow_nan=False) + "\n\n"
                await asyncio.sleep(2)

        return StreamingResponse(
            snapshots(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    build = ROOT / "frontend/dist"
    if (build / "assets").exists():
        app.mount("/assets", StaticFiles(directory=build / "assets"), name="assets")

    @app.get("/")
    async def home():
        if not (build / "index.html").exists():
            raise HTTPException(503, "Frontend not built. Run npm ci and npm run build in frontend.")
        return FileResponse(build / "index.html")

    return app


app = create_app()


def run_server():
    import uvicorn

    setup_logging()
    # Persistent dashboard SSE responses must not prevent lifespan cleanup forever.
    # Only HTTP draining is bounded; engine evidence reconciliation still runs fully.
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("RADAR_PORT", "8765")),
                access_log=False, timeout_graceful_shutdown=5)


if __name__ == "__main__":
    run_server()

import asyncio
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from backend.app.config import ROOT, load_settings
from backend.app.engine import RadarEngine
from backend.app.logging_setup import setup_logging


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET"],
        allow_headers=[],
    )

    @app.middleware("http")
    async def local_security(request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in ["127.0.0.1", "localhost", "testserver"]:
            from fastapi.responses import JSONResponse

            return JSONResponse({"detail": "Local host required"}, status_code=403)
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
            "status": "degraded" if e.metrics.get("resource_pressure") else "ok",
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

if __name__ == "__main__":
    import uvicorn

    setup_logging()
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("RADAR_PORT", "8765")), access_log=False)

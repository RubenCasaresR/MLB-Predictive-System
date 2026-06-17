# =============================================================================
# app.py
# FastAPI - MLB Predictive System API
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================

import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text

from api import __version__
from api.auth import router as auth_router
from api.database import get_async_engine, get_engine
from api.middleware import RequestSizeLimitMiddleware, SecurityHeadersMiddleware
from api.routers import alerts, analysis, bets, risk, stats
from etl.config import JWT_SECRET

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================================
# RATE LIMITER
# ============================================================================

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


# ============================================================================
# FASTAPI APP
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup — engines cached")
    if not JWT_SECRET:
        logger.warning(
            "JWT_SECRET not set! Authentication will reject all requests. "
            "Set JWT_SECRET in environment or .env file."
        )
    else:
        logger.info("JWT_SECRET is configured")
    yield
    sync_engine = get_engine()
    sync_engine.dispose()
    async_engine = get_async_engine()
    try:
        await async_engine.dispose()
    except RuntimeError:
        logger.warning("Event loop closed during async engine dispose — skipping")
    logger.info("Application shutdown — engines disposed")


app = FastAPI(
    title="MLB Predictive System API",
    description="Sistema de Análisis Predictivo y Gestión de Riesgo MLB",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de seguridad
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware, max_size=1_048_576)

# Incluir routers
app.include_router(auth_router)
app.include_router(bets.router)
app.include_router(alerts.router)
app.include_router(stats.router)
app.include_router(risk.router)
app.include_router(analysis.router)

# Frontend estático (desktop)
import pathlib

frontend_path = pathlib.Path(__file__).parent.parent / "7_frontend" / "desktop"
if frontend_path.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(frontend_path / "assets"), check_dir=False),
        name="assets",
    )
    app.mount(
        "/css", StaticFiles(directory=str(frontend_path / "css"), check_dir=False), name="css"
    )
    app.mount("/js", StaticFiles(directory=str(frontend_path / "js"), check_dir=False), name="js")

    index_file = str(frontend_path / "index.html")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(index_file)

# ============================================================================
# HEALTH & METRICS
# ============================================================================


@app.get("/health")
@limiter.exempt
async def health_check(request: Request):
    db_status = "unhealthy"
    try:
        async_engine = get_async_engine()
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        logger.warning(f"Health check DB failed: {e}")

    mlb_api_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2024-01-01"
            )
            mlb_api_status = "healthy" if resp.is_success else "unhealthy"
    except Exception as e:
        mlb_api_status = "unreachable"
        logger.warning(f"Health check MLB API failed: {e}")

    odds_api_status = "unconfigured"
    odds_key = os.getenv("ODDS_API_KEY", "")
    if odds_key:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"https://api.the-odds-api.com/v4/sports/baseball_mlb/odds?apiKey={odds_key}&regions=us&markets=h2h"
                )
                odds_api_status = "healthy" if resp.is_success else "unhealthy"
        except Exception as e:
            odds_api_status = "unreachable"
            logger.warning(f"Health check Odds API failed: {e}")

    overall = "healthy" if db_status == "healthy" else "degraded"
    return {
        "status": overall,
        "version": __version__,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "components": {
            "database": db_status,
            "mlb_api": mlb_api_status,
            "odds_api": odds_api_status,
        },
    }


# ============================================================================
# ERROR HANDLERS
# ============================================================================


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ============================================================================
# CLI ENTRY POINT (mlb-api)
# ============================================================================


def run_api():
    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )

# =============================================================================
# app.py
# FastAPI - MLB Predictive System API
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================

import uvicorn
import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging
import logging.config

from api.routers import bets, alerts, stats, risk, analysis
from api.database import get_engine
import requests as http_requests

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
    logger.info("Application startup — engine cached")
    yield
    engine = get_engine()
    engine.dispose()
    logger.info("Application shutdown — engine disposed")


app = FastAPI(
    title="MLB Predictive System API",
    description="Sistema de Análisis Predictivo y Gestión de Riesgo MLB",
    version="1.0.0",
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

# Incluir routers
app.include_router(bets.router)
app.include_router(alerts.router)
app.include_router(stats.router)
app.include_router(risk.router)
app.include_router(analysis.router)

# Frontend estático (desktop)
import pathlib
frontend_path = pathlib.Path(__file__).parent.parent / "7_frontend" / "desktop"
if frontend_path.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets"), check_dir=False), name="assets")
    app.mount("/css", StaticFiles(directory=str(frontend_path / "css"), check_dir=False), name="css")
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
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        logger.warning(f"Health check DB failed: {e}")

    mlb_api_status = "unknown"
    try:
        resp = http_requests.get("https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2024-01-01", timeout=5)
        mlb_api_status = "healthy" if resp.ok else "unhealthy"
    except Exception as e:
        mlb_api_status = "unreachable"
        logger.warning(f"Health check MLB API failed: {e}")

    odds_api_status = "unconfigured"
    odds_key = os.getenv("ODDS_API_KEY", "")
    if odds_key:
        try:
            resp = http_requests.get(
                f"https://api.the-odds-api.com/v4/sports/baseball_mlb/odds?apiKey={odds_key}&regions=us&markets=h2h",
                timeout=5,
            )
            odds_api_status = "healthy" if resp.ok else "unhealthy"
        except Exception as e:
            odds_api_status = "unreachable"
            logger.warning(f"Health check Odds API failed: {e}")

    overall = "healthy" if db_status == "healthy" else "degraded"
    return {
        "status": overall,
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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

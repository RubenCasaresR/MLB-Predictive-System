# =============================================================================
# alerts.py
# Router de alertas en tiempo real (Sharp Money, RLM, EV+)
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================

from typing import List
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
import asyncio
import json
import logging
from datetime import datetime

from api.models.pydantic_models import AlertResponse, AlertListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


# Store for active WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected: {len(self.active_connections)} active")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()


# ============================================================================
# REST ENDPOINTS
# ============================================================================

@router.get("/", response_model=AlertListResponse)
async def get_alerts(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
):
    from sqlalchemy import text
    from api.database import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT COUNT(*) FROM alerts")
        ).scalar() or 0

        unread = conn.execute(
            text("SELECT COUNT(*) FROM alerts WHERE is_read = FALSE")
        ).scalar() or 0

        query = "SELECT alert_id, game_id, team_id, signal_type, confidence, message, created_at, is_read FROM alerts"
        params = {}
        if unread_only:
            query += " WHERE is_read = FALSE"
        query += " ORDER BY created_at DESC LIMIT :lim"
        params["lim"] = limit

        rows = conn.execute(text(query), params).fetchall()

    alerts = [
        AlertResponse(
            alert_id=r[0], game_id=r[1] or "", team_id=r[2] or "",
            signal_type=r[3], confidence=float(r[4]) if r[4] else 0.0,
            message=r[5] or "", created_at=r[6] or datetime.now(),
            is_read=bool(r[7]),
        )
        for r in rows
    ]

    return AlertListResponse(alerts=alerts, total=total, unread_count=unread)


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: int):
    from sqlalchemy import text
    from api.database import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT alert_id, game_id, team_id, signal_type, confidence, message, created_at, is_read FROM alerts WHERE alert_id = :aid"),
            {"aid": alert_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")

    return AlertResponse(
        alert_id=row[0], game_id=row[1] or "", team_id=row[2] or "",
        signal_type=row[3], confidence=float(row[4]) if row[4] else 0.0,
        message=row[5] or "", created_at=row[6] or datetime.now(),
        is_read=bool(row[7]),
    )


@router.post("/{alert_id}/read")
async def mark_alert_read(alert_id: int):
    from sqlalchemy import text
    from api.database import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE alerts SET is_read = TRUE WHERE alert_id = :aid"),
            {"aid": alert_id},
        )
    return {"status": "ok"}


@router.post("/read-all")
async def mark_all_read():
    from sqlalchemy import text
    from api.database import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE alerts SET is_read = TRUE WHERE is_read = FALSE"))
    return {"status": "ok"}


# ============================================================================
# WEBSOCKET ENDPOINT (Real-time alerts)
# ============================================================================

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif message.get("type") == "subscribe":
                channels = message.get("channels", ["sharp_money", "ev_positive"])
                await websocket.send_json({
                    "type": "subscribed",
                    "channels": channels,
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket disconnected")


# ============================================================================
# FUNCIÓN PARA ENVIAR ALERTA DESDE EL MOTOR
# ============================================================================

async def send_sharp_money_alert(
    game_id: str,
    team_id: str,
    signal_type: str,
    confidence: float,
    details: dict,
):
    message = {
        "type": "alert",
        "signal_type": signal_type,
        "game_id": game_id,
        "team_id": team_id,
        "confidence": confidence,
        "timestamp": datetime.now().isoformat(),
        "details": details,
        "message": (
            f"Sharp Money detectado en {game_id}: "
            f"{team_id} - {signal_type} "
            f"(confianza: {confidence:.0%})"
        ),
    }
    await manager.broadcast(message)
    logger.info(f"Alert broadcast: {signal_type} for {game_id}")


async def send_ev_alert(
    game_id: str,
    team: str,
    odds: int,
    edge: float,
    kelly: float,
):
    message = {
        "type": "ev_alert",
        "game_id": game_id,
        "team": team,
        "odds": odds,
        "edge": edge,
        "kelly": kelly,
        "timestamp": datetime.now().isoformat(),
        "message": (
            f"EV+ encontrado! {team} @ {odds:+d} "
            f"(Edge: {edge:.2%}, Kelly: {kelly:.2%})"
        ),
    }
    await manager.broadcast(message)

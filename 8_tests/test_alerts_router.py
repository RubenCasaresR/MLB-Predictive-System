"""Tests para api/routers/alerts.py (218 líneas, 6 endpoints + WS + helpers)."""

import os
import sys
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from api.app import app


def _mock_engine(cursor):
    """Build a mock engine whose connect/begin return a context-manager con."""
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.execute.return_value = cursor
    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    mock_engine.begin.return_value = mock_conn
    return mock_engine


client = TestClient(app)


# ============================================================================
# ConnectionManager
# ============================================================================


class TestConnectionManager:
    def _ws_mock(self):
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.receive_text = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self):
        from api.routers.alerts import ConnectionManager

        cm = ConnectionManager()
        ws = self._ws_mock()
        await cm.connect(ws)
        assert ws in cm.active_connections
        cm.disconnect(ws)
        assert ws not in cm.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self):
        from api.routers.alerts import ConnectionManager

        cm = ConnectionManager()
        ws1, ws2 = self._ws_mock(), self._ws_mock()
        await cm.connect(ws1)
        await cm.connect(ws2)
        msg = {"type": "test"}
        await cm.broadcast(msg)
        ws1.send_json.assert_called_once_with(msg)
        ws2.send_json.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_broadcast_removes_failing_connection(self):
        from api.routers.alerts import ConnectionManager

        cm = ConnectionManager()
        ws_ok, ws_fail = self._ws_mock(), self._ws_mock()
        ws_fail.send_json.side_effect = Exception("gone")
        await cm.connect(ws_ok)
        await cm.connect(ws_fail)
        await cm.broadcast({"type": "test"})
        assert ws_fail not in cm.active_connections
        assert ws_ok in cm.active_connections


# ============================================================================
# GET /api/v1/alerts/
# ============================================================================


class TestGetAlerts:
    def test_returns_alert_list_response(self):
        mock_cursor = MagicMock()
        mock_cursor.scalar.return_value = 1
        mock_cursor.fetchall.return_value = [
            [
                1,
                "GAME-001",
                "NYY",
                "sharp_money",
                0.85,
                "Sharp Money detectado",
                "2026-05-20T12:00:00",
                0,
            ],
        ]
        mock_cursor.fetchone.return_value = None

        with patch("api.database.get_engine", return_value=_mock_engine(mock_cursor)):
            resp = client.get("/api/v1/alerts/")

        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert "total" in data
        assert "unread_count" in data
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["alert_id"] == 1
        assert data["alerts"][0]["signal_type"] == "sharp_money"

    def test_filters_unread_only(self):
        mock_cursor = MagicMock()
        mock_cursor.scalar.return_value = 0
        mock_cursor.fetchall.return_value = []

        with patch("api.database.get_engine", return_value=_mock_engine(mock_cursor)):
            resp = client.get("/api/v1/alerts/?unread_only=true")

        assert resp.status_code == 200

    def test_respects_limit(self):
        mock_cursor = MagicMock()
        mock_cursor.scalar.return_value = 0
        mock_cursor.fetchall.return_value = []

        with patch("api.database.get_engine", return_value=_mock_engine(mock_cursor)):
            resp = client.get("/api/v1/alerts/?limit=5")

        assert resp.status_code == 200

    def test_empty_alerts(self):
        mock_cursor = MagicMock()
        mock_cursor.scalar.return_value = 0
        mock_cursor.fetchall.return_value = []

        with patch("api.database.get_engine", return_value=_mock_engine(mock_cursor)):
            resp = client.get("/api/v1/alerts/")

        assert resp.status_code == 200
        data = resp.json()
        assert data["alerts"] == []
        assert data["total"] == 0


# ============================================================================
# GET /api/v1/alerts/{alert_id}
# ============================================================================


class TestGetAlert:
    def test_returns_alert_when_found(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [
            1,
            "GAME-001",
            "NYY",
            "sharp_money",
            0.85,
            "Test message",
            "2026-05-20T12:00:00",
            1,
        ]

        with patch("api.database.get_engine", return_value=_mock_engine(mock_cursor)):
            resp = client.get("/api/v1/alerts/1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["alert_id"] == 1
        assert data["is_read"] is True

    def test_returns_404_when_not_found(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None

        with patch("api.database.get_engine", return_value=_mock_engine(mock_cursor)):
            resp = client.get("/api/v1/alerts/999")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ============================================================================
# POST /api/v1/alerts/{alert_id}/read
# ============================================================================


class TestMarkAlertRead:
    def test_marks_alert_as_read(self):
        mock_cursor = MagicMock()

        with patch("api.database.get_engine", return_value=_mock_engine(mock_cursor)):
            resp = client.post("/api/v1/alerts/1/read")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ============================================================================
# POST /api/v1/alerts/read-all
# ============================================================================


class TestMarkAllRead:
    def test_marks_all_as_read(self):
        mock_cursor = MagicMock()

        with patch("api.database.get_engine", return_value=_mock_engine(mock_cursor)):
            resp = client.post("/api/v1/alerts/read-all")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ============================================================================
# WebSocket /api/v1/alerts/ws
# ============================================================================


class TestWebSocketEndpoint:
    def test_ping_pong(self):
        with client.websocket_connect("/api/v1/alerts/ws") as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_subscribe(self):
        with client.websocket_connect("/api/v1/alerts/ws") as ws:
            ws.send_json({"type": "subscribe", "channels": ["sharp_money"]})
            data = ws.receive_json()
            assert data["type"] == "subscribed"
            assert "sharp_money" in data["channels"]


# ============================================================================
# Helper: send_sharp_money_alert
# ============================================================================


class TestSendSharpMoneyAlert:
    @pytest.mark.asyncio
    async def test_broadcasts_correct_message(self):
        from api.routers import alerts as alerts_mod

        with patch.object(alerts_mod.manager, "broadcast", new_callable=AsyncMock) as mock_br:
            await alerts_mod.send_sharp_money_alert(
                game_id="GAME-001",
                team_id="NYY",
                signal_type="sharp_money",
                confidence=0.95,
                details={"movement_pct": 12.5},
            )
            mock_br.assert_called_once()
            msg = mock_br.call_args[0][0]
            assert msg["type"] == "alert"
            assert msg["signal_type"] == "sharp_money"
            assert msg["game_id"] == "GAME-001"
            assert "Sharp Money" in msg["message"]


# ============================================================================
# Helper: send_ev_alert
# ============================================================================


class TestSendEVAlert:
    @pytest.mark.asyncio
    async def test_broadcasts_correct_message(self):
        from api.routers import alerts as alerts_mod

        with patch.object(alerts_mod.manager, "broadcast", new_callable=AsyncMock) as mock_br:
            await alerts_mod.send_ev_alert(
                game_id="GAME-002",
                team="LAD",
                odds=-120,
                edge=0.08,
                kelly=0.03,
            )
            mock_br.assert_called_once()
            msg = mock_br.call_args[0][0]
            assert msg["type"] == "ev_alert"
            assert msg["game_id"] == "GAME-002"
            assert msg["team"] == "LAD"
            assert "EV+" in msg["message"]

"""Shared test fixtures for MLB Predictive System tests."""

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.app import app


@pytest.fixture
def db_url():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    url = f"sqlite:///{tmp.name}"
    yield url
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


@pytest.fixture
def setup_db_env(db_url):
    old = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = db_url
    yield
    if old is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = old


@pytest.fixture
def engine(db_url):
    eng = create_engine(db_url, connect_args={"check_same_thread": False})
    yield eng
    eng.dispose()


@pytest.fixture
def auth_override():
    """Override get_current_user for tests that need auth."""
    from api.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {"user_id": 1, "username": "testuser"}
    yield
    app.dependency_overrides.pop(get_current_user, None)


def auth_header(client=None):
    """Register a test user and return Authorization header."""
    if client is None:
        client = TestClient(app)
    client.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "password": "testpass123"},
    )
    token = client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "testpass123"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

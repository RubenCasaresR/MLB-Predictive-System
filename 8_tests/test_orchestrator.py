"""Tests para ETLOrchestrator con mocks."""

import pytest
import sys, os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from etl.orchestrator import ETLOrchestrator


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def orch():
    return ETLOrchestrator(db_url="sqlite://")


# ============================================================================
# Tests: run_daily_pipeline error handling
# ============================================================================

class TestPipelineErrorHandling:
    def test_continues_when_step_fails(self, orch, monkeypatch):
        call_log = []

        def fail_step(_):
            call_log.append("fail_step")
            raise RuntimeError("Step failed intentionally")

        def ok_step(_):
            call_log.append("ok_step")

        monkeypatch.setattr(orch, "_load_schedule", fail_step)
        monkeypatch.setattr(orch, "_ingest_statcast", ok_step)
        monkeypatch.setattr(orch, "_ingest_weather", ok_step)
        monkeypatch.setattr(orch, "_ingest_market", ok_step)
        monkeypatch.setattr(orch, "_compute_features", ok_step)
        monkeypatch.setattr(orch, "_run_predictions", ok_step)

        # Should not raise — step 1 fails, but pipeline continues
        orch.run_daily_pipeline(date(2026, 5, 20))

        assert call_log.count("fail_step") == 1
        assert call_log.count("ok_step") == 5

    def test_continues_when_middle_step_fails(self, orch, monkeypatch):
        call_log = []

        def ok(_):
            call_log.append("ok")

        def fail(_):
            call_log.append("fail")
            raise RuntimeError("mid-step failure")

        monkeypatch.setattr(orch, "_load_schedule", ok)
        monkeypatch.setattr(orch, "_ingest_statcast", ok)
        monkeypatch.setattr(orch, "_ingest_weather", fail)  # step 3 fails
        monkeypatch.setattr(orch, "_ingest_market", ok)
        monkeypatch.setattr(orch, "_compute_features", ok)
        monkeypatch.setattr(orch, "_run_predictions", ok)

        orch.run_daily_pipeline(date(2026, 5, 20))

        assert call_log.count("ok") == 5
        assert call_log.count("fail") == 1

    def test_continues_when_last_step_fails(self, orch, monkeypatch):
        call_log = []

        def ok(_):
            call_log.append("ok")

        monkeypatch.setattr(orch, "_load_schedule", ok)
        monkeypatch.setattr(orch, "_ingest_statcast", ok)
        monkeypatch.setattr(orch, "_ingest_weather", ok)
        monkeypatch.setattr(orch, "_ingest_market", ok)
        monkeypatch.setattr(orch, "_compute_features", ok)

        def fail_last(_):
            call_log.append("fail_last")
            raise RuntimeError("Last step failed")

        monkeypatch.setattr(orch, "_run_predictions", fail_last)

        orch.run_daily_pipeline(date(2026, 5, 20))

        assert call_log.count("ok") == 5
        assert call_log.count("fail_last") == 1

    def test_all_steps_succeed(self, orch, monkeypatch):
        call_log = []

        def ok(step_name):
            def fn(_):
                call_log.append(step_name)
            return fn

        monkeypatch.setattr(orch, "_load_schedule", ok("load_schedule"))
        monkeypatch.setattr(orch, "_ingest_statcast", ok("ingest_statcast"))
        monkeypatch.setattr(orch, "_ingest_weather", ok("ingest_weather"))
        monkeypatch.setattr(orch, "_ingest_market", ok("ingest_market"))
        monkeypatch.setattr(orch, "_compute_features", ok("compute_features"))
        monkeypatch.setattr(orch, "_run_predictions", ok("run_predictions"))

        orch.run_daily_pipeline(date(2026, 5, 20))
        assert len(call_log) == 6


# ============================================================================
# Tests: _load_schedule no data
# ============================================================================

class TestLoadSchedule:
    def test_empty_schedule_does_not_crash(self, orch, monkeypatch):
        import pandas as pd

        def mock_fetch(_self, _date):
            return pd.DataFrame()

        import etl.ingestors.statcast_ingestor as si
        monkeypatch.setattr(si.StatcastIngestor, "fetch_daily_games", mock_fetch)
        # Should not raise
        orch._load_schedule(date(2026, 5, 20))

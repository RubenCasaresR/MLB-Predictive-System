"""Tests para DataQualityValidator (calidad de datos ETL)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

from etl.validators.data_quality import DataQualityValidator


@pytest.fixture
def validator():
    return DataQualityValidator()


# ============================================================================
# Tests: validate_null_counts
# ============================================================================


class TestValidateNullCounts:
    def test_null_pct_exceeds_threshold(self, validator):
        df = pd.DataFrame(
            {
                "release_speed": [95.0, None, None, None, None, None],
            }
        )
        issues = validator.validate_null_counts(df, "test")
        assert len(issues) == 1
        assert "release_speed" in issues[0]

    def test_null_pct_below_threshold(self, validator):
        df = pd.DataFrame(
            {
                "release_speed": [95.0, 96.0, 94.0, 97.0, 93.0],
            }
        )
        issues = validator.validate_null_counts(df, "test")
        assert issues == []

    def test_null_pct_under_5_pct(self, validator):
        vals = [95.0] * 95 + [None] * 5  # 5% exactly → not greater than 5%
        df = pd.DataFrame({"release_speed": vals})
        issues = validator.validate_null_counts(df)
        assert len(issues) == 0

    def test_column_not_in_range_checks(self, validator):
        df = pd.DataFrame({"some_other_col": [None] * 10})
        issues = validator.validate_null_counts(df)
        assert len(issues) == 0

    def test_empty_dataframe(self, validator):
        df = pd.DataFrame()
        issues = validator.validate_null_counts(df)
        assert issues == []


# ============================================================================
# Tests: validate_ranges
# ============================================================================


class TestValidateRanges:
    def test_values_out_of_range(self, validator):
        df = pd.DataFrame(
            {
                "release_speed": [60, 95, 115, 80],
                "inning": [1, 2, 99, 4],
            }
        )
        issues = validator.validate_ranges(df, "test")
        assert len(issues) >= 2  # release_speed + inning (maybe more depends on pct)

    def test_all_values_in_range(self, validator):
        df = pd.DataFrame(
            {
                "release_speed": [85, 90, 95, 100],
                "inning": [1, 2, 3, 4],
            }
        )
        issues = validator.validate_ranges(df)
        assert issues == []

    def test_column_missing(self, validator):
        df = pd.DataFrame({"unrelated": [1, 2, 3]})
        issues = validator.validate_ranges(df)
        assert issues == []

    def test_nan_values_ignored(self, validator):
        df = pd.DataFrame({"release_speed": [95, None, None, 200]})
        issues = validator.validate_ranges(df)
        # 1 out of 4 values is out of range → 25% > 1% → issue
        assert len(issues) > 0

    def test_out_of_range_below_1pct_skipped(self, validator):
        vals = [95] * 199 + [999]
        df = pd.DataFrame({"release_speed": vals})
        issues = validator.validate_ranges(df)
        # 1/200 = 0.5% < 1% → no issue
        assert issues == []


# ============================================================================
# Tests: validate_unique_keys
# ============================================================================


class TestValidateUniqueKeys:
    def test_duplicate_keys_found(self, validator):
        df = pd.DataFrame(
            {
                "game_id": ["G1", "G1", "G2", "G1"],
                "pitcher_id": [100, 100, 200, 100],
            }
        )
        issues = validator.validate_unique_keys(df, ["game_id", "pitcher_id"], "test")
        assert len(issues) == 1
        assert "duplicados" in issues[0]

    def test_no_duplicates(self, validator):
        df = pd.DataFrame(
            {
                "game_id": ["G1", "G1", "G2"],
                "pitcher_id": [100, 200, 100],
            }
        )
        issues = validator.validate_unique_keys(df, ["game_id", "pitcher_id"])
        assert issues == []

    def test_single_key_no_dups(self, validator):
        df = pd.DataFrame({"game_id": ["G1", "G2", "G3"]})
        issues = validator.validate_unique_keys(df, ["game_id"])
        assert issues == []


# ============================================================================
# Tests: validate_pitch_consistency
# ============================================================================


class TestValidatePitchConsistency:
    def test_strike_and_ball_both_true(self, validator):
        df = pd.DataFrame(
            {
                "strike": [True, False, True, True],
                "ball": [False, False, True, False],
            }
        )
        issues = validator.validate_pitch_consistency(df)
        assert len(issues) == 1
        assert "strike y ball" in issues[0].lower()

    def test_no_conflicts(self, validator):
        df = pd.DataFrame(
            {
                "strike": [True, False, True],
                "ball": [False, True, False],
            }
        )
        issues = validator.validate_pitch_consistency(df)
        assert issues == []

    def test_missing_columns(self, validator):
        df = pd.DataFrame({"unrelated": [1, 2]})
        issues = validator.validate_pitch_consistency(df)
        assert issues == []


# ============================================================================
# Tests: validate_pitcher_usage
# ============================================================================


class TestValidatePitcherUsage:
    def test_excessive_batters_faced(self, validator):
        df = pd.DataFrame(
            {
                "game_id": ["G1"] * 45 + ["G2"] * 30,
                "pitcher_id": [100] * 45 + [100] * 30,
            }
        )
        issues = validator.validate_pitcher_usage(df)
        assert len(issues) == 1
        assert "40" in issues[0]

    def test_normal_usage(self, validator):
        df = pd.DataFrame(
            {
                "game_id": ["G1"] * 30 + ["G2"] * 35,
                "pitcher_id": [100] * 30 + [100] * 35,
            }
        )
        issues = validator.validate_pitcher_usage(df)
        assert issues == []

    def test_missing_columns(self, validator):
        df = pd.DataFrame({"unrelated": [1, 2]})
        issues = validator.validate_pitcher_usage(df)
        assert issues == []


# ============================================================================
# Tests: report
# ============================================================================


class TestReport:
    def test_report_structure(self, validator):
        df = pd.DataFrame(
            {
                "release_speed": [95, None],
                "inning": [1, None],
            }
        )
        report = validator.report(df, "my_data")
        assert isinstance(report, dict)
        assert report["dataset"] == "my_data"
        assert report["rows"] == 2
        assert report["cols"] == 2
        assert "issues" in report
        assert "passed" in report

    def test_report_passed_false_when_issues(self, validator):
        df = pd.DataFrame({"release_speed": [95, None, None, None, None, None]})
        report = validator.report(df, "bad")
        assert report["passed"] is False
        assert len(report["issues"]) > 0

    def test_report_passed_true_when_clean(self, validator):
        df = pd.DataFrame({"release_speed": [95, 96, 97]})
        report = validator.report(df, "clean")
        assert report["passed"] is True
        assert report["issues"] == []

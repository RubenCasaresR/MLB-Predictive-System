# =============================================================================
# data_quality.py
# Validación de calidad de datos ETL
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DataQualityValidator:
    NULL_THRESHOLD = 0.05  # 5% max nulls allowed
    RANGE_CHECKS = {
        "release_speed": (60, 110),
        "release_spin_rate": (500, 3500),
        "launch_speed": (0, 125),
        "launch_angle": (-45, 70),
        "temperature": (20, 120),
        "wind_speed": (0, 60),
        "humidity": (0, 100),
        "precipitation_pct": (0, 100),
        "home_score": (0, 50),
        "away_score": (0, 50),
        "inning": (1, 20),
        "home_moneyline_open": (-500, 500),
        "away_moneyline_open": (-500, 500),
    }

    def validate_null_counts(self, df: pd.DataFrame, name: str = "") -> list[str]:
        issues = []
        null_pcts = df.isnull().mean()
        for col, pct in null_pcts.items():
            if pct > self.NULL_THRESHOLD and col in self.RANGE_CHECKS:
                issues.append(f"{name}: {col} tiene {pct:.1%} nulos (>{self.NULL_THRESHOLD:.0%})")
        return issues

    def validate_ranges(self, df: pd.DataFrame, name: str = "") -> list[str]:
        issues = []
        for col, (lo, hi) in self.RANGE_CHECKS.items():
            if col in df.columns:
                out_of_range = df[~df[col].between(lo, hi)][col].dropna()
                if len(out_of_range) > 0:
                    pct = len(out_of_range) / len(df)
                    if pct > 0.01:
                        issues.append(
                            f"{name}: {col} tiene {pct:.1%} valores fuera de rango [{lo}, {hi}]"
                        )
        return issues

    def validate_unique_keys(
        self, df: pd.DataFrame, key_cols: list[str], name: str = ""
    ) -> list[str]:
        issues = []
        dups = df.duplicated(subset=key_cols, keep=False)
        if dups.any():
            count = dups.sum()
            issues.append(f"{name}: {count} duplicados en clave {key_cols}")
        return issues

    def validate_pitch_consistency(self, pitches: pd.DataFrame) -> list[str]:
        issues = []
        if "strike" in pitches.columns and "ball" in pitches.columns:
            both = pitches[(pitches["strike"] == True) & (pitches["ball"] == True)]
            if len(both) > 0:
                issues.append(f"Pitches marcados como strike y ball: {len(both)}")
        return issues

    def validate_pitcher_usage(self, at_bats: pd.DataFrame) -> list[str]:
        issues = []
        if "pitcher_id" in at_bats.columns and "game_id" in at_bats.columns:
            usage = at_bats.groupby(["game_id", "pitcher_id"]).size()
            excessive = usage[usage > 40]
            if len(excessive) > 0:
                issues.append(f"Pitchers con >40 batters faced: {len(excessive)} instancias")
        return issues

    def report(self, df: pd.DataFrame, name: str = "") -> dict:
        issues = []
        issues.extend(self.validate_null_counts(df, name))
        issues.extend(self.validate_ranges(df, name))
        return {
            "dataset": name,
            "rows": len(df),
            "cols": len(df.columns),
            "issues": issues,
            "passed": len(issues) == 0,
        }


# =============================================================================
# MODO LÍNEA DE COMANDOS
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    validator = DataQualityValidator()

    sample = pd.DataFrame(
        {
            "release_speed": [95, 70, 98, None, 102],
            "release_spin_rate": [2400, 200, 2500, 2600, None],
            "inning": [1, 2, 3, 4, 25],
        }
    )

    report = validator.report(sample, "pitches_test")
    print(f"Passed: {report['passed']}")
    for issue in report["issues"]:
        print(f"  Issue: {issue}")

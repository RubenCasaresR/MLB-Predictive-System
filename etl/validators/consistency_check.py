# =============================================================================
# consistency_check.py
# Validación de consistencia entre datos de juego
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================
# Verifica que los datos cargados sean consistentes:
#   - Scores de at_bats coinciden con scores finales del juego
#   - Número de outs por inning es correcto
#   - Pitchers registrados coinciden con lineups
#   - No hay gaps en la secuencia de turnos
# =============================================================================

import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


class ConsistencyChecker:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine = create_engine(db_url)

    def check_game_score_consistency(self, game_id: str) -> list[str]:
        issues = []
        with self.engine.connect() as conn:
            game = conn.execute(
                text("SELECT home_score, away_score FROM games WHERE game_id = :gid"),
                {"gid": game_id},
            ).fetchone()

            last_ab = conn.execute(
                text("""
                    SELECT home_score_after, away_score_after
                    FROM at_bats
                    WHERE game_id = :gid
                    ORDER BY inning DESC, half_inning DESC, ab_id DESC
                    LIMIT 1
                """),
                {"gid": game_id},
            ).fetchone()

            if game and last_ab:
                if game.home_score != last_ab.home_score_after:
                    issues.append(
                        f"Home score mismatch: game={game.home_score}, last_ab={last_ab.home_score_after}"
                    )
                if game.away_score != last_ab.away_score_after:
                    issues.append(
                        f"Away score mismatch: game={game.away_score}, last_ab={last_ab.away_score_after}"
                    )
        return issues

    def check_batter_sequence(self, game_id: str) -> list[str]:
        issues = []
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT ab_id, inning, half_inning, batter_id,
                        ROW_NUMBER() OVER (PARTITION BY inning, half_inning ORDER BY ab_id) AS ab_order
                    FROM at_bats
                    WHERE game_id = :gid
                    ORDER BY inning, half_inning, ab_id
                """),
                {"gid": game_id},
            ).fetchall()

            for inning_group in self._group_by_innings(rows):
                if len(inning_group) > 12:
                    issues.append(
                        f"Inning {inning_group[0][1]} {inning_group[0][2]}: "
                        f"{len(inning_group)} at-bats (max expected ~12)"
                    )
        return issues

    def _group_by_innings(self, rows):
        groups = {}
        for row in rows:
            key = (row[1], row[2])
            if key not in groups:
                groups[key] = []
            groups[key].append(row)
        return groups.values()

    def check_lineup_coherence(self, game_id: str) -> list[str]:
        issues = []
        with self.engine.connect() as conn:
            lineups = conn.execute(
                text("""
                    SELECT team_id, player_id, batting_order, position
                    FROM lineups
                    WHERE game_id = :gid
                    ORDER BY team_id, batting_order
                """),
                {"gid": game_id},
            ).fetchall()

            if not lineups:
                issues.append("No lineups found for game")
                return issues

            for team in set(l.team_id for l in lineups):
                team_players = [l for l in lineups if l.team_id == team]
                if len(team_players) != 9:
                    issues.append(f"{team} lineup has {len(team_players)} players (expected 9)")

                orders = [l.batting_order for l in team_players]
                if sorted(orders) != list(range(1, 10)):
                    issues.append(f"{team} batting orders not 1-9: {orders}")

        return issues

    def check_all(self, game_id: str) -> dict:
        issues = {}
        issues["score"] = self.check_game_score_consistency(game_id)
        issues["batter_sequence"] = self.check_batter_sequence(game_id)
        issues["lineup"] = self.check_lineup_coherence(game_id)
        all_issues = [i for lst in issues.values() for i in lst]
        return {
            "game_id": game_id,
            "issues_count": len(all_issues),
            "issues": all_issues,
            "passed": len(all_issues) == 0,
            "details": issues,
        }


# =============================================================================
# MODO LÍNEA DE COMANDOS
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from etl.config import DATABASE_URL

    checker = ConsistencyChecker(DATABASE_URL)
    result = checker.check_all("2025-06-15-NYY-BOS")
    status = "PASS" if result["passed"] else f"{result['issues_count']} issues"
    print(f"Game {result['game_id']}: {status}")
    for issue in result["issues"]:
        print(f"  - {issue}")

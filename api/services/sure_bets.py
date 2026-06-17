import logging
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import text

from api.database import get_async_engine
from api.models.sure_bet_models import SureBetRecommendation, SureBetsResponse

logger = logging.getLogger(__name__)

TIER_MUY_SEGURA = 75
TIER_SEGURA = 60
TIER_RIESGOSA = 40

MAX_REASONS = 8


def _vig_free_prob(over_odds: int, under_odds: int) -> tuple[float, float]:
    """Convierte odds americanos a probabilidades libres de vig."""

    def to_prob(odds):
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return -odds / (-odds + 100)

    p_over = to_prob(over_odds)
    p_under = to_prob(under_odds)
    total = p_over + p_under
    return p_over / total, p_under / total


def _normal_cdf(x, mean, std):
    """Aproximación de la CDF normal."""
    return 0.5 * (1 + math.erf((x - mean) / (std * math.sqrt(2))))


class SureBetService:
    def __init__(self):
        self.tz_name = os.getenv("TIMEZONE", "America/Mexico_City")
        self.target_tz = ZoneInfo(self.tz_name)

    async def get_sure_bets(self) -> SureBetsResponse:
        games = await self._get_upcoming_games()
        all_recs: list[SureBetRecommendation] = []

        for game in games:
            gid = game["game_id"]
            sim = await self._get_simulation(gid)
            market = await self._get_market(gid)
            pitchers = await self._get_pitcher_data(
                gid,
                game["home_team_id"],
                game["away_team_id"],
                game.get("home_pitcher_id"),
                game.get("away_pitcher_id"),
            )
            teams = await self._get_team_data(game["home_team_id"], game["away_team_id"])
            weather = await self._get_weather(gid)

            if sim and market:
                ml_recs = self._evaluate_moneyline(game, sim, market, pitchers, teams, weather)
                all_recs.extend(ml_recs)
                total_recs = self._evaluate_totals(game, sim, market, pitchers, teams, weather)
                all_recs.extend(total_recs)

        all_recs.sort(key=lambda r: r.safety_score, reverse=True)
        for i, rec in enumerate(all_recs):
            rec.rank = i + 1

        result = SureBetsResponse(generated_at=datetime.now(self.target_tz))
        for rec in all_recs:
            if rec.safety_score >= TIER_MUY_SEGURA:
                result.muy_seguras.append(rec)
            elif rec.safety_score >= TIER_SEGURA:
                result.seguras.append(rec)
            elif rec.safety_score >= TIER_RIESGOSA:
                result.riesgosas.append(rec)

        return result

    async def _get_upcoming_games(self) -> list[dict]:
        from datetime import date as d

        today = d.today().isoformat()
        async_engine = get_async_engine()
        async with async_engine.connect() as conn:
            result = await conn.execute(
                text("""
                SELECT g.game_id, g.game_date, g.home_team_id, g.away_team_id,
                       g.home_probable_pitcher, g.away_probable_pitcher,
                       g.status, g.start_time_et,
                       g.home_rest_days, g.away_rest_days,
                       g.home_travel_miles, g.away_travel_miles,
                       g.home_tz_crossings, g.away_tz_crossings
                FROM games g
                WHERE g.game_date >= :today
                  AND (g.status IS NULL OR g.status NOT IN ('Final','FINAL','Postponed','Cancelled'))
                ORDER BY g.start_time_et
                LIMIT 15
            """),
                {"today": today},
            )
            rows = result.fetchall()
        return [
            {
                "game_id": r[0],
                "game_date": str(r[1]) if r[1] else "",
                "home_team_id": r[2] or "",
                "away_team_id": r[3] or "",
                "home_pitcher_id": r[4],
                "away_pitcher_id": r[5],
                "status": r[6] or "",
                "start_time": str(r[7]) if r[7] else "",
                "home_rest_days": r[8] if r[8] else 0,
                "away_rest_days": r[9] if r[9] else 0,
                "home_travel_miles": r[10] if r[10] else 0,
                "away_travel_miles": r[11] if r[11] else 0,
                "home_tz_crossings": r[12] if r[12] else 0,
                "away_tz_crossings": r[13] if r[13] else 0,
            }
            for r in rows
        ]

    async def _get_simulation(self, game_id: str) -> dict | None:
        async_engine = get_async_engine()
        async with async_engine.connect() as conn:
            result = await conn.execute(
                text("""
                SELECT home_win_prob, away_win_prob,
                       mean_home_runs, mean_away_runs,
                       std_home_runs, std_away_runs,
                       extra_innings_prob, walkoff_prob, n_iterations
                FROM simulation_results
                WHERE game_id = :gid
            """),
                {"gid": game_id},
            )
            row = result.fetchone()
        if not row:
            return None
        return {
            "home_win_prob": float(row[0]),
            "away_win_prob": float(row[1]),
            "mean_home_runs": float(row[2]) if row[2] else 0,
            "mean_away_runs": float(row[3]) if row[3] else 0,
            "std_home_runs": float(row[4]) if row[4] else 0,
            "std_away_runs": float(row[5]) if row[5] else 0,
            "extra_innings_prob": float(row[6]) if row[6] else 0,
            "walkoff_prob": float(row[7]) if row[7] else 0,
            "n_iterations": row[8] or 10000,
        }

    async def _get_market(self, game_id: str) -> dict | None:
        async_engine = get_async_engine()
        async with async_engine.connect() as conn:
            result = await conn.execute(
                text("""
                SELECT home_moneyline_close, away_moneyline_close,
                       total_close, total_over_odds_close, total_under_odds_close,
                       sharp_money_flag, rlm_flag
                FROM market_lines
                WHERE game_id = :gid
                ORDER BY recorded_at DESC
                LIMIT 1
            """),
                {"gid": game_id},
            )
            row = result.fetchone()
        if not row:
            return None
        return {
            "home_moneyline": row[0],
            "away_moneyline": row[1],
            "total_close": float(row[2]) if row[2] else None,
            "total_over_odds": row[3],
            "total_under_odds": row[4],
            "sharp_money_flag": bool(row[5]) if row[5] else False,
            "rlm_flag": bool(row[6]) if row[6] else False,
        }

    async def _get_pitcher_data(
        self, game_id: str, home_team: str, away_team: str, home_pitcher_id, away_pitcher_id
    ) -> dict:
        result = {"home": {}, "away": {}}
        async_engine = get_async_engine()
        for side, pid, team in [
            ("home", home_pitcher_id, home_team),
            ("away", away_pitcher_id, away_team),
        ]:
            if not pid:
                continue
            try:
                pid_int = int(pid)
            except (ValueError, TypeError):
                result[side] = {"fatigue_score": None, "fip_30d": None, "avg_velo_30d": None}
                continue
            async with async_engine.connect() as conn:
                db_result = await conn.execute(
                    text("""
                    SELECT fatigue_score, fip_30d, avg_velo_30d, k_per_9_30d
                    FROM player_rolling_stats
                    WHERE player_id = :pid
                    ORDER BY as_of_date DESC
                    LIMIT 1
                """),
                    {"pid": pid_int},
                )
                row = db_result.fetchone()
            if row:
                result[side] = {
                    "fatigue_score": float(row[0]) if row[0] else None,
                    "fip_30d": float(row[1]) if row[1] else None,
                    "avg_velo_30d": float(row[2]) if row[2] else None,
                    "k_per_9_30d": float(row[3]) if row[3] else None,
                }
        return result

    async def _get_team_data(self, home_team: str, away_team: str) -> dict:
        result = {"home": {}, "away": {}}
        async_engine = get_async_engine()
        for side, team in [("home", home_team), ("away", away_team)]:
            async with async_engine.connect() as conn:
                db_result = await conn.execute(
                    text("""
                    SELECT bullpen_era_30d, bullpen_fip_30d, record_last_10, run_diff_30d
                    FROM team_rolling_stats
                    WHERE team_id = :tid
                    ORDER BY as_of_date DESC
                    LIMIT 1
                """),
                    {"tid": team},
                )
                row = db_result.fetchone()
            if row:
                result[side] = {
                    "bullpen_era_30d": float(row[0]) if row[0] else None,
                    "bullpen_fip_30d": float(row[1]) if row[1] else None,
                    "record_last_10": row[2] or "",
                    "run_diff_30d": float(row[3]) if row[3] else None,
                }
        return result

    async def _get_weather(self, game_id: str) -> dict | None:
        async_engine = get_async_engine()
        async with async_engine.connect() as conn:
            result = await conn.execute(
                text("""
                SELECT temperature, wind_speed, wind_direction, precipitation_pct, condition
                FROM weather_hourly
                WHERE game_id = :gid
                ORDER BY forecast_hour
                LIMIT 1
            """),
                {"gid": game_id},
            )
            row = result.fetchone()
        if not row:
            return None
        return {
            "temperature": float(row[0]) if row[0] else None,
            "wind_speed": float(row[1]) if row[1] else None,
            "wind_direction": row[2] or "",
            "precipitation_pct": float(row[3]) if row[3] else None,
            "condition": row[4] or "",
        }

    def _score_edge(self, edge_pct: float) -> int:
        if edge_pct >= 10:
            return 30
        if edge_pct >= 7:
            return 25
        if edge_pct >= 5:
            return 20
        if edge_pct >= 3:
            return 10
        return 0

    def _score_sim_gap(self, gap_pct: float) -> int:
        if gap_pct >= 30:
            return 15
        if gap_pct >= 20:
            return 10
        if gap_pct >= 10:
            return 5
        return 0

    def _score_sharp(self, sharp: bool, rlm: bool) -> int:
        s = 0
        if sharp:
            s += 10
        if rlm:
            s += 5
        return s

    def _score_pitcher_adv(self, fat_rec: float | None, fat_opp: float | None) -> int:
        if fat_rec is None or fat_opp is None:
            return 0
        diff = fat_opp - fat_rec
        if diff >= 0.20:
            return 15
        if diff >= 0.10:
            return 10
        if diff >= 0.05:
            return 5
        return 0

    def _score_bullpen(self, bull_rec: float | None, bull_opp: float | None) -> int:
        if bull_rec is None or bull_opp is None:
            return 0
        diff = bull_opp - bull_rec
        if diff >= 1.5:
            return 10
        if diff >= 0.8:
            return 6
        if diff >= 0.3:
            return 3
        return 0

    def _score_rest(
        self,
        rest_rec: int,
        rest_opp: int,
        tz_rec: int,
        tz_opp: int,
        travel_rec: int,
        travel_opp: int,
    ) -> int:
        s = 0
        rest_diff = rest_rec - rest_opp
        if rest_diff >= 2:
            s += 5
        elif rest_diff >= 1:
            s += 3

        tz_diff = tz_opp - tz_rec
        if tz_diff >= 2:
            s += 3
        elif tz_diff >= 1:
            s += 2

        travel_diff = travel_opp - travel_rec
        if travel_diff >= 1000:
            s += 2
        return s

    def _score_weather_ml(self, weather: dict | None) -> int:
        if not weather:
            return 0
        s = 0
        precip = weather.get("precipitation_pct")
        if precip is not None and precip < 20:
            s += 2
        wind = weather.get("wind_speed")
        if wind is not None and wind < 15:
            s += 2
        temp = weather.get("temperature")
        if temp is not None and 60 <= temp <= 85:
            s += 1
        return s

    def _score_weather_total(self, weather: dict | None, direction: str) -> int:
        """direction: 'OVER' o 'UNDER'"""
        if not weather:
            return 0
        s = 0
        wind_dir = (weather.get("wind_direction") or "").upper()
        wind = weather.get("wind_speed") or 0
        temp = weather.get("temperature")
        precip = weather.get("precipitation_pct") or 0

        if direction == "OVER":
            if wind_dir in ("OUT", "LTR", "RTL") and wind >= 10:
                s += 10
            elif wind_dir in ("OUT", "LTR", "RTL"):
                s += 5
            if temp is not None and temp >= 85:
                s += 5
            elif temp is not None and temp >= 75:
                s += 3
            if precip < 20:
                s += 3
        else:
            if wind_dir in ("IN",) and wind >= 10:
                s += 10
            elif wind_dir in ("IN",):
                s += 5
            if temp is not None and temp <= 50:
                s += 5
            elif temp is not None and temp <= 60:
                s += 3
            if precip >= 50:
                s += 3

        return s

    def _score_pitching_total(self, pitchers: dict) -> tuple[int, str]:
        """Retorna (score, direccion: 'OVER' o 'UNDER')"""
        fip_h = (pitchers.get("home", {}) or {}).get("fip_30d")
        fip_a = (pitchers.get("away", {}) or {}).get("fip_30d")
        if fip_h is None or fip_a is None:
            return 0, "OVER"
        avg_fip = (fip_h + fip_a) / 2
        if avg_fip >= 4.5:
            return 10, "OVER"
        if avg_fip >= 4.0:
            return 6, "OVER"
        if avg_fip <= 3.2:
            return 6, "UNDER"
        if avg_fip <= 3.6:
            return 3, "UNDER"
        return 0, "OVER"

    def _score_sim_total(self, mean_total: float, line: float) -> tuple[int, str, float]:
        """Retorna (score, direccion, gap_en_carreras)"""
        gap = mean_total - line
        abs_gap = abs(gap)
        if abs_gap >= 1.5:
            return 20, "OVER" if gap > 0 else "UNDER", abs_gap
        if abs_gap >= 1.0:
            return 14, "OVER" if gap > 0 else "UNDER", abs_gap
        if abs_gap >= 0.5:
            return 8, "OVER" if gap > 0 else "UNDER", abs_gap
        return 0, "OVER", abs_gap

    def _generate_ml_reasons(
        self,
        game: dict,
        team: str,
        opp: str,
        edge_pct: float,
        win_prob: float,
        market: dict,
        pitchers: dict,
        teams_data: dict,
        weather: dict | None,
    ) -> list[str]:
        reasons = []
        if edge_pct >= 5:
            reasons.append(
                f"Edge del {edge_pct:.1f}% sobre la cuota real → valor positivo significativo"
            )
        elif edge_pct >= 3:
            reasons.append(f"Edge del {edge_pct:.1f}% indica una leve ventaja sobre el mercado")

        if win_prob >= 65:
            reasons.append(
                f"Modelo Monte Carlo: {team} gana el {win_prob:.0f}% de las simulaciones"
            )
        elif win_prob >= 55:
            reasons.append(
                f"Modelo Monte Carlo: {team} gana el {win_prob:.0f}% de las simulaciones"
            )

        if market.get("sharp_money_flag"):
            reasons.append(
                f"Dinero sharp (profesional) respalda esta apuesta → señal de valor oculto"
            )
        if market.get("rlm_flag"):
            reasons.append(f"RLM detectado: la línea se mueve en dirección contraria al público")

        pit_rec = pitchers.get(team.lower(), {})
        pit_opp = pitchers.get(opp.lower(), {})
        fat_rec = pit_rec.get("fatigue_score")
        fat_opp = pit_opp.get("fatigue_score")
        if fat_rec is not None and fat_opp is not None:
            diff = fat_opp - fat_rec
            if diff >= 0.20:
                reasons.append(
                    f"Abridor de {team} descansado (fatiga {fat_rec:.2f}) vs {opp} muy fatigado ({fat_opp:.2f})"
                )
            elif diff >= 0.10:
                reasons.append(
                    f"Ventaja en fatiga de abridores: {team} ({fat_rec:.2f}) vs {opp} ({fat_opp:.2f})"
                )

        fip_rec = pit_rec.get("fip_30d")
        fip_opp = pit_opp.get("fip_30d")
        if fip_rec is not None and fip_opp is not None and fip_rec < fip_opp:
            reasons.append(f"Abridor de {team} tiene mejor FIP ({fip_rec:.2f} vs {fip_opp:.2f})")

        velo_rec = pit_rec.get("avg_velo_30d")
        velo_opp = pit_opp.get("avg_velo_30d")
        if velo_rec is not None and velo_opp is not None and velo_rec > velo_opp:
            reasons.append(
                f"Abridor de {team} promedia más velocidad ({velo_rec:.1f} mph vs {velo_opp:.1f})"
            )

        bull_rec = (teams_data.get(team.lower(), {}) or {}).get("bullpen_era_30d")
        bull_opp = (teams_data.get(opp.lower(), {}) or {}).get("bullpen_era_30d")
        if bull_rec is not None and bull_opp is not None and bull_rec < bull_opp:
            diff = bull_opp - bull_rec
            if diff >= 1.0:
                reasons.append(
                    f"Bullpen de {team} significativamente mejor (ERA {bull_rec:.2f} vs {bull_opp:.2f})"
                )
            else:
                reasons.append(f"Bullpen de {team} superior (ERA {bull_rec:.2f} vs {bull_opp:.2f})")

        rest_rec = game.get(f"{team.lower()}_rest_days", 0)
        rest_opp = game.get(f"{opp.lower()}_rest_days", 0)
        if rest_rec > rest_opp:
            reasons.append(f"{team} tiene {rest_rec} días de descanso vs {rest_opp} de {opp}")

        tz_rec = game.get(f"{team.lower()}_tz_crossings", 0)
        tz_opp = game.get(f"{opp.lower()}_tz_crossings", 0)
        if tz_opp > tz_rec:
            reasons.append(f"{opp} viajó a través de {tz_opp} husos horarios (fatiga de viaje)")

        if weather:
            temp = weather.get("temperature")
            wind = weather.get("wind_speed")
            precip = weather.get("precipitation_pct")
            cond = weather.get("condition", "")
            parts = []
            if temp is not None:
                parts.append(f"{temp:.0f}°F")
            if wind is not None:
                parts.append(f"viento {wind:.0f} mph")
            if precip is not None and precip < 20:
                parts.append("sin lluvia")
            if parts:
                reasons.append(
                    f"Clima: {' · '.join(parts)} → condiciones neutrales"
                    if precip is None or precip < 20
                    else f"Clima: {' · '.join(parts)}"
                )

        return reasons[:MAX_REASONS]

    def _generate_total_reasons(
        self,
        game: dict,
        direction: str,
        market: dict,
        edge_pct: float,
        mean_total: float,
        line: float,
        pitchers: dict,
        weather: dict | None,
    ) -> list[str]:
        reasons = []
        if edge_pct >= 5:
            reasons.append(
                f"Edge del {edge_pct:.1f}% sobre la línea de {line} → valor significativo"
            )
        elif edge_pct >= 3:
            reasons.append(f"Edge del {edge_pct:.1f}% sobre la línea de {line}")

        gap = mean_total - line
        label = "supera" if gap > 0 else "está por debajo de"
        reasons.append(
            f"El modelo proyecta {mean_total:.1f} carreras totales ({label} la línea de {line})"
        )

        if direction == "OVER":
            wind_dir = (weather.get("wind_direction") or "").upper() if weather else ""
            wind = weather.get("wind_speed", 0) if weather else 0
            if wind_dir in ("OUT", "LTR", "RTL") and wind >= 10:
                reasons.append(
                    f"Viento de {wind:.0f} mph hacia fuera del estadio → favorece carreras"
                )
            temp = weather.get("temperature") if weather else None
            if temp is not None and temp >= 85:
                reasons.append(f"Temperatura alta ({temp:.0f}°F) → el bateo se beneficia")
        else:
            wind_dir = (weather.get("wind_direction") or "").upper() if weather else ""
            wind = weather.get("wind_speed", 0) if weather else 0
            if wind_dir == "IN" and wind >= 10:
                reasons.append(
                    f"Viento de {wind:.0f} mph hacia dentro del estadio → limita las carreras"
                )
            temp = weather.get("temperature") if weather else None
            if temp is not None and temp <= 50:
                reasons.append(f"Temperatura baja ({temp:.0f}°F) → el bateo se perjudica")

        fip_h = (pitchers.get("home", {}) or {}).get("fip_30d")
        fip_a = (pitchers.get("away", {}) or {}).get("fip_30d")
        if fip_h is not None and fip_a is not None:
            avg_fip = (fip_h + fip_a) / 2
            if direction == "OVER" and avg_fip >= 4.0:
                reasons.append(
                    f"Abridores con FIP combinado alto ({avg_fip:.2f}) → más carreras esperadas"
                )
            elif direction == "UNDER" and avg_fip <= 3.5:
                reasons.append(
                    f"Abridores con FIP combinado bajo ({avg_fip:.2f}) → menos carreras esperadas"
                )

        if market.get("sharp_money_flag"):
            reasons.append(f"Dinero sharp respalda esta señal en el mercado de totales")

        return reasons[:MAX_REASONS]

    def _evaluate_moneyline(
        self,
        game: dict,
        sim: dict,
        market: dict,
        pitchers: dict,
        teams_data: dict,
        weather: dict | None,
    ) -> list[SureBetRecommendation]:
        recs = []
        home = game["home_team_id"]
        away = game["away_team_id"]
        home_ml = market.get("home_moneyline")
        away_ml = market.get("away_moneyline")
        home_prob = sim.get("home_win_prob", 0)
        away_prob = sim.get("away_win_prob", 0)

        if not home_ml or not away_ml:
            return []

        imp_home, imp_away = _vig_free_prob(home_ml, away_ml)
        edge_home = (home_prob - imp_home) * 100
        edge_away = (away_prob - imp_away) * 100

        for team, opp, edge_pct, odds, win_prob in [
            (home, away, edge_home, home_ml, home_prob),
            (away, home, edge_away, away_ml, away_prob),
        ]:
            if edge_pct < 2:
                continue

            score = 0
            score += self._score_edge(edge_pct)
            gap = abs(home_prob - away_prob) * 100
            score += self._score_sim_gap(gap)

            sharp = market.get("sharp_money_flag", False)
            rlm = market.get("rlm_flag", False)
            score += self._score_sharp(sharp, rlm)

            pit_rec = pitchers.get(team.lower(), {})
            pit_opp = pitchers.get(opp.lower(), {})
            score += self._score_pitcher_adv(
                pit_rec.get("fatigue_score"), pit_opp.get("fatigue_score")
            )

            td_rec = teams_data.get(team.lower(), {})
            td_opp = teams_data.get(opp.lower(), {})
            score += self._score_bullpen(
                td_rec.get("bullpen_era_30d"), td_opp.get("bullpen_era_30d")
            )

            rest_rec = game.get(f"{team.lower()}_rest_days", 0)
            rest_opp = game.get(f"{opp.lower()}_rest_days", 0)
            tz_rec = game.get(f"{team.lower()}_tz_crossings", 0)
            tz_opp = game.get(f"{opp.lower()}_tz_crossings", 0)
            travel_rec = game.get(f"{team.lower()}_travel_miles", 0)
            travel_opp = game.get(f"{opp.lower()}_travel_miles", 0)
            score += self._score_rest(rest_rec, rest_opp, tz_rec, tz_opp, travel_rec, travel_opp)

            score += self._score_weather_ml(weather)

            reasons = self._generate_ml_reasons(
                game, team, opp, edge_pct, win_prob, market, pitchers, teams_data, weather
            )

            label = (
                "Muy Segura"
                if score >= TIER_MUY_SEGURA
                else "Segura"
                if score >= TIER_SEGURA
                else "Riesgosa"
                if score >= TIER_RIESGOSA
                else ""
            )

            stats = {
                "edge_pct": round(edge_pct, 1),
                "win_prob": round(win_prob, 1),
                "opp_win_prob": round(100 - win_prob, 1),
                "odds": odds,
                "sharp_money": sharp,
                "rlm": rlm,
                "pitcher_fatigue_own": pit_rec.get("fatigue_score"),
                "pitcher_fatigue_opp": pit_opp.get("fatigue_score"),
                "pitcher_fip_own": pit_rec.get("fip_30d"),
                "pitcher_fip_opp": pit_opp.get("fip_30d"),
                "bullpen_era_own": td_rec.get("bullpen_era_30d"),
                "bullpen_era_opp": td_opp.get("bullpen_era_30d"),
                "rest_days_own": rest_rec,
                "rest_days_opp": rest_opp,
            }

            recs.append(
                SureBetRecommendation(
                    rank=0,
                    game_id=game["game_id"],
                    home_team=home,
                    away_team=away,
                    recommended_team=team,
                    market_type="moneyline",
                    odds=odds,
                    safety_score=score,
                    safety_label=label,
                    edge_pct=round(edge_pct, 1),
                    win_prob=round(win_prob, 1),
                    reasons=reasons,
                    key_stats=stats,
                )
            )

        return recs

    def _evaluate_totals(
        self,
        game: dict,
        sim: dict,
        market: dict,
        pitchers: dict,
        teams_data: dict,
        weather: dict | None,
    ) -> list[SureBetRecommendation]:
        recs = []
        line = market.get("total_close")
        over_odds = market.get("total_over_odds")
        under_odds = market.get("total_under_odds")
        if not line or not over_odds or not under_odds:
            return []

        mean_home = sim.get("mean_home_runs", 0)
        mean_away = sim.get("mean_away_runs", 0)
        std_home = sim.get("std_home_runs", 0.1)
        std_away = sim.get("std_away_runs", 0.1)
        mean_total = mean_home + mean_away
        std_total = math.sqrt(std_home**2 + std_away**2)

        if std_total < 0.01:
            std_total = 0.01

        prob_over = 1 - _normal_cdf(line, mean_total, std_total)
        prob_under = _normal_cdf(line, mean_total, std_total)

        imp_over, imp_under = _vig_free_prob(over_odds, under_odds)
        edge_over = (prob_over - imp_over) * 100
        edge_under = (prob_under - imp_under) * 100

        for direction, edge_pct, odds in [
            ("OVER", edge_over, over_odds),
            ("UNDER", edge_under, under_odds),
        ]:
            if edge_pct < 2:
                continue

            score = 0
            score += self._score_edge(edge_pct)

            sim_score, sim_dir, gap = self._score_sim_total(mean_total, line)
            if sim_dir == direction:
                score += sim_score
            else:
                score += max(0, sim_score - 5)

            score += self._score_weather_total(weather, direction)

            pitch_score, pitch_dir = self._score_pitching_total(pitchers)
            if pitch_dir == direction:
                score += pitch_score

            sharp = market.get("sharp_money_flag", False)
            if sharp:
                score += 5

            reasons = self._generate_total_reasons(
                game, direction, market, edge_pct, mean_total, line, pitchers, weather
            )

            label = (
                "Muy Segura"
                if score >= TIER_MUY_SEGURA
                else "Segura"
                if score >= TIER_SEGURA
                else "Riesgosa"
                if score >= TIER_RIESGOSA
                else ""
            )

            stats = {
                "edge_pct": round(edge_pct, 1),
                "line": line,
                "mean_total": round(mean_total, 2),
                "prob_over": round(prob_over * 100, 1),
                "prob_under": round(prob_under * 100, 1),
                "total_over_odds": over_odds,
                "total_under_odds": under_odds,
                "sharp_money": sharp,
                "wind_direction": (weather or {}).get("wind_direction", ""),
                "wind_speed": (weather or {}).get("wind_speed"),
                "temperature": (weather or {}).get("temperature"),
            }

            recs.append(
                SureBetRecommendation(
                    rank=0,
                    game_id=game["game_id"],
                    home_team=game["home_team_id"],
                    away_team=game["away_team_id"],
                    recommended_team=None,
                    market_type=f"{direction}_{line}",
                    odds=odds,
                    safety_score=score,
                    safety_label=label,
                    edge_pct=round(edge_pct, 1),
                    win_prob=None,
                    reasons=reasons,
                    key_stats=stats,
                )
            )

        return recs

# =============================================================================
# monte_carlo_simulator.py
# Motor de Simulación Monte Carlo para MLB
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================
# Simula 10,000 iteraciones de un juego de béisbol turno por turno.
# Cada plate appearance se modela como variable aleatoria categórica
# con probabilidades ajustadas por:
#   - Platoon splits (bateador zurdo vs. pitcher derecho)
#   - Park Factors (HR, singles)
#   - Fatiga del pitcher (pitch count > 75, velo/spin drop)
#   - Calidad del lanzador (K%, BB%)
#
# Salida: Probabilidad real de victoria para cada equipo,
#         distribución de carrés, y recomendaciones EV+.
# =============================================================================

import math
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# TIPOS Y ENUMS
# ============================================================================

class PAOutcome(Enum):
    OUT          = "out"
    SINGLE       = "single"
    DOUBLE       = "double"
    TRIPLE       = "triple"
    HOME_RUN     = "home_run"
    WALK         = "walk"
    HIT_BY_PITCH = "hit_by_pitch"
    SACRIFICE    = "sacrifice"
    ERROR        = "error"
    FIELDERS_CHOICE = "fielders_choice"


@dataclass
class BatterState:
    player_id: int
    name: str
    bats: str
    woba_vs_rhp: float = 0.310
    woba_vs_lhp: float = 0.290
    k_rate: float = 0.220
    bb_rate: float = 0.085
    hr_rate: float = 0.030
    groundball_rate: float = 0.440
    flyball_rate: float = 0.350


@dataclass
class PitcherState:
    player_id: int
    name: str
    throws: str
    k_rate: float = 0.225
    bb_rate: float = 0.080
    hr_rate: float = 0.030
    groundball_rate: float = 0.430
    whiff_pct: float = 0.110
    avg_velo: float = 93.0
    avg_spin: float = 2200.0
    fatigue_factor: float = 1.0
    pitch_count: int = 0

    def apply_fatigue(self, pitches_thrown: int):
        self.pitch_count = pitches_thrown
        if pitches_thrown > 75:
            excess = pitches_thrown - 75
            decay = excess * 0.003
            self.fatigue_factor = max(0.75, 1.0 - decay)
        else:
            self.fatigue_factor = 1.0


@dataclass
class GameState:
    home_score: int = 0
    away_score: int = 0
    inning: int = 1
    half: str = "top"
    outs: int = 0
    bases: Tuple[bool, bool, bool] = (False, False, False)
    home_pitch_count: int = 0
    away_pitch_count: int = 0
    is_final: bool = False
    is_walkoff: bool = False

    def reset_half(self):
        self.outs = 0
        self.bases = (False, False, False)

    def switch_half(self):
        if self.half == "top":
            self.half = "bot"
            self.inning += 0
        else:
            self.half = "top"
            self.inning += 1
        self.reset_half()


@dataclass
class SimulationResult:
    home_win_prob: float
    away_win_prob: float
    mean_home_runs: float
    mean_away_runs: float
    std_home_runs: float
    std_away_runs: float
    home_run_distribution: Dict[int, float]
    away_run_distribution: Dict[int, float]
    n_iterations: int
    home_runs_array: np.ndarray
    away_runs_array: np.ndarray
    walkoff_prob: float = 0.0
    extra_innings_prob: float = 0.0

    @staticmethod
    def american_to_implied(odds: int) -> float:
        if odds > 0:
            return 100.0 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)

    @staticmethod
    def implied_to_american(prob: float) -> int:
        if prob >= 0.5:
            return -int(round((100 * prob) / (1 - prob)))
        else:
            return int(round((100 * (1 - prob)) / prob))

    def kelly_fraction(self, prob: float, odds: int, fraction: float = 0.25) -> float:
        if odds > 0:
            decimal_odds = (odds / 100.0) + 1
        else:
            decimal_odds = (100.0 / abs(odds)) + 1
        b = decimal_odds - 1
        if b <= 0:
            return 0.0
        kelly = (prob * (b + 1) - 1) / b
        kelly = max(0.0, min(kelly * fraction, 0.05))
        return kelly

    def get_ev_positive_bets(
        self, home_odds: int, away_odds: int, min_ev: float = 0.02
    ) -> Dict:
        home_implied_raw = self.american_to_implied(home_odds)
        away_implied_raw = self.american_to_implied(away_odds)
        total_implied = home_implied_raw + away_implied_raw
        home_implied = home_implied_raw / total_implied
        away_implied = away_implied_raw / total_implied

        home_ev = self.home_win_prob - home_implied
        away_ev = self.away_win_prob - away_implied

        result = {
            "home_ev": round(home_ev, 4),
            "away_ev": round(away_ev, 4),
            "home_implied": round(home_implied, 4),
            "away_implied": round(away_implied, 4),
            "home_real_prob": round(self.home_win_prob, 4),
            "away_real_prob": round(self.away_win_prob, 4),
            "recommendation": "no_bet",
            "kelly_fraction": 0.0,
            "expected_value": 0.0,
        }

        if home_ev >= min_ev and home_ev > away_ev:
            result["recommendation"] = "home"
            result["kelly_fraction"] = round(
                self.kelly_fraction(self.home_win_prob, home_odds), 4
            )
            result["expected_value"] = round(home_ev, 4)
        elif away_ev >= min_ev and away_ev > home_ev:
            result["recommendation"] = "away"
            result["kelly_fraction"] = round(
                self.kelly_fraction(self.away_win_prob, away_odds), 4
            )
            result["expected_value"] = round(away_ev, 4)

        return result


# ============================================================================
# NÚCLEO DE LA SIMULACIÓN
# ============================================================================

class MonteCarloMLBSimulator:
    MAX_INNINGS = 9
    MAX_EXTRA_INNINGS = 15
    OUTS_PER_HALF = 3

    # Probabilidades de transición de bases (basadas en Statcast 2015-2024)
    BASE_ADVANCE_PROBS = {
        "single": {1: 0.35, 2: 0.45, 3: 0.85},
        "double": {1: 0.75, 2: 0.90, 3: 0.95},
        "triple": {1: 0.95, 2: 0.98, 3: 1.00},
    }

    # Promedios de liga MLB 2024 para ajuste
    LEAGUE_AVG_K_RATE = 0.225
    LEAGUE_AVG_BB_RATE = 0.085
    LEAGUE_AVG_HR_RATE = 0.030

    def __init__(self, seed: Optional[int] = None):
        self.rng = np.random.default_rng(seed)
        logger.info(f"MonteCarloMLBSimulator initialized (seed={seed})")

    # ------------------------------------------------------------------
    # MÉTODO PRINCIPAL
    # ------------------------------------------------------------------

    def run_simulation(
        self,
        home_lineup: List[BatterState],
        away_lineup: List[BatterState],
        home_pitcher: PitcherState,
        away_pitcher: PitcherState,
        park_factor_hr: float = 1.0,
        park_factor_single: float = 1.0,
        park_factor_k: float = 1.0,
        temperature_f: float = 70.0,
        wind_speed: float = 0.0,
        wind_direction: str = "NONE",
        umpire_cs_rate: float = 0.0,
        home_bullpen_era: float = 4.50,
        away_bullpen_era: float = 4.50,
        home_rest_days: int = 4,
        away_rest_days: int = 4,
        home_travel_miles: int = 0,
        away_travel_miles: int = 0,
        home_tz_crossings: int = 0,
        away_tz_crossings: int = 0,
        n_iterations: int = 10000,
        progress_callback: Optional[Callable] = None,
    ) -> SimulationResult:

        home_probs = [
            self._build_batter_probs(
                b, away_pitcher, park_factor_hr, park_factor_single, park_factor_k,
                temperature_f=temperature_f,
                wind_speed=wind_speed,
                wind_direction=wind_direction,
                umpire_cs_rate=umpire_cs_rate,
                batter_rest_days=home_rest_days,
                batter_travel_miles=home_travel_miles,
                batter_tz_crossings=home_tz_crossings,
                is_home=True,
            )
            for b in home_lineup
        ]
        away_probs = [
            self._build_batter_probs(
                b, home_pitcher, park_factor_hr, park_factor_single, park_factor_k,
                temperature_f=temperature_f,
                wind_speed=wind_speed,
                wind_direction=wind_direction,
                umpire_cs_rate=umpire_cs_rate,
                batter_rest_days=away_rest_days,
                batter_travel_miles=away_travel_miles,
                batter_tz_crossings=away_tz_crossings,
                is_home=False,
            )
            for b in away_lineup
        ]

        # Bullpen quality adjustment factors (applied to late innings)
        home_bullpen_factor = 1.0 + (home_bullpen_era - 4.0) * 0.02
        away_bullpen_factor = 1.0 + (away_bullpen_era - 4.0) * 0.02

        home_wins = np.zeros(n_iterations, dtype=bool)
        away_wins = np.zeros(n_iterations, dtype=bool)
        home_runs = np.zeros(n_iterations, dtype=np.int16)
        away_runs = np.zeros(n_iterations, dtype=np.int16)
        extra_innings = np.zeros(n_iterations, dtype=bool)
        walkoffs = np.zeros(n_iterations, dtype=bool)

        logger.info(f"Running {n_iterations} Monte Carlo iterations...")

        for it in range(n_iterations):
            state = GameState()
            sim_home_p = PitcherState(**home_pitcher.__dict__)
            sim_away_p = PitcherState(**away_pitcher.__dict__)
            home_idx, away_idx = 0, 0
            self._home_probs_late = None
            self._away_probs_late = None

            while True:
                if state.half == "top":
                    state.reset_half()
                    if state.inning > self.MAX_INNINGS:
                        extra_innings[it] = True
                    while state.outs < self.OUTS_PER_HALF:
                        batter_idx = away_idx % 9
                        bp = self._get_inning_probs(
                            away_probs[batter_idx], state.inning,
                            away_bullpen_factor, is_away=True,
                        )
                        outcome = self._sample_outcome(bp)
                        self._apply_outcome(outcome, state, away_probs[batter_idx], is_home=False)
                        sim_home_p.pitch_count += 1
                        away_idx += 1
                        if self._check_game_ended(state, is_walkoff_scenario=False):
                            break
                    if state.is_final:
                        break
                    state.half = "bot"
                else:
                    state.reset_half()
                    while state.outs < self.OUTS_PER_HALF:
                        batter_idx = home_idx % 9
                        bp = self._get_inning_probs(
                            home_probs[batter_idx], state.inning,
                            home_bullpen_factor, is_away=False,
                        )
                        outcome = self._sample_outcome(bp)
                        self._apply_outcome(outcome, state, home_probs[batter_idx], is_home=True)
                        sim_away_p.pitch_count += 1
                        home_idx += 1
                        if self._check_game_ended(state, is_walkoff_scenario=True):
                            break
                    if state.is_final:
                        break
                    state.half = "top"
                    state.inning += 1

            home_runs[it] = state.home_score
            away_runs[it] = state.away_score
            home_wins[it] = state.home_score > state.away_score
            away_wins[it] = state.away_score > state.home_score
            walkoffs[it] = state.is_walkoff

            if progress_callback and (it + 1) % 1000 == 0:
                progress_callback(it + 1, n_iterations)

        home_win_prob = float(np.mean(home_wins))
        away_win_prob = float(np.mean(away_wins))
        extra_innings_prob = float(np.mean(extra_innings))
        walkoff_prob = float(np.mean(walkoffs))

        percentiles = [5, 10, 25, 50, 75, 90, 95]

        return SimulationResult(
            home_win_prob=home_win_prob,
            away_win_prob=away_win_prob,
            mean_home_runs=float(np.mean(home_runs)),
            mean_away_runs=float(np.mean(away_runs)),
            std_home_runs=float(np.std(home_runs)),
            std_away_runs=float(np.std(away_runs)),
            home_run_distribution={p: float(np.percentile(home_runs, p)) for p in percentiles},
            away_run_distribution={p: float(np.percentile(away_runs, p)) for p in percentiles},
            n_iterations=n_iterations,
            home_runs_array=home_runs,
            away_runs_array=away_runs,
            walkoff_prob=walkoff_prob,
            extra_innings_prob=extra_innings_prob,
        )

    # ------------------------------------------------------------------
    # CONSTRUCCIÓN DE MATRIZ DE PROBABILIDAD
    # ------------------------------------------------------------------

    def _build_batter_probs(
        self,
        batter: BatterState,
        pitcher: PitcherState,
        park_hr: float,
        park_single: float,
        park_k: float,
        temperature_f: float = 70.0,
        wind_speed: float = 0.0,
        wind_direction: str = "NONE",
        umpire_cs_rate: float = 0.0,
        batter_rest_days: int = 4,
        batter_travel_miles: int = 0,
        batter_tz_crossings: int = 0,
        is_home: bool = True,
    ) -> np.ndarray:
        prob_out = 0.310
        prob_single = 0.155
        prob_double = 0.045
        prob_triple = 0.005
        prob_hr = 0.030
        prob_walk = 0.085
        prob_hbp = 0.010
        prob_sac = 0.045

        # --- Platoon split ---
        platoon = 1.0
        if batter.bats == pitcher.throws:
            platoon = 0.88
        if batter.bats == 'S':
            platoon = 0.95

        # --- Pitcher quality adjustments ---
        k_adj = (pitcher.k_rate - self.LEAGUE_AVG_K_RATE) * 2.0
        bb_adj = (pitcher.bb_rate - self.LEAGUE_AVG_BB_RATE) * 1.5
        hr_adj = (pitcher.hr_rate - self.LEAGUE_AVG_HR_RATE) * 1.5

        # --- Park factors ---
        prob_hr *= park_hr
        prob_single *= park_single
        prob_double *= (1 + (park_hr - 1) * 0.3)
        prob_out *= park_k

        # --- Fatigue adjustment ---
        fatigue = pitcher.fatigue_factor
        if fatigue < 1.0:
            fatigue_penalty = 1.0 - fatigue
            prob_hr *= (1 + fatigue_penalty * 0.3)
            prob_single *= (1 + fatigue_penalty * 0.2)
            prob_walk *= (1 + fatigue_penalty * 0.15)
            prob_out *= (1 - fatigue_penalty * 0.1)

        # --- Apply platoon ---
        if platoon < 1.0:
            hit_total = prob_single + prob_double + prob_triple + prob_hr
            reduction = hit_total * (1.0 - platoon)
            prob_single *= platoon
            prob_double *= platoon
            prob_triple *= platoon
            prob_hr *= platoon
            prob_out = min(0.95, prob_out + reduction * 0.5)
            prob_walk = min(0.20, prob_walk + reduction * 0.3)

        # --- Temperature effect (air density) ---
        if temperature_f > 80:
            heat_factor = (temperature_f - 80) / 40.0
            prob_hr *= (1 + heat_factor * 0.08)
            prob_single *= (1 + heat_factor * 0.03)
        elif temperature_f < 50:
            cold_factor = (50 - temperature_f) / 30.0
            prob_hr *= (1 - cold_factor * 0.10)
            prob_out *= (1 + cold_factor * 0.03)

        # --- Wind effect ---
        if wind_speed > 5:
            wd = wind_direction.upper().replace("_", "")
            if wd in ("OUT", "OUTC", "OUTTOCF", "LTR", "RTL"):
                wind_factor = wind_speed * 0.006
                prob_hr *= (1 + wind_factor)
                prob_single *= (1 + wind_factor * 0.3)
            elif wd in ("IN", "INC", "INFROCF"):
                wind_factor = wind_speed * 0.004
                prob_hr *= (1 - wind_factor)
                prob_double *= (1 - wind_factor * 0.3)

        # --- Umpire strike zone effect ---
        if umpire_cs_rate > 0:
            if umpire_cs_rate > 0.64:
                wide_zone = min(0.10, (umpire_cs_rate - 0.64) * 2.0)
                prob_out *= (1 + wide_zone * 0.3)
                prob_walk *= (1 - wide_zone * 0.2)
            elif umpire_cs_rate < 0.58:
                tight_zone = min(0.10, (0.58 - umpire_cs_rate) * 2.0)
                prob_out *= (1 - tight_zone * 0.2)
                prob_walk *= (1 + tight_zone * 0.3)

        # --- Batter travel fatigue ---
        if batter_travel_miles > 1500:
            travel_penalty = min(0.05, (batter_travel_miles - 1500) * 0.00002)
            prob_single *= (1 - travel_penalty)
            prob_double *= (1 - travel_penalty * 0.5)
            prob_hr *= (1 - travel_penalty)
            prob_out *= (1 + travel_penalty * 0.2)
        if batter_tz_crossings > 1:
            tz_penalty = (batter_tz_crossings - 1) * 0.02
            prob_single *= (1 - tz_penalty)
            prob_hr *= (1 - tz_penalty)
            prob_out *= (1 + tz_penalty * 0.3)

        # --- Home field advantage ---
        if is_home:
            prob_single *= 1.01
            prob_double *= 1.01
            prob_hr *= 1.005
            prob_out *= 0.995

        # --- Apply pitcher adjustments ---
        contact_reduction = max(0, k_adj * fatigue)
        prob_out += contact_reduction
        hit_reduction = contact_reduction * 0.10
        prob_single = max(0.001, prob_single - hit_reduction * 0.5)
        prob_double = max(0.001, prob_double - hit_reduction * 0.2)
        prob_hr = max(0.001, prob_hr - hit_reduction * 0.1)
        prob_walk = max(0.001, prob_walk + bb_adj * fatigue)
        prob_hr = max(0.001, prob_hr + hr_adj)
        prob_out = max(0.001, prob_out - bb_adj * fatigue * 0.5)
        prob_hbp = max(0.001, prob_hbp + bb_adj * 0.1)

        probs = np.array([
            prob_out, prob_single, prob_double, prob_triple,
            prob_hr, prob_walk, prob_hbp, prob_sac,
        ])
        probs = np.maximum(probs, 0.001)
        probs = probs / probs.sum()

        if not math.isclose(probs.sum(), 1.0, rel_tol=1e-3):
            probs = probs / probs.sum()

        return probs

    def _get_inning_probs(
        self,
        base_probs: np.ndarray,
        inning: int,
        bullpen_factor: float,
        is_away: bool,
    ) -> np.ndarray:
        if inning < 7 or abs(bullpen_factor - 1.0) < 0.005:
            return base_probs
        probs = base_probs.copy()
        if bullpen_factor > 1.0:
            penalty = (bullpen_factor - 1.0) * 0.5
            adjustment = min(0.05, penalty)
            probs[4] *= (1 + adjustment * 0.5)  # HR
            probs[1] *= (1 + adjustment * 0.3)  # single
            probs[5] *= (1 + adjustment * 0.2)  # walk
            probs[0] *= (1 - adjustment * 0.2)  # out
        else:
            boost = (1.0 - bullpen_factor) * 0.5
            adjustment = min(0.05, boost)
            probs[4] *= (1 - adjustment * 0.5)
            probs[1] *= (1 - adjustment * 0.3)
            probs[5] *= (1 - adjustment * 0.2)
            probs[0] *= (1 + adjustment * 0.2)
        probs = np.maximum(probs, 0.001)
        return probs / probs.sum()

    def _sample_outcome(self, probs: np.ndarray) -> PAOutcome:
        outcomes = [
            PAOutcome.OUT, PAOutcome.SINGLE, PAOutcome.DOUBLE,
            PAOutcome.TRIPLE, PAOutcome.HOME_RUN, PAOutcome.WALK,
            PAOutcome.HIT_BY_PITCH, PAOutcome.SACRIFICE,
        ]
        idx = self.rng.choice(len(outcomes), p=probs)
        return outcomes[idx]

    # ------------------------------------------------------------------
    # LÓGICA DE APLICACIÓN DE RESULTADOS
    # ------------------------------------------------------------------

    def _apply_outcome(
        self,
        outcome: PAOutcome,
        state: GameState,
        batter_probs: np.ndarray,
        is_home: bool,
    ):
        if outcome == PAOutcome.OUT:
            state.outs += 1

        elif outcome == PAOutcome.SINGLE:
            self._run_single(state, is_home)
            state.outs += 1

        elif outcome == PAOutcome.DOUBLE:
            self._run_extra(state, 2, is_home)
            state.outs += 1

        elif outcome == PAOutcome.TRIPLE:
            self._run_extra(state, 3, is_home)
            state.outs += 1

        elif outcome == PAOutcome.HOME_RUN:
            runs = sum(state.bases) + 1
            if is_home:
                state.home_score += runs
            else:
                state.away_score += runs
            state.bases = (False, False, False)
            state.outs += 1

        elif outcome == PAOutcome.WALK:
            if state.bases == (True, True, True):
                if is_home:
                    state.home_score += 1
                else:
                    state.away_score += 1
            else:
                if state.bases[0] and state.bases[1] and not state.bases[2]:
                    state.bases = (True, True, True)
                elif state.bases[0] and not state.bases[1]:
                    state.bases = (True, True, state.bases[2])
                elif not state.bases[0]:
                    state.bases = (True, state.bases[1], state.bases[2])

        elif outcome == PAOutcome.HIT_BY_PITCH:
            if state.bases == (True, True, True):
                if is_home:
                    state.home_score += 1
                else:
                    state.away_score += 1
            else:
                if state.bases[0] and state.bases[1] and not state.bases[2]:
                    state.bases = (True, True, True)
                elif state.bases[0] and not state.bases[1]:
                    state.bases = (True, True, state.bases[2])
                elif not state.bases[0]:
                    state.bases = (True, state.bases[1], state.bases[2])

        elif outcome == PAOutcome.SACRIFICE:
            if state.bases[2]:
                if is_home:
                    state.home_score += 1
                else:
                    state.away_score += 1
            state.bases = (state.bases[0], state.bases[1], False)
            state.outs += 1

        elif outcome == PAOutcome.ERROR:
            state.outs += 1
            if not state.bases[0]:
                state.bases = (True, state.bases[1], state.bases[2])

        elif outcome == PAOutcome.FIELDERS_CHOICE:
            state.outs += 1

    def _run_single(self, state: GameState, is_home: bool):
        new_bases = [False, False, False]
        runs = 0
        for i, occupied in enumerate(state.bases):
            if occupied:
                if i == 2:
                    runs += 1
                elif i == 1:
                    if self.rng.random() < 0.60:
                        runs += 1
                    else:
                        new_bases[2] = True
                elif i == 0:
                    if self.rng.random() < 0.40:
                        new_bases[2] = True
                    else:
                        new_bases[1] = True
        new_bases[0] = True
        state.bases = tuple(new_bases)
        if is_home:
            state.home_score += runs
        else:
            state.away_score += runs

    def _run_extra(self, state: GameState, bases: int, is_home: bool):
        new_bases = [False, False, False]
        runs = 0
        for i, occupied in enumerate(state.bases):
            if occupied:
                dest = i + bases
                if dest >= 3:
                    runs += 1
                else:
                    new_bases[dest] = True
        new_bases[bases - 1] = True
        state.bases = tuple(new_bases)
        if is_home:
            state.home_score += runs
        else:
            state.away_score += runs

    def _check_game_ended(self, state: GameState, is_walkoff_scenario: bool) -> bool:
        if (state.half == "bot"
            and state.inning >= self.MAX_INNINGS
            and state.home_score > state.away_score
            and state.outs < self.OUTS_PER_HALF):
            state.is_final = True
            state.is_walkoff = True
            return True

        if (state.half == "top"
            and state.inning > self.MAX_INNINGS
            and state.away_score > state.home_score
            and state.outs == self.OUTS_PER_HALF):
            state.is_final = True
            return True

        if (state.half == "top"
            and state.inning > self.MAX_INNINGS
            and state.outs == self.OUTS_PER_HALF
            and state.home_score > state.away_score):
            state.is_final = True
            return True

        if (state.outs == self.OUTS_PER_HALF
            and state.inning > self.MAX_INNINGS
            and state.home_score != state.away_score):
            state.is_final = True
            return True

        if state.inning > self.MAX_INNINGS + self.MAX_EXTRA_INNINGS:
            state.is_final = True
            return True

        return False


# ============================================================================
# EJEMPLO DE USO
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    sim = MonteCarloMLBSimulator(seed=42)

    home_lineup = [
        BatterState(player_id=1, name="Judge", bats="R", woba_vs_rhp=0.420, woba_vs_lhp=0.390, k_rate=0.280, bb_rate=0.180, hr_rate=0.065),
        BatterState(player_id=2, name="Soto", bats="L", woba_vs_rhp=0.410, woba_vs_lhp=0.350, k_rate=0.180, bb_rate=0.190, hr_rate=0.045),
        BatterState(player_id=3, name="Stanton", bats="R", woba_vs_rhp=0.350, woba_vs_lhp=0.330, k_rate=0.310, bb_rate=0.080, hr_rate=0.055),
        BatterState(player_id=4, name="Rizzo", bats="L", woba_vs_rhp=0.340, woba_vs_lhp=0.300, k_rate=0.170, bb_rate=0.090, hr_rate=0.035),
        BatterState(player_id=5, name="Torres", bats="R", woba_vs_rhp=0.330, woba_vs_lhp=0.320, k_rate=0.200, bb_rate=0.100, hr_rate=0.030),
        BatterState(player_id=6, name="Volpe", bats="R", woba_vs_rhp=0.300, woba_vs_lhp=0.290, k_rate=0.270, bb_rate=0.070, hr_rate=0.020),
        BatterState(player_id=7, name="Wells", bats="L", woba_vs_rhp=0.320, woba_vs_lhp=0.280, k_rate=0.220, bb_rate=0.100, hr_rate=0.025),
        BatterState(player_id=8, name="Verdugo", bats="L", woba_vs_rhp=0.310, woba_vs_lhp=0.270, k_rate=0.160, bb_rate=0.080, hr_rate=0.020),
        BatterState(player_id=9, name="Grisham", bats="L", woba_vs_rhp=0.290, woba_vs_lhp=0.250, k_rate=0.320, bb_rate=0.110, hr_rate=0.025),
    ]

    away_lineup = [
        BatterState(player_id=10, name="Acuna", bats="R", woba_vs_rhp=0.400, woba_vs_lhp=0.370, k_rate=0.230, bb_rate=0.130, hr_rate=0.050),
        BatterState(player_id=11, name="Albies", bats="S", woba_vs_rhp=0.350, woba_vs_lhp=0.340, k_rate=0.190, bb_rate=0.080, hr_rate=0.035),
        BatterState(player_id=12, name="Riley", bats="R", woba_vs_rhp=0.370, woba_vs_lhp=0.330, k_rate=0.250, bb_rate=0.090, hr_rate=0.050),
        BatterState(player_id=13, name="Olson", bats="L", woba_vs_rhp=0.360, woba_vs_lhp=0.300, k_rate=0.240, bb_rate=0.110, hr_rate=0.055),
        BatterState(player_id=14, name="Ozuna", bats="R", woba_vs_rhp=0.340, woba_vs_lhp=0.320, k_rate=0.220, bb_rate=0.100, hr_rate=0.045),
        BatterState(player_id=15, name="Murphy", bats="R", woba_vs_rhp=0.320, woba_vs_lhp=0.300, k_rate=0.200, bb_rate=0.080, hr_rate=0.030),
        BatterState(player_id=16, name="Arcia", bats="R", woba_vs_rhp=0.300, woba_vs_lhp=0.290, k_rate=0.210, bb_rate=0.060, hr_rate=0.020),
        BatterState(player_id=17, name="Harris", bats="L", woba_vs_rhp=0.330, woba_vs_lhp=0.280, k_rate=0.240, bb_rate=0.060, hr_rate=0.030),
        BatterState(player_id=18, name="Rosario", bats="L", woba_vs_rhp=0.290, woba_vs_lhp=0.250, k_rate=0.260, bb_rate=0.050, hr_rate=0.020),
    ]

    home_pitcher = PitcherState(
        player_id=100, name="Cole", throws="R",
        k_rate=0.280, bb_rate=0.070, hr_rate=0.028,
        whiff_pct=0.130, avg_velo=96.0, avg_spin=2500.0,
    )
    away_pitcher = PitcherState(
        player_id=101, name="Strider", throws="R",
        k_rate=0.350, bb_rate=0.080, hr_rate=0.025,
        whiff_pct=0.170, avg_velo=98.0, avg_spin=2400.0,
    )

    def progress(current, total):
        logger.info(f"Progress: {current}/{total} ({(current/total)*100:.0f}%)")

    result = sim.run_simulation(
        home_lineup=home_lineup,
        away_lineup=away_lineup,
        home_pitcher=home_pitcher,
        away_pitcher=away_pitcher,
        park_factor_hr=1.04,
        park_factor_single=1.01,
        park_factor_k=0.98,
        n_iterations=10000,
        progress_callback=progress,
    )

    print(f"\n{'='*60}")
    print(f"RESULTADOS DE SIMULACION MONTE CARLO (10,000 iteraciones)")
    print(f"{'='*60}")
    print(f"P(Local)  = {result.home_win_prob:.3f}  ({result.home_win_prob*100:.1f}%)")
    print(f"P(Visit.) = {result.away_win_prob:.3f}  ({result.away_win_prob*100:.1f}%)")
    print(f"Carreras esperadas: Local={result.mean_home_runs:.2f} (+-{result.std_home_runs:.2f})")
    print(f"                     Visit.={result.mean_away_runs:.2f} (+-{result.std_away_runs:.2f})")
    print(f"P(Extra innings) = {result.extra_innings_prob:.3f}")
    print(f"P(Walkoff)       = {result.walkoff_prob:.3f}")

    print(f"\nDistribucion de carreras (Local):")
    for p, v in result.home_run_distribution.items():
        print(f"  P{p}: {v:.1f}")

    print(f"\nAnalisis EV+ (odds: local -130, visitante +110):")
    ev = result.get_ev_positive_bets(home_odds=-130, away_odds=110)
    print(f"  EV(Local)  = {ev['home_ev']:.4f}")
    print(f"  EV(Visit.) = {ev['away_ev']:.4f}")
    print(f"  Recomendacion: {ev['recommendation']}")
    if ev['recommendation'] != 'no_bet':
        print(f"  Kelly frac = {ev['kelly_fraction']:.4f}")
        print(f"  Apuesta EV+ detectada! Valor: {ev['expected_value']:.4f}")

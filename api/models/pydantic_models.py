# =============================================================================
# pydantic_models.py
# Esquemas de solicitud/respuesta para la API REST
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================

from typing import List, Optional, Dict
from datetime import datetime, date
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# SIMULACIÓN
# ============================================================================

class SimulationRequest(BaseModel):
    game_id: str = Field(..., description="Game ID (YYYY-MM-DD-AWAY-HOME)")
    home_team_id: str = Field(..., description="Home team abbreviation")
    away_team_id: str = Field(..., description="Away team abbreviation")
    home_lineup: List[int] = Field(default_factory=list, description="Player IDs in batting order")
    away_lineup: List[int] = Field(default_factory=list, description="Player IDs in batting order")
    home_pitcher_id: int = 0
    away_pitcher_id: int = 0
    park_factor_hr: float = 1.0
    n_iterations: int = 10000

    @field_validator("n_iterations")
    @classmethod
    def validate_iterations(cls, v):
        if v < 1000:
            raise ValueError("Minimum 1000 iterations")
        if v > 100000:
            raise ValueError("Maximum 100000 iterations")
        return v


class SimulationResponse(BaseModel):
    game_id: str
    home_win_prob: float
    away_win_prob: float
    mean_home_runs: float
    mean_away_runs: float
    std_home_runs: float
    std_away_runs: float
    extra_innings_prob: float
    walkoff_prob: float
    n_iterations: int
    home_run_distribution: Dict[str, float]
    away_run_distribution: Dict[str, float]
    computed_at: datetime


# ============================================================================
# EV+ / APUESTAS
# ============================================================================

class EVRequest(BaseModel):
    game_id: str
    home_odds: int
    away_odds: int
    home_real_prob: float
    away_real_prob: float


class EVResponse(BaseModel):
    game_id: str
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    bets: List[Dict] = []


class BetSlipItem(BaseModel):
    game_id: str
    team: str
    market_type: str
    odds: int
    stake: float
    edge: float
    kelly_fraction: float


class BetSlipRequest(BaseModel):
    bets: List[BetSlipItem]


class BetSlipResponse(BaseModel):
    approved: bool
    total_stake: float
    violations: List[str] = []


# ============================================================================
# PROPS
# ============================================================================

class PropRequest(BaseModel):
    player_id: int
    prop_type: str = Field(..., pattern=r"^(STRIKEOUTS|HITS|HR|RBIS|WALKS)$")
    line_value: float
    over_odds: int
    under_odds: int
    features: Dict[str, float]


class PropResponse(BaseModel):
    player_name: str
    prop_type: str
    line_value: float
    predicted_mean: float
    prob_over: float
    prob_under: float
    ev_over: float
    ev_under: float
    recommendation: str
    kelly_fraction: float


# ============================================================================
# ALERTAS
# ============================================================================

class AlertResponse(BaseModel):
    alert_id: int
    game_id: str
    team_id: str
    signal_type: str
    confidence: float
    message: str
    created_at: datetime
    is_read: bool = False


class AlertListResponse(BaseModel):
    alerts: List[AlertResponse]
    total: int
    unread_count: int


# ============================================================================
# ESTADÍSTICAS
# ============================================================================

class PlayerStatsResponse(BaseModel):
    player_id: int
    full_name: str
    team_id: str
    position: Optional[str] = None
    bats: Optional[str] = None
    throws: Optional[str] = None
    woba_30d: Optional[float] = None
    fip_30d: Optional[float] = None
    xera_30d: Optional[float] = None
    avg_velo_30d: Optional[float] = None
    whiff_pct_30d: Optional[float] = None
    fatigue_score: Optional[float] = None


class PitcherPreviewStats(BaseModel):
    name: str = ""
    throws: str = ""
    fip: Optional[float] = None
    k_per_9: Optional[float] = None
    bb_per_9: Optional[float] = None
    hr_per_9: Optional[float] = None
    avg_velo: Optional[float] = None
    whiff_pct: Optional[float] = None
    fatigue_score: Optional[float] = None


class BullpenPreviewStats(BaseModel):
    era: Optional[float] = None
    fip: Optional[float] = None


class GamePreviewResponse(BaseModel):
    game_id: str
    game_date: str
    home_team: str
    away_team: str
    home_pitcher_id: Optional[int] = None
    away_pitcher_id: Optional[int] = None
    status: Optional[str] = None
    start_time: Optional[str] = None
    home_moneyline: Optional[int] = None
    away_moneyline: Optional[int] = None
    total: Optional[float] = None
    home_win_prob: Optional[float] = None
    away_win_prob: Optional[float] = None
    sharp_money_flag: bool = False
    rlm_flag: bool = False
    home_pitcher: PitcherPreviewStats = PitcherPreviewStats()
    away_pitcher: PitcherPreviewStats = PitcherPreviewStats()
    home_bullpen: BullpenPreviewStats = BullpenPreviewStats()
    away_bullpen: BullpenPreviewStats = BullpenPreviewStats()
    home_woba: Optional[float] = None
    away_woba: Optional[float] = None
    better_team: str = ""
    better_pitcher: str = ""
    better_bullpen: str = ""
    better_offense: str = ""


# ============================================================================
# RIESGO / BANKROLL
# ============================================================================

class BankrollResponse(BaseModel):
    initial: float
    current: float
    peak: float
    drawdown_pct: float
    total_wagered: float
    total_profit: float
    roi_pct: float
    total_return_pct: float
    sharpe_ratio: float
    bet_count: int
    updated_at: datetime


class ExposureResponse(BaseModel):
    approved: bool
    violations: List[str]
    current_bankroll: float
    stake: float
    stake_pct: float


# ============================================================================
# ANÁLISIS DIARIO
# ============================================================================

class PitchingAnalysis(BaseModel):
    pitcher_name: str = ""
    throws: str = ""
    fip_30d: Optional[float] = None
    k_per_9_30d: Optional[float] = None
    bb_per_9_30d: Optional[float] = None
    hr_per_9_30d: Optional[float] = None
    avg_velo_30d: Optional[float] = None
    whiff_pct_30d: Optional[float] = None
    fatigue_score: Optional[float] = None
    platoon_advantage: bool = False
    summary: str = ""


class OffensiveAnalysis(BaseModel):
    woba_30d: Optional[float] = None
    woba_vs_hand: Optional[float] = None
    barrel_pct_30d: Optional[float] = None
    hard_hit_pct_30d: Optional[float] = None
    k_pct_30d: Optional[float] = None
    bb_pct_30d: Optional[float] = None
    run_diff_30d: Optional[float] = None
    record_last_10: str = ""
    summary: str = ""


class BullpenAnalysis(BaseModel):
    bullpen_era_30d: Optional[float] = None
    bullpen_fip_30d: Optional[float] = None
    summary: str = ""


class WeatherImpact(BaseModel):
    temperature: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_direction: str = ""
    precipitation_pct: Optional[float] = None
    condition: str = ""
    wind_effect: str = ""
    temp_effect: str = ""
    summary: str = ""


class ParkFactor(BaseModel):
    hr_factor: float = 1.0
    woba_factor: float = 1.0
    k_factor: float = 1.0
    stadium_name: str = ""
    summary: str = ""


class FatigueAnalysis(BaseModel):
    rest_days: int = 0
    travel_miles: int = 0
    tz_crossings: int = 0
    day_game_after_night: bool = False
    summary: str = ""


class MarketSignals(BaseModel):
    sharp_money_flag: bool = False
    rlm_flag: bool = False
    home_moneyline: Optional[int] = None
    away_moneyline: Optional[int] = None
    total_line: Optional[float] = None
    summary: str = ""


class PropAnalysisItem(BaseModel):
    player_name: str = ""
    prop_type: str = ""
    line_value: float = 0
    predicted_mean: float = 0
    prob_over: float = 0
    prob_under: float = 0
    ev_over: float = 0
    ev_under: float = 0
    recommendation: str = ""
    edge_pct: float = 0
    kelly_fraction: float = 0


class RecommendedBet(BaseModel):
    team: str = ""
    opponent: str = ""
    market_type: str = ""
    odds: int = 0
    edge_pct: float = 0
    confidence: str = ""
    kelly_fraction: float = 0
    recommended_stake: float = 0
    reasoning: List[str] = []


class GameAnalysis(BaseModel):
    game_id: str
    game_date: str
    start_time: str = ""
    status: str = ""
    home_team_id: str
    away_team_id: str
    home_team_name: str = ""
    away_team_name: str = ""

    home_win_prob: float = 0
    away_win_prob: float = 0
    favorite_id: str = ""
    favorite_name: str = ""
    underdog_id: str = ""
    underdog_name: str = ""
    win_prob_gap: float = 0

    mean_home_runs: float = 0
    mean_away_runs: float = 0
    predicted_total: float = 0

    pitching_home: PitchingAnalysis = PitchingAnalysis()
    pitching_away: PitchingAnalysis = PitchingAnalysis()
    offensive_home: OffensiveAnalysis = OffensiveAnalysis()
    offensive_away: OffensiveAnalysis = OffensiveAnalysis()
    bullpen_home: BullpenAnalysis = BullpenAnalysis()
    bullpen_away: BullpenAnalysis = BullpenAnalysis()
    weather: WeatherImpact = WeatherImpact()
    park_factors: ParkFactor = ParkFactor()
    fatigue_home: FatigueAnalysis = FatigueAnalysis()
    fatigue_away: FatigueAnalysis = FatigueAnalysis()
    market_signals: MarketSignals = MarketSignals()

    recommended_bet: Optional[RecommendedBet] = None
    props: List[PropAnalysisItem] = []

    analysis_narrative: str = ""
    key_factors: List[str] = []


class DailyAnalysisResponse(BaseModel):
    game_date: str
    generated_at: datetime
    total_games: int = 0
    games: List[GameAnalysis] = []

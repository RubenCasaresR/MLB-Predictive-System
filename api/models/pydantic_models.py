# =============================================================================
# pydantic_models.py
# Esquemas de solicitud/respuesta para la API REST
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================

from typing import List, Optional, Dict
from datetime import datetime, date
from pydantic import BaseModel, Field, validator


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

    @validator("n_iterations")
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

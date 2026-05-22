from typing import List, Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel


class SureBetRecommendation(BaseModel):
    rank: int
    game_id: str
    home_team: str
    away_team: str
    recommended_team: Optional[str] = None
    market_type: str
    odds: int
    safety_score: int
    safety_label: str
    edge_pct: float
    win_prob: Optional[float] = None
    reasons: List[str] = []
    key_stats: Dict[str, Any] = {}


class SureBetsResponse(BaseModel):
    generated_at: datetime
    muy_seguras: List[SureBetRecommendation] = []
    seguras: List[SureBetRecommendation] = []
    riesgosas: List[SureBetRecommendation] = []

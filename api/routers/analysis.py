import logging
from typing import Optional

from fastapi import APIRouter, Query

from api.models.pydantic_models import DailyAnalysisResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@router.get("/daily", response_model=DailyAnalysisResponse)
async def get_daily_analysis(
    date: str | None = Query(None, description="Fecha en formato YYYY-MM-DD"),
):
    from api.services.daily_analysis_service import DailyAnalysisService

    service = DailyAnalysisService()
    return service.get_analysis(target_date=date)

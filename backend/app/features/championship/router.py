from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.features.championship.contracts import TeamCategoryBaselineResponse
from app.features.championship.service import get_team_category_baseline

router = APIRouter(prefix="/api/v1", tags=["Championship HQ"])


@router.get("/team-category-baseline", response_model=TeamCategoryBaselineResponse)
async def read_team_category_baseline(
    league_key: str = Query(min_length=1),
    session: AsyncSession = Depends(get_session),
) -> TeamCategoryBaselineResponse:
    return await get_team_category_baseline(session, league_key)

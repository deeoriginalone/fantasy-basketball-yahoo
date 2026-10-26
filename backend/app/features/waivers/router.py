from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.features.leagues.models import Team
from app.features.waivers.contracts import Mode, WaiverBoard, WaiverImpact, TransactionAnalysis
from app.features.waivers.service import get_waivers, get_impact, get_transactions

router = APIRouter(prefix="/api/v1/waivers", tags=["Waiver Center"])


async def configured_team(
    league_key: str | None = Query(default=None, min_length=1),
    team_key: str | None = Query(default=None, min_length=1),
    session: AsyncSession = Depends(get_session),
) -> Team:
    manager_key = get_settings().waiver_manager_team_key
    if team_key is not None and team_key != manager_key:
        raise HTTPException(422, "Waiver Command Center analyzes only the configured manager team")
    team = await session.get(Team, manager_key)
    if team is None:
        raise HTTPException(404, "Configured waiver manager team is not in the persisted Yahoo teams")
    if league_key is not None and league_key != team.league_key:
        raise HTTPException(422, "League must match the configured waiver manager team")
    return team


@router.get("", response_model=WaiverBoard)
async def read_waivers(
    mode: Mode = "this_week",
    team: Team = Depends(configured_team),
    session: AsyncSession = Depends(get_session),
) -> WaiverBoard:
    board = await get_waivers(session, team.league_key, team.team_key, mode)
    board.team_name = team.team_name
    return board


@router.get("/replacements", response_model=WaiverBoard)
async def read_replacements(
    drop_player_id: int = Query(...),
    mode: Mode = "this_week",
    team: Team = Depends(configured_team),
    session: AsyncSession = Depends(get_session),
) -> WaiverBoard:
    board = await get_waivers(session, team.league_key, team.team_key, mode, drop_player_id)
    board.team_name = team.team_name
    return board


@router.get("/transactions", response_model=TransactionAnalysis)
async def read_transactions(
    mode: Mode = "this_week",
    team: Team = Depends(configured_team),
    session: AsyncSession = Depends(get_session),
) -> TransactionAnalysis:
    analysis = await get_transactions(session, team.league_key, team.team_key, mode)
    analysis.team_name = team.team_name
    return analysis


@router.get("/{player_id}/impact", response_model=WaiverImpact)
async def read_impact(
    player_id: int,
    drop_player_id: int | None = None,
    mode: Mode = "this_week",
    team: Team = Depends(configured_team),
    session: AsyncSession = Depends(get_session),
) -> WaiverImpact:
    return await get_impact(session, team.league_key, team.team_key, player_id, drop_player_id, mode)

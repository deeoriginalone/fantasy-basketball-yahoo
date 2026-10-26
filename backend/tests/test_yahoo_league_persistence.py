import asyncio
import os
from copy import deepcopy
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.features.draft.models import DraftPick, DraftSession
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.leagues.service import import_manager_leagues
from app.services.yahoo.normalization import NormalizedYahooLeague, NormalizedYahooTeam
from schema_support import create_test_schema


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL")
def test_league_refresh_preserves_referenced_teams_and_rolls_back_failure(monkeypatch, caplog):
    url = os.environ["TEST_DATABASE_URL"]
    engine = create_async_engine(url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex[:12]
    league_key = f"refresh.test.{suffix}"
    team_key, retained_key = f"{league_key}.t.1", f"{league_key}.t.2"
    session_id = str(uuid4())
    normalized = NormalizedYahooLeague(
        league_key=league_key, game_key="nba_fixture", league_name="Refreshed league",
        season=2026, scoring_settings={"scoring_type": "head"},
        roster_positions=[], source_league={}, source_settings={},
        teams=[NormalizedYahooTeam(team_key=team_key, team_name="Refreshed team", source_payload={})],
    )
    monkeypatch.setattr("app.features.leagues.service.YahooAuthService.access_token", AsyncMock(return_value="synthetic"))
    monkeypatch.setattr("app.features.leagues.service.discover_active_nba_game_key", AsyncMock(return_value="nba_fixture"))
    fetch = AsyncMock(return_value=[normalized])
    monkeypatch.setattr("app.features.leagues.service.fetch_user_leagues", fetch)

    async def scenario():
        async with engine.begin() as connection:
            await create_test_schema(connection)
        try:
            async with sessions() as session, session.begin():
                session.add(League(league_key=league_key, game_key="nba_fixture",
                    league_name="Original", season=2026, source_payload={}))
                await session.flush()
                session.add_all([Team(team_key=key, league_key=league_key, team_name="Original", source_payload={})
                    for key in (team_key, retained_key)])
                await session.flush()
                session.add(DraftSession(id=session_id, league_key=league_key, season="2026-27",
                    manager_team_key=team_key, draft_position=1, total_teams=2, rounds=1,
                    status="active", mode="balanced", team_slots={team_key: 1, retained_key: 2}))
                await session.flush()
                session.add(DraftPick(session_id=session_id, overall_pick=1, round_number=1,
                    team_slot=2, team_key=retained_key, source="manual", source_evidence={}))
            async with sessions() as session:
                first = await import_manager_leagues(session, Settings(database_url=url))
                assert first.team_count == 1
                await import_manager_leagues(session, Settings(database_url=url))
            async with sessions() as session:
                team = await session.get(Team, team_key)
                assert team.team_name == "Refreshed team"
                assert await session.get(Team, retained_key) is not None
                assert await session.get(DraftSession, session_id) is not None
                assert (await session.get(DraftPick, (session_id, 1))).team_key == retained_key
                timestamps = (
                    (await session.get(League, league_key)).imported_at,
                    (await session.get(LeagueSettings, league_key)).imported_at,
                    team.imported_at,
                )
            invalid = deepcopy(normalized)
            invalid.league_name = "Must roll back"
            invalid.teams[0].team_name = "private-fixture-marker-" + "x" * 256
            fetch.return_value = [invalid]
            async with sessions() as session:
                with pytest.raises(HTTPException) as error:
                    await import_manager_leagues(session, Settings(database_url=url))
                assert error.value.status_code == 502
                assert error.value.detail == "Yahoo league data could not be persisted"
            async with sessions() as session:
                league = await session.get(League, league_key)
                settings = await session.get(LeagueSettings, league_key)
                team = await session.get(Team, team_key)
                assert league.league_name == "Refreshed league"
                assert team.team_name == "Refreshed team"
                assert (league.imported_at, settings.imported_at, team.imported_at) == timestamps
                assert await session.get(DraftPick, (session_id, 1)) is not None
            assert "private-fixture-marker" not in caplog.text
            assert "Unable to persist Yahoo league import" in caplog.text
        finally:
            async with sessions() as session, session.begin():
                await session.execute(delete(DraftSession).where(DraftSession.id == session_id))
                await session.execute(delete(League).where(League.league_key == league_key))
            await engine.dispose()

    asyncio.run(scenario())

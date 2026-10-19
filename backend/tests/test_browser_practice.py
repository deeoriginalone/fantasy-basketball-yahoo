import asyncio
from datetime import datetime, timezone
import os
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.features.draft.models import DraftPick, DraftPickEvent, DraftPlayerMetric, DraftRecommendationSnapshot, DraftSession
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.players.models import LeaguePlayer, PlayerIdentity
from app.services.draft.browser_practice import create_browser_practice, ingest_browser_practice
from app.services.draft.mock_drafts import simulate_internal_mock, delete_internal_mock
from app.services.draft.sessions import get_draft_board, record_draft_pick
from app.services.draft.sessions import get_draft_session
from app.features.draft.observer_connection import (
    ConnectBody, DesktopSnapshot, ObserverConnection, connect, desktop_snapshot, stop_connection,
)
from app.services.draft.sync import run_mock_sync_rehearsal
from app.features.draft.contracts import DraftPickUpdateRequest
from schema_support import create_test_schema

URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.skipif(not URL, reason="Requires isolated PostgreSQL test database")
def test_disposable_browser_practice_uses_existing_reconciler_and_isolates_teams(monkeypatch):
    monkeypatch.setenv("COURT_IQ_OBSERVER_PRACTICE_WRITES", "true")
    monkeypatch.setenv("COURT_IQ_OBSERVER_MOCK_ROUNDS", "13")
    assert "test" in (make_url(URL).database or "").lower()
    engine = create_async_engine(URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex[:12]
    league_key = f"observer-test.{suffix}"
    ids = []
    practice_league = None

    async def scenario():
        nonlocal practice_league
        async with engine.begin() as connection:
            await create_test_schema(connection)
        try:
            async with factory() as session:
                session.add(League(
                    league_key=league_key, game_key="fixture", league_name="Imported fixture",
                    season=2026, source_payload={},
                ))
                await session.flush()
                session.add(LeagueSettings(
                    league_key=league_key,
                    scoring_settings={"scoring_type": "headpoint", "categories": []},
                    roster_positions=[{"position": "PG", "count": 13, "is_starting_position": 1}],
                    source_payload={},
                ))
                for slot in range(1, 13):
                    session.add(Team(
                        league_key=league_key, team_key=f"{league_key}.t.{slot}",
                        team_name=f"Real opponent {slot}", source_payload={},
                    ))
                for index in range(15):
                    yahoo_id = str(900000000000 + int(suffix, 16) % 90000000000 + index)
                    player = PlayerIdentity(
                        yahoo_player_id=yahoo_id, nba_player_id=f"fixture-{suffix}-{index}",
                        player_name=f"Player {index}", team="BOS", position="PG",
                    )
                    session.add(player)
                    await session.flush()
                    ids.append(player.id)
                    session.add(LeaguePlayer(
                        league_key=league_key, yahoo_player_id=yahoo_id,
                        player_identity_id=player.id, source_payload={},
                    ))
                    session.add(DraftPlayerMetric(
                        league_key=league_key, player_identity_id=player.id, season="2026-27",
                        fantasy_value=40-index, replacement_value=5, positional_scarcity=50,
                        durability_score=80, risk_score=20, upside_score=60, sample_games=60,
                        source_season="2025-26", source_season_type="Regular Season", source_payload={},
                    ))
                await session.commit()
                connection = await connect(ConnectBody(
                    room_path=f"/draftclient/nba/{int(suffix,16)}/10", mode="mock",
                ), session)
                product = await desktop_snapshot(
                    connection["id"],
                    DesktopSnapshot(state="CONNECTED", user_slot=10, total_teams=12),
                    league_key, session,
                )
                state = await get_draft_session(session, product["draft_room_path"].split("/")[-1])
                practice_league = state.league_key
                assert state.browser_practice and state.draft_position == 10
                assert state.session_type == "mock" and not state.auto_pick_enabled
                assert all(key.startswith(practice_league) for key in state.team_slots)
                teams = (await session.scalars(select(Team).where(Team.league_key == practice_league))).all()
                assert len(teams) == 12
                assert {team.team_name for team in teams} == {
                    *(f"Mock Slot {slot}" for slot in range(1, 13) if slot != 10), "Box Score Bully",
                }
                yahoo_ids = (await session.scalars(select(PlayerIdentity.yahoo_player_id)
                    .where(PlayerIdentity.id.in_(ids)).order_by(PlayerIdentity.id))).all()
                picks = [SimpleNamespace(
                    overall_pick=i+1, yahoo_player_id=yahoo_id,
                    observed_at=datetime.now(timezone.utc),
                ) for i, yahoo_id in enumerate(yahoo_ids[:10])]
                await session.commit()
                first = await desktop_snapshot(
                    connection["id"], DesktopSnapshot(
                        state="CONNECTED", picks=[
                            {**vars(pick), "source": "yahoo_mock_browser"} for pick in picks[:4]
                        ],
                    ), league_key, session,
                )
                assert first["court_iq_through"] == 4
                board = await get_draft_board(session, state.session_id)
                assert board.session.next_overall_pick == 5
                assert not set(ids[:4]) & {p.player_identity_id for p in board.players}
                assert board.recommendation is not None
                assert board.session.recommendation_version == 4
                await session.commit()
                # Reconnecting the same sanitized room reuses the disposable session.
                repeated_connection = await connect(ConnectBody(
                    room_path=connection["room_path"], mode="mock",
                ), session)
                assert repeated_connection["draft_room_path"] == product["draft_room_path"]
                await session.commit()
                resumed = await create_browser_practice(
                    session, source_league_key=league_key, season="2026-27",
                    user_slot=10, rounds=13, connection_key=connection["id"],
                )
                assert resumed.state.session_id == state.session_id and resumed.event == "unchanged"
                duplicate = await ingest_browser_practice(session, state.session_id, picks[:4])
                assert duplicate["accepted_picks"] == []
                assert duplicate["confirmed_picks"] == [1, 2, 3, 4]
                await session.commit()
                catchup = await ingest_browser_practice(session, state.session_id, picks[:9])
                assert catchup["accepted_picks"] == [5, 6, 7, 8, 9]
                board = await get_draft_board(session, state.session_id)
                assert board.session.timing.your_turn is True
                assert board.session.timing.current_pick == 10
                await session.commit()
                await ingest_browser_practice(session, state.session_id, picks)
                board = await get_draft_board(session, state.session_id)
                assert board.session.timing.your_turn is False
                assert board.session.next_overall_pick == 11
                assert any(p.team_key == board.session.manager_team_key and p.selected_player_id == ids[9]
                           for p in board.session.picks)
                assert await session.scalar(select(func.count()).select_from(DraftPickEvent)
                    .where(DraftPickEvent.session_id == state.session_id)) == 10
                assert await session.scalar(select(func.count()).select_from(DraftRecommendationSnapshot)
                    .where(DraftRecommendationSnapshot.session_id == state.session_id)) == 11
                assert await session.scalar(select(func.count()).select_from(DraftPick)
                    .join(DraftSession).where(DraftSession.league_key == league_key)) == 0
                await session.commit()
                with pytest.raises(HTTPException, match="disabled"):
                    await simulate_internal_mock(session, state.session_id, "next_pick")
                await session.rollback()
                with pytest.raises(HTTPException, match="not enabled"):
                    await run_mock_sync_rehearsal(session, state.session_id, "fast")
                await session.rollback()
                with pytest.raises(HTTPException, match="browser observer"):
                    await record_draft_pick(session, state.session_id, 11,
                        DraftPickUpdateRequest(expected_version=10, selected_player_id=ids[10]))
                await session.rollback()
                with pytest.raises(HTTPException, match="Stop Tracking"):
                    await delete_internal_mock(session, state.session_id)
                await session.rollback()
                changed = [SimpleNamespace(
                    overall_pick=1, yahoo_player_id=yahoo_ids[10], observed_at=datetime.now(timezone.utc),
                ), *picks[1:]]
                with pytest.raises(HTTPException) as conflict:
                    await ingest_browser_practice(session, state.session_id, changed)
                assert conflict.value.status_code == 409
                await session.commit()
                with pytest.raises(HTTPException, match="latched"):
                    await ingest_browser_practice(session, state.session_id, picks)
                await session.rollback()
                # Live mode only observes: no practice session is created or production picks written.
                live = await connect(ConnectBody(
                    room_path=f"/draftclient/nba/{int(suffix,16)+1}/10", mode="live",
                ), session)
                observed = await desktop_snapshot(
                    live["id"], DesktopSnapshot(state="CONNECTED", user_slot=10, total_teams=12, rounds=13),
                    league_key, session,
                )
                assert observed["status"] == "OBSERVE ONLY" and observed["draft_room_path"] is None
                await session.commit()
                stopped = await stop_connection(live["id"], session)
                assert stopped["paired"] is True and "id" not in stopped
                assert await session.scalar(select(func.count()).select_from(DraftPick)
                    .where(DraftPick.session_id == state.session_id)) == 10
                await session.commit()
                assert (await stop_connection(live["id"], session))["paired"] is True
                await session.commit()
                await delete_internal_mock(session, state.session_id)
                assert await session.get(DraftSession, state.session_id) is None
                await session.commit()
        finally:
            async with factory() as session:
                await session.execute(delete(ObserverConnection).where(
                    ObserverConnection.room_path.in_([
                        f"/draftclient/nba/{int(suffix,16)}/10",
                        f"/draftclient/nba/{int(suffix,16)+1}/10",
                    ])
                ))
                for key in [practice_league, league_key]:
                    if key:
                        await session.execute(delete(DraftSession).where(DraftSession.league_key == key))
                        await session.execute(delete(League).where(League.league_key == key))
                if ids:
                    await session.execute(delete(PlayerIdentity).where(PlayerIdentity.id.in_(ids)))
                await session.commit()
            await engine.dispose()

    asyncio.run(scenario())

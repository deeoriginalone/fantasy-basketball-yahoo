import asyncio
from datetime import datetime, timezone
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.features.draft.contracts import (
    DraftLiveSessionCreateRequest,
    DraftOrderUpdateRequest,
    DraftPickUpdateRequest,
    DraftPickUpdateRequest,
    DraftSessionCreateRequest,
)
from app.features.draft.models import DraftPick, DraftPickEvent, DraftPlayerMetric, DraftSession, DraftSyncState
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.players.models import LeaguePlayer, PlayerIdentity
from app.services.draft.sessions import (
    create_draft_session,
    get_draft_session,
    reconcile_source_picks,
    record_draft_pick,
    update_live_draft_order,
)
from app.services.draft.sync import run_mock_sync_rehearsal, sync_yahoo_draft_results
from schema_support import create_test_schema

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
def test_live_reconciliation_and_mock_rehearsal_are_session_isolated():
    assert TEST_DATABASE_URL
    assert "test" in (make_url(TEST_DATABASE_URL).database or "").lower()
    suffix = uuid4().hex[:10]
    league_key = f"draft-sync.{suffix}"
    manager_key, opponent_key, third_key = (
        f"{league_key}.t.1",
        f"{league_key}.t.2",
        f"{league_key}.t.3",
    )
    yahoo_ids = [f"yahoo-{suffix}-{index}" for index in range(5)]
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def scenario():
        async with engine.begin() as connection:
            await create_test_schema(connection)
        try:
            async with session_factory() as session:
                session.add_all([
                    League(
                        league_key=league_key,
                        game_key="nba_fixture",
                        league_name="Draft Sync Fixture",
                        season=2026,
                        source_payload={"fixture": True},
                    ),
                    LeagueSettings(
                        league_key=league_key,
                        scoring_settings={"scoring_type": "headpoint", "categories": []},
                        roster_positions=[{"position": "PG", "count": 1, "is_starting_position": 1}],
                        source_payload={"fixture": True},
                    ),
                    Team(team_key=manager_key, league_key=league_key, team_name="Manager", source_payload={}),
                    Team(team_key=opponent_key, league_key=league_key, team_name="Opponent", source_payload={}),
                ])
                await session.flush()
                player_ids = []
                for index, yahoo_id in enumerate(yahoo_ids):
                    identity = PlayerIdentity(
                        yahoo_player_id=yahoo_id,
                        nba_player_id=f"nba-{suffix}-{index}",
                        player_name=f"Sync Player {index}",
                        team="BOS",
                        position="PG",
                        status=None,
                    )
                    session.add(identity)
                    await session.flush()
                    player_ids.append(identity.id)
                    session.add(LeaguePlayer(
                        league_key=league_key,
                        yahoo_player_id=yahoo_id,
                        player_identity_id=identity.id,
                        source_payload={"fixture": True},
                    ))
                    session.add(DraftPlayerMetric(
                        league_key=league_key,
                        player_identity_id=identity.id,
                        season="2026-27",
                        fantasy_value=30.0 - index,
                        replacement_value=5.0,
                        positional_scarcity=50.0,
                        durability_score=80.0,
                        risk_score=20.0,
                        upside_score=60.0,
                        sample_games=60,
                        source_season="2025-26",
                        source_season_type="Regular Season",
                        source_payload={"fixture": True},
                    ))
                await session.commit()

                live = await create_draft_session(
                    session,
                    DraftSessionCreateRequest(
                        league_key=league_key,
                        season="2026-27",
                        manager_team_key=manager_key,
                        draft_position=1,
                        total_teams=2,
                        rounds=3,
                        team_slots={manager_key: 1, opponent_key: 2},
                    ),
                    draft_source="yahoo_live",
                )
                assert live.state.sync_enabled is True
                with pytest.raises(HTTPException, match="already assigned"):
                    await create_draft_session(
                        session,
                        DraftLiveSessionCreateRequest(
                            league_key=league_key,
                            season="2026-27",
                            manager_team_key=manager_key,
                            draft_position=1,
                            total_teams=2,
                            rounds=3,
                            team_slots={opponent_key: 1},
                        ),
                        draft_source="yahoo_live",
                    )
                source_picks = [{
                    "overall_pick": 1,
                    "team_key": manager_key,
                    "player_identity_id": player_ids[0],
                    "source_evidence": {"source": "fixture"},
                }, {
                    "overall_pick": 2,
                    "team_key": opponent_key,
                    "player_identity_id": player_ids[1],
                    "source_evidence": {"source": "fixture"},
                }]
                pending = await create_draft_session(
                    session,
                    DraftLiveSessionCreateRequest(
                        league_key=league_key,
                        season="2026-27",
                        manager_team_key=manager_key,
                        total_teams=2,
                        rounds=3,
                    ),
                    draft_source="yahoo_live",
                )
                assert pending.state.draft_position is None
                assert pending.state.draft_order_status == "unresolved"
                assert pending.state.timing.your_turn is None
                assert pending.state.timing.current_pick is None
                with pytest.raises(HTTPException, match="already assigned"):
                    await update_live_draft_order(
                        session,
                        pending.state.session_id,
                        DraftOrderUpdateRequest(
                            expected_version=0,
                            draft_position=1,
                            team_slots={opponent_key: 1},
                            replace_mapping=True,
                        ),
                    )
                accepted, _, _, status, _, _ = await reconcile_source_picks(
                    session,
                    pending.state.session_id,
                    source_picks,
                    retrieved_at=datetime.now(timezone.utc),
                    source="yahoo_draftresults",
                )
                assert accepted == [1, 2]
                assert status == "synced"
                discovered = await get_draft_session(session, pending.state.session_id)
                assert discovered.draft_position is None
                assert discovered.draft_order_status == "confirmed"
                assert discovered.team_slots == {manager_key: 1, opponent_key: 2}
                assert [pick.team_key for pick in discovered.picks] == [manager_key, opponent_key]
                await session.commit()
                positioned = await update_live_draft_order(
                    session,
                    pending.state.session_id,
                    DraftOrderUpdateRequest(
                        expected_version=discovered.version,
                        draft_position=1,
                    ),
                )
                assert positioned.draft_position == 1
                assert positioned.timing.next_pick == 4

                conflicted = await create_draft_session(
                    session,
                    DraftLiveSessionCreateRequest(
                        league_key=league_key,
                        season="2026-27",
                        manager_team_key=manager_key,
                        draft_position=2,
                        total_teams=2,
                        rounds=3,
                        team_slots={manager_key: 2},
                    ),
                    draft_source="yahoo_live",
                )
                accepted, _, _, status, conflict_pick, evidence = await reconcile_source_picks(
                    session,
                    conflicted.state.session_id,
                    source_picks[:1],
                    retrieved_at=datetime.now(timezone.utc),
                    source="yahoo_draftresults",
                )
                assert accepted == []
                assert status == "conflict"
                assert conflict_pick == 1
                assert evidence["reason"] == "manager_position_mismatch"
                assert evidence["source_evidence"] == source_picks[0]["source_evidence"]
                accepted, _, _, status, _, _ = await reconcile_source_picks(
                    session,
                    conflicted.state.session_id,
                    source_picks,
                    retrieved_at=datetime.now(timezone.utc),
                    source="yahoo_draftresults",
                )
                assert accepted == []
                assert status == "conflict"
                conflicted_state = await get_draft_session(session, conflicted.state.session_id)
                assert conflicted_state.draft_order_status == "conflict"
                assert conflicted_state.draft_order_evidence["conflict"] == evidence
                await session.commit()
                resolved = await update_live_draft_order(
                    session,
                    conflicted.state.session_id,
                    DraftOrderUpdateRequest(
                        expected_version=conflicted_state.version,
                        draft_position=1,
                        team_slots={manager_key: 1, opponent_key: 2},
                        replace_mapping=True,
                    ),
                )
                assert resolved.draft_order_status == "confirmed"
                assert resolved.draft_order_evidence["conflict"] == evidence
                assert resolved.draft_order_evidence["slots"]["2"]["team_key"] == manager_key
                assert resolved.draft_order_evidence["slots"]["2"]["resolved_team_key"] == opponent_key
                assert (await session.get(DraftSyncState, conflicted.state.session_id)).status == "source_empty"
                await session.commit()

                unknown_slot_live = await create_draft_session(
                    session,
                    DraftLiveSessionCreateRequest(
                        league_key=league_key,
                        season="2026-27",
                        manager_team_key=manager_key,
                        draft_position=2,
                        total_teams=2,
                        rounds=3,
                    ),
                    draft_source="yahoo_live",
                )
                manual_pick = await record_draft_pick(
                    session,
                    unknown_slot_live.state.session_id,
                    1,
                    DraftPickUpdateRequest(
                        selected_player_id=player_ids[2],
                        expected_version=0,
                    ),
                )
                assert manual_pick.state.picks[0].team_key is None
                accepted, confirmed, _, status, _, _ = await reconcile_source_picks(
                    session,
                    live.state.session_id,
                    source_picks,
                    retrieved_at=datetime.now(timezone.utc),
                    source="yahoo_draftresults",
                )
                assert accepted == [1, 2]
                assert confirmed == []
                assert status == "synced"

                accepted, confirmed, _, status, _, _ = await reconcile_source_picks(
                    session,
                    live.state.session_id,
                    source_picks,
                    retrieved_at=datetime.now(timezone.utc),
                    source="yahoo_draftresults",
                )
                assert accepted == []
                assert confirmed == [1, 2]
                assert status == "synced"

                conflicting_picks = [{
                    **source_picks[0],
                    "player_identity_id": player_ids[2],
                }, source_picks[1]]
                accepted, _, _, status, conflict_pick, _ = await reconcile_source_picks(
                    session,
                    live.state.session_id,
                    conflicting_picks,
                    retrieved_at=datetime.now(timezone.utc),
                    source="yahoo_draftresults",
                )
                assert accepted == []
                assert status == "conflict"
                assert conflict_pick == 1
                assert (await get_draft_session(session, live.state.session_id)).version == 2
                await session.commit()

                session.add(Team(
                    team_key=third_key,
                    league_key=league_key,
                    team_name="Third",
                    source_payload={},
                ))
                await session.commit()
                mock = await create_draft_session(
                    session,
                    DraftSessionCreateRequest(
                        league_key=league_key,
                        season="2026-27",
                        manager_team_key=opponent_key,
                        draft_position=3,
                        total_teams=3,
                        rounds=3,
                        team_slots={manager_key: 1, third_key: 2, opponent_key: 3},
                    ),
                    draft_source="internal_mock",
                    mock_run_config={
                        "seed": 12,
                        "aggressiveness": 0.5,
                        "live_sync_rehearsal": True,
                    },
                )
                mock_state = await session.get(DraftSyncState, mock.state.session_id)
                assert mock_state.source_type == "mock_yahoo_snapshot"
                with pytest.raises(HTTPException) as live_sync_error:
                    await sync_yahoo_draft_results(session, mock.state.session_id)
                assert live_sync_error.value.status_code == 409

                rehearsal = await run_mock_sync_rehearsal(
                    session,
                    mock.state.session_id,
                    "simulate_source_lag",
                )
                assert rehearsal.sync.status == "source_lagging"
                assert rehearsal.sync.source_confirmed_through == 0
                assert len(mock_state.mock_generated_picks) == 2
                mock_picks = list((await session.scalars(
                    select(DraftPick).where(DraftPick.session_id == mock.state.session_id)
                )).all())
                assert len([pick for pick in mock_picks if pick.selected_player_id is not None]) == 0
                rehearsal = await run_mock_sync_rehearsal(
                    session,
                    mock.state.session_id,
                    "release_delayed_picks",
                )
                assert rehearsal.sync.status == "synced"
                assert rehearsal.sync.source_confirmed_through == 2
                mock_picks = list((await session.scalars(
                    select(DraftPick).where(DraftPick.session_id == mock.state.session_id)
                )).all())
                assert len([pick for pick in mock_picks if pick.selected_player_id is not None]) == 2
                mock_events = await session.scalar(select(func.count()).select_from(DraftPickEvent).where(
                    DraftPickEvent.session_id == mock.state.session_id
                ))
                assert mock_events == 2

                current_state = await get_draft_session(session, mock.state.session_id)
                drafted_ids = {
                    pick.selected_player_id for pick in current_state.picks
                    if pick.selected_player_id is not None
                }
                manager_player_id = next(player_id for player_id in player_ids if player_id not in drafted_ids)
                await session.commit()
                await record_draft_pick(
                    session,
                    mock.state.session_id,
                    3,
                    DraftPickUpdateRequest(
                        selected_player_id=manager_player_id,
                        expected_version=current_state.version,
                    ),
                )
                rehearsal = await run_mock_sync_rehearsal(
                    session,
                    mock.state.session_id,
                    "fast",
                )
                assert rehearsal.sync.status == "synced"
                assert rehearsal.sync.source_confirmed_through == 3
                current_state = await get_draft_session(session, mock.state.session_id)
                assert current_state.next_overall_pick == 4
                assert current_state.timing.your_turn is True
                completed_picks = [
                    pick for pick in current_state.picks
                    if pick.selected_player_id is not None
                ]
                assert [pick.overall_pick for pick in completed_picks] == [1, 2, 3]
                assert len({pick.selected_player_id for pick in completed_picks}) == 3
                assert {
                    pick.overall_pick: pick.selection_source
                    for pick in completed_picks
                } == {
                    1: "scored_board_ranking_adp_unavailable",
                    2: "scored_board_ranking_adp_unavailable",
                    3: None,
                }
                mock_events = await session.scalar(select(func.count()).select_from(DraftPickEvent).where(
                    DraftPickEvent.session_id == mock.state.session_id
                ))
                assert mock_events == 3
        finally:
            async with session_factory() as cleanup:
                await cleanup.execute(delete(DraftSession).where(DraftSession.league_key == league_key))
                await cleanup.execute(delete(League).where(League.league_key == league_key))
                await cleanup.execute(delete(PlayerIdentity).where(
                    PlayerIdentity.yahoo_player_id.in_(yahoo_ids)
                ))
                await cleanup.commit()
            await engine.dispose()

    asyncio.run(scenario())

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.features.draft.contracts import (
    DraftLiveSessionCreateRequest,
    DraftMockBatchCreateRequest,
    DraftMockCreateRequest,
    DraftOrderUpdateRequest,
    DraftPickUndoRequest,
    DraftPickUpdateRequest,
    DraftSessionCreateRequest,
    DraftSessionEventResult,
    DraftTargetRequest,
    DraftUtilityResult,
)
from app.features.draft.models import (
    DraftMarketData,
    DraftMockRun,
    DraftPick,
    DraftPickEvent,
    DraftPlayerMetric,
    DraftRecommendationSnapshot,
    DraftSession,
)
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.players.models import LeaguePlayer, PlayerIdentity
from app.main import app
from app.services.draft.sessions import (
    correct_draft_pick,
    create_draft_session,
    delete_draft_target,
    get_draft_board,
    get_draft_session,
    list_draft_sessions,
    put_draft_target,
    record_draft_pick,
    undo_draft_pick,
)
from app.services.draft import sessions as draft_sessions_service
from app.services.draft.mock_drafts import (
    create_internal_mock_batch,
    create_internal_mock,
    delete_internal_mock,
    get_internal_mock_batch,
    get_internal_mock_replay,
    restart_internal_mock,
    run_internal_mock_batch,
    set_internal_mock_paused,
    simulate_internal_mock,
)
from schema_support import create_test_schema

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def test_draft_session_routes_are_versioned_and_v1_remains_available() -> None:
    paths = app.openapi()["paths"]
    assert set(paths["/api/v1/draft/utility"]) == {"post"}
    assert set(paths["/api/v2/draft/sessions"]) == {"get", "post"}
    assert set(paths["/api/v2/draft/live-sessions"]) == {"post"}
    assert set(paths["/api/v2/draft/sessions/{session_id}/order"]) == {"put"}
    assert set(paths["/api/v2/draft/mock-order-preview"]) == {"post"}
    assert set(paths["/api/v2/draft/mock-sessions"]) == {"get", "post"}
    assert set(paths["/api/v2/draft/mock-sessions/{session_id}"]) == {"delete"}
    assert "get" in paths["/api/v2/draft/sessions"]
    assert set(paths["/api/v2/draft/sessions/{session_id}/board"]) == {"get"}
    assert set(paths["/api/v2/draft/sessions/{session_id}"]) == {"get"}
    assert set(paths["/api/v2/draft/sessions/{session_id}/picks/{overall_pick}"]) == {"post", "put"}
    assert set(paths["/api/v2/draft/mock-batches"]) == {"get", "post"}
    assert "post" in paths["/api/v2/draft/sessions/{session_id}/mock-action"]
    assert "get" in paths["/api/v2/draft/sessions/{session_id}/replay"]
    pending_live = DraftLiveSessionCreateRequest(
        league_key="league",
        season="2026-27",
        manager_team_key="manager",
        total_teams=12,
        rounds=13,
    )
    assert pending_live.draft_position is None
    with pytest.raises(ValueError, match="cannot be set"):
        DraftOrderUpdateRequest(
            expected_version=0,
            draft_position=2,
            clear_manager_position=True,
        )


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
def test_persisted_session_pick_lifecycle_and_target_versioning(monkeypatch) -> None:
    assert TEST_DATABASE_URL
    assert "test" in (make_url(TEST_DATABASE_URL).database or "").lower()
    suffix = uuid4().hex[:10]
    league_key = f"draft-session.{suffix}"
    team_keys = [f"{league_key}.t.1", f"{league_key}.t.2"]
    yahoo_ids = [f"yahoo-{suffix}-{index}" for index in range(7)]
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def scenario() -> None:
        async with engine.begin() as connection:
            await create_test_schema(connection)
        session_id = None
        try:
            async with session_factory() as session:
                session.add_all([
                    League(
                        league_key=league_key,
                        game_key="nba_fixture",
                        league_name="Draft Session Fixture",
                        season=2026,
                        source_payload={"fixture": True},
                    ),
                    LeagueSettings(
                        league_key=league_key,
                        scoring_settings={"scoring_type": "headpoint", "categories": []},
                        roster_positions=[{"position": "PG", "count": 1, "is_starting_position": 1}],
                        source_payload={"fixture": True},
                    ),
                    Team(team_key=team_keys[0], league_key=league_key, team_name="Manager", source_payload={}),
                    Team(team_key=team_keys[1], league_key=league_key, team_name="Opponent", source_payload={}),
                ])
                await session.flush()
                player_ids = []
                for index, yahoo_id in enumerate(yahoo_ids):
                    identity = PlayerIdentity(
                        yahoo_player_id=yahoo_id,
                        nba_player_id=f"nba-{suffix}-{index}",
                        player_name=f"Session Player {index}",
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
                    if index < 3:
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
                        session.add(DraftMarketData(
                            player_id=identity.id,
                            season="2026-27",
                            source="fantrax",
                            adp=10.0 + index * 5,
                            last_updated=datetime.now(timezone.utc),
                        ))
                await session.commit()

                created = await create_draft_session(session, DraftSessionCreateRequest(
                    league_key=league_key,
                    season="2026-27",
                    manager_team_key=team_keys[0],
                    draft_position=1,
                    total_teams=2,
                    rounds=3,
                    team_slots={team_keys[0]: 1, team_keys[1]: 2},
                ))
                session_id = created.state.session_id
                assert created.state.session_type == "live"
                assert created.state.version == 0
                assert created.state.latest_recommendation is not None
                assert len(created.state.latest_recommendation["ranked_players"]) == len(player_ids)
                assert created.state.timing.current_pick == 1
                assert created.state.timing.next_pick == 1
                assert created.state.timing.current_round == 1
                assert created.state.timing.next_round == 1
                assert created.state.timing.picks_until_next == 0
                assert created.state.timing.your_turn is True
                async with session_factory() as board_reader:
                    board = await get_draft_board(board_reader, session_id)
                assert board.recommendation is not None
                assert {row.player_identity_id for row in board.players} == set(player_ids)
                assert board.roster.open_count == 1
                assert board.roster.slots[0].player is None

                snapshot = await session.scalar(select(DraftRecommendationSnapshot).where(
                    DraftRecommendationSnapshot.session_id == session_id,
                    DraftRecommendationSnapshot.session_version == 0,
                ))
                assert snapshot is not None
                persisted_response = deepcopy(snapshot.response)
                assert snapshot.input_state.get("market_data_as_of_by_player")
                stored_result = DraftUtilityResult.model_validate(snapshot.response)
                best_identity = await session.get(PlayerIdentity, stored_result.best_pick.player_identity_id)
                best_identity.status = "O"
                await session.commit()
                async with session_factory() as board_reader:
                    gated_board = await get_draft_board(board_reader, session_id)
                    historical_board = await get_draft_board(board_reader, session_id, snapshot_version=0)
                assert gated_board.recommendation.recommended_player.player_identity_id != best_identity.id
                excluded_row = next(p for p in gated_board.players if p.player_identity_id == best_identity.id)
                assert excluded_row.recommendation_eligibility == "excluded"
                assert excluded_row.survival_probability is None
                assert historical_board.recommendation.recommended_player.player_identity_id == best_identity.id
                assert snapshot.response == persisted_response
                best_identity.status = None
                legacy_response = deepcopy(persisted_response)
                for row in legacy_response["ranked_players"]:
                    for key in ("yahoo_status", "recommendation_eligibility", "yahoo_status_reason"):
                        row.pop(key, None)
                snapshot.response = legacy_response
                await session.commit()
                async with session_factory() as board_reader:
                    legacy_board = await get_draft_board(board_reader, session_id)
                assert all(row.yahoo_status_reason for row in legacy_board.players)
                assert snapshot.response == legacy_response
                snapshot.response = persisted_response
                await session.commit()
                legacy_fit_response = deepcopy(persisted_response)
                legacy_fit_response.pop("roster_fit_version", None)
                snapshot.response = legacy_fit_response
                await session.commit()
                async with session_factory() as board_reader:
                    updated_fit_board = await get_draft_board(board_reader, session_id)
                    original_fit_board = await get_draft_board(board_reader, session_id, snapshot_version=0)
                assert updated_fit_board.session.latest_recommendation["roster_fit_version"] == 2
                assert updated_fit_board.session.recommendation_version == updated_fit_board.session.version
                assert "roster_fit_version" not in original_fit_board.session.latest_recommendation
                assert snapshot.response == legacy_fit_response
                snapshot.response = persisted_response
                await session.commit()
                changed_action = "wait" if stored_result.primary_action != "wait" else "draft_now"
                changed_rows = [stored_result.ranked_players[0].model_copy(
                    update={"player_name": "Fresh board revision"}
                )]
                refreshed_result = stored_result.model_copy(update={
                    "primary_action": changed_action,
                    "best_pick": stored_result.best_pick.model_copy(
                        update={"player_name": "Fresh board revision"}
                    ),
                    "ranked_players": changed_rows,
                })
                snapshot.response = stored_result.model_copy(update={
                    "ranked_players": [],
                }).model_dump(mode="json")
                await session.commit()

                async def return_refreshed_result(*args, **kwargs):
                    return refreshed_result

                with monkeypatch.context() as patcher:
                    patcher.setattr(
                        draft_sessions_service,
                        "calculate_draft_utility",
                        return_refreshed_result,
                    )
                    async with session_factory() as board_reader:
                        consistent_board = await get_draft_board(board_reader, session_id)
                assert consistent_board.recommendation is not None
                assert consistent_board.recommendation.action == changed_action
                assert consistent_board.recommendation.recommended_player is not None
                assert consistent_board.recommendation.recommended_player.player_name == "Fresh board revision"
                assert consistent_board.players[0].player_name == "Fresh board revision"
                assert consistent_board.session.latest_recommendation["primary_action"] == changed_action
                snapshot.response = persisted_response
                await session.commit()

                future_now = datetime.now(timezone.utc) + timedelta(hours=49)

                class FutureDateTime(datetime):
                    @classmethod
                    def now(cls, tz=None):
                        return future_now if tz else future_now.replace(tzinfo=None)

                with monkeypatch.context() as patcher:
                    patcher.setattr(draft_sessions_service, "datetime", FutureDateTime)
                    async with session_factory() as stale_reader:
                        stale_board = await get_draft_board(stale_reader, session_id)
                assert stale_board.recommendation is not None
                assert stale_board.recommendation.survival_probability is None
                assert stale_board.recommendation.expected_wait_cost is None
                assert stale_board.recommendation.data_quality["survival"] == "stale"
                assert stale_board.recommendation.data_quality["wait_cost"] == "stale"
                assert stale_board.recommendation.wait_analysis == []
                assert any("ADP data has expired" in warning for warning in stale_board.recommendation.warnings)
                assert all(
                    not any(marker in reason for marker in ("Survival impact:", "Expected wait utility", "ADP impact:"))
                    for reason in stale_board.recommendation.reasons
                )
                stale_player_ids = set(player_ids[:3])
                assert all(
                    row.survival_probability is None
                    and row.data_quality["survival"] == "stale"
                    for row in stale_board.players
                    if row.player_identity_id in stale_player_ids
                ), [
                    (row.player_identity_id, row.survival_probability, row.data_quality)
                    for row in stale_board.players
                    if row.player_identity_id in stale_player_ids
                ]
                assert all(
                    row.expected_wait_cost is None
                    for row in stale_board.players
                    if row.data_quality["value"] == "heuristic"
                ), [
                    (row.player_identity_id, row.expected_wait_cost, row.data_quality)
                    for row in stale_board.players
                    if row.data_quality["value"] == "heuristic"
                ]
                async with session_factory() as snapshot_reader:
                    persisted_snapshot = await snapshot_reader.scalar(select(DraftRecommendationSnapshot).where(
                        DraftRecommendationSnapshot.session_id == session_id,
                        DraftRecommendationSnapshot.session_version == 0,
                    ))
                    assert persisted_snapshot is not None
                    assert persisted_snapshot.response == persisted_response

                with pytest.raises(HTTPException) as out_of_order:
                    await record_draft_pick(session, session_id, 2, DraftPickUpdateRequest(
                        selected_player_id=player_ids[1],
                        expected_version=0,
                    ))
                assert out_of_order.value.status_code == 409
                assert out_of_order.value.detail["reason_code"] == "OUT_OF_ORDER_PICK"

                first_pick = await record_draft_pick(session, session_id, 1, DraftPickUpdateRequest(
                    selected_player_id=player_ids[0],
                    expected_version=0,
                ))
                assert first_pick.event == "recorded"
                assert first_pick.state.version == 1
                assert first_pick.state.picks[0].team_slot == 1

                duplicate = await record_draft_pick(session, session_id, 1, DraftPickUpdateRequest(
                    selected_player_id=player_ids[0],
                    expected_version=0,
                ))
                assert duplicate.event == "unchanged"
                assert duplicate.state.version == 1

                second_pick = await record_draft_pick(session, session_id, 2, DraftPickUpdateRequest(
                    selected_player_id=player_ids[1],
                    expected_version=1,
                ))
                assert second_pick.state.picks[1].team_slot == 2
                assert second_pick.state.version == 2
                assert second_pick.state.timing.current_pick == 3
                assert second_pick.state.timing.next_pick == 4
                assert second_pick.state.timing.picks_until_next == 1
                assert second_pick.state.timing.your_turn is False

                corrected = await correct_draft_pick(session, session_id, 1, DraftPickUpdateRequest(
                    selected_player_id=player_ids[2],
                    expected_version=2,
                    source="correction",
                    evidence={"reason": "room selection corrected"},
                ))
                assert corrected.event == "corrected"
                assert corrected.state.picks[0].selected_player_id == player_ids[2]
                assert corrected.state.version == 3

                undone = await undo_draft_pick(session, session_id, 2, DraftPickUndoRequest(
                    expected_version=3,
                    source="undo",
                ))
                assert undone.event == "undone"
                assert undone.state.next_overall_pick == 2
                assert undone.state.picks[1].selected_player_id is None
                assert undone.state.version == 4

                with pytest.raises(HTTPException) as stale:
                    await record_draft_pick(session, session_id, 2, DraftPickUpdateRequest(
                        selected_player_id=player_ids[1],
                        expected_version=3,
                    ))
                assert stale.value.status_code == 409
                assert stale.value.detail["reason_code"] == "STALE_SESSION_VERSION"

                targeted = await put_draft_target(
                    session,
                    session_id,
                    player_ids[1],
                    DraftTargetRequest(status="priority", expected_version=4, note="guard depth"),
                )
                assert targeted.version == 5
                assert targeted.targets[0].status == "priority"
                async with session_factory() as target_snapshot_reader:
                    target_snapshot = await target_snapshot_reader.scalar(select(DraftRecommendationSnapshot).where(
                        DraftRecommendationSnapshot.session_id == session_id,
                        DraftRecommendationSnapshot.session_version == 5,
                    ))
                    assert target_snapshot is not None
                    assert target_snapshot.input_state["targets"] == [{
                        "player_id": player_ids[1],
                        "status": "priority",
                        "note": "guard depth",
                    }]
                snapshots_before_noop = await session.scalar(select(func.count()).select_from(
                    DraftRecommendationSnapshot
                ).where(DraftRecommendationSnapshot.session_id == session_id))
                await session.commit()

                async def unexpected_recalculation(*args, **kwargs):
                    raise AssertionError("unchanged targets must not recalculate recommendations")

                with monkeypatch.context() as patcher:
                    patcher.setattr(
                        draft_sessions_service,
                        "calculate_draft_utility",
                        unexpected_recalculation,
                    )
                    unchanged_target = await put_draft_target(
                        session,
                        session_id,
                        player_ids[1],
                        DraftTargetRequest(status="priority", expected_version=5, note="guard depth"),
                    )
                assert unchanged_target.version == 5
                snapshots_after_noop = await session.scalar(select(func.count()).select_from(
                    DraftRecommendationSnapshot
                ).where(DraftRecommendationSnapshot.session_id == session_id))
                assert snapshots_after_noop == snapshots_before_noop
                await session.commit()
                async with session_factory() as board_reader:
                    sorted_board = await get_draft_board(
                        board_reader,
                        session_id,
                        sort_by="name",
                        descending=False,
                    )
                assert [player.player_name for player in sorted_board.players] == sorted(
                    player.player_name for player in sorted_board.players
                )
                assert next(
                    player for player in sorted_board.players
                    if player.player_identity_id == player_ids[1]
                ).target_status == "priority"
                unmarked = await delete_draft_target(session, session_id, player_ids[1], 5)
                assert unmarked.version == 6
                assert unmarked.targets == []

                async def race_pick(player_id: int):
                    async with session_factory() as client:
                        return await record_draft_pick(
                            client,
                            session_id,
                            2,
                            DraftPickUpdateRequest(
                                selected_player_id=player_id,
                                expected_version=6,
                            ),
                        )

                concurrent_results = await asyncio.gather(
                    race_pick(player_ids[0]),
                    race_pick(player_ids[1]),
                    return_exceptions=True,
                )
                assert sum(
                    isinstance(result, DraftSessionEventResult) and result.event == "recorded"
                    for result in concurrent_results
                ) == 1
                stale_results = [
                    result for result in concurrent_results
                    if isinstance(result, HTTPException)
                ]
                assert len(stale_results) == 1
                assert stale_results[0].status_code == 409
                assert stale_results[0].detail["reason_code"] == "STALE_SESSION_VERSION"

                session.expire_all()
                current_version = 7
                for overall_pick, player_index in zip(range(3, 7), range(3, 7)):
                    final_pick = await record_draft_pick(
                        session,
                        session_id,
                        overall_pick,
                        DraftPickUpdateRequest(
                            selected_player_id=player_ids[player_index],
                            expected_version=current_version,
                        ),
                    )
                    current_version += 1
                assert final_pick.state.status == "completed"
                assert final_pick.state.next_overall_pick == 7

                replacement_for_completed_pick = (
                    player_ids[0] if player_ids[1] in {
                        pick.selected_player_id for pick in final_pick.state.picks
                        if pick.overall_pick == 2
                    } else player_ids[1]
                )
                corrected_completed = await correct_draft_pick(
                    session,
                    session_id,
                    1,
                    DraftPickUpdateRequest(
                        selected_player_id=replacement_for_completed_pick,
                        expected_version=current_version,
                        source="completed_correction",
                    ),
                )
                current_version += 1
                assert corrected_completed.state.status == "completed"

                reopened = await undo_draft_pick(
                    session,
                    session_id,
                    6,
                    DraftPickUndoRequest(expected_version=current_version),
                )
                current_version += 1
                assert reopened.state.status == "active"

                completed_again = await record_draft_pick(
                    session,
                    session_id,
                    6,
                    DraftPickUpdateRequest(
                        selected_player_id=player_ids[2],
                        expected_version=current_version,
                    ),
                )
                current_version += 1
                assert completed_again.state.status == "completed"
                async with session_factory() as completed_writer:
                    with pytest.raises(HTTPException) as completed_pick:
                        await record_draft_pick(
                            completed_writer,
                            session_id,
                            7,
                            DraftPickUpdateRequest(
                                selected_player_id=player_ids[0],
                                expected_version=current_version,
                            ),
                        )
                assert completed_pick.value.status_code == 409
                assert completed_pick.value.detail == "Draft session is not active"

                async with session_factory() as reader:
                    resumed = await get_draft_session(reader, session_id)
                    assert resumed.version == current_version
                    assert resumed.recommendation_version == current_version
                    events = list((await reader.scalars(
                        select(DraftPickEvent)
                        .where(DraftPickEvent.session_id == session_id)
                        .order_by(DraftPickEvent.id)
                    )).all())
                    snapshots = list((await reader.scalars(
                        select(DraftRecommendationSnapshot).where(
                            DraftRecommendationSnapshot.session_id == session_id
                        )
                    )).all())
                    assert [event.event_type for event in events] == [
                        "recorded", "recorded", "corrected", "undone", "recorded",
                        "recorded", "recorded", "recorded", "recorded", "corrected",
                        "undone", "recorded",
                    ]
                    assert len(snapshots) == 15

                mock_batch = await create_internal_mock_batch(session, DraftMockBatchCreateRequest(
                    league_key=league_key,
                    season="2026-27",
                    manager_team_key=team_keys[0],
                    draft_position=1,
                    total_teams=2,
                    rounds=3,
                    team_slots={team_keys[0]: 1, team_keys[1]: 2},
                    mode="balanced",
                    count=2,
                    aggressiveness=0.5,
                    seed=1776,
                ))
                assert len(mock_batch.session_ids) == 2
                assert mock_batch.batch.requested_runs == 2
                batch_mock_id = mock_batch.session_ids[0]
                mock_state = await get_draft_session(session, batch_mock_id)
                assert mock_state.draft_source == "internal_mock"
                assert mock_state.session_type == "mock"
                assert mock_state.mock_seed == 1776
                assert mock_state.mock_run_index == 0
                await session.commit()
                with pytest.raises(HTTPException) as batch_owned_pick:
                    await record_draft_pick(
                        session,
                        batch_mock_id,
                        1,
                        DraftPickUpdateRequest(
                            selected_player_id=player_ids[0],
                            expected_version=0,
                        ),
                    )
                assert batch_owned_pick.value.status_code == 409
                assert batch_owned_pick.value.detail == "This mock run is controlled by its active batch"
                manual_sessions = await list_draft_sessions(session)
                assert batch_mock_id not in {item.session_id for item in manual_sessions}
                await session.commit()
                standalone_mock = await create_internal_mock(session, DraftMockCreateRequest(
                    league_key=league_key,
                    season="2026-27",
                    manager_team_key=team_keys[0],
                    draft_position=1,
                    total_teams=2,
                    rounds=3,
                    team_slots={team_keys[0]: 1, team_keys[1]: 2},
                    seed=1776,
                ))
                mock_id = standalone_mock.session_id
                mock_sessions = await list_draft_sessions(session, draft_source="internal_mock")
                listed_mock_ids = {item.session_id for item in mock_sessions}
                assert standalone_mock.session_id in listed_mock_ids
                assert batch_mock_id not in listed_mock_ids
                await session.commit()
                async with session_factory() as snapshot_reader:
                    mock_snapshots = list((await snapshot_reader.scalars(
                        select(DraftRecommendationSnapshot).where(
                            DraftRecommendationSnapshot.session_id == batch_mock_id
                        )
                    )).all())
                    second_run_snapshot = await snapshot_reader.scalar(select(DraftRecommendationSnapshot).where(
                        DraftRecommendationSnapshot.session_id == mock_batch.session_ids[1],
                        DraftRecommendationSnapshot.session_version == 0,
                    ))
                    assert len(mock_snapshots) == 1
                    assert second_run_snapshot is not None
                    assert second_run_snapshot.response == mock_snapshots[0].response
                    assert second_run_snapshot.input_state["session_id"] == mock_batch.session_ids[1]

                waiting_for_turn = await simulate_internal_mock(session, mock_id, "until_my_turn")
                assert waiting_for_turn.event == "manager_turn"
                assert waiting_for_turn.simulated_picks == 0
                auto_at_manager_turn = await simulate_internal_mock(session, mock_id, "next_pick")
                assert auto_at_manager_turn.event == "manager_turn"
                assert auto_at_manager_turn.simulated_picks == 0
                manager_pick = await record_draft_pick(
                    session,
                    mock_id,
                    1,
                    DraftPickUpdateRequest(
                        selected_player_id=player_ids[0],
                        expected_version=0,
                        source="mock_manager_pick",
                    ),
                )
                assert manager_pick.event == "recorded"
                assert manager_pick.state.picks[0].source == "mock_manager_pick"
                assert manager_pick.state.recommendation_version == manager_pick.state.version
                with pytest.raises(HTTPException) as mock_off_turn:
                    await record_draft_pick(
                        session,
                        mock_id,
                        2,
                        DraftPickUpdateRequest(
                            selected_player_id=player_ids[1],
                            expected_version=1,
                        ),
                    )
                assert mock_off_turn.value.status_code == 409
                assert mock_off_turn.value.detail == "Manual mock picks are allowed only on your turn"
                with pytest.raises(HTTPException) as live_simulation:
                    await simulate_internal_mock(session, session_id, "next_pick")
                assert live_simulation.value.status_code == 409

                opponent_pick = await simulate_internal_mock(session, mock_id, "next_pick")
                assert opponent_pick.simulated_picks == 1
                assert opponent_pick.state.picks[1].source == "internal_mock_opponent"
                async with session_factory() as evidence_reader:
                    opponent_pick_row = await evidence_reader.get(DraftPick, (mock_id, 2))
                    assert opponent_pick_row is not None
                    assert opponent_pick_row.source_evidence["seed"] == 1776

                auto_to_manager = await simulate_internal_mock(session, mock_id, "until_my_turn")
                assert auto_to_manager.event == "manager_turn"
                assert auto_to_manager.simulated_picks == 1
                assert auto_to_manager.state.timing.your_turn is True
                undone_mock_pick = await undo_draft_pick(
                    session,
                    mock_id,
                    3,
                    DraftPickUndoRequest(expected_version=3, source="mock_undo"),
                )
                assert undone_mock_pick.event == "undone"
                assert undone_mock_pick.state.next_overall_pick == 3
                assert undone_mock_pick.state.picks[2].selected_player_id is None

                paused_mock = await set_internal_mock_paused(session, mock_id, paused=True)
                assert paused_mock.status == "paused"
                with pytest.raises(HTTPException) as paused_step:
                    await simulate_internal_mock(session, mock_id, "next_pick")
                assert paused_step.value.status_code == 409
                resumed_mock = await set_internal_mock_paused(session, mock_id, paused=False)
                assert resumed_mock.status == "active"

                completed_mock = await simulate_internal_mock(session, mock_id, "full_draft")
                assert completed_mock.state.status == "completed"
                assert len(completed_mock.state.picks) == 6
                assert len({pick.selected_player_id for pick in completed_mock.state.picks}) == 6
                assert completed_mock.state.mock_evaluation is not None
                assert completed_mock.state.mock_evaluation["manager_decision_count"] == 3
                assert len(completed_mock.state.mock_evaluation["players_drafted"]) == 6
                assert "survival_outcomes" in completed_mock.state.mock_evaluation
                assert "wait_cost_outcomes" in completed_mock.state.mock_evaluation
                completed_target = await put_draft_target(
                    session,
                    mock_id,
                    player_ids[0],
                    DraftTargetRequest(
                        status="watch",
                        expected_version=completed_mock.state.version,
                        note="review completed mock",
                    ),
                )
                assert completed_target.status == "completed"
                assert completed_target.targets[0].status == "watch"
                replay = await get_internal_mock_replay(session, mock_id, version=1)
                assert replay.session.version == 1
                assert replay.board is not None
                assert replay.board.session.next_overall_pick == 2
                async with session_factory() as run_reader:
                    mock_run = await run_reader.get(DraftMockRun, mock_id)
                    assert mock_run is not None
                    assert mock_run.status == "completed"

                restarted = await restart_internal_mock(session, mock_id)
                assert restarted.session_id != mock_id
                assert restarted.draft_source == "internal_mock"
                assert restarted.picks == []
                assert restarted.mock_attempt_index == 1
                original_after_restart = await get_draft_session(session, mock_id)
                assert original_after_restart.status == "completed"
                repeated_complete = await simulate_internal_mock(session, mock_id, "full_draft")
                assert repeated_complete.event == "draft_complete"
                assert repeated_complete.simulated_picks == 0
                removable_mock = await create_internal_mock(session, DraftMockCreateRequest(
                    league_key=league_key,
                    season="2026-27",
                    manager_team_key=team_keys[0],
                    draft_position=1,
                    total_teams=2,
                    rounds=3,
                    team_slots={team_keys[0]: 1, team_keys[1]: 2},
                    seed=8181,
                ))
                await delete_internal_mock(session, removable_mock.session_id)
                with pytest.raises(HTTPException) as removed_mock:
                    await get_draft_session(session, removable_mock.session_id)
                assert removed_mock.value.status_code == 404
                assert (await get_draft_session(session, session_id)).session_type == "live"

                partial_batch_run = await simulate_internal_mock(
                    session,
                    mock_batch.session_ids[1],
                    "next_pick",
                    allow_batch_run=True,
                )
                assert partial_batch_run.simulated_picks == 1
                old_batch_attempt = mock_batch.session_ids[1]
                restarted_batch_attempt = await restart_internal_mock(session, old_batch_attempt)
                assert restarted_batch_attempt.mock_attempt_index == 1
                await session.commit()
                await asyncio.gather(
                    run_internal_mock_batch(mock_batch.batch.batch_id, session_factory),
                    run_internal_mock_batch(mock_batch.batch.batch_id, session_factory),
                )
                batch_after_recovery = await get_internal_mock_batch(session, mock_batch.batch.batch_id)
                assert batch_after_recovery.status == "completed"
                assert batch_after_recovery.completed_runs == 2
                assert len(batch_after_recovery.session_ids) == 3
                old_attempt_state = await get_draft_session(session, old_batch_attempt)
                newest_attempt_state = await get_draft_session(session, restarted_batch_attempt.session_id)
                assert old_attempt_state.status == "paused"
                assert newest_attempt_state.status == "completed"
        finally:
            async with session_factory() as session:
                async with session.begin():
                    await session.execute(delete(DraftSession).where(DraftSession.league_key == league_key))
                    await session.execute(delete(LeaguePlayer).where(LeaguePlayer.league_key == league_key))
                    await session.execute(delete(PlayerIdentity).where(PlayerIdentity.yahoo_player_id.in_(yahoo_ids)))
                    await session.execute(delete(Team).where(Team.league_key == league_key))
                    await session.execute(delete(LeagueSettings).where(LeagueSettings.league_key == league_key))
                    await session.execute(delete(League).where(League.league_key == league_key))
            await engine.dispose()

    asyncio.run(scenario())
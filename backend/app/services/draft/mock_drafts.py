import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import logging
import random
import secrets
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionFactory, engine
from app.features.draft.contracts import (
    DraftMockActionResult,
    DraftMockBatchCreateRequest,
    DraftMockBatchCreateResult,
    DraftMockBatchState,
    DraftMockCreateRequest,
    DraftMockOrderRequest,
    DraftMockOrderResponse,
    DraftMockRunRef,
    DraftPickUpdateRequest,
    DraftSessionCreateRequest,
    DraftSessionState,
    DraftUtilityRequest,
    DraftUtilityResult,
)
from app.features.draft.models import (
    DraftMarketData,
    DraftMockBatch,
    DraftMockRun,
    DraftPick,
    DraftPlayerMetric,
    DraftRecommendationSnapshot,
    DraftSession,
)
from app.features.leagues.models import LeagueSettings, Team
from app.features.players.models import LeaguePlayer, PlayerIdentity
from app.services.draft.mock_simulation import MockCandidate, choose_opponent_pick, generate_team_slots
from app.services.draft.sessions import (
    _locked_session,
    _pick_slot,
    _record_recommendation_snapshot,
    _session_state,
    correct_draft_pick,
    create_draft_session,
    get_draft_board,
    get_draft_session,
    record_draft_pick,
)
from app.services.draft.utility import calculate_draft_utility
from app.services.yahoo.normalization import normalize_yahoo_draft_pick_time

logger = logging.getLogger(__name__)


def _session_request(
    request: DraftMockCreateRequest | DraftMockBatchCreateRequest,
    team_slots: dict[str, int],
) -> DraftSessionCreateRequest:
    return DraftSessionCreateRequest.model_validate({
        **request.model_dump(include={
        "league_key",
        "season",
        "manager_team_key",
        "draft_position",
        "total_teams",
        "rounds",
        "mode",
        }),
        "team_slots": team_slots,
    })


async def _make_mock_order(
    session: AsyncSession,
    *,
    league_key: str,
    manager_team_key: str,
    draft_position: int,
    total_teams: int,
    seed: int,
    advanced_team_slots: dict[str, int] | None = None,
) -> dict[str, int]:
    team_keys = list((await session.scalars(
        select(Team.team_key).where(Team.league_key == league_key).order_by(Team.team_key)
    )).all())
    if len(team_keys) != total_teams:
        raise HTTPException(status_code=422, detail="total_teams does not match the imported Yahoo league")
    return _generate_order(
        team_keys=team_keys,
        manager_team_key=manager_team_key,
        draft_position=draft_position,
        seed=seed,
        advanced_team_slots=advanced_team_slots,
    )


def _generate_order(
    *,
    team_keys: list[str],
    manager_team_key: str,
    draft_position: int,
    seed: int,
    advanced_team_slots: dict[str, int] | None = None,
) -> dict[str, int]:
    try:
        return generate_team_slots(
            team_keys=team_keys,
            manager_team_key=manager_team_key,
            draft_position=draft_position,
            seed=seed,
            advanced_team_slots=advanced_team_slots,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


async def preview_internal_mock_order(
    session: AsyncSession,
    request: DraftMockOrderRequest,
) -> DraftMockOrderResponse:
    order = await _make_mock_order(
        session,
        league_key=request.league_key,
        manager_team_key=request.manager_team_key,
        draft_position=request.draft_position,
        total_teams=request.total_teams,
        seed=request.seed,
        advanced_team_slots=request.team_slots,
    )
    await session.commit()
    return DraftMockOrderResponse(
        league_key=request.league_key,
        draft_position=request.draft_position,
        team_slots=order,
        order_seed=request.seed,
        reused_advanced_mapping=request.team_slots is not None,
    )


async def create_internal_mock(
    session: AsyncSession,
    request: DraftMockCreateRequest,
    *,
    batch_id: str | None = None,
    run_index: int | None = None,
    attempt_index: int = 0,
    restarted_from_session_id: str | None = None,
    initial_snapshot_template: DraftRecommendationSnapshot | None = None,
    is_live_practice: bool = True,
    reuse_same_opponent_order: bool = False,
) -> DraftSessionState:
    seed = request.seed if request.seed is not None else secrets.randbits(63)
    order_seed = request.opponent_order_seed if request.opponent_order_seed is not None else seed
    if batch_id is not None and run_index not in {None, 0} and not reuse_same_opponent_order and request.team_slots is None:
        order_seed = random.Random(order_seed + run_index).getrandbits(63)
    team_slots = await _make_mock_order(
        session,
        league_key=request.league_key,
        manager_team_key=request.manager_team_key,
        draft_position=request.draft_position,
        total_teams=request.total_teams,
        seed=order_seed,
        advanced_team_slots=request.team_slots,
    )
    league_settings = await session.get(LeagueSettings, request.league_key)
    yahoo_pick_seconds = (
        normalize_yahoo_draft_pick_time(request.league_key, league_settings.source_payload)
        if league_settings else None
    )
    if is_live_practice:
        if yahoo_pick_seconds is not None:
            pick_timer_seconds = yahoo_pick_seconds
            pick_timer_source = "yahoo"
        elif request.pick_timer_seconds is not None:
            pick_timer_seconds = request.pick_timer_seconds
            pick_timer_source = "practice"
        else:
            pick_timer_seconds = None
            pick_timer_source = "not_applicable"
    else:
        pick_timer_seconds = None
        pick_timer_source = "not_applicable"
    await session.commit()
    session_request = _session_request(request, team_slots)
    result = await create_draft_session(
        session,
        session_request,
        draft_source="internal_mock",
        mock_run_config={
            "batch_id": batch_id,
            "run_index": run_index,
            "attempt_index": attempt_index,
            "restarted_from_session_id": restarted_from_session_id,
            "seed": seed,
            "opponent_order_seed": order_seed,
            "aggressiveness": request.aggressiveness,
            "generated_team_slots": team_slots,
            "pick_timer_seconds": pick_timer_seconds,
            "pick_timer_source": pick_timer_source,
            "practice_speed": request.practice_speed,
            "auto_pick_enabled": request.auto_pick_enabled if is_live_practice else False,
            "auto_pick_policy": request.auto_pick_policy,
            "live_sync_rehearsal": request.live_sync_rehearsal,
        },
        initial_snapshot_template=initial_snapshot_template,
    )
    return result.state


async def create_internal_mock_batch(
    session: AsyncSession,
    request: DraftMockBatchCreateRequest,
) -> DraftMockBatchCreateResult:
    batch_id = str(uuid4())
    seed = request.seed if request.seed is not None else secrets.randbits(63)
    config = request.model_dump(mode="json", exclude={"count"})
    batch = DraftMockBatch(
        id=batch_id,
        league_key=request.league_key,
        manager_team_key=request.manager_team_key,
        requested_runs=request.count,
        aggressiveness=request.aggressiveness,
        seed=seed,
        session_config=config,
        status="queued",
    )
    async with session.begin():
        session.add(batch)

    try:
        first_request = DraftMockCreateRequest.model_validate({
            **config,
            "aggressiveness": request.aggressiveness,
            "seed": seed,
            "opponent_order_seed": request.opponent_order_seed if request.opponent_order_seed is not None else seed,
        })
        first_state = await create_internal_mock(
            session,
            first_request,
            batch_id=batch_id,
            run_index=0,
            is_live_practice=False,
            reuse_same_opponent_order=request.reuse_same_opponent_order,
        )
        snapshot = await session.scalar(select(DraftRecommendationSnapshot).where(
            DraftRecommendationSnapshot.session_id == first_state.session_id,
            DraftRecommendationSnapshot.session_version == 0,
        ))
        if snapshot is None:
            raise RuntimeError("Initial mock recommendation snapshot was not created")
        template = deepcopy(snapshot)
        await session.commit()

        if request.count > 1:
            team_keys = list((await session.scalars(
                select(Team.team_key)
                .where(Team.league_key == request.league_key)
                .order_by(Team.team_key)
            )).all())
            if len(team_keys) != request.total_teams:
                raise HTTPException(status_code=422, detail="total_teams does not match the imported Yahoo league")
            base_order_seed = request.opponent_order_seed if request.opponent_order_seed is not None else seed
            await session.commit()
            async with session.begin():
                sessions = []
                mock_runs = []
                snapshots = []
                for run_index in range(1, request.count):
                    session_id = str(uuid4())
                    order_seed = base_order_seed if request.reuse_same_opponent_order or request.team_slots else random.Random(base_order_seed + run_index).getrandbits(63)
                    run_seed = (seed + run_index) % (2**63)
                    team_slots = _generate_order(
                        team_keys=team_keys,
                        manager_team_key=request.manager_team_key,
                        draft_position=request.draft_position,
                        seed=order_seed,
                        advanced_team_slots=request.team_slots,
                    )
                    sessions.append(DraftSession(
                        id=session_id,
                        league_key=request.league_key,
                        season=request.season,
                        manager_team_key=request.manager_team_key,
                        draft_position=request.draft_position,
                        total_teams=request.total_teams,
                        rounds=request.rounds,
                        status="active",
                        draft_source="internal_mock",
                        mode=request.mode,
                        team_slots=team_slots,
                        version=0,
                    ))
                    mock_runs.append(DraftMockRun(
                        session_id=session_id,
                        batch_id=batch_id,
                        run_index=run_index,
                        attempt_index=0,
                        seed=run_seed,
                        aggressiveness=request.aggressiveness,
                        status="queued",
                        opponent_order_seed=order_seed,
                        generated_team_slots=team_slots,
                        pick_timer_source="not_applicable",
                        practice_speed="instant_until_my_turn",
                        auto_pick_enabled=False,
                        auto_pick_policy=request.auto_pick_policy,
                    ))
                    input_state = deepcopy(template.input_state)
                    input_state["session_id"] = session_id
                    input_state["team_slots"] = team_slots
                    input_state["opponent_order_seed"] = order_seed
                    input_state["seed"] = run_seed
                    snapshots.append(DraftRecommendationSnapshot(
                        session_id=session_id,
                        session_version=0,
                        recommendation_player_id=template.recommendation_player_id,
                        input_state=input_state,
                        response=deepcopy(template.response),
                    ))
                session.add_all(sessions)
                await session.flush()
                session.add_all([*mock_runs, *snapshots])
    except Exception:
        await session.rollback()
        async with session.begin():
            await session.execute(delete(DraftSession).where(
                DraftSession.id.in_(select(DraftMockRun.session_id).where(
                    DraftMockRun.batch_id == batch_id
                ))
            ))
            persisted_batch = await session.get(DraftMockBatch, batch_id)
            if persisted_batch is not None:
                await session.delete(persisted_batch)
        raise

    batch_state = await get_internal_mock_batch(session, batch_id)
    return DraftMockBatchCreateResult(batch=batch_state, session_ids=batch_state.session_ids)


async def get_internal_mock_batch(
    session: AsyncSession,
    batch_id: str,
) -> DraftMockBatchState:
    batch = await session.get(DraftMockBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Mock batch was not found")
    rows = list((await session.execute(
        select(DraftMockRun, DraftSession)
        .join(DraftSession, DraftSession.id == DraftMockRun.session_id)
        .where(DraftMockRun.batch_id == batch_id)
        .order_by(DraftMockRun.run_index, DraftMockRun.attempt_index)
    )).all())
    latest_by_index: dict[int, tuple[DraftMockRun, DraftSession]] = {}
    for mock_run, draft_session in rows:
        if mock_run.run_index is not None:
            current = latest_by_index.get(mock_run.run_index)
            if current is None or mock_run.attempt_index > current[0].attempt_index:
                latest_by_index[mock_run.run_index] = (mock_run, draft_session)
    current_runs = [latest_by_index[index] for index in sorted(latest_by_index)]
    completed = sum(draft_session.status == "completed" for _, draft_session in current_runs)
    paused = sum(
        draft_session.status == "paused" or mock_run.status == "paused"
        for mock_run, draft_session in current_runs
    )
    failed = sum(mock_run.status == "failed" for mock_run, _ in current_runs)
    canceled = sum(mock_run.status == "canceled" for mock_run, _ in current_runs)
    queued = sum(mock_run.status == "queued" for mock_run, _ in current_runs)
    running = sum(mock_run.status in {"running", "awaiting_manager"} for mock_run, _ in current_runs)
    if batch.status == "canceled" or canceled == batch.requested_runs:
        batch_status = "canceled"
    elif completed == batch.requested_runs:
        batch_status = "completed"
    elif failed + completed == batch.requested_runs:
        batch_status = "failed"
    elif paused == batch.requested_runs - completed - failed - canceled:
        batch_status = "paused"
    elif running or batch.status == "running":
        batch_status = "running"
    else:
        batch_status = "queued"
    session_ids = [mock_run.session_id for mock_run, _ in rows]
    return DraftMockBatchState(
        batch_id=batch.id,
        league_key=batch.league_key,
        manager_team_key=batch.manager_team_key,
        requested_runs=batch.requested_runs,
        completed_runs=completed,
        paused_runs=paused,
        active_runs=queued + running,
        failed_runs=failed,
        queued_runs=queued,
        running_runs=running,
        canceled_runs=canceled,
        aggressiveness=batch.aggressiveness,
        seed=batch.seed,
        status=batch_status,
        created_at=batch.created_at.isoformat(),
        session_ids=session_ids,
        runs=[DraftMockRunRef(
            session_id=mock_run.session_id,
            run_index=mock_run.run_index,
            attempt_index=mock_run.attempt_index,
            status=draft_session.status,
            worker_status=mock_run.status,
        ) for mock_run, draft_session in rows],
    )


async def apply_internal_mock_batch_action(
    session: AsyncSession,
    batch_id: str,
    action: str,
) -> DraftMockBatchState:
    if action not in {"pause", "resume", "cancel", "retry_failed"}:
        raise HTTPException(status_code=422, detail="Unsupported mock batch action")
    async with session.begin():
        batch = await session.scalar(
            select(DraftMockBatch).where(DraftMockBatch.id == batch_id).with_for_update()
        )
        if batch is None:
            raise HTTPException(status_code=404, detail="Mock batch was not found")
        rows = list((await session.execute(
            select(DraftMockRun, DraftSession)
            .join(DraftSession, DraftSession.id == DraftMockRun.session_id)
            .where(DraftMockRun.batch_id == batch_id)
            .order_by(DraftMockRun.run_index, DraftMockRun.attempt_index.desc())
        )).all())
        latest_by_index = {}
        for mock_run, draft_session in rows:
            if mock_run.run_index is not None:
                latest_by_index.setdefault(mock_run.run_index, (mock_run, draft_session))
        if action == "pause":
            if batch.status in {"completed", "failed", "canceled"}:
                raise HTTPException(status_code=409, detail="This batch cannot be paused")
            batch.status = "paused"
            batch.worker_id = None
            batch.lease_expires_at = None
            for mock_run, draft_session in latest_by_index.values():
                if draft_session.status == "active":
                    draft_session.status = "paused"
                    draft_session.version += 1
                    draft_session.updated_at = datetime.now(timezone.utc)
                    mock_run.status = "paused"
                    mock_run.pick_deadline_at = None
                    await session.flush()
                    await _record_recommendation_snapshot(session, draft_session)
        elif action == "resume":
            if batch.status in {"completed", "failed", "canceled"}:
                raise HTTPException(status_code=409, detail="This batch cannot be resumed")
            batch.status = "queued"
            batch.cancel_requested = False
            batch.worker_id = None
            batch.lease_expires_at = None
        elif action == "cancel":
            if batch.status == "completed":
                raise HTTPException(status_code=409, detail="Completed batches cannot be canceled")
            batch.status = "canceled"
            batch.cancel_requested = True
            batch.canceled_at = datetime.now(timezone.utc)
            batch.worker_id = None
            batch.lease_expires_at = None
            for mock_run, draft_session in latest_by_index.values():
                mock_run.status = "canceled"
                mock_run.pick_deadline_at = None
                if draft_session.status == "active":
                    draft_session.status = "paused"
                    draft_session.version += 1
                    draft_session.updated_at = datetime.now(timezone.utc)
                    await session.flush()
                    await _record_recommendation_snapshot(session, draft_session)
        else:
            if batch.status == "running":
                raise HTTPException(status_code=409, detail="Pause the running batch before retrying failures")
            for mock_run, draft_session in latest_by_index.values():
                if mock_run.status == "failed":
                    mock_run.status = "queued"
                    if draft_session.status == "paused":
                        draft_session.status = "active"
                        draft_session.version += 1
                        draft_session.updated_at = datetime.now(timezone.utc)
                        await session.flush()
                        await _record_recommendation_snapshot(session, draft_session)
            batch.status = "queued"
            batch.cancel_requested = False
            batch.worker_id = None
            batch.lease_expires_at = None
        batch.updated_at = datetime.now(timezone.utc)
    return await get_internal_mock_batch(session, batch_id)


async def list_internal_mock_batches(session: AsyncSession) -> list[DraftMockBatchState]:
    ids = list((await session.scalars(
        select(DraftMockBatch.id).order_by(DraftMockBatch.created_at.desc())
    )).all())
    return [await get_internal_mock_batch(session, batch_id) for batch_id in ids]


async def _candidate_context(session: AsyncSession, state: DraftSessionState, board) -> tuple[
    list[MockCandidate], list[set[str]], list[dict]
]:
    drafted_ids = [pick.selected_player_id for pick in state.picks if pick.selected_player_id is not None]
    board_players = board.players
    if not board_players and state.timing.current_round is not None:
        all_ids = list((await session.scalars(
            select(LeaguePlayer.player_identity_id)
            .where(LeaguePlayer.league_key == state.league_key)
            .order_by(LeaguePlayer.player_identity_id)
        )).all())
        drafted_set = set(drafted_ids)
        available_ids_for_fallback = [player_id for player_id in all_ids if player_id not in drafted_set]
        if available_ids_for_fallback:
            fallback_result = await calculate_draft_utility(session, DraftUtilityRequest(
                league_key=state.league_key,
                team_key=state.manager_team_key,
                season=state.season,
                drafted_player_ids=drafted_ids,
                available_player_ids=available_ids_for_fallback,
                draft_position=state.draft_position,
                round_number=state.timing.current_round,
                total_teams=state.total_teams,
                recent_pick_player_ids=drafted_ids[-10:],
                mode=state.mode,
            ))
            board_players = fallback_result.ranked_players
    available_ids = [player.player_identity_id for player in board_players]
    ids = set(available_ids) | set(drafted_ids)
    identities = list((await session.scalars(
        select(PlayerIdentity).where(PlayerIdentity.id.in_(ids))
    )).all()) if ids else []
    identity_by_id = {identity.id: identity for identity in identities}
    metrics = list((await session.scalars(
        select(DraftPlayerMetric).where(
            DraftPlayerMetric.league_key == state.league_key,
            DraftPlayerMetric.season == state.season,
            DraftPlayerMetric.player_identity_id.in_(available_ids),
        )
    )).all()) if available_ids else []
    metric_by_id = {metric.player_identity_id: metric for metric in metrics}
    result = None
    if state.latest_recommendation and "primary_action" in state.latest_recommendation:
        result = DraftUtilityResult.model_validate(state.latest_recommendation)
    availability = {
        row.player_identity_id: row
        for row in result.player_availability
    } if result else {}
    candidates = []
    for row in board_players:
        identity = identity_by_id.get(row.player_identity_id)
        if identity is None:
            continue
        metric = metric_by_id.get(row.player_identity_id)
        market = availability.get(row.player_identity_id)
        positions = tuple(
            position.strip().upper()
            for position in (identity.position or "").replace("/", ",").split(",")
            if position.strip()
        )
        candidates.append(MockCandidate(
            player_id=row.player_identity_id,
            adp=(market.adp if market and market.data_freshness in {"fresh", "request"} else None),
            positions=positions,
            positional_scarcity=metric.positional_scarcity if metric else 0.0,
            fantasy_value=metric.fantasy_value if metric else 0.0,
            decision_score=row.decision_score,
        ))
    settings = await session.get(LeagueSettings, state.league_key)
    if settings is None:
        raise HTTPException(status_code=404, detail="Imported league settings were not found")
    return candidates, [
        {
            "position": slot.get("position"),
            "count": slot.get("count", 0),
            "is_starting_position": slot.get("is_starting_position", 1),
        }
        for slot in settings.roster_positions
    ], [
        {
            "team_slot": pick.team_slot,
            "positions": set(
                position.strip().upper()
                for position in (identity_by_id.get(pick.selected_player_id).position or "").replace("/", ",").split(",")
                if position.strip()
            ) if pick.selected_player_id in identity_by_id else set(),
        }
        for pick in state.picks
        if pick.selected_player_id is not None
    ]


async def _simulate_one_pick(
    session: AsyncSession,
    session_id: str,
    *,
    require_until_my_turn: bool = False,
    allow_manager_pick: bool = False,
):
    state = await get_draft_session(session, session_id)
    await session.commit()
    if state.draft_source != "internal_mock":
        raise HTTPException(status_code=409, detail="Simulation actions require an internal mock session")
    if state.browser_practice:
        raise HTTPException(status_code=409, detail="Internal simulation is disabled for Yahoo Mock Practice")
    if state.status != "active":
        return state, "draft_complete" if state.status == "completed" else "paused", False
    next_pick = state.next_overall_pick
    if next_pick > state.total_teams * state.rounds:
        return state, "draft_complete", False
    _, team_slot = _pick_slot(next_pick, state.total_teams)
    mock_run = await session.get(DraftMockRun, session_id)
    if mock_run is None:
        raise HTTPException(status_code=409, detail="Mock run metadata is missing")
    manager_turn = team_slot == state.draft_position
    if manager_turn and (require_until_my_turn or not allow_manager_pick):
        return state, "manager_turn", False

    board = await get_draft_board(session, session_id)
    state = board.session
    candidates, roster_positions, drafted_by_team = await _candidate_context(session, state, board)
    if not candidates:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No available player can be selected at overall pick {next_pick}; "
                f"the board returned {len(board.players)} candidates"
            ),
        )
    team_picks = [row["positions"] for row in drafted_by_team if row["team_slot"] == team_slot]
    recommendation = board.recommendation
    recommended = recommendation.recommended_player if recommendation else None
    candidate_ids = {candidate.player_id for candidate in candidates}
    prior_manager_pick = None
    if manager_turn:
        prior_manager_pick = await session.scalar(
            select(DraftPick)
            .where(
                DraftPick.session_id == session_id,
                DraftPick.team_key == state.manager_team_key,
                DraftPick.overall_pick < next_pick,
                DraftPick.selected_player_id.is_not(None),
            )
            .order_by(DraftPick.overall_pick.desc())
            .limit(1)
        )
    pending_wait_target = (
        prior_manager_pick.source_evidence.get("wait_target_player_id")
        if prior_manager_pick else None
    )
    if manager_turn and pending_wait_target in candidate_ids:
        selected_id = pending_wait_target
        selection_basis = "wait_target_survived"
    elif manager_turn and recommended and recommendation and recommendation.action == "wait":
        fallback_id = next((
            fallback.player_identity_id
            for fallback in recommendation.wait_analysis
            if fallback.player_identity_id in candidate_ids
        ), None)
        if fallback_id is None:
            fallback_id = next((
                candidate.player_identity_id for candidate in board.players
                if candidate.player_identity_id != recommended.player_identity_id
                and candidate.player_identity_id in candidate_ids
            ), None)
        selected_id = fallback_id or recommended.player_identity_id
        selection_basis = "wait_fallback" if fallback_id is not None else "recommendation_fallback_unavailable"
    elif manager_turn and recommended and recommended.player_identity_id in candidate_ids:
        selected_id = recommended.player_identity_id
        selection_basis = "recommendation"
    else:
        selected_id = choose_opponent_pick(
            candidates=candidates,
            roster_positions=roster_positions,
            drafted_positions=team_picks,
            overall_pick=next_pick,
            total_teams=state.total_teams,
            aggressiveness=(0.0 if manager_turn else mock_run.aggressiveness),
            seed=mock_run.seed,
        )
        selection_basis = "available_pool_fallback" if manager_turn else "opponent_policy"

    selected_candidate = next(
        candidate for candidate in candidates if candidate.player_id == selected_id
    )
    await session.commit()
    evidence = {
        "draft_source": "internal_mock",
        "actor": "manager" if manager_turn else "opponent",
        "selection_basis": selection_basis,
        "seed": mock_run.seed,
        "aggressiveness": mock_run.aggressiveness,
        "recommendation_version": state.recommendation_version,
        "recommended_player_id": recommended.player_identity_id if recommended else None,
        "recommended_utility": recommended.wait_utility_now if recommended else None,
        "recommendation_action": recommendation.action if recommendation else "insufficient_evidence",
        "predicted_survival": recommended.next_pick_survival_probability if recommended else None,
        "expected_wait_cost": recommended.expected_wait_cost if recommended else None,
        "available_count_before_pick": len(candidates),
        "opponent_selection_source": (
            "fresh_adp_plus_randomness"
            if not manager_turn and selected_candidate.adp is not None
            else "scored_board_ranking_adp_unavailable"
            if not manager_turn and selected_candidate.decision_score is not None
            else "available_pool_fallback_adp_and_score_unavailable"
            if not manager_turn
            else None
        ),
        "selection_utility": (
            recommended.wait_utility_now if recommended and selected_id == recommended.player_identity_id
            else next((fallback.utility_score for fallback in recommendation.wait_analysis
                       if fallback.player_identity_id == selected_id), None)
            if recommendation else None
        ),
    }
    if manager_turn and recommended and recommendation and recommendation.action == "wait" and selection_basis == "wait_fallback":
        evidence["wait_target_player_id"] = recommended.player_identity_id
        evidence["wait_target_utility"] = recommended.wait_utility_now
        evidence["wait_target_survival_probability"] = recommended.next_pick_survival_probability
    if pending_wait_target is not None:
        evidence["resolved_wait_target_player_id"] = pending_wait_target
        evidence["resolved_wait_target_survived"] = pending_wait_target in candidate_ids
    updated = await record_draft_pick(
        session,
        session_id,
        next_pick,
        DraftPickUpdateRequest(
            selected_player_id=selected_id,
            expected_version=state.version,
            source="internal_mock_manager" if manager_turn else "internal_mock_opponent",
            evidence=evidence,
        ),
        allow_batch_worker=True,
    )
    return updated.state, "pick_simulated", True


async def _evaluate_mock_run(session: AsyncSession, session_id: str) -> dict:
    draft_session = await session.get(DraftSession, session_id)
    if draft_session is None:
        raise HTTPException(status_code=404, detail="Draft session was not found")
    picks = list((await session.scalars(
        select(DraftPick)
        .where(DraftPick.session_id == session_id, DraftPick.selected_player_id.is_not(None))
        .order_by(DraftPick.overall_pick)
    )).all())
    manager_picks = [pick for pick in picks if pick.team_key == draft_session.manager_team_key]
    recommendations = [{
        "overall_pick": pick.overall_pick,
        "recommended_player_id": pick.source_evidence.get("recommended_player_id"),
        "selected_player_id": pick.selected_player_id,
        "decision": pick.source_evidence.get("recommendation_action"),
        "predicted_survival_probability": pick.source_evidence.get("predicted_survival"),
        "expected_wait_cost": pick.source_evidence.get("expected_wait_cost"),
        "selection_basis": pick.source_evidence.get("selection_basis"),
    } for pick in manager_picks]
    survival_outcomes = []
    wait_cost_outcomes = []
    for index, pick in enumerate(manager_picks):
        evidence = pick.source_evidence
        target_id = evidence.get("wait_target_player_id")
        if target_id is None:
            continue
        next_manager_pick = manager_picks[index + 1] if index + 1 < len(manager_picks) else None
        stop_pick = next_manager_pick.overall_pick if next_manager_pick else draft_session.total_teams * draft_session.rounds + 1
        opponents_picks = [
            later_pick for later_pick in picks
            if pick.overall_pick < later_pick.overall_pick < stop_pick
        ]
        target_survived = not any(later_pick.selected_player_id == target_id for later_pick in opponents_picks)
        if next_manager_pick is not None:
            outcome = "survived_and_selected" if target_survived and next_manager_pick.selected_player_id == target_id else (
                "survived" if target_survived else "lost_before_next_turn"
            )
            actual_cost = None
            if target_survived:
                actual_cost = 0.0 if next_manager_pick.selected_player_id == target_id else None
            else:
                next_utility = next_manager_pick.source_evidence.get("selection_utility")
                target_utility = evidence.get("wait_target_utility")
                if next_utility is not None and target_utility is not None:
                    actual_cost = round(target_utility - next_utility, 4)
        else:
            outcome = "survived_to_end" if target_survived else "lost_after_final_turn"
            actual_cost = None
        survival_outcomes.append({
            "overall_pick": pick.overall_pick,
            "player_id": target_id,
            "predicted_probability": evidence.get("wait_target_survival_probability"),
            "survived_to_next_manager_turn": target_survived if next_manager_pick else None,
            "survived_to_end": target_survived if next_manager_pick is None else None,
            "outcome": outcome,
        })
        wait_cost_outcomes.append({
            "overall_pick": pick.overall_pick,
            "player_id": target_id,
            "predicted_wait_cost": evidence.get("expected_wait_cost"),
            "realized_wait_cost": actual_cost,
            "outcome": outcome,
        })

    evaluation = {
        "manager_decision_count": len(recommendations),
        "recommendations": recommendations,
        "players_drafted": [{
            "overall_pick": pick.overall_pick,
            "team_slot": pick.team_slot,
            "player_id": pick.selected_player_id,
        } for pick in picks],
        "survival_outcomes": survival_outcomes,
        "wait_cost_outcomes": wait_cost_outcomes,
    }
    mock_run = await session.get(DraftMockRun, session_id)
    if mock_run is not None:
        mock_run.evaluation = evaluation
    await session.commit()
    return evaluation


async def simulate_internal_mock(
    session: AsyncSession,
    session_id: str,
    action: str,
    *,
    allow_batch_run: bool = False,
) -> DraftMockActionResult:
    if action not in {"next_pick", "until_my_turn", "full_draft"}:
        raise HTTPException(status_code=422, detail="Unsupported mock simulation action")
    initial = await get_draft_session(session, session_id)
    if initial.draft_source != "internal_mock":
        raise HTTPException(status_code=409, detail="Simulation actions require an internal mock session")
    if initial.browser_practice:
        raise HTTPException(status_code=409, detail="Internal simulation is disabled for Yahoo Mock Practice")
    run = await session.get(DraftMockRun, session_id)
    if run is None:
        raise HTTPException(status_code=409, detail="Mock run metadata is missing")
    if run.batch_id is not None and not allow_batch_run:
        await session.commit()
        raise HTTPException(status_code=409, detail="This mock run is controlled by its batch")
    await session.commit()
    if initial.status == "paused":
        raise HTTPException(status_code=409, detail="Mock run is paused")
    if initial.status == "completed":
        return DraftMockActionResult(state=initial, event="draft_complete", simulated_picks=0)

    run.status = "running"
    await session.commit()
    simulated = 0
    last_event = "manager_turn"
    maximum = 1 if action == "next_pick" else initial.total_teams * initial.rounds
    for _ in range(maximum):
        state, event, made_pick = await _simulate_one_pick(
            session,
            session_id,
            require_until_my_turn=action == "until_my_turn",
            allow_manager_pick=(
                action == "full_draft"
                or (allow_batch_run and run.batch_id is not None)
            ),
        )
        simulated += int(made_pick)
        last_event = event
        if event == "paused":
            break
        if state.status == "completed":
            run.status = "completed"
            await session.commit()
            await _evaluate_mock_run(session, session_id)
            last_event = "draft_complete"
            break
        if not made_pick or action == "next_pick":
            break
    else:
        state = await get_draft_session(session, session_id)

    if last_event == "draft_complete":
        run.status = "completed"
    elif last_event == "paused":
        run.status = "paused"
    else:
        run.status = "running"
    await session.commit()
    final_state = await get_draft_session(session, session_id)
    await session.commit()
    return DraftMockActionResult(
        state=final_state,
        event=last_event,
        simulated_picks=simulated,
    )


async def set_internal_mock_paused(
    session: AsyncSession,
    session_id: str,
    *,
    paused: bool,
) -> DraftSessionState:
    async with session.begin():
        draft_session = await _locked_session(session, session_id)
        if draft_session.draft_source != "internal_mock":
            raise HTTPException(status_code=409, detail="Pause controls require an internal mock session")
        if draft_session.status == "completed":
            raise HTTPException(status_code=409, detail="Completed mock drafts cannot be paused or resumed")
        run = await session.get(DraftMockRun, session_id)
        if run is None:
            raise HTTPException(status_code=409, detail="Mock run metadata is missing")
        desired = "paused" if paused else "active"
        if draft_session.status != desired:
            draft_session.status = desired
            draft_session.version += 1
            draft_session.updated_at = datetime.now(timezone.utc)
            run.status = "paused" if paused else "running"
            await session.flush()
            await _record_recommendation_snapshot(session, draft_session)
        return await _session_state(session, draft_session)


async def restart_internal_mock(session: AsyncSession, session_id: str) -> DraftSessionState:
    old_state = await get_draft_session(session, session_id)
    if old_state.browser_practice:
        raise HTTPException(status_code=409, detail="Create a new browser practice session instead of resetting")
    if old_state.draft_source != "internal_mock":
        raise HTTPException(status_code=409, detail="Reset requires an internal mock session")
    old_run = await session.get(DraftMockRun, session_id)
    if old_run is None:
        raise HTTPException(status_code=409, detail="Mock run metadata is missing")
    await session.commit()
    if old_state.status != "completed":
        old_state = await set_internal_mock_paused(session, session_id, paused=True)
    team_slots = await _team_slots_from_session(session, session_id)
    await session.commit()
    request = DraftMockCreateRequest(
        league_key=old_state.league_key,
        season=old_state.season,
        manager_team_key=old_state.manager_team_key,
        draft_position=old_state.draft_position,
        total_teams=old_state.total_teams,
        rounds=old_state.rounds,
        team_slots=team_slots,
        mode=old_state.mode,
        aggressiveness=old_run.aggressiveness,
        seed=(old_run.seed + 1) % (2**63),
        opponent_order_seed=old_run.opponent_order_seed,
        pick_timer_seconds=old_run.pick_timer_seconds,
        practice_speed=old_run.practice_speed,
        auto_pick_enabled=old_run.auto_pick_enabled,
        auto_pick_policy=old_run.auto_pick_policy,
    )
    return await create_internal_mock(
        session,
        request,
        batch_id=old_run.batch_id,
        run_index=old_run.run_index,
        attempt_index=old_run.attempt_index + 1,
        restarted_from_session_id=session_id,
    )


async def delete_internal_mock(session: AsyncSession, session_id: str) -> None:
    from app.features.draft.observer_connection import ObserverConnection

    async with session.begin():
        draft_session = await _locked_session(session, session_id)
        if draft_session.draft_source != "internal_mock":
            raise HTTPException(status_code=409, detail="Only mock sessions can be removed")
        run = await session.get(DraftMockRun, session_id)
        if run is None:
            raise HTTPException(status_code=409, detail="Mock run metadata is missing")
        if run.batch_id is not None:
            raise HTTPException(status_code=409, detail="Batch-managed mock runs cannot be removed individually")
        tracking = await session.scalar(select(ObserverConnection.id).where(
            ObserverConnection.session_id == session_id,
            ObserverConnection.active.is_(True),
        ))
        if tracking:
            raise HTTPException(status_code=409, detail="Stop Tracking before deleting this Yahoo mock")
        await session.delete(draft_session)


async def _team_slots_from_session(session: AsyncSession, session_id: str) -> dict[str, int]:
    draft_session = await session.get(DraftSession, session_id)
    return dict(draft_session.team_slots) if draft_session else {}


async def get_internal_mock_replay(
    session: AsyncSession,
    session_id: str,
    version: int,
):
    from app.features.draft.contracts import DraftReplayResponse

    current = await get_draft_session(session, session_id)
    if current.draft_source != "internal_mock":
        raise HTTPException(status_code=409, detail="Replay is available only for internal mock sessions")
    snapshot = await session.scalar(select(DraftRecommendationSnapshot).where(
        DraftRecommendationSnapshot.session_id == session_id,
        DraftRecommendationSnapshot.session_version == version,
    ))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Mock draft snapshot was not found")
    input_state = snapshot.input_state
    await session.commit()
    pick_rows = input_state.get("picks", [])
    from app.features.draft.contracts import DraftPickView, DraftSessionTiming, DraftTargetView
    from app.services.draft.sessions import _next_overall_pick, _session_timing

    picks = [DraftPickView(
        overall_pick=row["overall_pick"],
        round_number=row["round_number"],
        team_slot=row["team_slot"],
        team_key=row["team_key"],
        selected_player_id=row["selected_player_id"],
        source=row["source"],
        picked_at=row["picked_at"],
    ) for row in pick_rows]
    mock_session = await session.get(DraftSession, session_id)
    next_pick = _next_overall_pick(picks)
    replay_state = current.model_copy(update={
        "version": version,
        "next_overall_pick": next_pick,
        "timing": _session_timing(mock_session, next_pick),
        "picks": picks,
        "targets": [DraftTargetView(**row) for row in input_state.get("targets", [])],
        "latest_recommendation": snapshot.response,
        "recommendation_version": version,
        "status": "completed" if next_pick > mock_session.total_teams * mock_session.rounds else "active",
    })
    await session.commit()
    board = await get_draft_board(session, session_id, snapshot_version=version)
    total_versions = int(await session.scalar(select(DraftRecommendationSnapshot.session_version).where(
        DraftRecommendationSnapshot.session_id == session_id
    ).order_by(DraftRecommendationSnapshot.session_version.desc()).limit(1)) or 0) + 1
    return DraftReplayResponse(
        session_id=session_id,
        session_version=version,
        total_versions=total_versions,
        session=replay_state,
        board=board,
    )


MOCK_BATCH_LEASE_SECONDS = 45


async def claim_next_internal_mock_batch(
    session_factory=SessionFactory,
    worker_id: str | None = None,
) -> str | None:
    worker_id = worker_id or str(uuid4())
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        async with session.begin():
            batch = await session.scalar(
                select(DraftMockBatch)
                .where(
                    DraftMockBatch.archived_at.is_(None),
                    DraftMockBatch.cancel_requested.is_(False),
                    (
                        (DraftMockBatch.status == "queued")
                        | ((DraftMockBatch.status == "running") & (DraftMockBatch.lease_expires_at < now))
                    ),
                )
                .order_by(DraftMockBatch.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if batch is None:
                return None
            batch.status = "running"
            batch.worker_id = worker_id
            batch.heartbeat_at = now
            batch.lease_expires_at = now + timedelta(seconds=MOCK_BATCH_LEASE_SECONDS)
            batch.updated_at = now
            return batch.id


async def _batch_should_continue(session_factory, batch_id: str, worker_id: str) -> str:
    async with session_factory() as session:
        async with session.begin():
            batch = await session.scalar(
                select(DraftMockBatch).where(DraftMockBatch.id == batch_id).with_for_update()
            )
            if batch is None or batch.status == "canceled" or batch.cancel_requested:
                return "canceled"
            if batch.status == "paused":
                return "paused"
            if batch.worker_id != worker_id:
                return "lost_lease"
            now = datetime.now(timezone.utc)
            batch.heartbeat_at = now
            batch.lease_expires_at = now + timedelta(seconds=MOCK_BATCH_LEASE_SECONDS)
            batch.updated_at = now
            state = await get_internal_mock_batch(session, batch_id)
            batch.queued_runs = state.queued_runs
            batch.running_runs = state.running_runs
            batch.completed_runs = state.completed_runs
            batch.failed_runs = state.failed_runs
            batch.canceled_runs = state.canceled_runs
            return "running"


async def run_internal_mock_batch(
    batch_id: str,
    session_factory=SessionFactory,
    worker_id: str | None = None,
) -> None:
    worker_id = worker_id or str(uuid4())
    async with session_factory() as session:
        async with session.begin():
            batch = await session.scalar(
                select(DraftMockBatch).where(DraftMockBatch.id == batch_id).with_for_update()
            )
            if batch is None or batch.status in {"completed", "canceled"}:
                return
            if batch.status != "queued" and batch.status != "running":
                return
            if batch.status == "running" and batch.lease_expires_at and batch.lease_expires_at > datetime.now(timezone.utc) and batch.worker_id != worker_id:
                return
            batch.status = "running"
            batch.worker_id = worker_id
            batch.heartbeat_at = datetime.now(timezone.utc)
            batch.lease_expires_at = batch.heartbeat_at + timedelta(seconds=MOCK_BATCH_LEASE_SECONDS)

    lock_engine = getattr(session_factory, "kw", {}).get("bind") or engine
    async with lock_engine.connect() as connection:
        acquired = await connection.scalar(
            text("SELECT pg_try_advisory_lock(hashtext(:batch_id))"),
            {"batch_id": batch_id},
        )
        await connection.commit()
        if not acquired:
            return
        try:
            await _run_internal_mock_batch(batch_id, session_factory, worker_id)
        finally:
            await connection.execute(
                text("SELECT pg_advisory_unlock(hashtext(:batch_id))"),
                {"batch_id": batch_id},
            )
            await connection.commit()


async def _run_internal_mock_batch(batch_id: str, session_factory, worker_id: str) -> None:
    async with session_factory() as session:
        run_rows = list((await session.scalars(
            select(DraftMockRun)
            .where(DraftMockRun.batch_id == batch_id)
            .order_by(DraftMockRun.run_index, DraftMockRun.attempt_index.desc())
        )).all())
        latest_runs: dict[int, DraftMockRun] = {}
        for mock_run in run_rows:
            if mock_run.run_index is not None:
                latest_runs.setdefault(mock_run.run_index, mock_run)
        session_ids = [latest_runs[index].session_id for index in sorted(latest_runs)]
        await session.commit()
    for session_id in session_ids:
        while True:
            worker_state = await _batch_should_continue(session_factory, batch_id, worker_id)
            if worker_state != "running":
                async with session_factory() as session:
                    mock_run = await session.get(DraftMockRun, session_id)
                    if mock_run is not None:
                        mock_run.status = "canceled" if worker_state == "canceled" else "paused"
                        if worker_state == "paused":
                            draft_session = await _locked_session(session, session_id)
                            if draft_session.status == "active":
                                draft_session.status = "paused"
                                draft_session.version += 1
                                draft_session.updated_at = datetime.now(timezone.utc)
                                mock_run.pick_deadline_at = None
                                await session.flush()
                                await _record_recommendation_snapshot(session, draft_session)
                        await session.commit()
                if worker_state == "lost_lease":
                    return
                break
            async with session_factory() as run_session:
                mock_run = await run_session.get(DraftMockRun, session_id)
                state = await get_draft_session(run_session, session_id)
                if mock_run is None or state.status == "completed":
                    if mock_run:
                        mock_run.status = "completed"
                        await run_session.commit()
                    break
                if state.status == "paused":
                    await run_session.commit()
                    await set_internal_mock_paused(run_session, session_id, paused=False)
                else:
                    await run_session.commit()
                try:
                    await simulate_internal_mock(
                        run_session,
                        session_id,
                        "next_pick",
                        allow_batch_run=True,
                    )
                except Exception:
                    await run_session.rollback()
                    mock_run = await run_session.get(DraftMockRun, session_id)
                    if mock_run:
                        mock_run.status = "failed"
                        await run_session.commit()
                    break
    async with session_factory() as session:
        async with session.begin():
            batch = await session.scalar(
                select(DraftMockBatch).where(DraftMockBatch.id == batch_id).with_for_update()
            )
            if batch is None or batch.status in {"paused", "canceled"} or batch.worker_id != worker_id:
                return
            state = await get_internal_mock_batch(session, batch_id)
            batch.status = state.status
            batch.worker_id = None
            batch.lease_expires_at = None
            batch.heartbeat_at = datetime.now(timezone.utc)
            batch.queued_runs = state.queued_runs
            batch.running_runs = state.running_runs
            batch.completed_runs = state.completed_runs
            batch.failed_runs = state.failed_runs
            batch.canceled_runs = state.canceled_runs


async def mock_batch_worker_loop(stop_event: asyncio.Event, session_factory=SessionFactory) -> None:
    worker_id = str(uuid4())
    while not stop_event.is_set():
        batch_id = await claim_next_internal_mock_batch(session_factory, worker_id)
        if batch_id is not None:
            try:
                await run_internal_mock_batch(batch_id, session_factory, worker_id)
            except Exception:
                logger.exception("Internal mock batch worker failed for batch %s", batch_id)
            continue
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass

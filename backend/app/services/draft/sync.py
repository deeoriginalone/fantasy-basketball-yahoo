import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.draft.contracts import (
    DraftMockRehearsalActionRequest,
    DraftUtilityRequest,
    DraftSyncResult,
    DraftSyncStateView,
)
from app.features.draft.models import DraftMockRun, DraftPick, DraftPlayerMetric, DraftSession, DraftSyncState
from app.features.leagues.models import LeagueSettings, Team
from app.features.players.models import LeaguePlayer, PlayerIdentity
from app.services.draft.mock_simulation import MockCandidate, choose_opponent_pick
from app.services.draft.sessions import _pick_slot, reconcile_source_picks
from app.services.draft.utility import calculate_draft_utility
from app.services.yahoo.auth import YahooAuthService
from app.services.yahoo.client import YahooFantasyClient
from app.services.yahoo.draft_results import (
    NormalizedDraftResultPick,
    fetch_yahoo_draft_results,
    make_yahoo_draftresults_snapshot,
    normalize_yahoo_draft_results,
)

logger = logging.getLogger(__name__)


async def _view(session: AsyncSession, sync_state: DraftSyncState) -> DraftSyncStateView:
    local_recorded_through = await session.scalar(select(func.max(DraftPick.overall_pick)).where(
        DraftPick.session_id == sync_state.session_id,
        DraftPick.selected_player_id.is_not(None),
    ))
    return DraftSyncStateView(
        session_id=sync_state.session_id,
        source_type=sync_state.source_type,
        enabled=sync_state.enabled,
        paused=sync_state.paused,
        status=sync_state.status,
        last_retrieved_at=sync_state.last_retrieved_at,
        last_successful_retrieval_at=sync_state.last_successful_retrieval_at,
        source_confirmed_through=sync_state.source_confirmed_through,
        local_recorded_through=local_recorded_through or 0,
        consecutive_failures=sync_state.consecutive_failures,
        conflict_overall_pick=sync_state.conflict_overall_pick,
        conflict_evidence=sync_state.conflict_evidence,
        mock_mode=sync_state.mock_mode if sync_state.source_type == "mock_yahoo_snapshot" else None,
        mock_outage=sync_state.mock_outage if sync_state.source_type == "mock_yahoo_snapshot" else None,
        mock_hold_delivery=(
            sync_state.mock_hold_delivery
            if sync_state.source_type == "mock_yahoo_snapshot"
            else None
        ),
    )


async def get_draft_sync_state(session: AsyncSession, session_id: str) -> DraftSyncStateView:
    sync_state = await session.get(DraftSyncState, session_id)
    if sync_state is None:
        raise HTTPException(status_code=404, detail="Draft sync is not enabled for this session")
    return await _view(session, sync_state)


async def _mark_fetch_failure(
    session: AsyncSession,
    session_id: str,
    status: str,
    retrieved_at: datetime,
) -> DraftSyncResult:
    await session.commit()
    async with session.begin():
        sync_state = await session.get(DraftSyncState, session_id, with_for_update=True)
        if sync_state is None:
            raise HTTPException(status_code=404, detail="Draft sync is not enabled for this session")
        sync_state.last_retrieved_at = retrieved_at
        sync_state.consecutive_failures += 1
        sync_state.status = status
    return DraftSyncResult(sync=await get_draft_sync_state(session, session_id))


async def _mapped_source_picks(
    session: AsyncSession,
    draft_session: DraftSession,
    source_picks: list[NormalizedDraftResultPick],
) -> list[dict]:
    known_teams = set((await session.scalars(
        select(Team.team_key).where(Team.league_key == draft_session.league_key)
    )).all())
    identity_rows = list((await session.execute(
        select(PlayerIdentity.id, PlayerIdentity.yahoo_player_id)
        .join(LeaguePlayer, LeaguePlayer.player_identity_id == PlayerIdentity.id)
        .where(LeaguePlayer.league_key == draft_session.league_key)
    )).all())
    identities = {yahoo_id: int(identity_id) for identity_id, yahoo_id in identity_rows}
    mapped: list[dict] = []
    for pick in source_picks:
        if pick.team_key not in known_teams:
            raise ValueError("Draft source returned a team outside the selected Yahoo league")
        expected_round = (pick.overall_pick - 1) // draft_session.total_teams + 1
        if pick.round_number is not None and pick.round_number != expected_round:
            raise ValueError("Draft source round does not match its overall pick order")
        identity_id = identities.get(pick.yahoo_player_id)
        if identity_id is None:
            raise ValueError("Draft source returned a Yahoo player ID outside the imported league pool")
        mapped.append({
            "overall_pick": pick.overall_pick,
            "round_number": pick.round_number,
            "team_key": pick.team_key,
            "player_identity_id": identity_id,
            "source_evidence": pick.source_evidence,
        })
    return mapped


async def sync_yahoo_draft_results(
    session: AsyncSession,
    session_id: str,
    *,
    client: YahooFantasyClient | None = None,
) -> DraftSyncResult:
    draft_session = await session.get(DraftSession, session_id)
    if draft_session is None:
        raise HTTPException(status_code=404, detail="Draft session was not found")
    if draft_session.draft_source != "yahoo_live":
        raise HTTPException(status_code=409, detail="Yahoo source sync requires an explicitly linked live session")
    sync_state = await session.get(DraftSyncState, session_id)
    if sync_state is None or sync_state.source_type != "yahoo_draftresults":
        raise HTTPException(status_code=409, detail="Yahoo source sync is not enabled for this session")
    if not sync_state.enabled or sync_state.paused:
        return DraftSyncResult(sync=await _view(session, sync_state))
    await session.commit()
    session_version_before = draft_session.version

    retrieved_at = datetime.now(timezone.utc)
    try:
        access_token = await YahooAuthService(get_settings()).access_token(session)
        payload = await fetch_yahoo_draft_results(client or YahooFantasyClient(), access_token, draft_session.league_key)
    except HTTPException as error:
        status = "authentication_required" if error.status_code == 401 else "source_unavailable"
        logger.warning(
            "Yahoo draft results retrieval failed",
            extra={"event": "yahoo_draftresults_failed", "session_id": session_id, "status": status},
        )
        return await _mark_fetch_failure(session, session_id, status, retrieved_at)
    except httpx.TransportError:
        logger.exception(
            "Yahoo draft results transport failed",
            extra={"event": "yahoo_draftresults_transport_failed", "session_id": session_id},
        )
        return await _mark_fetch_failure(session, session_id, "source_unavailable", retrieved_at)

    try:
        source_picks = normalize_yahoo_draft_results(payload, retrieved_at=retrieved_at)
        mapped = await _mapped_source_picks(session, draft_session, source_picks)
    except ValueError as error:
        logger.warning(
            "Yahoo draft results payload was rejected",
            extra={"event": "yahoo_draftresults_malformed", "session_id": session_id, "reason": str(error)},
        )
        await session.commit()
        async with session.begin():
            current_state = await session.get(DraftSyncState, session_id, with_for_update=True)
            current_state.last_retrieved_at = retrieved_at
            current_state.consecutive_failures += 1
            current_state.status = "malformed_source"
        return DraftSyncResult(sync=await get_draft_sync_state(session, session_id))
    await session.commit()
    accepted, confirmed, _, _, _, _ = await reconcile_source_picks(
        session,
        session_id,
        mapped,
        retrieved_at=retrieved_at,
        source="yahoo_draftresults",
    )
    state = await get_draft_sync_state(session, session_id)
    updated_session = await session.get(DraftSession, session_id)
    return DraftSyncResult(
        sync=state,
        accepted_picks=accepted,
        confirmed_picks=confirmed,
        changed=bool(accepted) or (
            updated_session is not None and updated_session.version != session_version_before
        ),
    )


async def set_draft_sync_paused(
    session: AsyncSession,
    session_id: str,
    *,
    paused: bool,
) -> DraftSyncStateView:
    await session.commit()
    async with session.begin():
        sync_state = await session.get(DraftSyncState, session_id, with_for_update=True)
        if sync_state is None:
            raise HTTPException(status_code=404, detail="Draft sync is not enabled for this session")
        sync_state.paused = paused
        if paused:
            sync_state.status = "paused"
        elif sync_state.status == "paused":
            sync_state.status = "source_empty"
    return await get_draft_sync_state(session, session_id)


async def run_mock_sync_rehearsal(
    session: AsyncSession,
    session_id: str,
    action: str,
) -> DraftSyncResult:
    if action not in {
        "normal", "fast", "step_one_pick", "deliver_next_snapshot", "pause_source",
        "resume_source", "simulate_source_lag", "release_delayed_picks",
        "simulate_duplicate_snapshot", "simulate_multiple_picks_together",
        "simulate_source_outage", "recover_source", "simulate_local_ahead_confirmation",
        "simulate_pick_conflict", "keep_local_and_pause", "undo_latest_local",
        "simulate_malformed_source", "simulate_unknown_player", "reset_rehearsal",
    }:
        raise HTTPException(status_code=422, detail="Unsupported mock sync rehearsal action")
    draft_session = await session.get(DraftSession, session_id)
    sync_state = await session.get(DraftSyncState, session_id)
    if (
        draft_session is None
        or draft_session.draft_source != "internal_mock"
        or draft_session.draft_order_evidence.get("practice_source") == "yahoo_mock_browser"
        or sync_state is None
        or sync_state.source_type != "mock_yahoo_snapshot"
    ):
        raise HTTPException(status_code=409, detail="Mock sync rehearsal is not enabled for this session")
    run = await session.get(DraftMockRun, session_id)
    if run is None or run.batch_id is not None:
        raise HTTPException(status_code=409, detail="Mock sync rehearsal requires a single-run mock session")

    from app.services.draft.mock_drafts import restart_internal_mock
    from app.services.draft.sessions import undo_draft_pick
    from app.features.draft.contracts import DraftPickUndoRequest

    if action == "reset_rehearsal":
        await restart_internal_mock(session, session_id)
        await session.commit()
        async with session.begin():
            state = await session.get(DraftSyncState, session_id, with_for_update=True)
            state.enabled = True
            state.paused = False
            state.status = "source_empty"
            state.source_confirmed_through = 0
            state.consecutive_failures = 0
            state.conflict_overall_pick = None
            state.conflict_evidence = {}
            state.mock_mode = "normal"
            state.mock_outage = False
            state.mock_hold_delivery = False
            state.mock_generated_picks = []
            state.mock_snapshot = {}
            state.mock_snapshot_fault = None
        return DraftSyncResult(sync=await get_draft_sync_state(session, session_id))

    if action == "pause_source":
        await session.commit()
        async with session.begin():
            sync_state = await session.get(DraftSyncState, session_id, with_for_update=True)
            sync_state.paused = True
            sync_state.status = "paused"
        return DraftSyncResult(sync=await get_draft_sync_state(session, session_id))
    if action == "resume_source":
        await session.commit()
        async with session.begin():
            sync_state = await session.get(DraftSyncState, session_id, with_for_update=True)
            sync_state.paused = False
            sync_state.status = "source_empty"
        return DraftSyncResult(sync=await get_draft_sync_state(session, session_id))
    if action == "simulate_source_outage":
        await session.commit()
        async with session.begin():
            sync_state = await session.get(DraftSyncState, session_id, with_for_update=True)
            sync_state.mock_outage = True
            sync_state.status = "source_unavailable"
        return DraftSyncResult(sync=await get_draft_sync_state(session, session_id))
    if action == "recover_source":
        await session.commit()
        async with session.begin():
            sync_state = await session.get(DraftSyncState, session_id, with_for_update=True)
            sync_state.mock_outage = False
            sync_state.mock_hold_delivery = False
            sync_state.mock_snapshot_fault = None
        action = "deliver_next_snapshot"
    if action in {"normal", "fast", "step_one_pick", "simulate_multiple_picks_together", "simulate_source_lag"}:
        generated = await _generate_mock_source_picks(
            session,
            session_id,
            until_manager_turn=action != "step_one_pick" and action != "normal",
        )
        await session.commit()
        async with session.begin():
            sync_state = await session.get(DraftSyncState, session_id, with_for_update=True)
            if generated:
                sync_state.mock_generated_picks = generated
                draft_session = await session.get(DraftSession, session_id)
                sync_state.mock_snapshot = make_yahoo_draftresults_snapshot(
                    draft_session.league_key,
                    generated,
                )
            sync_state.mock_mode = (
                "step" if action == "step_one_pick" else "fast" if action in {"fast", "simulate_multiple_picks_together"} else "normal"
            )
            if action == "simulate_source_lag":
                sync_state.mock_hold_delivery = True
                sync_state.status = "source_lagging"
        if action == "simulate_source_lag":
            return DraftSyncResult(sync=await get_draft_sync_state(session, session_id))
        action = "deliver_next_snapshot"

    if action == "simulate_source_lag":
        return DraftSyncResult(sync=await get_draft_sync_state(session, session_id))
    if action == "release_delayed_picks":
        await session.commit()
        async with session.begin():
            sync_state = await session.get(DraftSyncState, session_id, with_for_update=True)
            sync_state.mock_hold_delivery = False
        action = "deliver_next_snapshot"
    if action == "simulate_local_ahead_confirmation":
        await _capture_mock_source_picks(session, session_id)
        await session.commit()
        action = "deliver_next_snapshot"
    if action == "simulate_pick_conflict":
        await _set_mock_fault(session, session_id, "conflict")
        action = "deliver_next_snapshot"
    elif action == "simulate_malformed_source":
        await _set_mock_fault(session, session_id, "malformed")
        action = "deliver_next_snapshot"
    elif action == "simulate_duplicate_snapshot":
        await _set_mock_fault(session, session_id, "duplicate")
        action = "deliver_next_snapshot"
    elif action == "simulate_unknown_player":
        await _set_mock_fault(session, session_id, "unknown_player")
        action = "deliver_next_snapshot"
    if action == "resolve_with_yahoo":
        await session.commit()
        current_sync = await session.get(DraftSyncState, session_id)
        source_payload = dict(current_sync.mock_snapshot)
        try:
            source_records = normalize_yahoo_draft_results(
                source_payload,
                retrieved_at=datetime.now(timezone.utc),
                source="mock_yahoo_snapshot",
            )
            mapped_records = await _mapped_source_picks(session, draft_session, source_records)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=f"Mock source cannot resolve the conflict: {error}") from error
        conflict_pick = current_sync.conflict_overall_pick
        source_record = next(
            (item for item in mapped_records if item["overall_pick"] == conflict_pick),
            None,
        )
        local_pick = await session.get(DraftPick, (session_id, conflict_pick)) if conflict_pick else None
        if source_record is None or local_pick is None or local_pick.selected_player_id is None:
            raise HTTPException(status_code=409, detail="The source conflict cannot be resolved as a recorded pick")
        from app.features.draft.contracts import DraftPickUpdateRequest
        from app.services.draft.sessions import correct_draft_pick

        latest_session = await session.get(DraftSession, session_id)
        await correct_draft_pick(
            session,
            session_id,
            conflict_pick,
            DraftPickUpdateRequest(
                selected_player_id=source_record["player_identity_id"],
                expected_version=latest_session.version,
                source="mock_yahoo_snapshot",
                evidence=source_record["source_evidence"],
            ),
        )
        await session.commit()
        async with session.begin():
            sync_state = await session.get(DraftSyncState, session_id, with_for_update=True)
            sync_state.mock_snapshot_fault = None
            sync_state.conflict_overall_pick = None
            sync_state.conflict_evidence = {}
        action = "deliver_next_snapshot"
    if action == "keep_local_and_pause":
        return DraftSyncResult(sync=await set_draft_sync_paused(session, session_id, paused=True))
    if action == "undo_latest_local":
        state = await session.get(DraftSession, session_id)
        latest = await session.scalar(select(func.max(DraftPick.overall_pick)).where(
            DraftPick.session_id == session_id,
            DraftPick.selected_player_id.is_not(None),
        ))
        if latest is not None:
            await undo_draft_pick(
                session,
                session_id,
                latest,
                DraftPickUndoRequest(expected_version=state.version, source="mock_rehearsal"),
            )
        await session.commit()
        action = "deliver_next_snapshot"

    if action not in {"deliver_next_snapshot", "resolve_with_yahoo"}:
        return DraftSyncResult(sync=await get_draft_sync_state(session, session_id))
    await session.commit()
    sync_state = await session.get(DraftSyncState, session_id)
    if sync_state.mock_outage:
        return DraftSyncResult(sync=await get_draft_sync_state(session, session_id))
    if sync_state.mock_hold_delivery:
        sync_state.status = "source_lagging"
        await session.commit()
        return DraftSyncResult(sync=await get_draft_sync_state(session, session_id))
    source_picks = sync_state.mock_generated_picks
    if not sync_state.mock_snapshot:
        sync_state.mock_snapshot = make_yahoo_draftresults_snapshot(
            draft_session.league_key,
            source_picks,
        )
    payload = dict(sync_state.mock_snapshot)
    fault = sync_state.mock_snapshot_fault
    if fault == "malformed":
        payload = {"fantasy_content": {"league": {"draft_results": "invalid"}}}
    elif fault == "duplicate":
        payload = _duplicate_mock_snapshot(payload)
    elif fault == "unknown_player":
        payload = _alter_mock_snapshot_player(payload, "unknown-yahoo-player-id")
    retrieved_at = datetime.now(timezone.utc)
    try:
        normalized = normalize_yahoo_draft_results(
            payload,
            retrieved_at=retrieved_at,
            source="mock_yahoo_snapshot",
        )
        mapped = await _mapped_source_picks(session, draft_session, normalized)
    except ValueError as error:
        await session.commit()
        async with session.begin():
            current = await session.get(DraftSyncState, session_id, with_for_update=True)
            current.status = "malformed_source"
            current.last_retrieved_at = retrieved_at
            current.consecutive_failures += 1
        logger.warning(
            "Mock rehearsal snapshot rejected",
            extra={"event": "mock_rehearsal_snapshot_rejected", "session_id": session_id, "reason": str(error)},
        )
        return DraftSyncResult(sync=await get_draft_sync_state(session, session_id))
    await session.commit()
    accepted, confirmed, _, _, _, _ = await reconcile_source_picks(
        session,
        session_id,
        mapped,
        retrieved_at=retrieved_at,
        source="mock_yahoo_snapshot",
    )
    await session.commit()
    async with session.begin():
        current = await session.get(DraftSyncState, session_id, with_for_update=True)
        current.mock_snapshot_fault = None
    return DraftSyncResult(
        sync=await get_draft_sync_state(session, session_id),
        accepted_picks=accepted,
        confirmed_picks=confirmed,
        changed=bool(accepted),
    )


async def _capture_mock_source_picks(session: AsyncSession, session_id: str) -> None:
    rows = list((await session.execute(
        select(
            DraftPick.overall_pick,
            DraftPick.round_number,
            DraftPick.team_key,
            PlayerIdentity.yahoo_player_id,
        )
        .join(PlayerIdentity, PlayerIdentity.id == DraftPick.selected_player_id)
        .where(
            DraftPick.session_id == session_id,
            DraftPick.selected_player_id.is_not(None),
        )
        .order_by(DraftPick.overall_pick)
    )).all())
    source_picks = [{
        "overall_pick": row.overall_pick,
        "round_number": row.round_number,
        "team_key": row.team_key,
        "yahoo_player_id": row.yahoo_player_id,
    } for row in rows]
    draft_session = await session.get(DraftSession, session_id)
    sync_state = await session.get(DraftSyncState, session_id, with_for_update=True)
    sync_state.mock_generated_picks = source_picks
    sync_state.mock_snapshot = make_yahoo_draftresults_snapshot(draft_session.league_key, source_picks)


async def _generate_mock_source_picks(
    session: AsyncSession,
    session_id: str,
    *,
    until_manager_turn: bool,
) -> list[dict[str, Any]]:
    draft_session = await session.get(DraftSession, session_id)
    sync_state = await session.get(DraftSyncState, session_id)
    if draft_session is None or sync_state is None:
        raise HTTPException(status_code=404, detail="Draft sync session was not found")
    if sync_state.mock_hold_delivery:
        return list(sync_state.mock_generated_picks)

    source_picks = [dict(pick) for pick in sync_state.mock_generated_picks]
    source_by_pick = {int(pick["overall_pick"]): pick for pick in source_picks}
    local_rows = list((await session.execute(
        select(DraftPick.overall_pick, DraftPick.round_number, DraftPick.team_key,
               DraftPick.selected_player_id, PlayerIdentity.yahoo_player_id, PlayerIdentity.position)
        .outerjoin(PlayerIdentity, PlayerIdentity.id == DraftPick.selected_player_id)
        .where(DraftPick.session_id == session_id)
        .order_by(DraftPick.overall_pick)
    )).all())
    local_by_pick = {row.overall_pick: row for row in local_rows}
    identities = list((await session.scalars(
        select(PlayerIdentity)
        .join(LeaguePlayer, LeaguePlayer.player_identity_id == PlayerIdentity.id)
        .where(LeaguePlayer.league_key == draft_session.league_key)
    )).all())
    identity_by_id = {identity.id: identity for identity in identities}
    identity_by_yahoo_id = {
        identity.yahoo_player_id: identity for identity in identities
        if identity.yahoo_player_id is not None
    }
    all_ids = sorted(identity_by_id)
    settings = await session.get(LeagueSettings, draft_session.league_key)
    if settings is None:
        raise HTTPException(status_code=404, detail="Imported league settings were not found")
    mock_run = await session.get(DraftMockRun, session_id)
    if mock_run is None:
        raise HTTPException(status_code=409, detail="Mock run metadata is missing")
    team_by_slot = {slot: team_key for team_key, slot in draft_session.team_slots.items()}
    pick_limit = draft_session.total_teams * draft_session.rounds
    pick_number = max(source_by_pick, default=0) + 1
    generated_count = 0

    while pick_number <= pick_limit:
        existing_local = local_by_pick.get(pick_number)
        round_number, team_slot = _pick_slot(pick_number, draft_session.total_teams)
        team_key = team_by_slot.get(team_slot)
        if team_key is None:
            raise HTTPException(status_code=409, detail="Draft team-slot mapping is incomplete")

        if existing_local and existing_local.selected_player_id and not existing_local.yahoo_player_id:
            break
        if existing_local and existing_local.yahoo_player_id:
            source_pick = {
                "overall_pick": pick_number,
                "round_number": round_number,
                "team_key": existing_local.team_key,
                "yahoo_player_id": existing_local.yahoo_player_id,
            }
        elif team_key == draft_session.manager_team_key:
            break
        else:
            drafted_ids = []
            drafted_positions_by_team: dict[str, list[set[str]]] = {}
            for prior in range(1, pick_number):
                source_pick = source_by_pick.get(prior)
                local_pick = local_by_pick.get(prior)
                if source_pick:
                    identity = identity_by_yahoo_id.get(source_pick["yahoo_player_id"])
                    player_id = identity.id if identity else None
                    position = identity.position if identity else None
                    prior_team = source_pick["team_key"]
                elif local_pick and local_pick.selected_player_id:
                    player_id = local_pick.selected_player_id
                    position = local_pick.position
                    prior_team = local_pick.team_key
                else:
                    continue
                if player_id is not None:
                    drafted_ids.append(player_id)
                    drafted_positions_by_team.setdefault(prior_team, []).append({
                        value.strip().upper()
                        for value in (position or "").replace("/", ",").split(",")
                        if value.strip()
                    })
            drafted_set = set(drafted_ids)
            available_ids = [player_id for player_id in all_ids if player_id not in drafted_set]
            if not available_ids:
                break
            utility = await calculate_draft_utility(session, DraftUtilityRequest(
                league_key=draft_session.league_key,
                team_key=draft_session.manager_team_key,
                season=draft_session.season,
                drafted_player_ids=drafted_ids,
                available_player_ids=available_ids,
                draft_position=draft_session.draft_position,
                round_number=round_number,
                total_teams=draft_session.total_teams,
                recent_pick_player_ids=drafted_ids[-10:],
                mode=draft_session.mode,
            ))
            rankings = {row.player_identity_id: row for row in utility.ranked_players}
            metrics = list((await session.scalars(
                select(DraftPlayerMetric).where(
                    DraftPlayerMetric.league_key == draft_session.league_key,
                    DraftPlayerMetric.season == draft_session.season,
                    DraftPlayerMetric.player_identity_id.in_(available_ids),
                )
            )).all())
            metric_by_id = {row.player_identity_id: row for row in metrics}
            availability = {row.player_identity_id: row for row in utility.player_availability}
            adp_by_id = {
                player_id: availability[player_id].adp
                for player_id in available_ids
                if player_id in availability and availability[player_id].adp is not None
            }
            candidates = []
            for player_id in available_ids:
                identity = identity_by_id.get(player_id)
                metric = metric_by_id.get(player_id)
                ranked = rankings.get(player_id)
                if not identity or not identity.yahoo_player_id or not metric or not ranked:
                    continue
                candidates.append(MockCandidate(
                    player_id=player_id,
                    adp=adp_by_id.get(player_id),
                    positions=tuple((identity.position or "").replace("/", ",").split(",")),
                    positional_scarcity=metric.positional_scarcity,
                    fantasy_value=metric.fantasy_value,
                    decision_score=ranked.decision_score,
                ))
            if not candidates:
                break
            selected_id = choose_opponent_pick(
                candidates=candidates,
                roster_positions=settings.roster_positions,
                drafted_positions=drafted_positions_by_team.get(team_key, []),
                overall_pick=pick_number,
                total_teams=draft_session.total_teams,
                aggressiveness=mock_run.aggressiveness,
                seed=mock_run.seed,
            )
            selected_candidate = next(candidate for candidate in candidates if candidate.player_id == selected_id)
            identity = identity_by_id[selected_id]
            source_pick = {
                "overall_pick": pick_number,
                "round_number": round_number,
                "team_key": team_key,
                "yahoo_player_id": identity.yahoo_player_id,
                "source_evidence": {
                    "source": "mock_opponent_policy",
                    "opponent_selection_source": (
                        "fresh_adp_plus_randomness"
                        if selected_candidate.adp is not None
                        else "scored_board_ranking_adp_unavailable"
                    ),
                    "selection_basis": "opponent_policy",
                },
            }
            generated_count += 1

        source_picks.append(source_pick)
        source_by_pick[pick_number] = source_pick
        pick_number += 1
        if not until_manager_turn and generated_count:
            break
    return source_picks


async def _set_mock_fault(session: AsyncSession, session_id: str, fault: str) -> None:
    await session.commit()
    async with session.begin():
        sync_state = await session.get(DraftSyncState, session_id, with_for_update=True)
        if fault == "conflict":
            picks = list(sync_state.mock_generated_picks)
            if not picks:
                raise HTTPException(status_code=409, detail="Simulate at least one pick before introducing a conflict")
            draft_session = await session.get(DraftSession, session_id)
            identities = list((await session.scalars(
                select(PlayerIdentity.yahoo_player_id)
                .join(LeaguePlayer, LeaguePlayer.player_identity_id == PlayerIdentity.id)
                .where(LeaguePlayer.league_key == draft_session.league_key)
            )).all())
            available_ids = set(identities) - {pick["yahoo_player_id"] for pick in picks}
            if not available_ids:
                raise HTTPException(status_code=409, detail="No unused Yahoo player is available for a conflict fixture")
            picks[0] = {**picks[0], "yahoo_player_id": sorted(available_ids)[0]}
            sync_state.mock_snapshot = make_yahoo_draftresults_snapshot(
                (await session.get(DraftSession, session_id)).league_key,
                picks,
            )
        sync_state.mock_snapshot_fault = fault


def _duplicate_mock_snapshot(payload: dict) -> dict:
    copied = dict(payload)
    fantasy = dict(copied["fantasy_content"])
    league = dict(fantasy["league"])
    collection = dict(league["draft_results"])
    records = [value for key, value in collection.items() if key != "count"]
    if not records:
        raise HTTPException(status_code=409, detail="Simulate at least one pick before duplicating a snapshot")
    collection[str(len(records))] = records[0]
    collection["count"] = len(records) + 1
    league["draft_results"] = collection
    fantasy["league"] = league
    copied["fantasy_content"] = fantasy
    return copied


def _alter_mock_snapshot_player(payload: dict, yahoo_player_id: str) -> dict:
    copied = dict(payload)
    fantasy = dict(copied["fantasy_content"])
    league = dict(fantasy["league"])
    collection = dict(league["draft_results"])
    record_key = next((key for key in collection if key != "count"), None)
    if record_key is not None:
        wrapper = dict(collection[record_key])
        record = dict(wrapper["draft_result"])
        record["player_key"] = f"nba.p.{yahoo_player_id}"
        wrapper["draft_result"] = record
        collection[record_key] = wrapper
    league["draft_results"] = collection
    fantasy["league"] = league
    copied["fantasy_content"] = fantasy
    return copied

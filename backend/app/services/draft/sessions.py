from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.draft.contracts import (
    DraftBoardView,
    DraftPickUndoRequest,
    DraftPickUpdateRequest,
    DraftPickView,
    DraftSessionCreateRequest,
    DraftLiveSessionCreateRequest,
    DraftOrderUpdateRequest,
    DraftSessionEventResult,
    DraftSessionState,
    DraftSessionTiming,
    DraftRecommendationView,
    DraftTargetRequest,
    DraftTargetView,
    DraftUtilityResult,
    DraftUtilityRequest,
)
from app.features.draft.models import (
    DraftMarketData,
    DraftMockRun,
    DraftPick,
    DraftPickEvent,
    DraftRecommendationSnapshot as DraftRecommendationSnapshotModel,
    DraftSession,
    DraftSyncState,
    DraftTarget as DraftTargetModel,
)
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.players.models import LeaguePlayer, PlayerIdentity
from app.services.draft.market_sync import MARKET_STALE_AFTER
from app.services.draft.utility import ROSTER_FIT_VERSION, build_draft_roster, calculate_draft_utility


def _next_overall_pick(picks: list[DraftPick]) -> int:
    selected = {pick.overall_pick for pick in picks if pick.selected_player_id is not None}
    overall_pick = 1
    while overall_pick in selected:
        overall_pick += 1
    return overall_pick


def _pick_slot(overall_pick: int, total_teams: int) -> tuple[int, int]:
    round_number = (overall_pick - 1) // total_teams + 1
    pick_in_round = (overall_pick - 1) % total_teams + 1
    team_slot = pick_in_round if round_number % 2 else total_teams - pick_in_round + 1
    return round_number, team_slot


def _session_timing(draft_session: DraftSession, current_pick: int) -> DraftSessionTiming:
    if draft_session.draft_position is None:
        return DraftSessionTiming(
            current_pick=None,
            next_pick=None,
            current_round=None,
            next_round=None,
            picks_until_next=None,
            your_turn=None,
            current_team_key=None,
        )
    current_round = (current_pick - 1) // draft_session.total_teams + 1
    current_slot = _pick_slot(current_pick, draft_session.total_teams)[1]
    current_team_key = (
        next(
            (key for key, slot in draft_session.team_slots.items() if slot == current_slot),
            None,
        )
        if current_pick <= draft_session.rounds * draft_session.total_teams
        else None
    )
    next_pick = current_pick
    while next_pick <= draft_session.rounds * draft_session.total_teams:
        round_number, team_slot = _pick_slot(next_pick, draft_session.total_teams)
        if team_slot == draft_session.draft_position:
            return DraftSessionTiming(
                current_pick=current_pick,
                next_pick=next_pick,
                current_round=current_round,
                next_round=round_number,
                picks_until_next=next_pick - current_pick,
                your_turn=current_slot == draft_session.draft_position,
                current_team_key=current_team_key,
            )
        next_pick += 1
    return DraftSessionTiming(
        current_pick=current_pick if current_pick <= draft_session.rounds * draft_session.total_teams else None,
        next_pick=None,
        current_round=current_round if current_pick <= draft_session.rounds * draft_session.total_teams else None,
        next_round=None,
        picks_until_next=None,
        your_turn=False,
        current_team_key=None,
    )


def _order_status(team_slots: dict[str, int], total_teams: int) -> str:
    if len(team_slots) == total_teams:
        return "confirmed"
    return "partial" if team_slots else "unresolved"


async def _locked_session(session: AsyncSession, session_id: str) -> DraftSession:
    draft_session = await session.scalar(
        select(DraftSession).where(DraftSession.id == session_id).with_for_update()
    )
    if draft_session is None:
        raise HTTPException(status_code=404, detail="Draft session was not found")
    return draft_session


def _mask_expired_market_data(
    result: DraftUtilityResult,
    market_data_as_of_by_player: dict[str, str],
    now: datetime,
) -> tuple[DraftUtilityResult, set[int], set[int]]:
    stale_player_ids: set[int] = set()
    unknown_player_ids: set[int] = set()
    for player in result.player_availability:
        if player.next_pick_survival_probability is None:
            continue
        raw_as_of = market_data_as_of_by_player.get(str(player.player_identity_id))
        if raw_as_of is None:
            unknown_player_ids.add(player.player_identity_id)
            continue
        try:
            as_of = datetime.fromisoformat(raw_as_of)
        except ValueError:
            unknown_player_ids.add(player.player_identity_id)
            continue
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        if now - as_of > MARKET_STALE_AFTER:
            stale_player_ids.add(player.player_identity_id)

    wait_cost_blocked = bool(stale_player_ids or unknown_player_ids)
    availability = []
    for player in result.player_availability:
        blocked_id = player.player_identity_id in stale_player_ids | unknown_player_ids
        update = {}
        if blocked_id:
            update.update(
                next_pick_survival_probability=None,
                availability_score=None,
                miss_risk_score=None,
                survival_confidence="unknown",
                data_freshness=(
                    "stale" if player.player_identity_id in stale_player_ids else "unknown"
                ),
                draft_now=None,
                safe_to_wait=None,
                decision_action="insufficient_evidence",
                decision_confidence="unavailable",
                blocker=(
                    "ADP data is stale"
                    if player.player_identity_id in stale_player_ids
                    else "ADP freshness was not recorded for this recommendation"
                ),
            )
        if wait_cost_blocked:
            update.update(
                opportunity_cost_if_wait=None,
                decision_action="insufficient_evidence",
                decision_confidence="unavailable",
                explanation=(
                    "ADP data is stale; survival and expected wait cost are unavailable."
                    if player.player_identity_id in stale_player_ids
                    else "Expected wait cost is unavailable because current survival inputs are incomplete."
                ),
            )
        availability.append(player.model_copy(update=update))

    ranked_players = []
    for player in result.ranked_players:
        update = {}
        if player.player_identity_id in stale_player_ids:
            quality = {**player.data_quality, "survival": "stale"}
            update.update(
                survival_probability=None,
                miss_risk_score=None,
                survival_confidence="unknown",
                data_freshness="stale",
                decision_action="insufficient_evidence",
                data_quality=quality,
            )
        elif player.player_identity_id in unknown_player_ids:
            quality = {**player.data_quality, "survival": "unknown"}
            update.update(
                survival_probability=None,
                miss_risk_score=None,
                survival_confidence="unknown",
                data_freshness="unknown",
                decision_action="insufficient_evidence",
                data_quality=quality,
            )
        else:
            quality = player.data_quality
        if wait_cost_blocked:
            wait_quality = "stale" if stale_player_ids else "unknown"
            update.update(
                expected_wait_cost=None,
                decision_action="insufficient_evidence",
                data_quality={
                    **quality,
                    "decision": "insufficient_evidence",
                    "wait_cost": wait_quality,
                },
            )
        ranked_players.append(player.model_copy(update=update))

    def mask_pick(pick):
        if pick is None:
            return None
        update = {}
        if pick.player_identity_id in stale_player_ids:
            update.update(
                next_pick_survival_probability=None,
                miss_risk_score=None,
                availability_score=None,
                survival_confidence="unknown",
                data_freshness="stale",
            )
        elif pick.player_identity_id in unknown_player_ids:
            update.update(
                next_pick_survival_probability=None,
                miss_risk_score=None,
                availability_score=None,
                survival_confidence="unknown",
                data_freshness="unknown",
            )
        if wait_cost_blocked:
            update.update(
                expected_fallback_utility=None,
                expected_wait_utility=None,
                expected_wait_cost=None,
                opportunity_cost_if_wait=None,
                wait_fallbacks=[],
                decision_action="insufficient_evidence",
                decision_confidence="unavailable",
                draft_now=None,
                safe_to_wait=None,
                wait_cost_method="unavailable",
                reasons=[
                    *[
                        reason for reason in pick.reasons
                        if not reason.startswith((
                            "ADP impact:",
                            "Survival impact:",
                            "Conditional utility at stake if gone:",
                            "Survival confidence:",
                            "Expected wait utility",
                            "Decision: Draft now;",
                            "Decision: Wait;",
                        ))
                    ],
                    "Survival or fallback ADP freshness is unavailable; wait cost is not current.",
                ],
            )
        return pick.model_copy(update=update)

    if not wait_cost_blocked:
        return result, stale_player_ids, unknown_player_ids
    return result.model_copy(update={
        "primary_action": "insufficient_evidence",
        "decision_confidence": "unavailable",
        "player_availability": availability,
        "ranked_players": ranked_players,
        "best_pick": mask_pick(result.best_pick),
        "best_value_before_next_pick": None,
    }), stale_player_ids, unknown_player_ids


async def _session_state(session: AsyncSession, draft_session: DraftSession) -> DraftSessionState:
    picks = list((await session.scalars(
        select(DraftPick)
        .where(DraftPick.session_id == draft_session.id)
        .order_by(DraftPick.overall_pick)
    )).all())
    targets = list((await session.scalars(
        select(DraftTargetModel)
        .where(DraftTargetModel.session_id == draft_session.id)
        .order_by(DraftTargetModel.player_id)
    )).all())
    snapshot = await session.scalar(
        select(DraftRecommendationSnapshotModel)
        .where(DraftRecommendationSnapshotModel.session_id == draft_session.id)
        .order_by(DraftRecommendationSnapshotModel.session_version.desc())
        .limit(1)
    )
    latest_recommendation = snapshot.response if snapshot else None
    if latest_recommendation and "primary_action" in latest_recommendation:
        result = DraftUtilityResult.model_validate(latest_recommendation)
        result, _, _ = _mask_expired_market_data(
            result,
            snapshot.input_state.get("market_data_as_of_by_player", {}),
            datetime.now(timezone.utc),
        )
        latest_recommendation = result.model_dump(mode="json")
    mock_run = (
        await session.get(DraftMockRun, draft_session.id)
        if draft_session.draft_source == "internal_mock"
        else None
    )
    sync_state = await session.get(DraftSyncState, draft_session.id)
    return DraftSessionState(
        session_id=draft_session.id,
        league_key=draft_session.league_key,
        season=draft_session.season,
        manager_team_key=draft_session.manager_team_key,
        draft_position=draft_session.draft_position,
        total_teams=draft_session.total_teams,
        rounds=draft_session.rounds,
        team_slots=draft_session.team_slots,
        draft_order_status=draft_session.draft_order_status,
        draft_order_evidence=draft_session.draft_order_evidence,
        status=draft_session.status,
        session_type="mock" if draft_session.draft_source == "internal_mock" else "live",
        draft_source=draft_session.draft_source,
        sync_enabled=sync_state is not None and sync_state.enabled,
        browser_practice=draft_session.draft_order_evidence.get("practice_source") == "yahoo_mock_browser",
        mock_aggressiveness=mock_run.aggressiveness if mock_run else None,
        mock_seed=mock_run.seed if mock_run else None,
        mock_batch_id=mock_run.batch_id if mock_run else None,
        mock_run_index=mock_run.run_index if mock_run else None,
        mock_attempt_index=mock_run.attempt_index if mock_run else None,
        mock_run_status=mock_run.status if mock_run else None,
        mock_evaluation=mock_run.evaluation if mock_run else None,
        mock_generated_team_slots=mock_run.generated_team_slots if mock_run else None,
        mock_opponent_order_seed=mock_run.opponent_order_seed if mock_run else None,
        pick_deadline_at=mock_run.pick_deadline_at if mock_run else None,
        pick_timer_seconds=mock_run.pick_timer_seconds if mock_run else None,
        pick_timer_source=mock_run.pick_timer_source if mock_run else None,
        auto_pick_enabled=mock_run.auto_pick_enabled if mock_run else None,
        auto_pick_policy=mock_run.auto_pick_policy if mock_run else None,
        practice_speed=mock_run.practice_speed if mock_run else None,
        archived_at=draft_session.archived_at,
        mode=draft_session.mode,
        version=draft_session.version,
        next_overall_pick=_next_overall_pick(picks),
        timing=_session_timing(draft_session, _next_overall_pick(picks)),
        picks=[DraftPickView(
            overall_pick=pick.overall_pick,
            round_number=pick.round_number,
            team_slot=pick.team_slot,
            team_key=pick.team_key,
            selected_player_id=pick.selected_player_id,
            source=pick.source,
            picked_at=pick.picked_at.isoformat() if pick.picked_at else None,
            selection_basis=pick.source_evidence.get("selection_basis"),
            selection_source=pick.source_evidence.get("opponent_selection_source"),
        ) for pick in picks],
        targets=[DraftTargetView(
            player_id=target.player_id,
            status=target.status,
            note=target.note,
        ) for target in targets],
        latest_recommendation=latest_recommendation,
        recommendation_version=snapshot.session_version if snapshot else None,
    )


async def _record_recommendation_snapshot(
    session: AsyncSession,
    draft_session: DraftSession,
) -> None:
    picks = list((await session.scalars(
        select(DraftPick)
        .where(
            DraftPick.session_id == draft_session.id,
            DraftPick.selected_player_id.is_not(None),
        )
        .order_by(DraftPick.overall_pick)
    )).all())
    drafted_ids = [pick.selected_player_id for pick in picks if pick.selected_player_id is not None]
    manager_drafted_ids = [
        pick.selected_player_id for pick in picks
        if pick.team_key == draft_session.manager_team_key and pick.selected_player_id is not None
    ]
    all_player_ids = list((await session.scalars(
        select(LeaguePlayer.player_identity_id)
        .where(LeaguePlayer.league_key == draft_session.league_key)
        .order_by(LeaguePlayer.player_identity_id)
    )).all())
    targets = list((await session.scalars(
        select(DraftTargetModel)
        .where(DraftTargetModel.session_id == draft_session.id)
        .order_by(DraftTargetModel.player_id)
    )).all())
    drafted_set = set(drafted_ids)
    available_ids = [player_id for player_id in all_player_ids if player_id not in drafted_set]
    input_state = {
        "session_id": draft_session.id,
        "session_version": draft_session.version,
        "draft_source": draft_session.draft_source,
        "status": draft_session.status,
        "league_key": draft_session.league_key,
        "season": draft_session.season,
        "manager_team_key": draft_session.manager_team_key,
        "draft_position": draft_session.draft_position,
        "total_teams": draft_session.total_teams,
        "rounds": draft_session.rounds,
        "mode": draft_session.mode,
        "team_slots": draft_session.team_slots,
        "draft_order_status": draft_session.draft_order_status,
        "draft_order_evidence": draft_session.draft_order_evidence,
        "targets": [{
            "player_id": target.player_id,
            "status": target.status,
            "note": target.note,
        } for target in targets],
        "drafted_player_ids": drafted_ids,
        "manager_drafted_player_ids": manager_drafted_ids,
        "available_player_ids": available_ids,
        "picks": [{
            "overall_pick": pick.overall_pick,
            "round_number": pick.round_number,
            "team_slot": pick.team_slot,
            "team_key": pick.team_key,
            "selected_player_id": pick.selected_player_id,
            "source": pick.source,
            "picked_at": pick.picked_at.isoformat() if pick.picked_at else None,
            "source_evidence": pick.source_evidence,
        } for pick in picks],
        "available_player_count": len(available_ids),
        "pick_count": len(picks),
    }

    if not available_ids:
        response = {
            "status": "draft_complete",
            "recommendation": None,
            "reason_code": "NO_AVAILABLE_PLAYERS",
            "message": "No unselected Yahoo league-pool players remain.",
        }
        recommendation_player_id = None
    elif draft_session.draft_position is None:
        response = {
            "status": "manager_position_required",
            "recommendation": None,
            "reason_code": "MANAGER_POSITION_REQUIRED",
            "message": "Set your Yahoo draft position to enable turn timing and recommendations.",
        }
        recommendation_player_id = None
    else:
        next_overall = _next_overall_pick(picks)
        manager_round = next((
            round_number
            for round_number in range(1, draft_session.rounds + 1)
            if ((round_number - 1) * draft_session.total_teams
                + (draft_session.draft_position if round_number % 2
                   else draft_session.total_teams - draft_session.draft_position + 1)) >= next_overall
        ), None)
        if manager_round is None:
            if draft_session.draft_source == "internal_mock" and next_overall <= draft_session.total_teams * draft_session.rounds:
                utility_request = DraftUtilityRequest(
                    league_key=draft_session.league_key,
                    team_key=draft_session.manager_team_key,
                    season=draft_session.season,
                    drafted_player_ids=drafted_ids,
                    available_player_ids=available_ids,
                    recent_pick_player_ids=drafted_ids[-10:],
                    mode=draft_session.mode,
                )
                result = await calculate_draft_utility(
                    session, utility_request,
                    manager_drafted_player_ids=manager_drafted_ids,
                )
                response = result.model_dump(mode="json")
                input_state["market_data_as_of_by_player"] = {
                    str(player.player_identity_id): player.market_data_as_of.isoformat()
                    for player in result.player_availability
                    if player.market_data_as_of is not None
                }
                recommendation_player_id = (
                    result.best_pick.player_identity_id if result.best_pick else None
                )
            else:
                response = {
                    "status": "draft_complete",
                    "recommendation": None,
                    "reason_code": "DRAFT_ROUNDS_COMPLETE",
                    "message": "The configured draft rounds are complete.",
                }
                recommendation_player_id = None
        else:
            utility_request = DraftUtilityRequest(
                league_key=draft_session.league_key,
                team_key=draft_session.manager_team_key,
                season=draft_session.season,
                drafted_player_ids=drafted_ids,
                available_player_ids=available_ids,
                draft_position=draft_session.draft_position,
                round_number=manager_round,
                total_teams=draft_session.total_teams,
                recent_pick_player_ids=drafted_ids[-10:],
                mode=draft_session.mode,
            )
            result = await calculate_draft_utility(
                session, utility_request,
                manager_drafted_player_ids=manager_drafted_ids,
            )
            response = result.model_dump(mode="json")
            input_state["market_data_as_of_by_player"] = {
                str(player.player_identity_id): player.market_data_as_of.isoformat()
                for player in result.player_availability
                if player.market_data_as_of is not None
            }
            recommendation_player_id = (
                result.best_pick.player_identity_id if result.best_pick else None
            )

    session.add(DraftRecommendationSnapshotModel(
        session_id=draft_session.id,
        session_version=draft_session.version,
        recommendation_player_id=recommendation_player_id,
        input_state=input_state,
        response=response,
    ))


async def create_draft_session(
    session: AsyncSession,
    request: DraftSessionCreateRequest | DraftLiveSessionCreateRequest,
    *,
    draft_source: str = "manual",
    mock_run_config: dict | None = None,
    initial_snapshot_template: DraftRecommendationSnapshotModel | None = None,
) -> DraftSessionEventResult:
    if draft_source not in {"manual", "internal_mock", "yahoo_live"}:
        raise ValueError("Unsupported draft session source")
    if (draft_source == "internal_mock") != (mock_run_config is not None):
        raise ValueError("Internal mock sessions require mock run configuration")
    async with session.begin():
        league = await session.get(League, request.league_key)
        if league is None:
            raise HTTPException(status_code=404, detail="Imported Yahoo league was not found")
        settings = await session.get(LeagueSettings, request.league_key)
        if settings is None:
            raise HTTPException(status_code=409, detail="Imported Yahoo league settings are required")
        teams = list((await session.scalars(
            select(Team).where(Team.league_key == request.league_key)
        )).all())
        team_keys = {team.team_key for team in teams}
        if len(teams) != request.total_teams:
            raise HTTPException(status_code=422, detail="total_teams must match the imported Yahoo league")
        if request.manager_team_key not in team_keys:
            raise HTTPException(status_code=404, detail="Manager team was not found in the selected league")
        team_slots = dict(request.team_slots)
        if draft_source == "yahoo_live":
            if not set(team_slots).issubset(team_keys):
                raise HTTPException(status_code=422, detail="team_slots contains a team outside the selected league")
            if any(not 1 <= slot <= request.total_teams for slot in team_slots.values()):
                raise HTTPException(status_code=422, detail="team_slots contains an invalid draft position")
            if len(set(team_slots.values())) != len(team_slots):
                raise HTTPException(status_code=422, detail="team_slots must use unique draft positions")
            if request.draft_position is not None:
                existing_manager_slot = team_slots.get(request.manager_team_key)
                if existing_manager_slot not in (None, request.draft_position):
                    raise HTTPException(status_code=422, detail="Manager team slot does not match draft_position")
                if existing_manager_slot is None:
                    slot_owner = next(
                        (key for key, slot in team_slots.items() if slot == request.draft_position),
                        None,
                    )
                    if slot_owner is not None:
                        raise HTTPException(
                            status_code=422,
                            detail="draft_position is already assigned to another Yahoo team",
                        )
                team_slots[request.manager_team_key] = request.draft_position
        elif (
            len(team_slots) != request.total_teams
            or set(team_slots) != team_keys
            or request.draft_position is None
        ):
            raise HTTPException(
                status_code=422,
                detail="team_slots must map every imported Yahoo team and total_teams must match",
            )
        if request.draft_position is not None and team_slots.get(request.manager_team_key) != request.draft_position:
            slot_owner = next(
                (key for key, slot in team_slots.items() if slot == request.draft_position),
                None,
            )
            if slot_owner is not None and slot_owner != request.manager_team_key:
                raise HTTPException(
                    status_code=422,
                    detail="draft_position is already assigned to another Yahoo team",
                )
            raise HTTPException(status_code=422, detail="manager_team_key must map to draft_position")
        if league.season is not None and str(league.season) != request.season[:4]:
            raise HTTPException(status_code=422, detail="season does not match the imported Yahoo league")

        draft_session = DraftSession(
            id=str(uuid4()),
            league_key=request.league_key,
            season=request.season,
            manager_team_key=request.manager_team_key,
            draft_position=request.draft_position,
            total_teams=request.total_teams,
            rounds=request.rounds,
            status="active",
            draft_source=draft_source,
            mode=request.mode,
            team_slots=team_slots,
            draft_order_status=(
                "confirmed" if len(team_slots) == request.total_teams
                else "partial" if team_slots else "unresolved"
            ),
            draft_order_evidence={
                **({"practice_source": "yahoo_mock_browser"} if (
                    draft_source == "internal_mock" and mock_run_config
                    and mock_run_config.get("practice_source") == "yahoo_mock_browser"
                    and request.league_key.startswith("yahoo-mock-practice.")
                ) else {}),
                "slots": {
                    str(slot): {
                        "team_key": team_key,
                        "source": "setup",
                    }
                    for team_key, slot in team_slots.items()
                }
            },
            version=0,
        )
        session.add(draft_session)
        await session.flush()
        if draft_source == "yahoo_live" or (
            draft_source == "internal_mock" and mock_run_config and mock_run_config.get("live_sync_rehearsal")
        ):
            session.add(DraftSyncState(
                session_id=draft_session.id,
                source_type=(
                    "mock_yahoo_snapshot" if draft_source == "internal_mock"
                    else "yahoo_draftresults"
                ),
                status="source_empty",
            ))
        if mock_run_config is not None:
            session.add(DraftMockRun(
                session_id=draft_session.id,
                batch_id=mock_run_config.get("batch_id"),
                run_index=mock_run_config.get("run_index"),
                attempt_index=mock_run_config.get("attempt_index", 0),
                restarted_from_session_id=mock_run_config.get("restarted_from_session_id"),
                seed=mock_run_config["seed"],
                aggressiveness=mock_run_config["aggressiveness"],
                status="queued",
                opponent_order_seed=mock_run_config.get("opponent_order_seed", mock_run_config["seed"]),
                generated_team_slots=mock_run_config.get("generated_team_slots", team_slots),
                pick_timer_seconds=mock_run_config.get("pick_timer_seconds"),
                pick_timer_source=mock_run_config.get("pick_timer_source", "not_applicable"),
                practice_speed=mock_run_config.get("practice_speed", "realistic"),
                auto_pick_enabled=mock_run_config.get("auto_pick_enabled", False),
                auto_pick_policy=mock_run_config.get("auto_pick_policy", "recommended"),
            ))
        if initial_snapshot_template is None:
            await _record_recommendation_snapshot(session, draft_session)
        else:
            input_state = dict(initial_snapshot_template.input_state)
            input_state["session_id"] = draft_session.id
            input_state["session_version"] = draft_session.version
            session.add(DraftRecommendationSnapshotModel(
                session_id=draft_session.id,
                session_version=draft_session.version,
                recommendation_player_id=initial_snapshot_template.recommendation_player_id,
                input_state=input_state,
                response=initial_snapshot_template.response,
            ))
        state = await _session_state(session, draft_session)
    return DraftSessionEventResult(state=state, event="created")


async def update_live_draft_order(
    session: AsyncSession,
    session_id: str,
    request: DraftOrderUpdateRequest,
) -> DraftSessionState:
    async with session.begin():
        draft_session = await _locked_session(session, session_id)
        if draft_session.draft_source != "yahoo_live":
            raise HTTPException(status_code=409, detail="Order resolution is only available for Live Draft sessions")
        _check_version(draft_session, request.expected_version)
        teams = set((await session.scalars(
            select(Team.team_key).where(Team.league_key == draft_session.league_key)
        )).all())
        team_slots = {} if request.replace_mapping else dict(draft_session.team_slots)
        if not set(request.team_slots).issubset(teams):
            raise HTTPException(status_code=422, detail="team_slots contains a team outside the selected league")
        if request.replace_mapping:
            team_slots.update(request.team_slots)
        else:
            for team_key, slot in request.team_slots.items():
                team_slots[team_key] = slot
        if any(not 1 <= slot <= draft_session.total_teams for slot in team_slots.values()):
            raise HTTPException(status_code=422, detail="team_slots contains an invalid draft position")
        if len(set(team_slots.values())) != len(team_slots):
            raise HTTPException(status_code=409, detail="A draft slot is assigned to more than one Yahoo team")
        if request.clear_manager_position:
            draft_position = None
        elif request.draft_position is not None:
            draft_position = request.draft_position
        else:
            draft_position = draft_session.draft_position
        manager_slot = team_slots.get(draft_session.manager_team_key)
        if manager_slot is not None and manager_slot != draft_position:
            raise HTTPException(status_code=409, detail="Manager slot conflicts with the selected draft position")
        if draft_position is not None and manager_slot is None:
            slot_owner = next(
                (key for key, slot in team_slots.items() if slot == draft_position),
                None,
            )
            if slot_owner is not None:
                raise HTTPException(
                    status_code=409,
                    detail="Selected manager position is already assigned to another Yahoo team",
                )
            team_slots[draft_session.manager_team_key] = draft_position

        order_evidence = dict(draft_session.draft_order_evidence or {})
        slot_evidence = dict(order_evidence.get("slots", {}))
        for team_key, slot in request.team_slots.items():
            key = str(slot)
            prior_evidence = slot_evidence.get(key)
            slot_evidence[key] = {
                **(prior_evidence if isinstance(prior_evidence, dict) else {}),
                "resolved_team_key": team_key,
                "manual_resolution": {
                    "team_key": team_key,
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                },
            }
        if draft_position is not None and team_slots.get(draft_session.manager_team_key) == draft_position:
            slot_evidence.setdefault(str(draft_position), {
                "team_key": draft_session.manager_team_key,
                "source": "manager_position_selection",
            })
        if request.team_slots or request.replace_mapping or request.clear_manager_position:
            order_evidence["manual_resolution"] = {
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "team_slots": team_slots,
                "draft_position": draft_position,
            }
        draft_session.team_slots = team_slots
        draft_session.draft_position = draft_position
        draft_session.draft_order_status = _order_status(team_slots, draft_session.total_teams)
        draft_session.draft_order_evidence = {**order_evidence, "slots": slot_evidence}
        draft_session.version += 1
        draft_session.updated_at = datetime.now(timezone.utc)
        await session.flush()
        await _record_recommendation_snapshot(session, draft_session)
        sync_state = await session.get(DraftSyncState, session_id, with_for_update=True)
        if (
            sync_state is not None
            and sync_state.status == "conflict"
            and sync_state.conflict_evidence.get("reason") in {
                "team_assigned_multiple_slots",
                "first_round_slot_conflict",
                "manager_position_mismatch",
                "snake_order_mismatch",
            }
        ):
            sync_state.status = "source_empty"
            sync_state.conflict_overall_pick = None
            sync_state.conflict_evidence = {}
        return await _session_state(session, draft_session)


async def get_draft_session(session: AsyncSession, session_id: str) -> DraftSessionState:
    draft_session = await session.get(DraftSession, session_id)
    if draft_session is None:
        raise HTTPException(status_code=404, detail="Draft session was not found")
    return await _session_state(session, draft_session)


async def list_draft_sessions(
    session: AsyncSession,
    *,
    draft_source: str | None = None,
) -> list[DraftSessionState]:
    statement = select(DraftSession)
    if draft_source is None:
        statement = statement.where(DraftSession.draft_source != "internal_mock")
    else:
        statement = statement.where(DraftSession.draft_source == draft_source)
        if draft_source == "internal_mock":
            statement = statement.join(
                DraftMockRun,
                DraftMockRun.session_id == DraftSession.id,
            ).where(DraftMockRun.batch_id.is_(None))
    draft_sessions = list((await session.scalars(
        statement.order_by(DraftSession.updated_at.desc(), DraftSession.created_at.desc())
    )).all())
    return [await _session_state(session, draft_session) for draft_session in draft_sessions]


async def get_draft_board(
    session: AsyncSession,
    session_id: str,
    *,
    sort_by: str = "decision",
    descending: bool = True,
    snapshot_version: int | None = None,
) -> DraftBoardView:
    async with session.begin():
        draft_session = await _locked_session(session, session_id)
        state = await _session_state(session, draft_session)
        if snapshot_version is not None:
            snapshot = await session.scalar(select(DraftRecommendationSnapshotModel).where(
                DraftRecommendationSnapshotModel.session_id == session_id,
                DraftRecommendationSnapshotModel.session_version == snapshot_version,
            ))
            if snapshot is None:
                raise HTTPException(status_code=404, detail="Draft snapshot was not found")
            input_state = snapshot.input_state
            historical_picks = [DraftPickView(
                overall_pick=pick["overall_pick"],
                round_number=pick["round_number"],
                team_slot=pick["team_slot"],
                team_key=pick["team_key"],
                selected_player_id=pick["selected_player_id"],
                source=pick["source"],
                picked_at=pick["picked_at"],
                selection_basis=pick.get("source_evidence", {}).get("selection_basis"),
                selection_source=pick.get("source_evidence", {}).get("opponent_selection_source"),
            ) for pick in input_state.get("picks", [])]
            historical_targets = [DraftTargetView(**target) for target in input_state.get("targets", [])]
            historical_next = _next_overall_pick(historical_picks)
            state = state.model_copy(update={
                "version": snapshot_version,
                "next_overall_pick": historical_next,
                "timing": _session_timing(draft_session, historical_next),
                "picks": historical_picks,
                "targets": historical_targets,
                "latest_recommendation": snapshot.response,
                "recommendation_version": snapshot_version,
                "status": (
                    "completed"
                    if historical_next > draft_session.total_teams * draft_session.rounds
                    else "active"
                ),
            })
        manager_player_ids = [
            pick.selected_player_id for pick in state.picks
            if pick.team_key == state.manager_team_key and pick.selected_player_id is not None
        ]
        roster = await build_draft_roster(session, state.league_key, manager_player_ids)
        raw_recommendation = state.latest_recommendation
        if not raw_recommendation or "primary_action" not in raw_recommendation:
            return DraftBoardView(session=state, recommendation=None, players=[], roster=roster)

        recommendation_result = DraftUtilityResult.model_validate(raw_recommendation)
        board_result = recommendation_result
        current_statuses = dict((await session.execute(
            select(PlayerIdentity.id, PlayerIdentity.status).where(
                PlayerIdentity.id.in_([player.player_identity_id for player in recommendation_result.ranked_players])
            )
        )).all()) if snapshot_version is None else {}
        status_policy_changed = snapshot_version is None and any(
            not player.get("yahoo_status_reason")
            or player.get("yahoo_status") != current_statuses.get(player["player_identity_id"])
            for player in raw_recommendation.get("ranked_players", [])
        )
        if snapshot_version is None and (
            not recommendation_result.ranked_players or status_policy_changed
            or recommendation_result.roster_fit_version != ROSTER_FIT_VERSION
        ):
            drafted_ids = [
                pick.selected_player_id for pick in state.picks
                if pick.selected_player_id is not None
            ]
            available_ids = list((await session.scalars(
                select(LeaguePlayer.player_identity_id)
                .where(LeaguePlayer.league_key == state.league_key)
                .order_by(LeaguePlayer.player_identity_id)
            )).all())
            drafted_set = set(drafted_ids)
            available_ids = [player_id for player_id in available_ids if player_id not in drafted_set]
            if available_ids and state.timing.next_round is not None:
                board_result = await calculate_draft_utility(session, DraftUtilityRequest(
                    league_key=state.league_key,
                    team_key=state.manager_team_key,
                    season=state.season,
                    drafted_player_ids=drafted_ids,
                    available_player_ids=available_ids,
                    draft_position=state.draft_position,
                    round_number=state.timing.next_round,
                    total_teams=state.total_teams,
                    recent_pick_player_ids=drafted_ids[-10:],
                    mode=state.mode,
                ), manager_drafted_player_ids=manager_player_ids)
                current_market_times = {
                    str(player.player_identity_id): player.market_data_as_of.isoformat()
                    for player in board_result.player_availability
                    if player.market_data_as_of is not None
                }
                board_result, _, _ = _mask_expired_market_data(
                    board_result,
                    current_market_times,
                    datetime.now(timezone.utc),
                )
                recommendation_result = board_result
                state = state.model_copy(update={
                    "latest_recommendation": board_result.model_dump(mode="json"),
                    "recommendation_version": state.version,
                })

    recommendation_player = recommendation_result.best_pick
    recommendation = DraftRecommendationView(
        action=recommendation_result.primary_action,
        decision_score=(
            recommendation_player.mode_adjusted_utility_score if recommendation_player else None
        ),
        confidence=recommendation_result.decision_confidence,
        recommended_player=recommendation_player,
        best_value_at_risk=recommendation_result.best_value_before_next_pick,
        survival_probability=(
            recommendation_player.next_pick_survival_probability if recommendation_player else None
        ),
        expected_wait_cost=(
            recommendation_player.expected_wait_cost if recommendation_player else None
        ),
        wait_analysis=recommendation_player.wait_fallbacks if recommendation_player else [],
        alternatives=recommendation_player.wait_fallbacks if recommendation_player else [],
        reasons=recommendation_player.reasons if recommendation_player else [],
        warnings=[
            warning for condition, warning in (
                (bool(recommendation_result.adp_missing_available_player_ids), "Some available players have no usable ADP."),
                (any(player.data_freshness == "stale" for player in recommendation_result.player_availability), "ADP data has expired; survival and wait-cost estimates are unavailable."),
                (bool(recommendation_result.unscored_available_player_ids), "Some available players have no usable draft metrics."),
                (True, "Category fit is unavailable; no category engine is implemented."),
            ) if condition
        ],
        data_quality={
            "decision": "heuristic" if recommendation_result.decision_confidence != "unavailable" else "insufficient_evidence",
            "value": "heuristic" if recommendation_player else "insufficient_evidence",
            "survival": (
                "heuristic" if recommendation_player and recommendation_player.next_pick_survival_probability is not None
                else "stale" if recommendation_player and recommendation_player.data_freshness == "stale"
                else "insufficient_evidence"
            ),
            "wait_cost": (
                "heuristic"
                if recommendation_player and recommendation_player.expected_wait_cost is not None
                else next((
                    player.data_quality["wait_cost"]
                    for player in board_result.ranked_players
                    if player.data_quality["wait_cost"] in {"stale", "unknown"}
                ), "insufficient_evidence")
            ),
            "category_fit": "insufficient_evidence",
        },
    )

    target_status_by_player = {target.player_id: target.status for target in state.targets}
    availability_by_player = {
        player.player_identity_id: player
        for player in board_result.player_availability
    }
    players = [
        player.model_copy(update={
            "target_status": target_status_by_player.get(player.player_identity_id),
            **(
                {
                    "survival_probability": availability_by_player[player.player_identity_id].next_pick_survival_probability,
                    "miss_risk_score": availability_by_player[player.player_identity_id].miss_risk_score,
                    "survival_confidence": availability_by_player[player.player_identity_id].survival_confidence,
                    "data_freshness": availability_by_player[player.player_identity_id].data_freshness,
                    "adp": availability_by_player[player.player_identity_id].adp,
                    "adp_source": availability_by_player[player.player_identity_id].adp_source,
                    "market_data_as_of": availability_by_player[player.player_identity_id].market_data_as_of,
                    "market_value_delta": availability_by_player[player.player_identity_id].market_value_delta,
                }
                if player.player_identity_id in availability_by_player
                else {}
            ),
        })
        for player in board_result.ranked_players
    ]
    if sort_by == "name":
        players.sort(key=lambda player: player.player_name.casefold(), reverse=descending)
    else:
        score_field = {
            "decision": "decision_score",
            "value": "value_score",
            "survival": "survival_probability",
        }[sort_by]
        scored_players = [player for player in players if getattr(player, score_field) is not None]
        unscored_players = [player for player in players if getattr(player, score_field) is None]
        scored_players.sort(key=lambda player: getattr(player, score_field), reverse=descending)
        players = [*scored_players, *unscored_players]
    return DraftBoardView(
        session=state,
        recommendation=recommendation,
        players=players,
        roster=roster,
    )


async def _validate_player(
    session: AsyncSession,
    draft_session: DraftSession,
    player_id: int,
    *,
    excluding_pick: int | None = None,
) -> None:
    in_pool = await session.scalar(select(LeaguePlayer.player_identity_id).where(
        LeaguePlayer.league_key == draft_session.league_key,
        LeaguePlayer.player_identity_id == player_id,
    ))
    if in_pool is None:
        raise HTTPException(status_code=422, detail="Selected player is not in the imported Yahoo league pool")
    already_selected = await session.scalar(select(DraftPick.overall_pick).where(
        DraftPick.session_id == draft_session.id,
        DraftPick.selected_player_id == player_id,
        DraftPick.overall_pick != (excluding_pick or -1),
    ))
    if already_selected is not None:
        raise HTTPException(status_code=409, detail="Selected player is already drafted in this session")


def _check_version(
    draft_session: DraftSession,
    expected_version: int,
    *,
    allow_completed: bool = False,
) -> None:
    if draft_session.version != expected_version:
        raise HTTPException(
            status_code=409,
            detail={
                "reason_code": "STALE_SESSION_VERSION",
                "expected_version": expected_version,
                "current_version": draft_session.version,
            },
        )
    if draft_session.status != "active" and not (allow_completed and draft_session.status == "completed"):
        raise HTTPException(status_code=409, detail="Draft session is not active")


async def _check_mock_batch_ownership(
    session: AsyncSession,
    draft_session: DraftSession,
    *,
    allow_batch_worker: bool = False,
) -> None:
    if draft_session.draft_order_evidence.get("practice_source") == "yahoo_mock_browser":
        raise HTTPException(status_code=409, detail="Yahoo Mock Practice picks must come from the browser observer")
    if draft_session.draft_source != "internal_mock" or allow_batch_worker:
        return
    mock_run = await session.get(DraftMockRun, draft_session.id)
    if mock_run and mock_run.batch_id and mock_run.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="This mock run is controlled by its active batch")


async def _finish_update(
    session: AsyncSession,
    draft_session: DraftSession,
    *,
    overall_pick: int,
    event_type: str,
    previous_player_id: int | None,
    selected_player_id: int | None,
    source: str,
    evidence: dict,
) -> DraftSessionEventResult:
    draft_session.version += 1
    draft_session.updated_at = datetime.now(timezone.utc)
    session.add(DraftPickEvent(
        session_id=draft_session.id,
        overall_pick=overall_pick,
        event_type=event_type,
        previous_player_id=previous_player_id,
        selected_player_id=selected_player_id,
        source=source,
        version_after=draft_session.version,
        evidence=evidence,
    ))
    await session.flush()
    picks = list((await session.scalars(
        select(DraftPick).where(DraftPick.session_id == draft_session.id)
    )).all())
    if _next_overall_pick(picks) > draft_session.total_teams * draft_session.rounds:
        draft_session.status = "completed"
    elif event_type == "undone" and draft_session.status == "completed":
        draft_session.status = "active"
    await session.flush()
    if draft_session.draft_source == "internal_mock":
        mock_run = await session.get(DraftMockRun, draft_session.id)
        if mock_run is not None:
            mock_run.status = "completed" if draft_session.status == "completed" else "running"
    await _record_recommendation_snapshot(session, draft_session)
    state = await _session_state(session, draft_session)
    return DraftSessionEventResult(state=state, event=event_type)


async def record_draft_pick(
    session: AsyncSession,
    session_id: str,
    overall_pick: int,
    request: DraftPickUpdateRequest,
    *,
    allow_batch_worker: bool = False,
) -> DraftSessionEventResult:
    async with session.begin():
        draft_session = await _locked_session(session, session_id)
        existing = await session.get(DraftPick, (session_id, overall_pick))
        if existing is not None and existing.selected_player_id == request.selected_player_id:
            return DraftSessionEventResult(state=await _session_state(session, draft_session), event="unchanged")
        _check_version(draft_session, request.expected_version)
        await _check_mock_batch_ownership(
            session,
            draft_session,
            allow_batch_worker=allow_batch_worker,
        )
        picks = list((await session.scalars(
            select(DraftPick).where(DraftPick.session_id == session_id)
        )).all())
        next_pick = _next_overall_pick(picks)
        if overall_pick != next_pick:
            raise HTTPException(
                status_code=409,
                detail={"reason_code": "OUT_OF_ORDER_PICK", "expected_overall_pick": next_pick},
            )
        if overall_pick > draft_session.total_teams * draft_session.rounds:
            raise HTTPException(status_code=409, detail="Pick exceeds the configured draft rounds")
        round_number, team_slot = _pick_slot(overall_pick, draft_session.total_teams)
        if (
            draft_session.draft_source == "internal_mock"
            and not allow_batch_worker
            and team_slot != draft_session.draft_position
        ):
            raise HTTPException(status_code=409, detail="Manual mock picks are allowed only on your turn")
        await _validate_player(session, draft_session, request.selected_player_id)
        team_key = next((key for key, slot in draft_session.team_slots.items() if slot == team_slot), None)
        if team_key is None and draft_session.draft_source != "yahoo_live":
            raise HTTPException(status_code=409, detail="Draft slot mapping is incomplete")
        picked_at = request.picked_at or datetime.now(timezone.utc)
        if picked_at.tzinfo is None:
            raise HTTPException(status_code=422, detail="picked_at must include a timezone")
        if existing is None:
            existing = DraftPick(
                session_id=session_id,
                overall_pick=overall_pick,
                round_number=round_number,
                team_slot=team_slot,
                team_key=team_key,
                selected_player_id=request.selected_player_id,
                source=request.source,
                picked_at=picked_at,
                source_evidence=request.evidence,
            )
            session.add(existing)
        else:
            existing.round_number = round_number
            existing.team_slot = team_slot
            existing.team_key = team_key
            existing.selected_player_id = request.selected_player_id
            existing.source = request.source
            existing.picked_at = picked_at
            existing.source_evidence = request.evidence
        result = await _finish_update(
            session,
            draft_session,
            overall_pick=overall_pick,
            event_type="recorded",
            previous_player_id=None,
            selected_player_id=request.selected_player_id,
            source=request.source,
            evidence=request.evidence,
        )
    return result


async def reconcile_source_picks(
    session: AsyncSession,
    session_id: str,
    picks: list[dict],
    *,
    retrieved_at: datetime,
    source: str,
) -> tuple[list[int], list[int], int, str, int | None, dict]:
    accepted: list[int] = []
    confirmed: list[int] = []
    conflict_pick: int | None = None
    conflict_evidence: dict = {}
    order_changed = False
    async with session.begin():
        draft_session = await _locked_session(session, session_id)
        if draft_session.draft_source not in {"yahoo_live", "internal_mock"}:
            raise HTTPException(status_code=409, detail="Source reconciliation is not enabled for this session")
        sync_state = await session.get(DraftSyncState, session_id)
        if sync_state is None or sync_state.source_type not in {source, "mock_yahoo_snapshot"}:
            raise HTTPException(status_code=409, detail="Draft source sync state is unavailable")
        if draft_session.draft_order_evidence.get("practice_source") == "yahoo_mock_browser":
            if source != "yahoo_mock_browser":
                raise HTTPException(status_code=409, detail="Browser practice rejects simulated or production sources")
            if sync_state.status == "conflict":
                return accepted, confirmed, sync_state.source_confirmed_through, "conflict", sync_state.conflict_overall_pick, sync_state.conflict_evidence
        if sync_state.paused:
            sync_state.status = "paused"
            return accepted, confirmed, sync_state.source_confirmed_through, "paused", None, {}
        if draft_session.draft_order_status == "conflict":
            sync_state.status = "conflict"
            return (
                accepted,
                confirmed,
                sync_state.source_confirmed_through,
                "conflict",
                sync_state.conflict_overall_pick,
                sync_state.conflict_evidence,
            )

        for incoming in picks:
            overall_pick = incoming["overall_pick"]
            round_number, team_slot = _pick_slot(overall_pick, draft_session.total_teams)
            source_round = incoming.get("round_number")
            if source_round is not None and source_round != round_number:
                conflict_pick = overall_pick
                conflict_evidence = {
                    "overall_pick": overall_pick,
                    "expected_round": round_number,
                    "source_round": source_round,
                    "source_evidence": incoming["source_evidence"],
                    "reason": "round_order_mismatch",
                }
                break
            source_team_key = incoming["team_key"]
            team_slots = dict(draft_session.team_slots)
            occupied_slot = team_slots.get(source_team_key)
            slot_team = next(
                (key for key, slot in team_slots.items() if slot == team_slot),
                None,
            )
            if round_number == 1:
                if (
                    source_team_key == draft_session.manager_team_key
                    and draft_session.draft_position is not None
                    and draft_session.draft_position != team_slot
                ):
                    conflict_evidence = {
                        "overall_pick": overall_pick,
                        "configured_manager_position": draft_session.draft_position,
                        "observed_manager_position": team_slot,
                        "manager_team_key": source_team_key,
                        "source_evidence": incoming["source_evidence"],
                        "reason": "manager_position_mismatch",
                    }
                elif occupied_slot is not None and occupied_slot != team_slot:
                    conflict_evidence = {
                        "overall_pick": overall_pick,
                        "team_key": source_team_key,
                        "existing_slot": occupied_slot,
                        "observed_slot": team_slot,
                        "source_evidence": incoming["source_evidence"],
                        "reason": "team_assigned_multiple_slots",
                    }
                elif slot_team is not None and slot_team != source_team_key:
                    conflict_evidence = {
                        "overall_pick": overall_pick,
                        "slot": team_slot,
                        "existing_team_key": slot_team,
                        "source_team_key": source_team_key,
                        "source_evidence": incoming["source_evidence"],
                        "reason": "first_round_slot_conflict",
                    }
                if conflict_evidence:
                    conflict_pick = overall_pick
                    draft_session.draft_order_status = "conflict"
                    draft_session.draft_order_evidence = {
                        **(draft_session.draft_order_evidence or {}),
                        "conflict": conflict_evidence,
                    }
                    order_changed = True
                    break
                if slot_team is None:
                    team_slots[source_team_key] = team_slot
                    draft_session.team_slots = team_slots
                    order_evidence = dict(draft_session.draft_order_evidence or {})
                    slot_evidence = dict(order_evidence.get("slots", {}))
                    slot_evidence[str(team_slot)] = {
                        "team_key": source_team_key,
                        "source": source,
                        "overall_pick": overall_pick,
                        "round_number": round_number,
                        "retrieved_at": retrieved_at.isoformat(),
                        "source_evidence": incoming["source_evidence"],
                    }
                    draft_session.draft_order_evidence = {
                        **order_evidence,
                        "slots": slot_evidence,
                    }
                    draft_session.draft_order_status = _order_status(
                        team_slots, draft_session.total_teams
                    )
                    order_changed = True
            elif slot_team is not None and slot_team != source_team_key:
                conflict_pick = overall_pick
                conflict_evidence = {
                    "overall_pick": overall_pick,
                    "slot": team_slot,
                    "expected_team_key": slot_team,
                    "source_team_key": source_team_key,
                    "source_evidence": incoming["source_evidence"],
                    "reason": "snake_order_mismatch",
                }
                draft_session.draft_order_status = "conflict"
                draft_session.draft_order_evidence = {
                    **(draft_session.draft_order_evidence or {}),
                    "conflict": conflict_evidence,
                }
                order_changed = True
                break

            existing = await session.get(DraftPick, (session_id, overall_pick))
            if existing is not None and existing.selected_player_id is not None:
                if (
                    existing.selected_player_id == incoming["player_identity_id"]
                    and existing.team_key in (None, source_team_key)
                ):
                    if existing.team_key is None:
                        existing.team_key = source_team_key
                        order_changed = True
                    confirmed.append(overall_pick)
                    continue
                conflict_pick = overall_pick
                conflict_evidence = {
                    "overall_pick": overall_pick,
                    "local_player_identity_id": existing.selected_player_id,
                    "source_player_identity_id": incoming["player_identity_id"],
                    "local_team_key": existing.team_key,
                    "source_team_key": incoming["team_key"],
                }
                break

            current_picks = list((await session.scalars(
                select(DraftPick).where(DraftPick.session_id == session_id)
            )).all())
            expected_pick = _next_overall_pick(current_picks)
            if overall_pick != expected_pick:
                conflict_pick = overall_pick
                conflict_evidence = {
                    "overall_pick": overall_pick,
                    "expected_overall_pick": expected_pick,
                    "reason": "source_gap",
                }
                break
            if overall_pick > draft_session.total_teams * draft_session.rounds:
                conflict_pick = overall_pick
                conflict_evidence = {"overall_pick": overall_pick, "reason": "pick_outside_draft"}
                break
            duplicate_local_pick = await session.scalar(select(DraftPick.overall_pick).where(
                DraftPick.session_id == session_id,
                DraftPick.selected_player_id == incoming["player_identity_id"],
                DraftPick.overall_pick != overall_pick,
            ))
            if duplicate_local_pick is not None:
                conflict_pick = overall_pick
                conflict_evidence = {
                    "overall_pick": overall_pick,
                    "source_player_identity_id": incoming["player_identity_id"],
                    "already_recorded_at": duplicate_local_pick,
                    "reason": "duplicate_local_player",
                }
                break
            await _validate_player(session, draft_session, incoming["player_identity_id"])
            pick = DraftPick(
                session_id=session_id,
                overall_pick=overall_pick,
                round_number=round_number,
                team_slot=team_slot,
                team_key=source_team_key,
                selected_player_id=incoming["player_identity_id"],
                source=source,
                picked_at=retrieved_at,
                source_evidence=incoming["source_evidence"],
            )
            session.add(pick)
            await _finish_update(
                session,
                draft_session,
                overall_pick=overall_pick,
                event_type="recorded",
                previous_player_id=None,
                selected_player_id=incoming["player_identity_id"],
                source=source,
                evidence=incoming["source_evidence"],
            )
            accepted.append(overall_pick)

        if order_changed and not accepted:
            draft_session.version += 1
            draft_session.updated_at = datetime.now(timezone.utc)
            await session.flush()
            await _record_recommendation_snapshot(session, draft_session)
        local_picks = list((await session.scalars(
            select(DraftPick).where(
                DraftPick.session_id == session_id,
                DraftPick.selected_player_id.is_not(None),
            )
        )).all())
        local_recorded_through = max((pick.overall_pick for pick in local_picks), default=0)
        prior_confirmed_through = sync_state.source_confirmed_through
        confirmed_through = max(
            [sync_state.source_confirmed_through, *confirmed, *accepted],
            default=sync_state.source_confirmed_through,
        )
        sync_state.source_confirmed_through = confirmed_through
        sync_state.last_retrieved_at = retrieved_at
        sync_state.last_successful_retrieval_at = retrieved_at
        sync_state.consecutive_failures = 0
        sync_state.conflict_overall_pick = conflict_pick
        sync_state.conflict_evidence = conflict_evidence
        if conflict_pick is not None:
            status = "conflict"
        elif len(picks) < prior_confirmed_through:
            status = "source_lagging"
        elif local_recorded_through > len(picks):
            status = "local_ahead"
        elif not picks:
            status = "source_empty"
        elif draft_session.status == "completed":
            status = "completed"
        else:
            status = "synced"
        sync_state.status = status
    return accepted, confirmed, confirmed_through, status, conflict_pick, conflict_evidence


async def correct_draft_pick(
    session: AsyncSession,
    session_id: str,
    overall_pick: int,
    request: DraftPickUpdateRequest,
) -> DraftSessionEventResult:
    async with session.begin():
        draft_session = await _locked_session(session, session_id)
        pick = await session.get(DraftPick, (session_id, overall_pick))
        if pick is None or pick.selected_player_id is None:
            raise HTTPException(status_code=404, detail="Recorded draft pick was not found")
        if pick.selected_player_id == request.selected_player_id:
            return DraftSessionEventResult(state=await _session_state(session, draft_session), event="unchanged")
        _check_version(draft_session, request.expected_version, allow_completed=True)
        await _check_mock_batch_ownership(session, draft_session)
        await _validate_player(
            session,
            draft_session,
            request.selected_player_id,
            excluding_pick=overall_pick,
        )
        previous_player_id = pick.selected_player_id
        picked_at = request.picked_at or datetime.now(timezone.utc)
        if picked_at.tzinfo is None:
            raise HTTPException(status_code=422, detail="picked_at must include a timezone")
        pick.selected_player_id = request.selected_player_id
        pick.source = request.source
        pick.picked_at = picked_at
        pick.source_evidence = request.evidence
        return await _finish_update(
            session,
            draft_session,
            overall_pick=overall_pick,
            event_type="corrected",
            previous_player_id=previous_player_id,
            selected_player_id=request.selected_player_id,
            source=request.source,
            evidence=request.evidence,
        )


async def undo_draft_pick(
    session: AsyncSession,
    session_id: str,
    overall_pick: int,
    request: DraftPickUndoRequest,
) -> DraftSessionEventResult:
    async with session.begin():
        draft_session = await _locked_session(session, session_id)
        pick = await session.get(DraftPick, (session_id, overall_pick))
        if pick is None or pick.selected_player_id is None:
            return DraftSessionEventResult(state=await _session_state(session, draft_session), event="unchanged")
        _check_version(draft_session, request.expected_version, allow_completed=True)
        await _check_mock_batch_ownership(session, draft_session)
        picks = list((await session.scalars(
            select(DraftPick).where(DraftPick.session_id == session_id)
        )).all())
        latest_selected = max(
            (item.overall_pick for item in picks if item.selected_player_id is not None),
            default=0,
        )
        if overall_pick != latest_selected:
            raise HTTPException(status_code=409, detail="Only the latest recorded pick can be undone")
        previous_player_id = pick.selected_player_id
        pick.selected_player_id = None
        pick.picked_at = None
        pick.source = request.source
        pick.source_evidence = request.evidence
        return await _finish_update(
            session,
            draft_session,
            overall_pick=overall_pick,
            event_type="undone",
            previous_player_id=previous_player_id,
            selected_player_id=None,
            source=request.source,
            evidence=request.evidence,
        )


async def put_draft_target(
    session: AsyncSession,
    session_id: str,
    player_id: int,
    request: DraftTargetRequest,
) -> DraftSessionState:
    async with session.begin():
        draft_session = await _locked_session(session, session_id)
        _check_version(
            draft_session,
            request.expected_version,
            allow_completed=draft_session.draft_source == "internal_mock",
        )
        await _check_mock_batch_ownership(session, draft_session)
        if await session.scalar(select(LeaguePlayer.player_identity_id).where(
            LeaguePlayer.league_key == draft_session.league_key,
            LeaguePlayer.player_identity_id == player_id,
        )) is None:
            raise HTTPException(status_code=404, detail="Player is not in the imported Yahoo league pool")
        target = await session.get(DraftTargetModel, (session_id, player_id))
        if target is not None and target.status == request.status and target.note == request.note:
            return await _session_state(session, draft_session)
        if target is None:
            target = DraftTargetModel(
                session_id=session_id,
                player_id=player_id,
                status=request.status,
                note=request.note,
            )
            session.add(target)
        else:
            target.status = request.status
            target.note = request.note
        draft_session.version += 1
        draft_session.updated_at = datetime.now(timezone.utc)
        await session.flush()
        await _record_recommendation_snapshot(session, draft_session)
        return await _session_state(session, draft_session)


async def delete_draft_target(
    session: AsyncSession,
    session_id: str,
    player_id: int,
    expected_version: int,
) -> DraftSessionState:
    async with session.begin():
        draft_session = await _locked_session(session, session_id)
        _check_version(
            draft_session,
            expected_version,
            allow_completed=draft_session.draft_source == "internal_mock",
        )
        await _check_mock_batch_ownership(session, draft_session)
        target = await session.get(DraftTargetModel, (session_id, player_id))
        if target is not None:
            await session.delete(target)
            draft_session.version += 1
            draft_session.updated_at = datetime.now(timezone.utc)
            await session.flush()
            await _record_recommendation_snapshot(session, draft_session)
        return await _session_state(session, draft_session)
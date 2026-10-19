from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.features.draft.contracts import (
    DraftBoardView,
    DraftMockActionRequest,
    DraftMockActionResult,
    DraftMockRehearsalActionRequest,
    DraftMockBatchCreateRequest,
    DraftMockBatchCreateResult,
    DraftMockBatchState,
    DraftMockBatchRunResult,
    DraftMockCreateRequest,
    DraftMockOrderRequest,
    DraftMockOrderResponse,
    DraftLiveSessionCreateRequest,
    DraftOrderUpdateRequest,
    DraftReplayResponse,
    DraftMetricsResult,
    DraftPickUndoRequest,
    DraftPickUpdateRequest,
    DraftSessionCreateRequest,
    DraftSessionEventResult,
    DraftSessionState,
    DraftSyncResult,
    DraftSyncStateView,
    DraftTargetRequest,
    DraftUtilityRequest,
    DraftUtilityResult,
)
from app.services.draft.metrics import recompute_draft_metrics
from app.services.draft.mock_drafts import (
    apply_internal_mock_batch_action,
    create_internal_mock,
    create_internal_mock_batch,
    delete_internal_mock,
    get_internal_mock_batch,
    get_internal_mock_replay,
    list_internal_mock_batches,
    preview_internal_mock_order,
    restart_internal_mock,
    set_internal_mock_paused,
    simulate_internal_mock,
)
from app.services.draft.sessions import (
    correct_draft_pick,
    create_draft_session,
    delete_draft_target,
    get_draft_session,
    get_draft_board,
    list_draft_sessions,
    put_draft_target,
    record_draft_pick,
    undo_draft_pick,
    update_live_draft_order,
)
from app.services.draft.sync import (
    get_draft_sync_state,
    run_mock_sync_rehearsal,
    set_draft_sync_paused,
    sync_yahoo_draft_results,
)
from app.services.draft.utility import calculate_draft_utility

router = APIRouter(prefix="/api/v1/draft", tags=["Draft Readiness"])
v2_router = APIRouter(prefix="/api/v2/draft", tags=["Draft Sessions"])


@router.post("/metrics", response_model=DraftMetricsResult)
async def build_draft_metrics(
    league_key: str = Query(min_length=1),
    season: str = Query(pattern=r"^\d{4}-\d{2}$"),
    session: AsyncSession = Depends(get_session),
) -> DraftMetricsResult:
    return await recompute_draft_metrics(session, league_key, season)


@router.post("/utility", response_model=DraftUtilityResult)
async def draft_utility(
    request: DraftUtilityRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftUtilityResult:
    await recompute_draft_metrics(session, request.league_key, request.season)
    return await calculate_draft_utility(session, request)


@v2_router.post("/sessions", response_model=DraftSessionEventResult, status_code=201)
async def create_session(
    request: DraftSessionCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionEventResult:
    return await create_draft_session(session, request)


@v2_router.post("/live-sessions", response_model=DraftSessionEventResult, status_code=201)
async def create_live_session(
    request: DraftLiveSessionCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionEventResult:
    return await create_draft_session(session, request, draft_source="yahoo_live")


@v2_router.put("/sessions/{session_id}/order", response_model=DraftSessionState)
async def resolve_session_order(
    session_id: str,
    request: DraftOrderUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionState:
    return await update_live_draft_order(session, session_id, request)


@v2_router.get("/sessions", response_model=list[DraftSessionState])
async def read_sessions(
    session: AsyncSession = Depends(get_session),
) -> list[DraftSessionState]:
    return await list_draft_sessions(session)


@v2_router.get("/mock-sessions", response_model=list[DraftSessionState])
async def read_mock_sessions(
    session: AsyncSession = Depends(get_session),
) -> list[DraftSessionState]:
    return await list_draft_sessions(session, draft_source="internal_mock")


@v2_router.post("/mock-sessions", response_model=DraftSessionEventResult, status_code=201)
async def create_mock_session(
    request: DraftMockCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionEventResult:
    state = await create_internal_mock(session, request)
    return DraftSessionEventResult(state=state, event="created")


@v2_router.post("/mock-order-preview", response_model=DraftMockOrderResponse)
async def preview_mock_order(
    request: DraftMockOrderRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftMockOrderResponse:
    return await preview_internal_mock_order(session, request)


@v2_router.delete("/mock-sessions/{session_id}", status_code=204)
async def remove_mock_session(
    session_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    await delete_internal_mock(session, session_id)


@v2_router.post("/mock-batches", response_model=DraftMockBatchCreateResult, status_code=201)
async def create_mock_batch(
    request: DraftMockBatchCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftMockBatchCreateResult:
    return await create_internal_mock_batch(session, request)


@v2_router.get("/mock-batches", response_model=list[DraftMockBatchState])
async def read_mock_batches(
    session: AsyncSession = Depends(get_session),
) -> list[DraftMockBatchState]:
    return await list_internal_mock_batches(session)


@v2_router.get("/mock-batches/{batch_id}", response_model=DraftMockBatchState)
async def read_mock_batch(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
) -> DraftMockBatchState:
    return await get_internal_mock_batch(session, batch_id)


@v2_router.post("/mock-batches/{batch_id}/run", response_model=DraftMockBatchRunResult)
async def run_mock_batch(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
) -> DraftMockBatchRunResult:
    batch = await apply_internal_mock_batch_action(session, batch_id, "resume")
    return DraftMockBatchRunResult(batch=batch)


@v2_router.post("/mock-batches/{batch_id}/pause", response_model=DraftMockBatchState)
async def pause_mock_batch(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
) -> DraftMockBatchState:
    return await apply_internal_mock_batch_action(session, batch_id, "pause")


@v2_router.post("/mock-batches/{batch_id}/resume", response_model=DraftMockBatchState)
async def resume_mock_batch(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
) -> DraftMockBatchState:
    return await apply_internal_mock_batch_action(session, batch_id, "resume")


@v2_router.post("/mock-batches/{batch_id}/cancel", response_model=DraftMockBatchState)
async def cancel_mock_batch(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
) -> DraftMockBatchState:
    return await apply_internal_mock_batch_action(session, batch_id, "cancel")


@v2_router.post("/mock-batches/{batch_id}/retry-failed", response_model=DraftMockBatchState)
async def retry_failed_mock_batch(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
) -> DraftMockBatchState:
    return await apply_internal_mock_batch_action(session, batch_id, "retry_failed")


@v2_router.get("/sessions/{session_id}", response_model=DraftSessionState)
async def read_session(
    session_id: str,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionState:
    return await get_draft_session(session, session_id)


@v2_router.get("/sessions/{session_id}/sync", response_model=DraftSyncStateView)
async def read_session_sync(
    session_id: str,
    session: AsyncSession = Depends(get_session),
) -> DraftSyncStateView:
    return await get_draft_sync_state(session, session_id)


@v2_router.post("/sessions/{session_id}/sync", response_model=DraftSyncResult)
async def sync_session(
    session_id: str,
    session: AsyncSession = Depends(get_session),
) -> DraftSyncResult:
    return await sync_yahoo_draft_results(session, session_id)


@v2_router.post("/sessions/{session_id}/sync/pause", response_model=DraftSyncStateView)
async def pause_session_sync(
    session_id: str,
    session: AsyncSession = Depends(get_session),
) -> DraftSyncStateView:
    return await set_draft_sync_paused(session, session_id, paused=True)


@v2_router.post("/sessions/{session_id}/sync/resume", response_model=DraftSyncStateView)
async def resume_session_sync(
    session_id: str,
    session: AsyncSession = Depends(get_session),
) -> DraftSyncStateView:
    return await set_draft_sync_paused(session, session_id, paused=False)


@v2_router.post("/sessions/{session_id}/mock-rehearsal", response_model=DraftSyncResult)
async def mock_sync_rehearsal(
    session_id: str,
    request: DraftMockRehearsalActionRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftSyncResult:
    return await run_mock_sync_rehearsal(session, session_id, request.action)


@v2_router.get("/sessions/{session_id}/replay", response_model=DraftReplayResponse)
async def read_session_replay(
    session_id: str,
    version: int = Query(ge=0),
    session: AsyncSession = Depends(get_session),
) -> DraftReplayResponse:
    return await get_internal_mock_replay(session, session_id, version)


@v2_router.post("/sessions/{session_id}/mock-action", response_model=DraftMockActionResult)
async def mock_action(
    session_id: str,
    request: DraftMockActionRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftMockActionResult:
    return await simulate_internal_mock(session, session_id, request.action)


@v2_router.post("/sessions/{session_id}/mock/pause", response_model=DraftSessionState)
async def pause_mock(
    session_id: str,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionState:
    return await set_internal_mock_paused(session, session_id, paused=True)


@v2_router.post("/sessions/{session_id}/mock/resume", response_model=DraftSessionState)
async def resume_mock(
    session_id: str,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionState:
    return await set_internal_mock_paused(session, session_id, paused=False)


@v2_router.post("/sessions/{session_id}/mock/reset", response_model=DraftSessionState, status_code=201)
async def reset_mock(
    session_id: str,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionState:
    return await restart_internal_mock(session, session_id)


@v2_router.get("/sessions/{session_id}/board", response_model=DraftBoardView)
async def read_draft_board(
    session_id: str,
    sort_by: Literal["decision", "value", "survival", "name"] = Query(default="decision"),
    descending: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> DraftBoardView:
    return await get_draft_board(
        session,
        session_id,
        sort_by=sort_by,
        descending=descending,
    )


@v2_router.post(
    "/sessions/{session_id}/picks/{overall_pick}",
    response_model=DraftSessionEventResult,
)
async def add_pick(
    session_id: str,
    overall_pick: int,
    request: DraftPickUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionEventResult:
    return await record_draft_pick(session, session_id, overall_pick, request)


@v2_router.put(
    "/sessions/{session_id}/picks/{overall_pick}",
    response_model=DraftSessionEventResult,
)
async def replace_pick(
    session_id: str,
    overall_pick: int,
    request: DraftPickUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionEventResult:
    return await correct_draft_pick(session, session_id, overall_pick, request)


@v2_router.post(
    "/sessions/{session_id}/picks/{overall_pick}/undo",
    response_model=DraftSessionEventResult,
)
async def remove_latest_pick(
    session_id: str,
    overall_pick: int,
    request: DraftPickUndoRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionEventResult:
    return await undo_draft_pick(session, session_id, overall_pick, request)


@v2_router.put("/sessions/{session_id}/targets/{player_id}", response_model=DraftSessionState)
async def mark_target(
    session_id: str,
    player_id: int,
    request: DraftTargetRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionState:
    return await put_draft_target(session, session_id, player_id, request)


@v2_router.delete("/sessions/{session_id}/targets/{player_id}", response_model=DraftSessionState)
async def unmark_target(
    session_id: str,
    player_id: int,
    expected_version: int = Query(ge=0),
    session: AsyncSession = Depends(get_session),
) -> DraftSessionState:
    return await delete_draft_target(session, session_id, player_id, expected_version)

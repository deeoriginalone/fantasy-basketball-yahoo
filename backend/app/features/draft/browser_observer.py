"""Secret-protected evidence collection only; deliberately no draft mutation path."""

import asyncio
import hmac
import os
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.features.players.models import LeaguePlayer, PlayerIdentity
from app.services.draft.browser_practice import create_browser_practice, ingest_browser_practice

router = APIRouter(prefix="/api/v2/draft/browser-observer", tags=["Observer evidence"])


class PracticePick(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overall_pick: int = Field(ge=1, le=600, strict=True)
    yahoo_player_id: str = Field(pattern=r"^[0-9]{1,12}$")
    observed_at: datetime
    source: Literal["yahoo_mock_browser"]

    @field_validator("observed_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at requires a timezone")
        return value


class PracticeHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["yahoo_mock_practice"]
    picks: list[PracticePick] = Field(min_length=1, max_length=600)


class PracticeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["yahoo_mock_practice"]
    season: str = Field(pattern=r"^\d{4}-\d{2}$")
    user_slot: int = Field(ge=1, le=12, strict=True)
    rounds: int = Field(ge=1, le=50, strict=True)


class ObservedPick(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_pick: int = Field(ge=1, le=600, strict=True)
    yahoo_player_id: str = Field(pattern=r"^[0-9]{1,12}$")
    draft_slot: int = Field(ge=1, le=12, strict=True)
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at requires a timezone")
        return value


class ObserverSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observer_session: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    source: Literal["yahoo_browser_observer"]
    picks: list[ObservedPick] = Field(max_length=600)


def authorize_observer(
    request: Request,
    secret: str | None = Header(default=None, alias="X-Court-IQ-Observer"),
) -> str:
    expected = os.environ.get("COURT_IQ_OBSERVER_SECRET", "")
    enabled = os.environ.get("COURT_IQ_OBSERVER_PRACTICE_SESSION", "")
    league = os.environ.get("COURT_IQ_OBSERVER_LEAGUE_KEY", "")
    origin = urlsplit(os.environ.get("COURT_IQ_OBSERVER_ORIGIN", ""))
    if len(expected) < 43 or not enabled or not league or origin.scheme != "https" or not origin.hostname:
        raise HTTPException(status_code=503, detail="Practice observer is disabled")
    if not secret or not hmac.compare_digest(secret.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Observer authentication required")
    if request.url.hostname != origin.hostname:
        raise HTTPException(status_code=403, detail="Observer requires the configured Court IQ origin")
    return league


def require_practice_enabled() -> None:
    if os.environ.get("COURT_IQ_OBSERVER_PRACTICE_WRITES") != "true":
        raise HTTPException(status_code=503, detail="Yahoo Mock Practice writes are disabled")


@router.post("/practice", status_code=201, dependencies=[Depends(require_practice_enabled)])
async def create_practice(
    body: PracticeCreate, league_key: str = Depends(authorize_observer),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await create_browser_practice(
        session, source_league_key=league_key, season=body.season,
        user_slot=body.user_slot, rounds=body.rounds,
    )
    return {"mode": "yahoo_mock_practice", "session_id": result.state.session_id,
            "draft_room_path": f"/draft/{result.state.session_id}"}


@router.post("/practice/{session_id}/history", dependencies=[Depends(require_practice_enabled)])
async def practice_history(
    session_id: str, body: PracticeHistory,
    league_key: str = Depends(authorize_observer),
    session: AsyncSession = Depends(get_session),
) -> dict:
    seen = set()
    for expected, pick in enumerate(body.picks, 1):
        if pick.overall_pick != expected:
            raise HTTPException(status_code=422, detail="Resend contiguous full history starting at pick 1")
        if pick.yahoo_player_id in seen:
            raise HTTPException(status_code=422, detail="Duplicate Yahoo player ID")
        seen.add(pick.yahoo_player_id)
    # The target must belong to the explicitly configured imported pool.
    from app.features.draft.models import DraftSession
    from app.features.leagues.models import League
    draft = await session.get(DraftSession, session_id)
    league = await session.get(League, draft.league_key) if draft else None
    if league is None or league.source_payload.get("source_league_key") != league_key:
        raise HTTPException(status_code=403, detail="Practice session is outside the configured source league")
    return await ingest_browser_practice(session, session_id, body.picks)


def validate_history(snapshot: ObserverSnapshot) -> None:
    ids: set[str] = set()
    for expected, pick in enumerate(snapshot.picks, 1):
        slot = (expected - 1) % 12 + 1
        if ((expected - 1) // 12) % 2:
            slot = 13 - slot
        if pick.overall_pick != expected or pick.draft_slot != slot:
            raise HTTPException(status_code=422, detail="History must be contiguous from pick 1 with verified snake slots")
        if pick.yahoo_player_id in ids:
            raise HTTPException(status_code=422, detail="Duplicate Yahoo player ID")
        ids.add(pick.yahoo_player_id)


@router.post("/observe")
async def observe(
    snapshot: ObserverSnapshot,
    request: Request,
    league_key: str = Depends(authorize_observer),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if snapshot.observer_session != os.environ.get("COURT_IQ_OBSERVER_PRACTICE_SESSION"):
        raise HTTPException(status_code=403, detail="Only the explicitly enabled practice observation is accepted")
    validate_history(snapshot)
    yahoo_ids = [pick.yahoo_player_id for pick in snapshot.picks]
    rows = (await session.execute(
        select(PlayerIdentity.id, PlayerIdentity.yahoo_player_id)
        .where(PlayerIdentity.yahoo_player_id.in_(yahoo_ids))
    )).all()
    mapped: dict[str, list[int]] = {}
    for identity_id, yahoo_id in rows:
        mapped.setdefault(yahoo_id, []).append(identity_id)
    if any(len(mapped.get(yahoo_id, [])) != 1 for yahoo_id in yahoo_ids):
        raise HTTPException(status_code=422, detail="Unknown or ambiguous Yahoo player ID")
    imported = set((await session.scalars(
        select(LeaguePlayer.player_identity_id).where(
            LeaguePlayer.league_key == league_key,
            LeaguePlayer.player_identity_id.in_([ids[0] for ids in mapped.values()]),
        )
    )).all())
    if any(ids[0] not in imported for ids in mapped.values()):
        raise HTTPException(status_code=422, detail="Yahoo player ID is outside the configured league pool")
    if not hasattr(request.app.state, "observer_evidence_lock"):
        request.app.state.observer_evidence_lock = asyncio.Lock()
        request.app.state.observer_evidence = None
    async with request.app.state.observer_evidence_lock:
        evidence = request.app.state.observer_evidence
        if evidence is None or evidence["session"] != snapshot.observer_session:
            evidence = {"session": snapshot.observer_session, "history": [], "conflict": False}
            request.app.state.observer_evidence = evidence
        history = [(pick.yahoo_player_id, pick.draft_slot) for pick in snapshot.picks]
        previous = evidence["history"]
        if evidence["conflict"] or history[:len(previous)] != previous:
            evidence["conflict"] = True
            raise HTTPException(status_code=409, detail="Observer history conflict; observation stopped")
        evidence["history"] = history
    # No session creation, pick writes, simulation, or reconciliation before real mock evidence.
    return {
        "mode": "observe_only",
        "mapped_count": len(yahoo_ids),
        "confirmed_through": len(yahoo_ids),
        "draft_writes": False,
    }

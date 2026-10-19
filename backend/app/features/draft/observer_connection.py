"""Paired desktop mailbox. Browser requests never carry Yahoo credentials."""

from datetime import datetime, timezone
import asyncio
import hashlib
import hmac
import os
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, String, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, get_session
from app.features.draft.browser_observer import (
    PracticePick, authorize_observer, require_practice_enabled,
)
from app.features.draft.models import DraftSession, DraftSyncState
from app.features.leagues.models import League
from app.features.players.models import PlayerIdentity
from app.services.draft.browser_practice import create_browser_practice, ingest_browser_practice

router = APIRouter(prefix="/api/v2/draft/observer-connection", tags=["Desktop observer"])
COOKIE = "court_iq_observer_pair"


@router.get("/installer")
async def installer():
    from io import BytesIO
    from pathlib import Path
    from zipfile import ZipFile

    folder = Path("/opt/court-iq-observer")
    names = [
        "Install-CourtIQObserver.cmd", "Install-CourtIQObserver.ps1",
        "Launch-YahooDraftChrome.ps1", "desktop.py", "observer.py", "picks.py", "requirements.txt",
    ]
    if any(not (folder / name).is_file() for name in names):
        raise HTTPException(status_code=503, detail="Windows installer is not deployed")
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, (folder / name).read_bytes())
    return StreamingResponse(iter([buffer.getvalue()]), media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="CourtIQ-Yahoo-Observer.zip"'})


async def desktop_lock(request: Request):
    # Deployment uses one API worker; serialize desktop callbacks across session creation commits.
    if not hasattr(request.app.state, "desktop_connection_lock"):
        request.app.state.desktop_connection_lock = asyncio.Lock()
    async with request.app.state.desktop_connection_lock:
        yield


class ObserverConnection(Base):
    __tablename__ = "observer_connections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    room_path: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="CONNECTING")
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def same_origin(request: Request) -> None:
    import os
    from urllib.parse import urlsplit

    configured = os.environ.get("COURT_IQ_OBSERVER_ORIGIN", "").rstrip("/")
    if not configured.startswith("https://"):
        raise HTTPException(status_code=503, detail="Desktop connection is not configured")
    if request.url.hostname != urlsplit(configured).hostname:
        raise HTTPException(status_code=403, detail="Use the configured Court IQ HTTPS origin")
    if request.method not in {"GET", "HEAD"} and request.headers.get("origin") != configured:
        raise HTTPException(status_code=403, detail="Same-origin request required")


def paired(request: Request) -> None:
    import os

    same_origin(request)
    secret = os.environ.get("COURT_IQ_OBSERVER_SECRET", "")
    value = request.cookies.get(COOKIE, "")
    stamp, _, signature = value.partition(".")
    expected = hmac.new(secret.encode(), f"desktop-pair:{stamp}".encode(), hashlib.sha256).hexdigest()
    if len(secret) < 43 or not stamp.isdigit() or not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Pair the installed observer once")
    if not 0 <= time.time() - int(stamp) < 365 * 86400:
        raise HTTPException(status_code=401, detail="Desktop pairing expired")


class PairBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{24,100}$")


@router.post("/pairing", dependencies=[Depends(authorize_observer)])
async def offer_pairing(body: PairBody, request: Request) -> dict:
    request.app.state.observer_pairing = (
        hashlib.sha256(body.code.encode()).digest(), time.monotonic() + 600,
    )
    return {"expires_in": 600}


@router.post("/pair", dependencies=[Depends(same_origin)])
async def pair(body: PairBody, request: Request, response: Response) -> dict:
    import os

    offer = getattr(request.app.state, "observer_pairing", None)
    if offer is None or offer[1] < time.monotonic() or not hmac.compare_digest(
        offer[0], hashlib.sha256(body.code.encode()).digest()
    ):
        raise HTTPException(status_code=401, detail="Invalid or expired desktop pairing code")
    request.app.state.observer_pairing = None
    stamp = str(int(time.time()))
    signature = hmac.new(os.environ["COURT_IQ_OBSERVER_SECRET"].encode(),
                         f"desktop-pair:{stamp}".encode(), hashlib.sha256).hexdigest()
    response.set_cookie(COOKIE, f"{stamp}.{signature}", secure=True, httponly=True,
                        samesite="strict", max_age=365 * 86400, path="/api/v2/draft")
    return {"paired": True}


class ConnectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_path: str = Field(pattern=r"^/draftclient/nba/[0-9]{1,20}/[0-9]{1,10}/?$")
    mode: Literal["mock", "live"]


def view(connection: ObserverConnection | None) -> dict:
    if connection is None:
        return {"status": "SOURCE UNAVAILABLE", "paired": True}
    stale = (datetime.now(timezone.utc) - connection.updated_at).total_seconds() > 20
    status = "RECONNECTING" if stale and connection.status not in {"CONFLICT", "DRAFT ENDED"} else connection.status
    measurements = connection.details.get("latency_samples_ms", [])
    import statistics
    latency = {
        "count": len(measurements), "min": min(measurements),
        "median": statistics.median(measurements), "max": max(measurements),
    } if measurements else None
    return {
        "id": connection.id, "mode": connection.mode, "room_path": connection.room_path,
        "status": status, "paired": True, **connection.details,
        "draft_room_path": f"/draft/{connection.session_id}" if connection.session_id else None,
        "local_dom_latency_ms": latency,
    }


async def current(session: AsyncSession) -> ObserverConnection | None:
    return await session.scalar(select(ObserverConnection).where(ObserverConnection.active.is_(True)))


@router.get("", dependencies=[Depends(paired)])
async def status(session: AsyncSession = Depends(get_session)) -> dict:
    return view(await current(session))


@router.post("", dependencies=[Depends(paired), Depends(desktop_lock)])
async def connect(body: ConnectBody, session: AsyncSession = Depends(get_session)) -> dict:
    path = body.room_path.rstrip("/")
    identity = hashlib.sha256(f"{body.mode}:{path}".encode()).hexdigest()
    async with session.begin():
        await session.execute(text("SELECT pg_advisory_xact_lock(2026101801)"))
        await session.execute(update(ObserverConnection).values(active=False))
        connection = await session.get(ObserverConnection, identity)
        if connection is None:
            connection = ObserverConnection(
                id=identity, room_path=path, mode=body.mode, active=True,
                status="CONNECTING", details={}, updated_at=datetime.now(timezone.utc),
            )
            session.add(connection)
        else:
            connection.active = True
            connection.updated_at = datetime.now(timezone.utc)
        connection.details = {
            **connection.details, "request_generation": connection.details.get("request_generation", 0) + 1,
        }
    return view(connection)


class SlotBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot: int = Field(ge=1, le=12, strict=True)


@router.post("/{connection_id}/stop", dependencies=[Depends(paired)])
async def stop_connection(connection_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    async with session.begin():
        connection = await session.get(ObserverConnection, connection_id, with_for_update=True)
        if connection is None:
            raise HTTPException(status_code=404, detail="Connection not found")
        connection.active = False
    return view(await current(session))


@router.put("/{connection_id}/slot", dependencies=[Depends(paired), Depends(desktop_lock)])
async def set_slot(connection_id: str, body: SlotBody, session: AsyncSession = Depends(get_session)) -> dict:
    async with session.begin():
        connection = await session.get(ObserverConnection, connection_id, with_for_update=True)
        if connection is None or not connection.active:
            raise HTTPException(status_code=404, detail="Connection not found")
        if connection.session_id:
            raise HTTPException(status_code=409, detail="Practice slot cannot change after initialization")
        connection.details = {**connection.details, "user_slot": body.slot, "slot_source": "user_confirmed"}
    return view(connection)


@router.get("/agent", dependencies=[Depends(authorize_observer)])
async def agent_job(session: AsyncSession = Depends(get_session)) -> dict:
    connection = await current(session)
    return {"connection": view(connection) if connection else None}


class DesktopSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["CONNECTED", "RECONNECTING", "SOURCE UNAVAILABLE", "NEEDS ATTENTION", "CONFLICT"]
    user_slot: int | None = Field(default=None, ge=1, le=12, strict=True)
    total_teams: int | None = Field(default=None, ge=2, le=12, strict=True)
    rounds: int | None = Field(default=None, ge=1, le=50, strict=True)
    picks: list[PracticePick] = Field(default_factory=list, max_length=600)
    latency_ms: float | None = Field(default=None, ge=0, le=600000, allow_inf_nan=False)


def apply_confirmed_mock_rounds(mode: str, details: dict) -> None:
    if mode != "mock" or details.get("total_teams") != 12 or details.get("rounds") is not None:
        return
    configured = os.environ.get("COURT_IQ_OBSERVER_MOCK_ROUNDS", "")
    if not configured:
        return
    if not configured.isascii() or not configured.isdigit() or not 1 <= int(configured) <= 50:
        raise HTTPException(status_code=503, detail="Configured Yahoo mock rounds must be an integer from 1 to 50")
    details.update(rounds=int(configured), rounds_source="user_confirmed_mock_configuration")


@router.post("/{connection_id}/snapshot", dependencies=[Depends(desktop_lock)])
async def desktop_snapshot(
    connection_id: str, body: DesktopSnapshot,
    league_key: str = Depends(authorize_observer), session: AsyncSession = Depends(get_session),
) -> dict:
    connection = await session.get(ObserverConnection, connection_id)
    if connection is None or not connection.active:
        raise HTTPException(status_code=409, detail="Desktop connection is no longer active")
    if connection.status == "CONFLICT":
        raise HTTPException(status_code=409, detail="Conflict latched; automatic writes stopped")
    ids: set[str] = set()
    for expected, pick in enumerate(body.picks, 1):
        if pick.overall_pick != expected or pick.yahoo_player_id in ids:
            raise HTTPException(status_code=422, detail="Complete unique history from pick 1 required")
        ids.add(pick.yahoo_player_id)
    details = dict(connection.details)
    if body.state in {"CONNECTED", "RECONNECTING", "SOURCE UNAVAILABLE"}:
        details["target_detected"] = body.state == "CONNECTED"
    if body.user_slot is not None:
        if details.get("user_slot") not in (None, body.user_slot):
            connection.status = "CONFLICT"
            await session.commit()
            raise HTTPException(status_code=409, detail="Observed user slot conflicts with practice slot")
        details.update(user_slot=body.user_slot, slot_source="rendered")
    for key, value in (("total_teams", body.total_teams), ("rounds", body.rounds)):
        if value is not None:
            if details.get(key) not in (None, value):
                connection.status = "CONFLICT"
                await session.commit()
                raise HTTPException(status_code=409, detail="Rendered draft settings changed")
            details[key] = value
    apply_confirmed_mock_rounds(connection.mode, details)
    details["source"] = "Browser"
    if body.picks or body.state == "CONNECTED":
        details["yahoo_through"] = len(body.picks)
    if body.latency_ms is not None:
        samples = [*details.get("latency_samples_ms", []), body.latency_ms][-1000:]
        details["latency_samples_ms"] = samples
    connection.updated_at = datetime.now(timezone.utc)
    connection.details = details
    if body.state != "CONNECTED":
        # A disconnect must not erase the last verified baseline/metadata.
        connection.status = body.state
        await session.commit()
        return view(connection)
    if body.picks:
        mapped = (await session.execute(select(PlayerIdentity.yahoo_player_id, PlayerIdentity.id)
            .where(PlayerIdentity.yahoo_player_id.in_(ids)))).all()
        if len(mapped) != len(ids) or len({yahoo_id for yahoo_id, _ in mapped}) != len(ids):
            connection.status = "NEEDS ATTENTION"
            await session.commit()
            raise HTTPException(status_code=422, detail="Unknown or ambiguous Yahoo player ID")
    if connection.mode == "live":
        connection.status = "OBSERVE ONLY"
        await session.commit()
        return view(connection)
    require_practice_enabled()
    if details.get("total_teams") != 12 or not details.get("rounds") or not details.get("user_slot"):
        connection.status = "NEEDS ATTENTION"
        await session.commit()
        return view(connection)
    if not connection.session_id:
        connection.status = "CATCHING UP"
        await session.commit()
        league = await session.get(League, league_key)
        if league is None or league.season is None:
            raise HTTPException(status_code=422, detail="Imported source season unavailable")
        year = league.season
        await session.commit()
        result = await create_browser_practice(
            session, source_league_key=league_key, season=f"{year}-{(year+1)%100:02}",
            user_slot=details["user_slot"], rounds=details["rounds"],
            connection_key=connection.id,
        )
        connection.session_id = result.state.session_id
        await session.commit()
    if body.picks:
        try:
            await ingest_browser_practice(session, connection.session_id, body.picks)
        except HTTPException as error:
            await session.rollback()
            connection = await session.get(ObserverConnection, connection_id)
            connection.status = "CONFLICT" if error.status_code == 409 else "NEEDS ATTENTION"
            await session.commit()
            raise
    draft = await session.get(DraftSession, connection.session_id, populate_existing=True)
    sync = await session.get(DraftSyncState, connection.session_id, populate_existing=True)
    through = sync.source_confirmed_through
    next_pick = through + 1
    slot = (next_pick-1) % 12 + 1
    if ((next_pick-1)//12) % 2:
        slot = 13-slot
    connection.details = {**details, "court_iq_through": through, "next_pick": next_pick}
    connection.status = (
        "DRAFT ENDED" if draft.status == "completed" else
        "YOUR TURN" if slot == details["user_slot"] else "SYNCED"
    )
    await session.commit()
    return view(connection)

"""Disposable Yahoo mock acquisition using the existing internal session engine."""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import insert, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.draft.contracts import DraftSessionCreateRequest, DraftSessionEventResult
from app.features.draft.models import DraftPlayerMetric, DraftSession, DraftSyncState
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.players.models import LeaguePlayer, PlayerIdentity
from app.services.draft.sessions import _pick_slot, create_draft_session, get_draft_session, reconcile_source_picks

SOURCE = "yahoo_mock_browser"


class BrowserPick(Protocol):
    overall_pick: int
    yahoo_player_id: str
    observed_at: datetime


def is_browser_practice(draft: DraftSession) -> bool:
    return (
        draft.draft_source == "internal_mock"
        and draft.draft_order_evidence.get("practice_source") == SOURCE
        and draft.league_key.startswith("yahoo-mock-practice.")
    )


async def create_browser_practice(
    session: AsyncSession, *, source_league_key: str, season: str,
    user_slot: int, rounds: int, connection_key: str | None = None,
):
    key = f"yahoo-mock-practice.{connection_key[:32] if connection_key else uuid4().hex}"
    if connection_key:
        async with session.begin():
            existing = await session.scalar(select(DraftSession).where(DraftSession.league_key == key))
            if existing:
                if (not is_browser_practice(existing) or existing.draft_position != user_slot
                        or existing.rounds != rounds or existing.season != season):
                    raise HTTPException(status_code=409, detail="Existing practice initialization conflicts")
                state = await get_draft_session(session, existing.id)
                return DraftSessionEventResult(state=state, event="unchanged")
            if await session.get(League, key):
                raise HTTPException(status_code=409, detail="Practice initialization interrupted before session creation")
    async with session.begin():
        original = await session.get(League, source_league_key)
        settings = await session.get(LeagueSettings, source_league_key)
        if original is None or settings is None or source_league_key.startswith("yahoo-mock-practice."):
            raise HTTPException(status_code=422, detail="An imported source league with settings is required")
        if str(original.season) != season[:4] or not 1 <= user_slot <= 12 or not 1 <= rounds <= 50:
            raise HTTPException(status_code=422, detail="Invalid practice season, slot or rounds")
        session.add(League(
            league_key=key, game_key="yahoo_mock_practice", season=original.season,
            league_name="Yahoo Mock Practice - disposable",
            source_payload={"practice_source": SOURCE, "source_league_key": source_league_key},
        ))
        await session.flush()
        session.add(LeagueSettings(
            league_key=key, scoring_settings=deepcopy(settings.scoring_settings),
            roster_positions=deepcopy(settings.roster_positions), source_payload={"practice_source": SOURCE},
        ))
        slots = {f"{key}.slot.{slot}": slot for slot in range(1, 13)}
        for team_key, slot in slots.items():
            session.add(Team(
                league_key=key, team_key=team_key,
                team_name="Box Score Bully" if slot == user_slot else f"Mock Slot {slot}",
                source_payload={"practice_source": SOURCE, "mock_slot": slot},
            ))
        # Copy only league-scoped pool/metrics, never identities, NBA stats, rosters or opponents.
        for model in (LeaguePlayer, DraftPlayerMetric):
            table = model.__table__
            columns = [column for column in table.columns if column.name not in {"id", "imported_at"}]
            await session.execute(insert(table).from_select(
                [column.name for column in columns],
                select(*[
                    literal(key) if column.name == "league_key" else column
                    for column in columns
                ]).where(table.c.league_key == source_league_key),
            ))
    return await create_draft_session(
        session,
        DraftSessionCreateRequest(
            league_key=key, season=season, manager_team_key=f"{key}.slot.{user_slot}",
            draft_position=user_slot, total_teams=12, rounds=rounds, team_slots=slots,
        ),
        draft_source="internal_mock",
        mock_run_config={
            "seed": 0, "aggressiveness": 0, "auto_pick_enabled": False,
            "live_sync_rehearsal": True, "practice_source": SOURCE,
        },
    )


async def ingest_browser_practice(session: AsyncSession, session_id: str, picks: list[BrowserPick]) -> dict:
    draft = await session.get(DraftSession, session_id)
    if draft is None or not is_browser_practice(draft):
        raise HTTPException(status_code=403, detail="Only a disposable Yahoo Mock Practice session is accepted")
    sync = await session.get(DraftSyncState, session_id)
    if sync is None or not sync.enabled:
        raise HTTPException(status_code=409, detail="Practice observation is disabled")
    if sync.status == "conflict":
        raise HTTPException(status_code=409, detail="Practice conflict is latched; automatic writes stopped")
    if len(picks) < sync.source_confirmed_through:
        raise HTTPException(status_code=409, detail="History shortened; resend complete history from pick 1")
    seen: set[str] = set()
    for expected, pick in enumerate(picks, 1):
        if pick.overall_pick != expected or pick.yahoo_player_id in seen:
            raise HTTPException(status_code=422, detail="History must be contiguous from 1 with unique Yahoo IDs")
        seen.add(pick.yahoo_player_id)
    ids = [pick.yahoo_player_id for pick in picks]
    rows = (await session.execute(select(PlayerIdentity.id, PlayerIdentity.yahoo_player_id)
        .where(PlayerIdentity.yahoo_player_id.in_(ids)))).all()
    mapping: dict[str, list[int]] = {}
    for identity_id, yahoo_id in rows:
        mapping.setdefault(yahoo_id, []).append(identity_id)
    if any(len(mapping.get(yahoo_id, [])) != 1 for yahoo_id in ids):
        raise HTTPException(status_code=422, detail="Unknown or ambiguous Yahoo player ID")
    pool = set((await session.scalars(select(LeaguePlayer.player_identity_id)
        .where(LeaguePlayer.league_key == draft.league_key))).all())
    if any(mapping[yahoo_id][0] not in pool for yahoo_id in ids):
        raise HTTPException(status_code=422, detail="Yahoo ID is outside the practice pool")
    slot_keys = {slot: key for key, slot in draft.team_slots.items()}
    normalized = []
    for pick in picks:
        round_number, slot = _pick_slot(pick.overall_pick, 12)
        if round_number > draft.rounds:
            raise HTTPException(status_code=422, detail="Pick exceeds configured mock rounds")
        normalized.append({
            "overall_pick": pick.overall_pick,
            "round_number": round_number,
            "team_key": slot_keys[slot],
            "player_identity_id": mapping[pick.yahoo_player_id][0],
            "source_evidence": {
                "source": SOURCE, "yahoo_player_id": pick.yahoo_player_id,
                "observed_at": pick.observed_at.isoformat(),
            },
        })
    # End the read transaction before the existing reconciler acquires its session lock.
    await session.commit()
    accepted, confirmed, through, status, conflict_pick, _ = await reconcile_source_picks(
        session, session_id, normalized, retrieved_at=datetime.now(timezone.utc), source=SOURCE,
    )
    if status == "conflict":
        raise HTTPException(status_code=409, detail={
            "reason": "practice_source_conflict", "overall_pick": conflict_pick,
        })
    return {
        "mode": SOURCE, "accepted_picks": accepted, "confirmed_picks": confirmed,
        "confirmed_through": through, "status": status, "draft_writes": bool(accepted),
        "draft_room_path": f"/draft/{session_id}",
    }

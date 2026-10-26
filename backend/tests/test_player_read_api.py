import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.database import Base, SessionFactory, engine
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.players.models import FantasyTeam, LeaguePlayer, PlayerIdentity, RosterEntry
from app.main import app
from app.services.yahoo.client import YahooFantasyClient
from schema_support import create_test_schema

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL to run PostgreSQL-backed player API tests",
)


def test_player_and_league_read_routes_use_postgres_only(monkeypatch) -> None:
    suffix = uuid4().hex[:12]
    league_key = f"nba.read.{suffix}"
    team_key = f"{league_key}.t.1"
    stale_team_key = f"{league_key}.t.2"
    not_imported_team_key = f"{league_key}.t.3"
    yahoo_player_id = f"read-{suffix}"
    source_as_of = datetime(2026, 10, 19, tzinfo=timezone.utc)
    source_settings = {
        "fantasy_content": {
            "league": [
                {"league_key": league_key},
                {
                    "settings": [
                        {"scoring_type": "head"},
                        {
                            "stat_categories": {
                                "stats": [
                                    {"stat": {"stat_id": "77", "display_name": "Fixture Stat"}}
                                ]
                            }
                        },
                        {
                            "stat_modifiers": {
                                "stats": [{"stat": {"stat_id": "77", "value": "2.5"}}]
                            }
                        },
                        {
                            "roster_positions": {
                                "0": {"roster_position": {"position": "C", "count": "1"}}
                            }
                        },
                    ]
                },
            ]
        }
    }

    async def forbidden_yahoo_call(self, path: str, access_token: str) -> dict:
        raise AssertionError("A GET endpoint attempted to call Yahoo")

    monkeypatch.setattr(YahooFantasyClient, "get_json", forbidden_yahoo_call)

    async def seed() -> int:
        async with engine.begin() as connection:
            await create_test_schema(connection)
        async with SessionFactory() as session:
            async with session.begin():
                session.add(
                    League(
                        league_key=league_key,
                        game_key="nba_fixture",
                        league_name="Read Contract Fixture",
                        season=2026,
                        source_payload={"league_key": league_key},
                        imported_at=source_as_of,
                    )
                )
                session.add(
                    LeagueSettings(
                        league_key=league_key,
                        scoring_settings={"scoring_type": "head", "categories": []},
                        roster_positions=[{"position": "C", "count": "1"}],
                        source_payload=source_settings,
                        imported_at=source_as_of,
                    )
                )
                session.add(
                    Team(
                        team_key=team_key,
                        league_key=league_key,
                        team_name="Read Fixture Team",
                        source_payload={"team_key": team_key},
                        imported_at=source_as_of,
                    )
                )
                session.add(
                    Team(
                        team_key=stale_team_key,
                        league_key=league_key,
                        team_name="Stale Fixture Team",
                        source_payload={"team_key": stale_team_key},
                        imported_at=source_as_of + timedelta(hours=1),
                    )
                )
                session.add(
                    Team(
                        team_key=not_imported_team_key,
                        league_key=league_key,
                        team_name="Unimported Fixture Team",
                        source_payload={"team_key": not_imported_team_key},
                        imported_at=source_as_of,
                    )
                )
                identity = PlayerIdentity(
                    yahoo_player_id=yahoo_player_id,
                    player_name="Fixture Center",
                    team="DEN",
                    position="C",
                    status=None,
                )
                session.add(identity)
                await session.flush()
                session.add(
                    FantasyTeam(
                        team_key=team_key,
                        league_key=league_key,
                        team_name="Read Fixture Team",
                        source_payload={"team_key": team_key},
                        imported_at=source_as_of,
                    )
                )
                session.add(
                    FantasyTeam(
                        team_key=stale_team_key,
                        league_key=league_key,
                        team_name="Stale Fixture Team",
                        source_payload={"team_key": stale_team_key},
                        imported_at=source_as_of,
                    )
                )
                session.add(
                    LeaguePlayer(
                        league_key=league_key,
                        yahoo_player_id=yahoo_player_id,
                        player_identity_id=identity.id,
                        source_payload={"player_key": f"nba.p.{yahoo_player_id}"},
                    )
                )
                session.add(
                    RosterEntry(
                        league_key=league_key,
                        team_key=team_key,
                        yahoo_player_id=yahoo_player_id,
                        player_identity_id=identity.id,
                        roster_position="C",
                        source_payload={"selected_position": "C"},
                    )
                )
                return identity.id

    internal_id = asyncio.run(seed())
    asyncio.run(engine.dispose())
    try:
        with TestClient(app) as client:
            league_response = client.get("/api/v1/league", params={"league_key": league_key})
            players_response = client.get("/api/v1/players")
            player_response = client.get(f"/api/v1/player/{internal_id}")
            rosters_response = client.get("/api/v1/rosters", params={"league_key": league_key})

        assert league_response.status_code == 200
        assert set(league_response.json()) == {
            "league_key",
            "league_name",
            "season",
            "league_imported_at",
            "settings_imported_at",
            "draft_pick_time_seconds",
            "scoring_settings",
            "roster_positions",
            "teams",
        }
        assert league_response.json()["draft_pick_time_seconds"] is None
        assert league_response.json()["scoring_settings"] == {
            "scoring_type": "head",
            "categories": [{"stat_id": "77", "name": "Fixture Stat", "value": 2.5}],
        }
        assert league_response.json()["roster_positions"] == [
            {"position": "C", "count": "1"}
        ]
        assert players_response.status_code == 200
        assert any(player["yahoo_player_id"] == yahoo_player_id for player in players_response.json())
        assert player_response.status_code == 200
        assert player_response.json()["id"] == internal_id
        assert rosters_response.status_code == 200
        rosters = {roster["team_key"]: roster for roster in rosters_response.json()}
        assert set(rosters) == {team_key, stale_team_key, not_imported_team_key}
        assert rosters[team_key]["roster_data_status"] == "available"
        assert rosters[team_key]["roster_source"] == "yahoo"
        assert datetime.fromisoformat(
            rosters[team_key]["roster_as_of"].replace("Z", "+00:00")
        ) == source_as_of
        assert rosters[team_key]["players"][0]["id"] == internal_id
        assert rosters[stale_team_key]["roster_data_status"] == "stale"
        assert rosters[stale_team_key]["players"] == []
        assert rosters[not_imported_team_key]["roster_data_status"] == "not_imported"
        assert rosters[not_imported_team_key]["roster_source"] is None
        assert rosters[not_imported_team_key]["roster_as_of"] is None
        assert rosters[not_imported_team_key]["players"] == []
    finally:
        async def cleanup() -> None:
            async with SessionFactory() as session:
                async with session.begin():
                    await session.execute(delete(RosterEntry).where(RosterEntry.league_key == league_key))
                    await session.execute(delete(LeaguePlayer).where(LeaguePlayer.league_key == league_key))
                    await session.execute(delete(FantasyTeam).where(FantasyTeam.league_key == league_key))
                    await session.execute(delete(PlayerIdentity).where(PlayerIdentity.yahoo_player_id == yahoo_player_id))
                    await session.execute(delete(Team).where(Team.league_key == league_key))
                    await session.execute(delete(LeagueSettings).where(LeagueSettings.league_key == league_key))
                    await session.execute(delete(League).where(League.league_key == league_key))

        asyncio.run(cleanup())
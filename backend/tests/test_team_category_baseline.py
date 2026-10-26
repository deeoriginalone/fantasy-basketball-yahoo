import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.features.championship.contracts import TeamCategoryResult, TeamIdentityBaseline
from app.features.championship.service import (
    MINIMUM_COMPARABLE_TEAMS,
    STRENGTH_THRESHOLD,
    TEAM_IDENTITY_CALCULATION_VERSION,
    WEAKNESS_THRESHOLD,
    _apply_league_relative_comparisons,
    _category_definition,
    _category_direction,
    _identity_label,
    _source_season,
)
from app.core.database import get_session
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.nba.models import NbaPlayer, NbaPlayerSeasonStats
from app.features.players.models import FantasyTeam, PlayerIdentity, RosterEntry
from app.main import app
from app.services.nba.client import NbaApiClient
from app.services.yahoo.client import YahooFantasyClient
from schema_support import create_test_schema

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL to run PostgreSQL-backed category baseline tests",
)


def test_category_setting_recognition() -> None:
    persisted_fixture_categories = [
        ("12", "PTS", "PTS"),
        ("15", "REB", "REB"),
        ("16", "AST", "AST"),
        ("17", "ST", "STL"),
        ("18", "BLK", "BLK"),
        ("19", "TO", "TOV"),
    ]
    for stat_id, name, field in persisted_fixture_categories:
        assert _category_definition({"stat_id": stat_id, "name": name}) == (
            "sum_of_player_per_game_rates",
            field,
        )
    assert _category_definition({"stat_id": "5", "name": "FG%"}) == (
        "weighted_percentage_from_season_makes_attempts",
        ("FGM", "FGA"),
    )
    assert _category_definition({"stat_id": "77", "name": "Free Throw Percentage"}) == (
        "weighted_percentage_from_season_makes_attempts",
        ("FTM", "FTA"),
    )
    assert _category_definition({"stat_id": "77", "name": "Fixture Stat"}) is None
    assert _category_direction({"stat_id": "19", "configured_value": -1}, "TOV") == "lower_is_better"
    assert _category_direction({"stat_id": "12", "configured_value": 1}, "PTS") == "higher_is_better"


def _identity_team(
    team_key: str,
    value: float | None,
    *,
    status: str = "available",
    roster_status: str = "available",
    direction: str = "higher_is_better",
) -> TeamIdentityBaseline:
    category = TeamCategoryResult(
        category_id="12",
        category_name="PTS",
        configured_value=-1 if direction == "lower_is_better" else 1,
        status=status,
        reason=None,
        calculation_type="sum_of_player_per_game_rates",
        direction=direction if status != "unsupported" else None,
        raw_value=value,
        numerator_total=None,
        denominator_total=None,
        contributing_player_count=int(value is not None),
        missing_or_unmapped_player_count=int(status == "partial"),
        missing_denominator_player_count=0,
        missing_players=[],
        source_table="nba_player_season_stats" if value is not None else None,
        source_imports=[],
    )
    return TeamIdentityBaseline(
        league_key="nba.l.fixture",
        team_key=team_key,
        team_name=team_key,
        roster_data_status=roster_status,
        roster_as_of=None,
        roster_player_count=1,
        mapped_player_count=1,
        unmapped_player_count=0,
        categories=[category],
    )


def test_source_season_is_latest_eligible_season_not_player_intersection() -> None:
    rows = [
        SimpleNamespace(season="2024-25", season_type="Regular Season", games_played=50),
        SimpleNamespace(season="2025-26", season_type="Regular Season", games_played=30),
        SimpleNamespace(season="2024-25", season_type="Regular Season", games_played=20),
    ]

    assert _source_season(rows, 2026) == "2025-26"
    assert _source_season(rows, 2024) == "2024-25"


def test_league_relative_higher_is_better_ranks_ties_and_normalizes() -> None:
    teams = [
        _identity_team("low", 10),
        _identity_team("tied-a", 20),
        _identity_team("tied-b", 20),
        _identity_team("high", 40),
    ]

    _apply_league_relative_comparisons(teams, "2025-26", "Regular Season")
    results = {team.team_key: team.categories[0].league_relative for team in teams}

    assert results["high"].rank == 1
    assert results["tied-a"].rank == results["tied-b"].rank == 2
    assert results["low"].rank == 4
    assert results["low"].minimum == 10
    assert results["high"].maximum == 40
    assert results["tied-a"].median == 20
    assert results["tied-a"].normalized_position == pytest.approx(100 / 3)
    assert results["high"].normalized_position == 100
    assert results["high"].label == "strength"
    assert results["low"].label == "weakness"
    assert results["high"].comparable_team_count == 4
    assert results["high"].calculation_version == TEAM_IDENTITY_CALCULATION_VERSION
    assert results["high"].minimum_comparable_teams == MINIMUM_COMPARABLE_TEAMS
    assert results["high"].strength_threshold == STRENGTH_THRESHOLD
    assert results["high"].weakness_threshold == WEAKNESS_THRESHOLD


def test_identity_thresholds_are_inclusive_and_versioned() -> None:
    assert _identity_label(STRENGTH_THRESHOLD, True) == "strength"
    assert _identity_label(WEAKNESS_THRESHOLD, True) == "weakness"
    assert _identity_label(50, True) == "neutral"
    assert _identity_label(100, False) == "insufficient_evidence"


def test_league_relative_lower_is_better_reverses_rank_and_position() -> None:
    teams = [
        _identity_team("best", 1, direction="lower_is_better"),
        _identity_team("middle", 2, direction="lower_is_better"),
        _identity_team("poor", 4, direction="lower_is_better"),
    ]

    _apply_league_relative_comparisons(teams, "2025-26", "Regular Season")
    results = {team.team_key: team.categories[0].league_relative for team in teams}

    assert results["best"].rank == 1
    assert results["poor"].rank == 3
    assert results["best"].normalized_position == 100
    assert results["poor"].normalized_position == 0
    assert results["best"].label == "strength"
    assert results["poor"].label == "weakness"


def test_league_relative_equal_values_are_tied_and_neutral() -> None:
    teams = [_identity_team(f"team-{index}", 5) for index in range(3)]

    _apply_league_relative_comparisons(teams, "2025-26", "Regular Season")

    for team in teams:
        relative = team.categories[0].league_relative
        assert relative.rank == 1
        assert relative.normalized_position == 50
        assert relative.label == "neutral"


def test_league_relative_comparisons_never_cross_league_boundaries() -> None:
    teams = [
        _identity_team("a-1", 10),
        _identity_team("a-2", 20),
        _identity_team("a-3", 30),
        _identity_team("b-1", 100),
        _identity_team("b-2", 200),
        _identity_team("b-3", 300),
    ]
    for team in teams[3:]:
        team.league_key = "nba.l.other"

    _apply_league_relative_comparisons(teams, "2025-26", "Regular Season")

    results = {team.team_key: team.categories[0].league_relative for team in teams}
    assert all(results[key].comparable_team_count == 3 for key in results)
    assert [results[f"a-{index}"].rank for index in (1, 2, 3)] == [3, 2, 1]
    assert [results[f"b-{index}"].rank for index in (1, 2, 3)] == [3, 2, 1]


def test_league_relative_excludes_partial_stale_unavailable_and_unsupported() -> None:
    teams = [
        _identity_team("complete-1", 10),
        _identity_team("complete-2", 20),
        _identity_team("partial", 30, status="partial"),
        _identity_team("stale", 40, roster_status="stale"),
        _identity_team("unavailable", None, status="unavailable"),
        _identity_team("unsupported", None, status="unsupported"),
    ]

    _apply_league_relative_comparisons(teams, "2025-26", "Regular Season")
    results = {team.team_key: team.categories[0].league_relative for team in teams}
    excluded = {team.team_key: team for team in results["partial"].excluded_teams}

    assert results["partial"].comparison_status == "insufficient"
    assert results["partial"].comparable_team_count == 2
    assert results["partial"].rank is None
    assert results["partial"].normalized_position is None
    assert results["partial"].label == "insufficient_evidence"
    assert results["partial"].coverage_status == "partial"
    assert results["stale"].coverage_status == "stale"
    assert results["unavailable"].coverage_status == "unavailable"
    assert results["unsupported"].coverage_status == "unsupported"
    assert "partial_category_coverage" in excluded["partial"].reasons
    assert "stale_roster_snapshot" in excluded["stale"].reasons
    assert "unsupported_category" in excluded["unsupported"].reasons


def test_league_relative_requires_a_selected_source_contract() -> None:
    teams = [_identity_team(f"team-{index}", index) for index in range(3)]

    _apply_league_relative_comparisons(teams, None, None)

    assert all(team.categories[0].league_relative.comparison_status == "insufficient" for team in teams)
    assert all(team.categories[0].league_relative.rank is None for team in teams)
    assert all(
        {"source_season_unavailable", "source_stat_type_unavailable"}.issubset(
            team.categories[0].league_relative.excluded_teams[0].reasons
        )
        for team in teams
    )


def test_database_only_team_category_baseline(monkeypatch) -> None:
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"], poolclass=NullPool)
    SessionFactory = async_sessionmaker(engine, expire_on_commit=False)

    async def test_session():
        async with SessionFactory() as session:
            yield session

    monkeypatch.setitem(app.dependency_overrides, get_session, test_session)
    suffix = uuid4().hex[:12]
    league_key = f"nba.category.{suffix}"
    team_keys = {index: f"{league_key}.t.{index}" for index in range(1, 6)}
    nba_ids = {number: f"nba-{suffix}-{number}" for number in (111, 222, 444, 555)}
    timestamp = datetime(2026, 10, 19, tzinfo=timezone.utc)
    categories = [
        {"stat_id": "12", "name": "PTS", "value": 1},
        {"stat_id": "5", "name": "FG%", "value": 1},
        {"stat_id": "8", "name": "FT%", "value": 1},
        {"stat_id": "19", "name": "TO", "value": -1},
        {"stat_id": "77", "name": "Fixture Stat", "value": 1},
    ]

    async def forbidden_yahoo_call(self, path: str, access_token: str) -> dict:
        raise AssertionError("The category baseline attempted to call Yahoo")

    def forbidden_nba_call(self, *args, **kwargs):
        raise AssertionError("The category baseline attempted to call an NBA provider")

    monkeypatch.setattr(YahooFantasyClient, "get_json", forbidden_yahoo_call)
    monkeypatch.setattr(NbaApiClient, "fetch_player_season_stats", forbidden_nba_call)

    async def seed() -> None:
        async with engine.begin() as connection:
            await create_test_schema(connection)
        async with SessionFactory() as session:
            async with session.begin():
                session.add(League(
                    league_key=league_key,
                    game_key="nba_fixture",
                    league_name="Category Fixture",
                    season=2026,
                    source_payload={"league_key": league_key},
                    imported_at=timestamp,
                ))
                session.add(LeagueSettings(
                    league_key=league_key,
                    scoring_settings={"scoring_type": "head", "categories": categories},
                    roster_positions=[],
                    source_payload={},
                    imported_at=timestamp,
                ))

                players = [
                    PlayerIdentity(yahoo_player_id=f"y-{suffix}-1", nba_player_id=nba_ids[111], player_name="First Player"),
                    PlayerIdentity(yahoo_player_id=f"y-{suffix}-2", nba_player_id=nba_ids[222], player_name="Second Player"),
                    PlayerIdentity(yahoo_player_id=f"y-{suffix}-3", nba_player_id=None, player_name="Unmapped Player"),
                    PlayerIdentity(yahoo_player_id=f"y-{suffix}-4", nba_player_id=nba_ids[444], player_name="Older Stats Player"),
                    PlayerIdentity(yahoo_player_id=f"y-{suffix}-5", nba_player_id=nba_ids[555], player_name="No Attempts Player"),
                ]
                session.add_all(players)
                await session.flush()

                for index, team_key in team_keys.items():
                    session.add(Team(
                        team_key=team_key,
                        league_key=league_key,
                        team_name=f"Fixture Team {index}",
                        source_payload={"team_key": team_key},
                        imported_at=timestamp,
                    ))
                session.add_all([
                    FantasyTeam(
                        team_key=team_keys[1], league_key=league_key, team_name="Fixture Team 1",
                        source_payload={}, imported_at=timestamp,
                    ),
                    FantasyTeam(
                        team_key=team_keys[2], league_key=league_key, team_name="Fixture Team 2",
                        source_payload={}, imported_at=timestamp,
                    ),
                    FantasyTeam(
                        team_key=team_keys[3], league_key=league_key, team_name="Fixture Team 3",
                        source_payload={}, imported_at=timestamp,
                    ),
                    FantasyTeam(
                        team_key=team_keys[5], league_key=league_key, team_name="Fixture Team 5",
                        source_payload={}, imported_at=timestamp,
                    ),
                ])
                assignments = [
                    (1, 0), (1, 1),
                    (2, 0), (2, 2), (2, 3),
                    (5, 4),
                ]
                for team_index, player_index in assignments:
                    if player_index is None:
                        continue
                    player = players[player_index]
                    session.add(RosterEntry(
                        league_key=league_key,
                        team_key=team_keys[team_index],
                        yahoo_player_id=player.yahoo_player_id,
                        player_identity_id=player.id,
                        roster_position=None,
                        source_payload={},
                        imported_at=timestamp,
                    ))

                for nba_id in nba_ids.values():
                    session.add(NbaPlayer(
                        nba_player_id=nba_id,
                        player_name=nba_id,
                        team_id=None,
                        team_abbreviation=None,
                        roster_status=None,
                        from_year=None,
                        to_year=None,
                        source_payload={},
                    ))
                await session.flush()
                session.add_all([
                    NbaPlayerSeasonStats(
                        nba_player_id=nba_ids[111], season="2025-26", season_type="Regular Season",
                        games_played=30, games_started=30, minutes_per_game=30, usage_pct=0.2,
                        base_stats={"PTS": 20, "FGM": 8, "FGA": 10, "FTM": 4, "FTA": 5, "TOV": 3},
                        advanced_stats={}, source_payload={}, imported_at=timestamp,
                    ),
                    NbaPlayerSeasonStats(
                        nba_player_id=nba_ids[222], season="2025-26", season_type="Regular Season",
                        games_played=20, games_started=10, minutes_per_game=24, usage_pct=0.15,
                        base_stats={"PTS": 10, "FGM": 3, "FGA": 10, "FTM": 2, "FTA": 4, "TOV": 1},
                        advanced_stats={}, source_payload={}, imported_at=timestamp,
                    ),
                    NbaPlayerSeasonStats(
                        nba_player_id=nba_ids[444], season="2024-25", season_type="Regular Season",
                        games_played=50, games_started=40, minutes_per_game=28, usage_pct=0.18,
                        base_stats={"PTS": 18, "FGM": 7, "FGA": 12, "FTM": 3, "FTA": 4, "TOV": 2},
                        advanced_stats={}, source_payload={}, imported_at=timestamp,
                    ),
                    NbaPlayerSeasonStats(
                        nba_player_id=nba_ids[555], season="2025-26", season_type="Regular Season",
                        games_played=10, games_started=0, minutes_per_game=8, usage_pct=0.05,
                        base_stats={"PTS": 2, "FGM": 5, "FTM": 1, "FTA": 2, "TOV": 0},
                        advanced_stats={}, source_payload={}, imported_at=timestamp,
                    ),
                ])

    try:
        asyncio.run(seed())
        asyncio.run(engine.dispose())
        client = TestClient(app)
        try:
            response = client.get(
                "/api/v1/team-category-baseline",
                params={"league_key": league_key},
            )
        finally:
            client.close()

        assert response.status_code == 200
        payload = response.json()
        assert payload["league_key"] == league_key
        assert payload["selected_source_season"] == "2025-26"
        assert payload["selected_source_stat_type"] == "Regular Season"
        assert payload["source_season_selection"] == "latest_eligible_season_with_rostered_player_stats"
        assert payload["identity_method"]["calculation_version"] == "team-identity-relative-v1"
        teams = {team["team_key"]: team for team in payload["teams"]}

        complete = teams[team_keys[1]]
        by_category = {category["category_id"]: category for category in complete["categories"]}
        assert by_category["12"]["status"] == "available"
        assert by_category["12"]["raw_value"] == 30
        assert by_category["12"]["calculation_type"] == "sum_of_player_per_game_rates"
        assert by_category["12"]["contributing_player_count"] == 2
        points_source = by_category["12"]["source_imports"][0]
        assert points_source["season"] == "2025-26"
        assert points_source["stat_type"] == "Regular Season"
        assert datetime.fromisoformat(points_source["imported_at"].replace("Z", "+00:00")) == timestamp
        assert points_source["player_count_with_source_stats"] == 2
        assert points_source["contributing_player_count"] == 2
        assert by_category["5"]["raw_value"] == pytest.approx(0.6)
        assert by_category["5"]["numerator_total"] == 300
        assert by_category["5"]["denominator_total"] == 500
        assert by_category["5"]["calculation_type"] == "weighted_percentage_from_season_makes_attempts"
        assert by_category["8"]["raw_value"] == pytest.approx(160 / 230)
        assert by_category["19"]["raw_value"] == 4
        assert by_category["19"]["configured_value"] == -1
        assert by_category["19"]["direction"] == "lower_is_better"
        assert by_category["77"]["status"] == "unsupported"
        assert by_category["77"]["raw_value"] is None

        partial = teams[team_keys[2]]
        partial_pts = next(category for category in partial["categories"] if category["category_id"] == "12")
        assert partial_pts["status"] == "partial"
        assert partial_pts["raw_value"] == 20
        assert partial_pts["contributing_player_count"] == 1
        assert partial_pts["missing_or_unmapped_player_count"] == 2
        assert {player["reason"] for player in partial_pts["missing_players"]} == {
            "unmapped_nba_identity",
            "no_stats_for_selected_source",
        }

        empty = teams[team_keys[3]]
        empty_pts = next(category for category in empty["categories"] if category["category_id"] == "12")
        assert empty["roster_data_status"] == "available"
        assert empty["roster_player_count"] == 0
        assert empty_pts["status"] == "unavailable"
        assert empty_pts["reason"] == "empty_roster"

        unimported = teams[team_keys[4]]
        unimported_pts = next(category for category in unimported["categories"] if category["category_id"] == "12")
        assert unimported["roster_data_status"] == "not_imported"
        assert unimported["roster_player_count"] is None
        assert unimported_pts["status"] == "unavailable"
        assert unimported_pts["reason"] == "roster_not_imported"

        no_denominator = next(
            category for category in teams[team_keys[5]]["categories"]
            if category["category_id"] == "5"
        )
        assert no_denominator["status"] == "unavailable"
        assert no_denominator["raw_value"] is None
        assert no_denominator["reason"] == "no_valid_percentage_components"
        assert no_denominator["missing_denominator_player_count"] == 1
        assert no_denominator["missing_players"][0]["player_name"] == "No Attempts Player"
        assert no_denominator["source_imports"][0]["player_count_with_source_stats"] == 1
        assert no_denominator["source_imports"][0]["contributing_player_count"] == 0

        older_only = next(
            category for category in teams[team_keys[2]]["categories"]
            if category["category_id"] == "12"
        )
        assert any(
            player["reason"] == "no_stats_for_selected_source"
            for player in older_only["missing_players"]
        )
    finally:
        async def cleanup() -> None:
            async with SessionFactory() as session:
                async with session.begin():
                    await session.execute(delete(League).where(League.league_key == league_key))
                    await session.execute(delete(NbaPlayer).where(NbaPlayer.nba_player_id.in_(nba_ids.values())))
                    await session.execute(
                        delete(PlayerIdentity).where(
                            PlayerIdentity.yahoo_player_id.like(f"y-{suffix}-%")
                        )
                    )

        asyncio.run(cleanup())
        asyncio.run(engine.dispose())

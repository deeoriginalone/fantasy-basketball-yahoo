import asyncio
import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy import delete, select, event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.core.database import engine as app_engine, get_session
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.nba.models import NbaGame, NbaPlayer, NbaPlayerSeasonStats, NbaTeam, PlayerGameLog, PlayerSchedule
from app.features.players.models import FantasyTeam, LeaguePlayer, PlayerIdentity, RosterEntry
from app.features.waivers.contracts import Candidate, Components, Evidence, Opportunity, Schedule, ValueEvidence
from app.features.waivers.service import (
    Context, WAIVER_TIMEZONE, aggregate, board_coverage, compare, coverage, current_role, enrich, freshness, identity_chain_diagnostic, identity_mapping, log_average, percentile, production, resolve_schedule, roster_fit, sample_label, scoring_fields, sufficient_sample, transaction_blockers, validated_weights, verify_league_contract, window_end_date,
)
from app.main import app
from app.services.nba.client import NbaApiClient
from app.services.yahoo.client import YahooFantasyClient
from app.services.draft.player_status import status_is_supported
from schema_support import create_test_schema

engine = create_async_engine(os.getenv("TEST_DATABASE_URL") or app_engine.url, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)
NOW = datetime.now(timezone.utc)
WEIGHTS = dict(roster_fit=.35, player_value=.25, opportunity=.15, schedule=.15, acquisition_value=.10)


def candidate(pid, position="C", value=60, schedule=50):
    return Candidate(
        player_id=pid, yahoo_player_id=str(pid), player_name=f"Player {pid}",
        position=position, nba_team="DEN", yahoo_status=None, availability="free_agent", eligible=True,
        recent=ValueEvidence(value=value, games=4, label="Recent"),
        ros=ValueEvidence(value=value, games=40, label="History, not projection"),
        opportunity=Opportunity(minutes=30), schedule=Schedule(window_start=NOW.date(), window_end=NOW.date()),
        components=Components(roster_fit=50, player_value=value, schedule=schedule, opportunity=70),
        recommended_action="WATCH", hold_type="undetermined", reasons=[], limitations=[], data_quality={},
    )


def test_weights_missing_evidence_and_determinism():
    weights = validated_weights(WEIGHTS)
    parts = Components(roster_fit=100, player_value=80, opportunity=40, schedule=60)
    first, effective = aggregate(parts, weights)
    assert first == aggregate(parts, weights)[0]
    assert first == round((35 + 20 + 6 + 9) / .9, 6)
    assert "acquisition_value" not in effective
    assert sum(effective.values()) == pytest.approx(1)
    assert aggregate(Components(roster_fit=100), weights) == (None, {})
    assert percentile(10, [10, 10]) == 50
    assert percentile(10, [1, 10, 20]) == percentile(10, [20, 10, 1])
    for invalid in ({}, {**WEIGHTS, "schedule": float("nan")}, {key: 0 for key in WEIGHTS}):
        with pytest.raises(ValueError):
            validated_weights(invalid)
    assert freshness(NOW - timedelta(days=2), NOW) == "stale"
    assert scoring_fields({"scoring_type": "head", "categories": []}) is None
    assert scoring_fields({"scoring_type": "points", "categories": [{"stat_id": "999", "name": "made up", "value": 1}]}) is None
    assert scoring_fields({"scoring_type": "points", "categories": [{"stat_id": "12"}]}) is None
    assert production({"PTS": 20}, {"PTS": 1, "AST": 2}) is None
    assert production({"PTS": 20, "AST": 0}, {"PTS": 1, "AST": 2}) == 20
    assert log_average([SimpleNamespace(stats_payload={"PTS": 10, "MIN": 20}), SimpleNamespace(stats_payload={"PTS": 20})]) == {"PTS": 15}


def test_personal_application_manager_configuration():
    settings = Settings(_env_file=None)
    assert settings.waiver_manager_team_key == "478.l.50505.t.9"


def test_identity_mapping_requires_normalized_name_and_verified_team_without_writes():
    nba = SimpleNamespace(
        nba_player_id="123", player_name="Jrue Holiday",
        team_id="den-id", team_abbreviation="DEN",
    )
    identity = SimpleNamespace(
        player_name="Jrue Holiday", yahoo_player_id="y123",
        nba_player_id="123", team="DEN",
    )
    by_name = {"jrue holiday": [nba]}
    assert identity_mapping(identity, nba, by_name, {"den-id": "DEN"}, "DEN")[:2] == (
        "EXACT_NAME_TEAM", "Yahoo and NBA names and team abbreviations match.",
    )

    state, reason, _ = identity_mapping(identity, nba, by_name, {"den-id": "DEN"}, "BOS")
    assert state == "AMBIGUOUS"
    assert "conflicts" in reason

    unmapped = SimpleNamespace(
        player_name="Jrue Holiday", yahoo_player_id="y-unmapped",
        nba_player_id=None, team="BOS",
    )
    state, reason, matches = identity_mapping(unmapped, None, by_name, {"den-id": "DEN"}, "BOS")
    assert state == "AMBIGUOUS"
    assert len(matches) == 1
    assert "does not establish a unique" in reason
    assert unmapped.nba_player_id is None


def test_positional_fit_changes_ranking_without_inventing_categories():
    guard = candidate(1, "PG", 90)
    extra_guard = candidate(2, "PG", 90)
    center = candidate(3, "C", 65)
    slots = ["PG", "C"]
    assert roster_fit(center, [guard], slots) == 100
    assert roster_fit(extra_guard, [guard], slots) == 50
    center.components.roster_fit = roster_fit(center, [guard], slots)
    extra_guard.components.roster_fit = roster_fit(extra_guard, [guard], slots)
    assert aggregate(center.components, WEIGHTS)[0] > aggregate(extra_guard.components, WEIGHTS)[0]
    assert roster_fit(center, [candidate(4, None)], slots) is None


def test_swap_model_recomputes_roster_with_fixed_common_weights():
    guard, weak, add = candidate(1, "PG", 60), candidate(2, "PG", 10), candidate(3, "C", 90)
    ctx = Context(SimpleNamespace(), "t1", "this_week", NOW, {row.player_id: row for row in [guard, weak, add]},
        [1, 2], ["PG", "C"], 2, True, WEIGHTS, {})
    result = compare(ctx, add, 2)
    assert result.net_improvement > 0
    assert result.net_improvement == pytest.approx(result.after_score - result.before_score, abs=1e-6)
    assert result.component_deltas.roster_fit > 0
    assert compare(ctx, add, 2) == result
    add.components.schedule = 10
    assert compare(ctx, add, 2).net_improvement < result.net_improvement
    add.components.player_value = None
    assert compare(ctx, add, 2).net_improvement is None
    add.components.player_value = 90
    ctx.roster_ready = False
    assert compare(ctx, add, 2).net_improvement is None


def test_add_without_drop_uses_same_roster_model():
    guard, add = candidate(1, "PG", 60), candidate(2, "C", 80)
    ctx = Context(SimpleNamespace(), "t1", "ros", NOW, {1: guard, 2: add}, [1], ["PG", "C"], 2, True, WEIGHTS, {})
    result = compare(ctx, add, None)
    assert result.player_id is None
    assert result.net_improvement > 0
    assert result.component_deltas.roster_fit > 0


def test_fully_covered_lineup_has_no_fit_gain_from_reassignment_or_bench_flexibility():
    players = [candidate(1, "PG,SG", 70), candidate(2, "PF,C", 60),
        candidate(3, "SF,PF", 50), candidate(4, "PG", 65), candidate(5, "C", 55)]
    slots = ["PG", "C", "UTIL"]
    ctx = Context(SimpleNamespace(), "t1", "this_week", NOW,
        {row.player_id: row for row in players}, [1, 2, 3, 5], slots, 4, True, WEIGHTS, {})
    result = compare(ctx, players[3], 3)
    assert result.starting_slots_before == result.starting_slots_after == 3
    assert result.component_before.roster_fit == result.component_after.roster_fit == 100
    assert result.component_deltas.roster_fit == 0
    assert coverage(players[:3], slots) == 100
    for key, delta in result.component_deltas.model_dump().items():
        if delta is not None:
            assert -100 <= delta <= 100
            assert 0 <= getattr(result.component_before, key) <= 100
            assert 0 <= getattr(result.component_after, key) <= 100
    assert result.component_deltas.player_value == pytest.approx((65 - 50) / 4)
    assert 0 <= result.before_score <= 100
    assert 0 <= result.after_score <= 100
    for player in players:
        assert 0 <= roster_fit(player, players[:3], slots) <= 100
    assert compare(ctx, players[3], 3) == compare(ctx, players[3], 3)


def test_explicit_drop_controls_net_even_with_open_slot_or_better_drop():
    guard, weak, add = candidate(1, "PG", 90), candidate(2, "C", 10), candidate(3, "PG,C", 50)
    add.overall_score, add.effective_weights = aggregate(add.components, WEIGHTS)
    ctx = Context(SimpleNamespace(), "t1", "this_week", NOW, {r.player_id: r for r in [guard, weak, add]},
        [1, 2], ["PG", "C"], 3, True, WEIGHTS, {})
    preferred = enrich(ctx, add)
    explicit = enrich(ctx, add, 1)
    assert explicit.net_improvement == compare(ctx, add, 1).net_improvement
    assert explicit.comparison.player_id == 1
    assert [row.player_id for row in explicit.best_drop_options] == [1]
    assert explicit.net_improvement < compare(ctx, add, 2).net_improvement
    assert explicit.recommended_action == "INSUFFICIENT EVIDENCE"
    assert preferred.net_improvement != explicit.net_improvement
    with pytest.raises(HTTPException) as error:
        compare(ctx, add, 999)
    assert error.value.status_code == 422


@pytest.mark.parametrize(("games", "expected"), [
    (0, "NO CURRENT-SEASON EVIDENCE"), (1, "INSUFFICIENT FOR STRONG RECOMMENDATION"), (2, "INSUFFICIENT FOR STRONG RECOMMENDATION"), (3, "INSUFFICIENT FOR STRONG RECOMMENDATION"),
    (4, "VERY LIMITED"), (6, "VERY LIMITED"), (7, "LIMITED"), (9, "LIMITED"),
    (10, "GOOD"), (19, "GOOD"), (20, "EXCELLENT"),
])
def test_sample_size_labels(games, expected):
    assert sample_label(games) == expected
    player = candidate(1)
    player.recent.games = games
    player.current_season_games = games
    player.data_quality["recent"] = Evidence(state="available", source="Fixture", detail="Fresh")
    assert sufficient_sample(player, "this_week") == (games >= 7)
    assert sufficient_sample(player, "next_7_days") == (games >= 7)
    player.data_quality["recent"].state = "stale"
    assert not sufficient_sample(player, "this_week")


@pytest.mark.parametrize("instant", ["2026-10-26T06:30:00+00:00", "2026-12-28T07:30:00+00:00"])
def test_next_seven_days_crosses_pacific_sunday(instant):
    today = datetime.fromisoformat(instant).astimezone(WAIVER_TIMEZONE).date()
    assert today.weekday() == 6
    assert window_end_date(today, today.year, "this_week") == today
    assert window_end_date(today, today.year, "next_7_days") == today + timedelta(days=6)
    assert (window_end_date(today, today.year, "next_7_days") - today).days + 1 == 7
    assert window_end_date(date(2026, 10, 26), 2026, "this_week") == date(2026, 11, 1)


@pytest.fixture
def persisted(monkeypatch):
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Set TEST_DATABASE_URL for PostgreSQL-backed waiver API tests")
    suffix = uuid4().hex[:10]
    league_key = f"waiver.{suffix}"
    team1, team2 = f"{league_key}.t.1", f"{league_key}.t.2"
    monkeypatch.setattr(get_settings(), "waiver_manager_team_key", team1)
    now = datetime.now(timezone.utc)
    today = now.astimezone(WAIVER_TIMEZONE).date()
    # Choose a current NBA season with today inside the fixture schedule window.
    year = today.year if today.month >= 7 else today.year - 1
    season = f"{year}-{str(year + 1)[-2:]}"
    earlier = now - timedelta(minutes=1)
    ids = {}
    no_yahoo = AsyncMock(side_effect=AssertionError("Yahoo provider called by waiver read"))
    monkeypatch.setattr(YahooFantasyClient, "get_json", no_yahoo)
    for name in dir(NbaApiClient):
        if name.startswith("fetch_"):
            monkeypatch.setattr(NbaApiClient, name, lambda *args, **kwargs: pytest.fail("NBA provider called by waiver read"))

    async def seed():
        async with engine.begin() as connection:
            await create_test_schema(connection)
        async with SessionFactory() as session, session.begin():
            session.add(League(league_key=league_key, game_key="nba", league_name="Waiver fixture", season=year, source_payload={}, imported_at=earlier))
            await session.flush()
            session.add(LeagueSettings(league_key=league_key,
                scoring_settings={"scoring_type": "points", "categories": [{"stat_id": "12", "name": "PTS", "value": 1}]},
                roster_positions=[{"position": "PG", "count": "1"}, {"position": "C", "count": "1"}],
                source_payload={}, imported_at=earlier))
            for key in (team1, team2):
                session.add(Team(team_key=key, league_key=league_key, team_name=key, source_payload={}, imported_at=earlier))
            await session.flush()
            for key in (team1, team2):
                session.add(FantasyTeam(team_key=key, league_key=league_key, team_name=key, source_payload={}, imported_at=now))
            team_a, team_b, team_c = f"{suffix}a", f"{suffix}b", f"{suffix}c"
            for tid, abbr in ((team_a, f"A{suffix[:4]}"), (team_b, f"B{suffix[:4]}"), (team_c, f"C{suffix[:4]}")):
                session.add(NbaTeam(nba_team_id=tid, abbreviation=abbr, full_name=abbr, source_payload={}, imported_at=now))
            await session.flush()
            for offset in range(3):
                session.add(NbaGame(game_id=f"{suffix}g{offset}", season=season, game_date=today + timedelta(days=offset),
                    home_team_id=team_a if offset < 2 else team_b, away_team_id=team_b if offset < 2 else team_c,
                    game_status="Scheduled", source_payload={}, imported_at=now))
            await session.flush()
            data = [
                ("guard", "PG", 40, 35, None, team1),
                ("weak", "PG", 5, 5, None, team1),
                ("opponent", "C", 15, 20, None, team2),
                ("center", "C", 20, 45, "Q", None),
                ("star", "PG", 50, 20, "P", None),
                ("out", "C", 99, 99, "O", None),
                ("inactive", "C", 99, 99, "NA", None),
                ("unknown", "C", 10, 10, "", None),
                ("unmapped", "C", None, None, "", None),
            ]
            for name, position, recent, historical, status, owner in data:
                yahoo_id = f"{suffix}-{name}"
                nba_id = yahoo_id if recent is not None else None
                identity = PlayerIdentity(yahoo_player_id=yahoo_id, nba_player_id=nba_id, player_name=name, position=position, team=f"A{suffix[:4]}", status="O")
                session.add(identity)
                await session.flush()
                ids[name] = identity.id
                payload = {"player_id": yahoo_id, "name": {"full": name}, "display_position": position,
                    "editorial_team_abbr": f"{'B' if name == 'star' else 'A'}{suffix[:4]}", "status": status}
                session.add(LeaguePlayer(league_key=league_key, yahoo_player_id=yahoo_id, player_identity_id=identity.id, source_payload=payload, imported_at=now))
                if owner:
                    session.add(RosterEntry(league_key=league_key, team_key=owner, yahoo_player_id=yahoo_id, player_identity_id=identity.id, roster_position=position, source_payload=payload, imported_at=now))
                if nba_id is not None:
                    player_team_id = team_b if name == "star" else team_a
                    session.add(NbaPlayer(nba_player_id=nba_id, player_name=name, team_id=player_team_id,
                        team_abbreviation="B" if name == "star" else "A", source_payload={}, imported_at=now))
                    await session.flush()
                    session.add(NbaPlayerSeasonStats(nba_player_id=nba_id, season=season, season_type="Regular Season",
                        games_played=30, games_started=20, minutes_per_game=30, usage_pct=.2,
                        base_stats={"PTS": historical}, advanced_stats={}, source_payload={}, imported_at=now))
                    for offset in range(4):
                        game_id = f"{suffix}-{name}-{offset}"
                        session.add(NbaGame(game_id=game_id, season=season, game_date=today - timedelta(days=offset + 1),
                            home_team_id=team_a, away_team_id=team_b, source_payload={}, imported_at=now))
                        await session.flush()
                        session.add(PlayerGameLog(nba_player_id=nba_id, game_id=game_id, season=season, season_type="Regular Season",
                            game_date=today - timedelta(days=offset + 1), stats_payload={"PTS": recent, "MIN": 30 - offset},
                            source_payload={}, imported_at=now))
                    for offset in range(3):
                        if name == "star" and offset < 2:
                            team_id, opponent_id, is_home = team_b, team_a, False
                        elif name != "star" and offset < 2:
                            team_id, opponent_id, is_home = team_a, team_b, True
                        elif name == "star":
                            team_id, opponent_id, is_home = team_b, team_c, True
                        else:
                            continue
                        session.add(PlayerSchedule(
                            nba_player_id=nba_id,
                            game_id=f"{suffix}g{offset}",
                            season=season,
                            game_date=today + timedelta(days=offset),
                            team_id=team_id,
                            opponent_team_id=opponent_id,
                            is_home=is_home,
                            game_status="Scheduled",
                            source_payload={},
                            imported_at=now,
                        ))
    asyncio.run(seed())
    asyncio.run(engine.dispose())
    async def test_session():
        async with SessionFactory() as session:
            yield session
    monkeypatch.setitem(app.dependency_overrides, get_session, test_session)
    client = TestClient(app)
    try:
        yield SimpleNamespace(client=client, league=league_key, team1=team1, team2=team2, ids=ids, no_yahoo=no_yahoo)
    finally:
        client.close()
        async def cleanup():
            await engine.dispose()
            async with SessionFactory() as session, session.begin():
                await session.execute(delete(League).where(League.league_key == league_key))
                await session.execute(delete(PlayerIdentity).where(PlayerIdentity.id.in_(ids.values())))
                await session.execute(delete(NbaPlayer).where(NbaPlayer.nba_player_id.like(f"{suffix}-%")))
                await session.execute(delete(NbaGame).where(NbaGame.game_id.like(f"{suffix}%")))
                await session.execute(delete(NbaTeam).where(NbaTeam.nba_team_id.in_([f"{suffix}a", f"{suffix}b", f"{suffix}c"])))
            await engine.dispose()
        asyncio.run(cleanup())


def board(fixture, **params):
    response = fixture.client.get("/api/v1/waivers", params={"league_key": fixture.league, "team_key": fixture.team1, **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_yahoo_availability_status_manager_isolation_and_provider_free_reads(persisted):
    f = persisted
    result = board(f)
    names = {row["player_name"] for row in result["candidates"]}
    assert {"center", "star", "unknown", "unmapped"} == names
    assert result["excluded_count"] == 2
    unknown = next(row for row in result["candidates"] if row["player_name"] == "unknown")
    assert unknown["yahoo_status"] is None
    assert unknown["data_quality"]["status"]["state"] == "unknown"
    assert unknown["raw_yahoo_status"] == ""
    assert next(row for row in result["candidates"] if row["player_name"] == "center")["yahoo_status"] == "Q"
    center = next(row for row in result["candidates"] if row["player_name"] == "center")
    assert center["mapping_diagnostic"] == "COMPLETE_MAPPING"
    assert center["status_diagnostic"] == "STATUS_PRESENT"
    assert all(option["player_id"] in {f.ids["guard"], f.ids["weak"]} for row in result["candidates"] for option in row["best_drop_options"])
    assert next(row for row in result["candidates"] if row["player_name"] == "unmapped")["overall_score"] is None
    assert result["best_add_for_team_id"] is None
    assert result["top_measured_candidate_id"] == f.ids["center"]
    assert result["best_overall_available_id"] == f.ids["star"]
    assert result["coverage"]["population"] == {"total": 9, "candidates": 4, "roster": 2}
    assert result["coverage"]["pool"]["identity"]["complete"]["count"] == 8
    assert result["coverage"]["pool"]["identity"]["unresolved"]["count"] == 1
    assert result["coverage"]["pool"]["identity"]["resolution_counts"]["NO_MATCH"] == 1
    assert result["coverage"]["candidates"]["identity"]["unresolved"] == {
        "count": 1, "total": 4, "percentage": 25.0,
    }
    assert result["coverage"]["roster"]["identity"]["complete"] == {
        "count": 2, "total": 2, "percentage": 100.0,
    }
    unresolved = result["coverage"]["mapping_worklist"]
    assert len(unresolved) == 1 and unresolved[0]["resolution_state"] == "NO_MATCH"
    assert unresolved[0]["yahoo_player_id"] == f"{f.league.split('.')[1]}-unmapped"
    assert any(gap["category"] == "SOURCE CONTRACT UNVERIFIED" and gap["field"] == "Game-level usage"
        and gap["root_cause"] == "SOURCE_CONTRACT_UNVERIFIED" for gap in result["data_gaps"])
    assert any(gap["category"] == "SOURCE CONTRACT UNVERIFIED" for gap in result["data_gaps"])
    invalid = f.client.get(f"/api/v1/waivers/{f.ids['center']}/impact",
        params={"league_key": f.league, "team_key": f.team1, "drop_player_id": f.ids["opponent"]})
    assert invalid.status_code == 422
    assert f.client.get("/api/v1/waivers", params={"league_key": f.league, "team_key": "foreign-team"}).status_code == 422
    f.no_yahoo.assert_not_called()


def test_modes_schedule_and_add_drop_impact(persisted):
    f = persisted
    week, ros = board(f), board(f, mode="ros")
    center_week = next(row for row in week["candidates"] if row["player_name"] == "center")
    center_ros = next(row for row in ros["candidates"] if row["player_name"] == "center")
    assert center_ros["components"]["player_value"] > center_week["components"]["player_value"]
    assert center_week["recent"]["value"] == 20
    assert center_ros["ros"]["value"] == 45
    assert center_ros["schedule"]["games_remaining"] >= center_week["schedule"]["games_remaining"]
    assert center_ros["schedule"]["games_remaining"] == 2
    assert next(row for row in ros["candidates"] if row["player_name"] == "star")["schedule"]["games_remaining"] == 3
    assert center_week["data_quality"]["schedule"]["state"] == "partial"
    next_days = board(f, mode="next_7_days")
    center_next = next(row for row in next_days["candidates"] if row["player_name"] == "center")
    assert center_next["ranking_value"] == center_week["ranking_value"]
    assert center_next["schedule"]["window_end"] == (
        date.fromisoformat(center_next["schedule"]["window_start"]) + timedelta(days=6)
    ).isoformat()
    assert center_next["schedule"]["games_remaining"] == 2
    impact = f.client.get(f"/api/v1/waivers/{f.ids['center']}/impact", params={
        "league_key": f.league, "team_key": f.team1, "drop_player_id": f.ids["weak"]})
    assert impact.status_code == 200
    comparison = impact.json()["comparison"]
    assert comparison["net_improvement"] > 0
    assert comparison["after_score"] - comparison["before_score"] == pytest.approx(comparison["net_improvement"], abs=1e-6)
    repeat = board(f)
    assert [row["overall_score"] for row in repeat["candidates"]] == [row["overall_score"] for row in week["candidates"]]
    assert f.client.get("/api/v1/waivers", params={"league_key": f.league, "team_key": f.team1, "mode": "fake"}).status_code == 422
    assert f.client.get("/api/v2/draft/sessions").status_code == 200
    f.no_yahoo.assert_not_called()


def test_replacements_use_only_explicit_manager_drop_and_reject_foreign_ids(persisted):
    f = persisted
    for drop_id in (f.ids["weak"], f.ids["guard"]):
        response = f.client.get("/api/v1/waivers/replacements", params={"drop_player_id": drop_id})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["selected_drop_player_id"] == drop_id
        assert {row["player_id"] for row in result["roster"]} == {f.ids["weak"], f.ids["guard"]}
        assert all(row["availability"] != "rostered" for row in result["candidates"])
        measured = []
        for row in result["candidates"]:
            assert row["comparison"]["player_id"] == drop_id
            assert [option["player_id"] for option in row["best_drop_options"]] == [drop_id]
            assert row["net_improvement"] == row["comparison"]["net_improvement"]
            detail = f.client.get(f"/api/v1/waivers/{row['player_id']}/impact",
                params={"drop_player_id": drop_id}).json()
            assert detail["comparison"] == row["comparison"]
            if row["net_improvement"] is not None:
                measured.append(row["net_improvement"])
        assert measured == sorted(measured, reverse=True)
    for foreign in (f.ids["opponent"], f.ids["center"], -1):
        assert f.client.get("/api/v1/waivers/replacements", params={"drop_player_id": foreign}).status_code == 422
    assert f.client.get("/api/v1/waivers/replacements").status_code == 422
    assert f.client.get("/api/v1/waivers/replacements", params={
        "drop_player_id": f.ids["weak"], "team_key": f.team2,
    }).status_code == 422
    for method in ("post", "put", "delete"):
        assert getattr(f.client, method)("/api/v1/waivers/replacements", params={"drop_player_id": f.ids["weak"]}).status_code == 405
    f.no_yahoo.assert_not_called()


def test_different_selected_positions_change_replacement_ranking(persisted):
    f = persisted

    async def change():
        async with SessionFactory() as session, session.begin():
            entry = (await session.scalars(select(RosterEntry).where(
                RosterEntry.team_key == f.team1, RosterEntry.player_identity_id == f.ids["weak"]))).one()
            entry.source_payload = {**entry.source_payload, "display_position": "C"}
        await engine.dispose()
    asyncio.run(change())
    center_drop = f.client.get("/api/v1/waivers/replacements", params={"drop_player_id": f.ids["weak"]}).json()
    guard_drop = f.client.get("/api/v1/waivers/replacements", params={"drop_player_id": f.ids["guard"]}).json()
    assert center_drop["candidates"][0]["player_id"] == f.ids["center"]
    assert guard_drop["candidates"][0]["player_id"] == f.ids["star"]
    assert center_drop["candidates"][0]["comparison"]["component_deltas"]["roster_fit"] == 0
    assert guard_drop["candidates"][0]["comparison"]["component_deltas"]["roster_fit"] == 0


def test_two_game_production_uses_independent_history_with_visible_uncertainty(persisted):
    f = persisted

    async def change():
        async with SessionFactory() as session, session.begin():
            identity = await session.get(PlayerIdentity, f.ids["star"])
            logs = list((await session.scalars(select(PlayerGameLog).where(
                PlayerGameLog.nba_player_id == identity.nba_player_id).order_by(PlayerGameLog.game_date))).all())
            for row in logs[:2]:
                await session.delete(row)
            year = logs[0].season[:4]
            session.add(NbaPlayerSeasonStats(nba_player_id=identity.nba_player_id,
                season=f"{int(year)-1}-{str(year)[-2:]}", season_type="Regular Season",
                games_played=60, games_started=30, base_stats={"PTS": 10}, advanced_stats={},
                source_payload={}, imported_at=datetime.now(timezone.utc)))
        await engine.dispose()
    asyncio.run(change())
    result = board(f)
    star = next(row for row in result["candidates"] if row["player_name"] == "star")
    assert star["recent"]["games"] == 2
    assert star["recent"]["sample_label"] == "INSUFFICIENT FOR STRONG RECOMMENDATION"
    assert star["ranking_value"]["recent_weight"] == pytest.approx(2/12)
    assert star["ranking_value"]["value"] == pytest.approx(50 * 2/12 + 10 * 10/12)
    assert star["ranking_value"]["historical_games"] == 60
    assert star["ranking_value"]["historical_value"] == 10
    assert "not a projection" in star["ranking_value"]["label"]
    assert result["best_add_for_team_id"] is None
    assert any("INSUFFICIENT FOR STRONG RECOMMENDATION" in reason for reason in star["reasons"])
    ros = board(f, mode="ros")
    ros_star = next(row for row in ros["candidates"] if row["player_name"] == "star")
    assert ros_star["ranking_value"]["value"] == 20
    assert ros_star["ranking_value"]["recent_weight"] is None
    assert "not a projection" in ros_star["ranking_value"]["label"]

    async def stale_prior():
        async with SessionFactory() as session, session.begin():
            identity = await session.get(PlayerIdentity, f.ids["star"])
            prior = (await session.scalars(select(NbaPlayerSeasonStats).where(
                NbaPlayerSeasonStats.nba_player_id == identity.nba_player_id,
                NbaPlayerSeasonStats.games_played == 60))).one()
            prior.imported_at = datetime.now(timezone.utc) - timedelta(days=8)
        await engine.dispose()
    asyncio.run(stale_prior())
    stale_star = next(row for row in board(f)["candidates"] if row["player_name"] == "star")
    assert stale_star["ranking_value"]["recent_weight"] == 1
    assert stale_star["ranking_value"]["value"] == 50
    assert stale_star["ranking_value"]["historical_value"] is None
    assert stale_star["recent"]["sample_label"] == "INSUFFICIENT FOR STRONG RECOMMENDATION"


def test_stale_rosters_unknown_availability_and_unsupported_scoring(persisted):
    f = persisted

    async def change():
        async with SessionFactory() as session, session.begin():
            roster = await session.get(FantasyTeam, f.team2)
            roster.imported_at = NOW - timedelta(days=2)
            settings = await session.get(LeagueSettings, f.league)
            settings.scoring_settings = {"scoring_type": "head", "categories": [{"stat_id": "12", "name": "PTS"}]}
        await engine.dispose()
    asyncio.run(change())
    result = board(f)
    assert result["candidates"] == []
    assert result["unknown_availability_count"] >= 4
    assert result["data_quality"]["availability"]["state"] == "partial"
    impact = f.client.get(f"/api/v1/waivers/{f.ids['center']}/impact", params={"league_key": f.league, "team_key": f.team1})
    assert impact.status_code == 200
    assert impact.json()["model_version"] == "waiver-evidence-phase3"
    assert impact.json()["candidate"]["recommended_action"] == "INSUFFICIENT EVIDENCE"
    assert impact.json()["comparison"]["net_improvement"] is None
    assert impact.json()["candidate"]["data_quality"]["recent"]["state"] == "unsupported"


def test_explicit_yahoo_ownership_and_stale_manager_and_game_logs(persisted):
    f = persisted

    async def change():
        await engine.dispose()
        async with SessionFactory() as session, session.begin():
            manager = await session.get(FantasyTeam, f.team1)
            manager.imported_at = NOW - timedelta(days=2)
            row = (await session.execute(
                select(LeaguePlayer).where(
                    LeaguePlayer.league_key == f.league, LeaguePlayer.player_identity_id == f.ids["center"])
            )).scalar_one()
            row.source_payload = {**row.source_payload, "ownership": {"ownership_type": "waivers"}}
            logs = list((await session.scalars(
                select(PlayerGameLog).where(PlayerGameLog.nba_player_id == row.yahoo_player_id)
            )).all())
            for log in logs:
                log.imported_at = NOW - timedelta(days=8)
        await engine.dispose()
    asyncio.run(change())
    result = board(f)
    assert result["data_quality"]["roster"]["state"] == "stale"
    assert len(result["candidates"]) == 1
    center = result["candidates"][0]
    assert center["availability"] == "waivers"
    assert center["overall_score"] is None
    assert center["recommended_action"] == "INSUFFICIENT EVIDENCE"
    assert center["data_quality"]["recent"]["state"] == "stale"
    assert center["recent"]["value"] == 20
    assert center["components"]["player_value"] is None


def test_stale_ros_values_remain_visible_but_cannot_score_or_label_holds(persisted):
    f = persisted

    async def change():
        async with SessionFactory() as session, session.begin():
            identity = await session.get(PlayerIdentity, f.ids["center"])
            stats = (await session.scalars(select(NbaPlayerSeasonStats).where(
                NbaPlayerSeasonStats.nba_player_id == identity.nba_player_id,
            ))).one()
            stats.imported_at = datetime.now(timezone.utc) - timedelta(days=8)
        await engine.dispose()
    asyncio.run(change())
    result = board(f, mode="ros")
    center = next(row for row in result["candidates"] if row["player_name"] == "center")
    assert center["ros"]["value"] == 45
    assert center["data_quality"]["ros"]["state"] == "stale"
    assert center["components"]["player_value"] is None
    assert center["overall_score"] is None
    assert center["net_improvement"] is None
    assert center["hold_type"] == "undetermined"
    assert result["best_overall_available_id"] != f.ids["center"]
    week_center = next(row for row in board(f)["candidates"] if row["player_name"] == "center")
    assert week_center["hold_type"] != "longer_term_hold"


@pytest.mark.parametrize("mode", ["this_week", "ros"])
def test_stale_settings_cannot_supply_scoring_or_roster_fit(persisted, mode):
    f = persisted

    async def change():
        async with SessionFactory() as session, session.begin():
            settings = await session.get(LeagueSettings, f.league)
            settings.imported_at = datetime.now(timezone.utc) - timedelta(days=2)
        await engine.dispose()
    asyncio.run(change())
    result = board(f, mode=mode)
    assert result["data_quality"]["settings"]["state"] == "stale"
    assert result["best_overall_available_id"] is None
    assert result["best_add_for_team_id"] is None
    assert result["candidates"]
    for row in result["candidates"]:
        assert row["components"]["player_value"] is None
        assert row["components"]["roster_fit"] is None
        assert row["overall_score"] is None
        assert row["net_improvement"] is None
        assert row["recommended_action"] == "INSUFFICIENT EVIDENCE"


def test_window_configured_weights_and_missing_resource_contracts(persisted, monkeypatch):
    f = persisted
    configured = {**WEIGHTS, "schedule": 0}
    monkeypatch.setattr("app.features.waivers.service.get_settings",
        lambda: SimpleNamespace(waiver_weights=configured))
    result = board(f)
    assert result["weights"] == pytest.approx(validated_weights(configured))
    for row in result["candidates"]:
        window = row["schedule"]
        today = datetime.now(timezone.utc).astimezone(WAIVER_TIMEZONE).date()
        assert window["window_start"] == today.isoformat()
        assert window["window_end"] == (today + timedelta(days=6 - today.weekday())).isoformat()
        assert "schedule" not in row["effective_weights"]
    params = {"league_key": f.league, "team_key": f.team1}
    assert f.client.get("/api/v1/waivers", params={**params, "league_key": "missing"}).status_code == 422
    assert f.client.get("/api/v1/waivers/-1/impact", params=params).status_code == 404
    assert f.client.get(f"/api/v1/waivers/{f.ids['guard']}/impact", params=params).status_code == 409


def test_configured_target_defaults_and_rejects_other_rosters(persisted, monkeypatch):
    f = persisted
    fixed = datetime.now(timezone.utc)
    monkeypatch.setattr("app.features.waivers.service.datetime", SimpleNamespace(now=lambda tz: fixed))
    default = f.client.get("/api/v1/waivers")
    assert default.status_code == 200
    result = default.json()
    assert result["league_key"] == f.league
    assert result["team_key"] == f.team1
    assert result["team_name"] == f.team1
    assert result["mode"] == "this_week"
    assert result["candidates"] == board(f)["candidates"]
    assert result["best_add_for_team_id"] is None
    assert result["top_measured_candidate_id"] == f.ids["center"]
    for mode in ("this_week", "next_7_days", "ros"):
        impact_path = f"/api/v1/waivers/{f.ids['center']}/impact"
        impact = f.client.get(impact_path, params={"mode": mode, "drop_player_id": f.ids["weak"]})
        assert impact.status_code == 200
        assert impact.json()["league_key"] == f.league
        assert impact.json()["team_key"] == f.team1
        assert impact.json()["comparison"]["player_id"] == f.ids["weak"]
        assert impact.json()["comparison"]["net_improvement"] is not None
        for path in ("/api/v1/waivers", impact_path):
            for params in ({"team_key": f.team2}, {"league_key": "other.league"}):
                rejected = f.client.get(path, params={**params, "mode": mode})
                assert rejected.status_code == 422
                assert "configured" in rejected.json()["detail"]
    f.no_yahoo.assert_not_called()


def test_missing_configured_team_never_falls_back_to_another_roster(persisted, monkeypatch):
    f = persisted
    monkeypatch.setattr(get_settings(), "waiver_manager_team_key", "missing.t.9")
    for path in ("/api/v1/waivers", f"/api/v1/waivers/{f.ids['center']}/impact"):
        response = f.client.get(path)
        assert response.status_code == 404
        assert "Configured waiver manager team" in response.json()["detail"]


@pytest.mark.parametrize(("instant", "expected_day"), [
    ("2026-10-26T06:30:00+00:00", "2026-10-25"),
    ("2026-12-28T07:30:00+00:00", "2026-12-27"),
])
def test_pacific_sunday_window_does_not_roll_over_at_utc_midnight(persisted, monkeypatch, instant, expected_day):
    fixed = datetime.fromisoformat(instant)
    monkeypatch.setattr("app.features.waivers.service.datetime", SimpleNamespace(now=lambda tz: fixed))
    response = persisted.client.get(f"/api/v1/waivers/{persisted.ids['center']}/impact")
    assert response.status_code == 200
    schedule = response.json()["candidate"]["schedule"]
    assert schedule["window_start"] == expected_day
    assert schedule["window_end"] == expected_day


def verified_league():
    scoring = {"scoring_type": "headpoint", "categories": [
        {"stat_id": str(stat), "name": name, "value": weight}
        for stat, name, weight in [(12, "PTS", 1), (15, "REB", 1.2), (16, "AST", 1.5),
            (18, "BLK", 3), (17, "ST", 3), (19, "TO", -1)]
    ]}
    positions = [{"position": position, "count": count} for position, count in
        {"PG": 1, "SG": 1, "G": 1, "SF": 1, "PF": 1, "F": 1, "C": 2, "UTIL": 2, "BN": 3, "IL": 3}.items()]
    raw = dict(scoring_type="headpoint", max_teams="12", uses_faab="0", waiver_type="R",
        waiver_rule="all", waiver_time="2", max_weekly_adds="4", post_draft_players="W",
        stat_categories={"stats": [{"stat": {"stat_id": row["stat_id"], "display_name": row["name"]}} for row in scoring["categories"]]},
        stat_modifiers={"stats": [{"stat": {"stat_id": row["stat_id"], "value": row["value"]}} for row in scoring["categories"]]},
        roster_positions=[{"roster_position": row} for row in positions])
    record = dict(league_key="478.l.50505", num_teams=12, weekly_deadline="intraday",
        allow_add_to_dl_extra_pos=1, settings=[raw])
    return SimpleNamespace(league_key="478.l.50505", league_name="Driveway Dudes",
        source_payload={"scoring_type": "headpoint"},
        settings=SimpleNamespace(scoring_settings=scoring, roster_positions=positions,
            source_payload={"fantasy_content": {"league": record}}))


def test_exact_persisted_yahoo_formula_and_required_nba_mapping():
    league = verified_league()
    assert all("FAAB" not in rule.upper() for rule in verify_league_contract(league))
    fields = scoring_fields(league.settings.scoring_settings)
    assert fields == {"PTS": 1, "REB": 1.2, "AST": 1.5, "BLK": 3, "STL": 3, "TOV": -1}
    stats = dict(PTS=20, REB=10, AST=6, BLK=2, STL=3, TOV=4)
    assert production(stats, fields) == 52
    for field, weight in fields.items():
        assert production({**stats, field: stats[field] + 1}, fields) == pytest.approx(52 + weight)
        assert production({key: value for key, value in stats.items() if key != field}, fields) is None
    assert production(log_average([
        SimpleNamespace(stats_payload=stats),
        SimpleNamespace(stats_payload={key: value for key, value in stats.items() if key != "TOV"}),
    ]), fields) is None


@pytest.mark.parametrize("mutation", [
    "scoring", "raw_scoring", "slots", "raw_slots", "uses_faab", "waiver_type",
    "waiver_rule", "waiver_time", "max_weekly_adds", "max_teams", "post_draft_players",
    "max_adds", "weekly_deadline", "allow_add_to_dl_extra_pos", "num_teams", "identity", "missing",
])
def test_persisted_contract_mismatch_fails_closed(mutation):
    league = verified_league()
    record = league.settings.source_payload["fantasy_content"]["league"]
    raw = record["settings"][0]
    if mutation == "scoring":
        league.settings.scoring_settings["categories"][1]["value"] = 1
    elif mutation == "raw_scoring":
        raw["stat_modifiers"]["stats"][1]["stat"]["value"] = 1
    elif mutation == "slots":
        league.settings.roster_positions = []
    elif mutation == "raw_slots":
        raw["roster_positions"] = []
    elif mutation in {"weekly_deadline", "allow_add_to_dl_extra_pos", "num_teams"}:
        record[mutation] = "wrong"
    elif mutation == "identity":
        league.league_name = "Other"
    elif mutation == "missing":
        league.settings = None
    else:
        raw[mutation] = "wrong"
    with pytest.raises(HTTPException) as error:
        verify_league_contract(league)
    assert error.value.status_code == 409


def role_logs(minutes, usages=None):
    return [PlayerGameLog(nba_player_id="role", game_id=f"role-{index}", season="2026-27",
        season_type="Regular Season", game_date=NOW.date() - timedelta(days=len(minutes) - index),
        stats_payload={**({"MIN": value} if value is not None else {}),
            **({"USG_PCT": usages[index]} if usages is not None else {})},
        source_payload={}, imported_at=NOW)
        for index, value in enumerate(minutes)]


@pytest.mark.parametrize("minutes,expected,delta", [
    ([20, 20, 20, 27, 27, 27], "RISING", 7),
    ([30, 30, 30, 23, 23, 23], "FALLING", -7),
    ([25, 25, 25, 26, 26, 26], "STABLE", 1),
    ([20, 20, 20, 23, 23, 23], "RISING", 3),
    ([30, 30, 30, 27, 27, 27], "FALLING", -3),
    ([20, 20, 40], "INSUFFICIENT EVIDENCE", None),
    ([20, 20, 20, 30, 30], "INSUFFICIENT EVIDENCE", None),
])
def test_role_fixed_supported_windows_and_thresholds(minutes, expected, delta):
    opportunity = current_role(role_logs(minutes), None, "2026-27", NOW, NOW.date())
    role = opportunity.current_role
    assert role.trend == expected
    assert role.minutes.delta == delta
    assert role.minutes.recent.game_ids == [f"role-{i}" for i in range(max(0, len(minutes)-3), len(minutes))]
    assert role.minutes.recent.window_end == NOW.date() - timedelta(days=1)
    assert role.usage.quality.state == "unavailable"
    assert role.usage.delta is None
    assert "minutes_change" not in opportunity.score_parts
    assert (opportunity.score is not None) == (expected != "INSUFFICIENT EVIDENCE")
    assert not any(phrase in role.model_dump_json().lower() for phrase in
        ("expected minutes", "projected role", "usage will", "will replace", "breakout probability"))


@pytest.mark.parametrize("value", [None, -4, "bad", float("nan"), True])
def test_role_missing_invalid_minutes_never_zero_filled_or_backfilled(value):
    logs = role_logs([40, 40, 20, 20, 20, value, 30])
    opportunity = current_role(logs, None, "2026-27", NOW, NOW.date())
    role = opportunity.current_role
    assert role.trend == "INSUFFICIENT EVIDENCE"
    assert role.minutes.recent.games == 2
    assert role.minutes.recent.average == 25
    assert role.minutes.recent.missing_game_ids == ["role-5"]
    assert role.minutes.delta is None
    assert opportunity.score is None
    all_missing = current_role(role_logs([value] * 6), None, "2026-27", NOW, NOW.date())
    assert all_missing.current_role.minutes.quality.state == "unavailable"
    assert all_missing.minutes is None
    assert all_missing.current_role.minutes.recent.average is None


@pytest.mark.parametrize("minutes,usages", [
    ([20, 20, 20, 20, 20, 40], None),
    ([40, 20, 20, 20, 20, 20], None),
    ([25]*6, [.2]*5+[.4]),
    ([25]*6, [.4]+[.2]*5),
])
def test_single_game_outlier_cannot_supply_supported_role_direction(minutes, usages):
    opportunity = current_role(role_logs(minutes, usages), None, "2026-27", NOW, NOW.date())
    assert opportunity.current_role.trend == "INSUFFICIENT EVIDENCE"
    assert opportunity.current_role.quality.state == "partial"
    assert opportunity.score is None


@pytest.mark.parametrize("stale_import", [True, False])
def test_stale_log_import_or_old_game_window_cannot_supply_current_role(stale_import):
    logs = role_logs([20, 20, 20, 30, 30, 30])
    for row in logs:
        if stale_import:
            row.imported_at = NOW - timedelta(days=8)
        else:
            row.game_date -= timedelta(days=14)
    opportunity = current_role(logs, None, "2026-27", NOW, NOW.date())
    assert opportunity.current_role.quality.state == "stale"
    assert opportunity.current_role.trend == "INSUFFICIENT EVIDENCE"
    assert opportunity.minutes_trend is None
    assert opportunity.score is None


@pytest.mark.parametrize("minutes,usages,expected", [
    ([25]*6, [.20]*3 + [.22]*3, "RISING"),
    ([25]*6, [.22]*3 + [.20]*3, "FALLING"),
    ([25]*6, [.20]*3 + [.219]*3, "STABLE"),
    ([20]*3+[30]*3, [.30]*3+[.20]*3, "INSUFFICIENT EVIDENCE"),
])
def test_usage_units_thresholds_and_conflicting_role_directions(minutes, usages, expected):
    opportunity = current_role(role_logs(minutes, usages), None, "2026-27", NOW, NOW.date())
    role = opportunity.current_role
    assert role.trend == expected
    assert role.usage.recent.average == pytest.approx(usages[-1])
    assert role.usage.delta == pytest.approx(usages[-1] - usages[0])
    assert role.usage.quality.state == "available"
    assert (opportunity.score is not None) == (expected != "INSUFFICIENT EVIDENCE")
    if opportunity.score is not None:
        assert set(opportunity.score_parts) == {"minutes_level", "usage_change"}
        assert opportunity.score == pytest.approx(sum(opportunity.score_parts.values())/2)


@pytest.mark.parametrize("usage", [-.01, 1.1, None, float("inf"), True])
def test_invalid_game_usage_is_unavailable_not_neutral(usage):
    opportunity = current_role(role_logs([25]*6, [usage]*6), None, "2026-27", NOW, NOW.date())
    assert opportunity.current_role.usage.quality.state == "unavailable"
    assert opportunity.usage_trend is None
    assert set(opportunity.score_parts) == {"minutes_level"}


@pytest.mark.parametrize("payload,starts,games,state,value", [
    ({}, 0, 8, "unavailable", None),
    ({"GP": 4}, 4, 8, "available", 4),
    ({"GP": 0}, 0, 8, "available", 0),
    ({"GP": 4}, 3, 8, "unavailable", None),
    ({"GP": 9}, 9, 8, "unavailable", None),
    ({"GP": 2}, 2, 2, "partial", 2),
    ({"GP": 0}, 0, 0, "unavailable", None),
])
def test_season_starts_need_explicit_matching_provenance_not_default_zero(payload, starts, games, state, value):
    history = NbaPlayerSeasonStats(nba_player_id="role", season="2026-27",
        season_type="Regular Season", games_played=games, games_started=starts,
        base_stats={}, advanced_stats={"USG_PCT": .24}, usage_pct=.24,
        source_payload={"starter_filter": payload}, imported_at=NOW)
    opportunity = current_role(role_logs([20]*3+[30]*3), history, "2026-27", NOW, NOW.date())
    role = opportunity.current_role
    assert role.starts.quality.state == state
    assert role.starts.season_starts == value
    assert role.starts.recent_starts is None
    assert role.season_usage == .24
    assert role.usage.quality.state == "unavailable"
    assert role.usage.delta is None
    assert ("season_start_rate" in opportunity.score_parts) == (state == "available")
    history.season = "2025-26"
    prior = current_role(role_logs([25]*6), history, "2026-27", NOW, NOW.date())
    assert prior.current_role.starts.season_starts is None
    assert prior.current_role.season_usage is None


def test_season_starts_and_usage_staleness_are_independent_of_fresh_minutes():
    history = NbaPlayerSeasonStats(nba_player_id="role", season="2026-27",
        season_type="Regular Season", games_played=8, games_started=4,
        base_stats={}, advanced_stats={"USG_PCT": .24}, usage_pct=.24,
        source_payload={"starter_filter": {"GP": 4}}, imported_at=NOW-timedelta(days=8))
    opportunity = current_role(role_logs([25]*6), history, "2026-27", NOW, NOW.date())
    assert opportunity.current_role.starts.quality.state == "stale"
    assert opportunity.current_role.season_usage_quality.state == "stale"
    assert set(opportunity.score_parts) == {"minutes_level"}


def decision_context(games=7):
    drop, add = candidate(1, value=20), candidate(2, value=90)
    fresh = Evidence(state="available", source="Fixture", as_of=NOW, detail="Verified")
    for row in (drop, add):
        row.identity_mapping_state = "EXACT_NAME_TEAM"
        row.current_season_games = games
        row.recent.games = games
        row.evidence_quality = sample_label(games)
        row.yahoo_status = "P"
        row.opportunity = current_role(role_logs([20, 20, 20, 27, 27, 27]), None, "2026-27", NOW, NOW.date())
        row.data_quality = {key: fresh.model_copy() for key in
            ("recent", "ros", "status", "availability", "schedule", "opportunity")}
        row.overall_score, row.effective_weights = aggregate(row.components, WEIGHTS)
    ctx = Context(SimpleNamespace(), "t1", "this_week", NOW, {1: drop, 2: add},
        [1], ["C"], 1, True, WEIGHTS,
        {"settings": fresh, "roster": fresh, "acquisition_value": fresh})
    return ctx, drop, add


@pytest.mark.parametrize("mode", ["this_week", "next_7_days", "ros"])
@pytest.mark.parametrize("games", [2, 5])
def test_low_sample_breakout_is_watch_never_add_despite_rising_role_and_prior_history(mode, games):
    ctx, drop, add = decision_context(games)
    ctx.mode = mode
    assert add.opportunity.current_role.trend == "RISING"
    add.ranking_value.historical_games = 80
    add.ranking_value.historical_value = 100
    assert enrich(ctx, add, drop.player_id).recommended_action == "WATCH"
    assert not sufficient_sample(add, mode)


def test_seven_game_positive_candidate_and_negative_swap_decisions():
    ctx, drop, add = decision_context()
    assert enrich(ctx, add, drop.player_id).recommended_action == "ADD"
    add.components.player_value = 1
    assert enrich(ctx, add, drop.player_id).recommended_action == "PASS"


@pytest.mark.parametrize("status", [None, "", "HEALTHY", "D", "IL"])
def test_blank_or_unrecognized_yahoo_status_fails_closed(status):
    ctx, drop, add = decision_context()
    add.yahoo_status = status
    add.data_quality["status"] = Evidence(
        state="available", source="Fixture", as_of=NOW, detail="Nonblank status observed",
    )
    assert enrich(ctx, add, drop.player_id).recommended_action == "INSUFFICIENT EVIDENCE"
    assert any("status is unknown" in blocker.lower() or "unrecognized" in blocker.lower()
        for blocker in transaction_blockers(ctx, add, drop))
    add.components.player_value = 1
    negative = enrich(ctx, add, drop.player_id)
    assert negative.comparison.net_improvement < 0
    assert negative.recommended_action == "INSUFFICIENT EVIDENCE"
    assert not status_is_supported(status)


@pytest.mark.parametrize("identity_state", ["NO_MATCH", "MISSING_MAPPING", "AMBIGUOUS"])
@pytest.mark.parametrize("side", ["add", "drop"])
def test_unresolved_yahoo_nba_identity_blocks_add(identity_state, side):
    ctx, drop, add = decision_context()
    (add if side == "add" else drop).identity_mapping_state = identity_state
    assert enrich(ctx, add, drop.player_id).recommended_action == "INSUFFICIENT EVIDENCE"
    assert any("identity is unresolved" in blocker
        for blocker in transaction_blockers(ctx, add, drop))


def test_only_verified_yahoo_status_tokens_are_supported():
    assert all(status_is_supported(value) for value in ("O", "NA", "P", "Q"))
    assert not status_is_supported(None)
    assert not status_is_supported("HEALTHY")


def test_data_gaps_keep_supported_root_causes_and_truthful_unknowns():
    rows = [candidate(1), candidate(2), candidate(3)]
    resolved = "EXACT_NAME_TEAM"
    rows[0].identity_mapping_state = "NO_MATCH"
    rows[0].schedule.diagnostic_reason = "NO_PLAYER_SCHEDULE_ROWS"
    rows[0].status_diagnostic = "YAHOO_SUPPLIED_BLANK"
    rows[0].raw_yahoo_status = ""
    rows[0].data_quality = {
        "recent": Evidence(state="missing", source="Fixture", as_of=NOW,
            detail="Recent production is missing because no eligible persisted NBA game/stat observations exist in the selected window."),
        "ros": Evidence(state="unsupported", source="Fixture", as_of=NOW,
            detail="Season Evidence production is unsupported because persisted Yahoo points modifiers are unavailable."),
        "status": Evidence(state="unknown", source="Fixture", as_of=NOW, detail="Yahoo supplied a blank status."),
    }
    rows[1].identity_mapping_state = resolved
    rows[1].schedule.coverage = "UNKNOWN"
    rows[1].schedule.diagnostic_reason = "NO_GAMES_IN_WINDOW"
    rows[1].status_diagnostic = "UNRECOGNIZED_STATUS"
    rows[1].raw_yahoo_status = "HEALTHY"
    rows[1].data_quality = {
        "recent": Evidence(state="stale", source="Fixture", as_of=NOW-timedelta(days=8), detail="Stale recent data."),
        "ros": Evidence(state="missing", source="Fixture", as_of=NOW,
            detail="Season Evidence is unavailable because persisted NBA observations lack required scoring fields: REB."),
        "status": Evidence(state="unknown", source="Fixture", as_of=NOW, detail="Unrecognized status token."),
    }
    rows[2].identity_mapping_state = resolved
    rows[2].schedule.diagnostic_reason = "NO_PLAYER_SCHEDULE_ROWS"
    rows[2].data_quality = {
        "recent": Evidence(state="available", source="Fixture", as_of=NOW, detail="Complete recent data."),
        "ros": Evidence(state="available", source="Fixture", as_of=NOW, detail="Complete season data."),
        "status": Evidence(state="available", source="Fixture", as_of=NOW, detail="Supported Yahoo status."),
    }
    rows[2].raw_yahoo_status = "Q"
    rows[2].yahoo_status = "Q"
    quality = {
        "settings": Evidence(state="available", source="Fixture", as_of=NOW, detail="Settings"),
        "roster": Evidence(state="available", source="Fixture", as_of=NOW, detail="Roster"),
        "acquisition_value": Evidence(state="unknown", source="Fixture", as_of=NOW, detail="Unverified"),
    }
    ctx = Context(SimpleNamespace(), "team", "this_week", NOW,
        {row.player_id: row for row in rows}, [], [], 0, True, WEIGHTS, quality)

    coverage_result, gaps = board_coverage(ctx)
    causes = {(gap.field, gap.root_cause) for gap in gaps}
    assert ("Yahoo ↔ NBA identity mapping", "MISSING_MAPPING") in causes
    assert ("Player schedule rows blocked by identity", "MISSING_MAPPING") in causes
    assert ("Player schedule rows missing", "MISSING_EXISTING_SOURCE_FIELD") in causes
    assert ("Recent production", "REQUIRES_MORE_GAMES") in causes
    assert ("Recent production", "STALE_EXISTING_SOURCE") in causes
    assert ("Season Evidence", "SOURCE_CONTRACT_UNVERIFIED") in causes
    assert ("Season Evidence", "MISSING_EXISTING_SOURCE_FIELD") in causes
    assert ("Game-level usage", "SOURCE_CONTRACT_UNVERIFIED") in causes
    assert not any(gap.field == "Yahoo player status" for gap in gaps)
    assert coverage_result.pool.status.yahoo_blank.count == 1
    assert coverage_result.pool.schedule.unknown.count == 3
    assert all(row.schedule.coverage != "COMPLETE" for row in rows)


@pytest.mark.parametrize("field", ["settings", "roster", "recent", "availability", "status"])
def test_stale_critical_evidence_blocks_add(field):
    ctx, drop, add = decision_context()
    target = ctx.quality if field in {"settings", "roster"} else add.data_quality
    target[field] = Evidence(state="stale", source="Fixture", as_of=NOW - timedelta(days=8), detail="Stale")
    assert enrich(ctx, add, drop.player_id).recommended_action == "INSUFFICIENT EVIDENCE"


@pytest.mark.parametrize("field", ["schedule", "opportunity"])
def test_stream_requires_schedule_and_opportunity_evidence(field):
    ctx, drop, add = decision_context()
    add.hold_type = "streamer"
    add.opportunity.minutes_trend = 2
    add.schedule.games_remaining = 3
    assert enrich(ctx, add, drop.player_id).recommended_action == "STREAM"
    add.data_quality[field].state = "missing"
    assert enrich(ctx, add, drop.player_id).recommended_action == "INSUFFICIENT EVIDENCE"


@pytest.mark.parametrize("side", ["add", "drop"])
@pytest.mark.parametrize("state", ["unavailable", "partial", "stale"])
def test_missing_partial_or_stale_role_blocks_stream_and_opportunity_led_add(side, state):
    ctx, drop, add = decision_context()
    row = add if side == "add" else drop
    row.opportunity.current_role.quality.state = state
    add.hold_type = "streamer"
    add.schedule.games_remaining = 4
    assert enrich(ctx, add, drop.player_id).recommended_action == "INSUFFICIENT EVIDENCE"
    add.hold_type = "undetermined"
    ctx.mode = "ros"
    add.components.player_value = drop.components.player_value
    add.components.opportunity = 100
    drop.components.opportunity = 10
    assert enrich(ctx, add, drop.player_id).recommended_action == "INSUFFICIENT EVIDENCE"
    row.opportunity.current_role.quality.state = "available"
    assert enrich(ctx, add, drop.player_id).recommended_action == "ADD"
    row.opportunity.current_role.quality.as_of = NOW-timedelta(days=8)
    assert enrich(ctx, add, drop.player_id).recommended_action == "INSUFFICIENT EVIDENCE"


def test_phase3_evidence_consistent_and_bulk_derived_before_pair_expansion(persisted, monkeypatch):
    import app.features.waivers.service as service
    calls, sql = [], []
    original = service.current_role
    def derive(*args):
        logs, season_stats = args[:2]
        calls.append(logs[0].nba_player_id if logs else season_stats.nba_player_id if season_stats else None)
        return original(*args)
    def statement(*args):
        sql.append(args[2])
        assert args[2].lstrip().upper().startswith("SELECT")
    monkeypatch.setattr(service, "current_role", derive)
    event.listen(engine.sync_engine, "before_cursor_execute", statement)
    try:
        selected = board(persisted, drop_player_id=persisted.ids["weak"])
        board_calls, board_queries = len(calls), len(sql)
        assert board_calls == len(set(calls))
        assert board_calls >= len(selected["roster"]) + len(selected["candidates"])
        calls.clear()
        sql.clear()
        response = persisted.client.get("/api/v1/waivers/transactions")
        assert response.status_code == 200
        transactions = response.json()
        assert transactions["evaluated_pair_count"] > len(calls)
        assert len(calls) == board_calls
        assert len(sql) == board_queries
        for swap in transactions["watch_transactions"] + transactions["top_supported_transactions"]:
            add, drop = swap["add_player"], swap["drop_player"]
            replacements = persisted.client.get("/api/v1/waivers/replacements", params={"drop_player_id": drop["player_id"]}).json()
            replacement = next(row for row in replacements["candidates"] if row["player_id"] == add["player_id"])
            impact = persisted.client.get(f"/api/v1/waivers/{add['player_id']}/impact", params={"drop_player_id": drop["player_id"]}).json()
            assert swap["comparison"] == replacement["comparison"] == impact["comparison"]
            assert add["opportunity"] == replacement["opportunity"] == impact["candidate"]["opportunity"]
        for row in selected["candidates"] + selected["roster"]:
            for key in ("role", "minutes", "usage", "starts", "status", "schedule"):
                quality = row["data_quality"][key]
                assert quality["state"] in {"available", "partial", "unknown", "unavailable", "stale"}
                assert quality["source"] and quality["detail"]
                assert quality["sample_count"] is not None
            assert row["components"]["opportunity"] is None
            assert row["opportunity"]["score"] is None
            assert row["opportunity"]["current_role"]["trend"] == "INSUFFICIENT EVIDENCE"
        q, p = (next(row for row in selected["candidates"] if row["player_name"] == name) for name in ("center", "star"))
        assert q["data_quality"]["status"]["state"] == p["data_quality"]["status"]["state"] == "partial"
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", statement)


def test_phase3_schedule_counts_partial_coverage_and_absent_rows_not_zero(persisted):
    result = board(persisted, mode="next_7_days")
    center = next(row for row in result["candidates"] if row["player_name"] == "center")
    schedule = center["schedule"]
    assert schedule["games_remaining"] == schedule["off_day_games"] == 2
    assert schedule["back_to_backs"] == 1
    assert len(schedule["opponents"]) == 2
    assert schedule["coverage"] == "PARTIAL" and schedule["imported_at"]
    assert "difficulty" not in center["components"]
    unknown = next(row for row in result["candidates"] if row["player_name"] == "unmapped")
    assert unknown["mapping_diagnostic"] == "NBA_ID_UNMAPPED"
    assert unknown["schedule"]["coverage"] == "UNKNOWN"
    assert unknown["schedule"]["diagnostic_reason"] == "NBA_ID_UNMAPPED"
    assert unknown["schedule"]["games_remaining"] is None
    async def remove_future_rows():
        async with SessionFactory() as session, session.begin():
            await session.execute(delete(NbaGame).where(NbaGame.game_id.in_(
                select(NbaGame.game_id).where(NbaGame.game_id.like(persisted.league.split(".")[-1] + "g%")))))
        await engine.dispose()
    asyncio.run(remove_future_rows())
    missing = board(persisted, mode="next_7_days")
    for row in missing["candidates"]:
        assert row["schedule"]["games_remaining"] is None
        assert row["schedule"]["off_day_games"] is None
        assert row["schedule"]["back_to_backs"] is None
        assert row["schedule"]["coverage"] == "UNKNOWN"
        assert row["schedule"]["imported_at"] is None
        assert row["data_quality"]["schedule"]["state"] == "unavailable"


def test_schedule_resolution_distinguishes_mapping_rows_freshness_and_windows():
    from types import SimpleNamespace

    today = date(2026, 10, 26)
    now = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    daily = Counter({today: 6, today + timedelta(days=1): 5, today + timedelta(days=2): 4})

    def row(day, opponent="B", imported_at=now, status="Scheduled"):
        return SimpleNamespace(
            game_date=day, opponent_team_id=opponent, imported_at=imported_at,
            game_status=status, game_id=f"{opponent}-{day}",
        )

    upcoming = [row(today), row(today + timedelta(days=1)), row(today + timedelta(days=2))]
    mapped = resolve_schedule(upcoming, today, today + timedelta(days=2), now, daily,
        {"B": "BOS"}, nba_mapped=True, team_mapped=True)
    assert mapped.diagnostic_reason == "SCHEDULE_ROWS_PRESENT"
    assert mapped.coverage == "PARTIAL" and mapped.freshness == "fresh"
    assert mapped.games_remaining == mapped.next_7_days_games == 3
    assert mapped.source_row_count == 3
    assert mapped.off_day_games == 2
    assert mapped.back_to_backs == 2
    assert mapped.opponents == ["BOS", "BOS", "BOS"]

    no_games = resolve_schedule([row(today + timedelta(days=10))], today, today + timedelta(days=2),
        now, daily, {"B": "BOS"}, nba_mapped=True, team_mapped=True)
    assert no_games.diagnostic_reason == "SCHEDULE_SOURCE_INCOMPLETE"
    assert no_games.coverage == "UNKNOWN" and no_games.games_remaining is None
    assert no_games.source_row_count == 1

    unmapped = resolve_schedule([], today, today + timedelta(days=2), now, daily, {},
        nba_mapped=False, team_mapped=False)
    assert unmapped.diagnostic_reason == "NBA_ID_UNMAPPED"
    assert unmapped.coverage == "UNKNOWN" and unmapped.games_remaining is None

    missing_team = resolve_schedule(upcoming, today, today + timedelta(days=2), now, daily,
        {"B": "BOS"}, nba_mapped=True, team_mapped=False)
    assert missing_team.diagnostic_reason == "TEAM_MAPPING_MISSING"
    assert missing_team.coverage == "PARTIAL" and missing_team.games_remaining == 3

    stale = resolve_schedule([row(today, imported_at=now - timedelta(days=8))],
        today, today + timedelta(days=2), now, daily, {"B": "BOS"},
        nba_mapped=True, team_mapped=True)
    assert stale.diagnostic_reason == "SCHEDULE_STALE"
    assert stale.coverage == "STALE" and stale.games_remaining is None

    no_rows = resolve_schedule([], today, today + timedelta(days=2), now, daily, {},
        nba_mapped=True, team_mapped=True)
    assert no_rows.diagnostic_reason == "NO_PLAYER_SCHEDULE_ROWS"
    assert no_rows.coverage == "UNKNOWN" and no_rows.games_remaining is None


@pytest.mark.parametrize(("changes", "expected"), [
    ({"yahoo_id": None}, "YAHOO_ID_MISSING"),
    ({"nba_id": None}, "NBA_ID_UNMAPPED"),
    ({"nba_player_present": False}, "NBA_PLAYER_MISSING"),
    ({"team_mapped": False}, "TEAM_MAPPING_MISSING"),
    ({"has_game_logs": False}, "GAME_LOGS_MISSING"),
    ({"has_season_stats": False}, "SEASON_STATS_MISSING"),
    ({"has_schedule_rows": False}, "SCHEDULE_ROWS_MISSING"),
    ({"schedule_stale": True}, "SCHEDULE_STALE"),
    ({}, "COMPLETE_MAPPING"),
])
def test_identity_chain_returns_first_broken_mapping_state(changes, expected):
    values = dict(yahoo_id="y1", nba_id="n1", nba_player_present=True, team_mapped=True,
        has_game_logs=True, has_season_stats=True, has_schedule_rows=True, schedule_stale=False)
    assert identity_chain_diagnostic(**(values | changes)) == expected


def test_read_endpoints_have_no_writes_or_acquisition_scoring(persisted):
    statements = []
    def record_statement(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
        assert statement.lstrip().upper().startswith("SELECT"), statement
    event.listen(engine.sync_engine, "before_cursor_execute", record_statement)
    try:
        result = board(persisted, drop_player_id=persisted.ids["guard"])
        for row in result["candidates"]:
            assert row["components"]["acquisition_value"] is None
            assert "acquisition_value" not in row["effective_weights"]
            assert not any("faab" in key.lower() for key in row)
            assert "faab" not in row["data_quality"]
        assert statements
        assert result["best_add_for_team_id"] is None
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record_statement)


def test_negative_selected_drop_set_holds_and_never_names_least_negative_best_add(monkeypatch):
    from app.features.waivers.service import get_waivers
    ctx, drop, add = decision_context()
    ctx.league.league_key = "fixture"
    add.components.player_value = 1
    drop.eligible = False
    drop.availability = "rostered"
    monkeypatch.setattr("app.features.waivers.service.load_context", AsyncMock(return_value=ctx))
    result = asyncio.run(get_waivers(None, "fixture", ctx.team_key, ctx.mode, drop.player_id))
    assert result.selected_player_result == "HOLD Player 1"
    assert result.top_measured_candidate_id == add.player_id
    assert result.best_add_for_team_id is None
    assert result.candidates[0].recommended_action == "PASS"
    assert result.candidates[0].net_improvement < 0


@pytest.mark.parametrize("mode", ["this_week", "next_7_days", "ros"])
def test_two_game_candidate_cannot_be_board_best_add(monkeypatch, mode):
    from app.features.waivers.service import get_waivers
    ctx, drop, add = decision_context(2)
    ctx.mode = mode
    ctx.league.league_key = "fixture"
    drop.eligible = False
    drop.availability = "rostered"
    monkeypatch.setattr("app.features.waivers.service.load_context", AsyncMock(return_value=ctx))
    result = asyncio.run(get_waivers(None, "fixture", ctx.team_key, mode, drop.player_id))
    assert result.best_add_for_team_id is None
    assert result.selected_player_result == "WATCH"
    assert result.candidates[0].recommended_action == "WATCH"


def optimizer_context(games=7):
    from app.features.waivers.service import analyze_transactions
    ctx, drop, add = decision_context(games)
    ctx.league.league_key = "fixture"
    drop.availability = "rostered"
    drop.eligible = False
    return ctx, drop, add, analyze_transactions


def test_optimizer_multiple_adds_drops_deterministic_global_fit_and_same_math():
    ctx, drop, add, analyze = optimizer_context()
    strong = drop.model_copy(deep=True, update={"player_id": 3, "player_name": "Strong guard", "position": "PG"})
    strong.components.player_value = 95
    drop.position = "PG"
    add.position = "C"
    overall = add.model_copy(deep=True, update={"player_id": 4, "player_name": "Best overall guard", "position": "PG"})
    overall.components.player_value = 99
    ctx.players.update({3: strong, 4: overall})
    ctx.roster_ids = [1, 3]
    ctx.slots = ["PG", "C"]
    result = analyze(ctx)
    assert result.evaluated_pair_count == 4
    best = result.best_transaction
    assert best is not None
    assert best.add_player.player_id == add.player_id
    assert best.drop_player.player_id == drop.player_id
    assert best.decision == "ADD"
    assert best.comparison == compare(ctx, add, drop.player_id)
    assert best.comparison == enrich(ctx, add, drop.player_id).comparison
    assert best.add_player.comparison == best.comparison
    assert best.add_player.best_drop_options == [best.comparison]
    assert 0 <= best.comparison.component_after.roster_fit <= 100
    assert best.comparison.component_deltas.roster_fit == 50
    ctx.players = dict(reversed(list(ctx.players.items())))
    ctx.roster_ids.reverse()
    assert analyze(ctx) == result


def test_optimizer_all_nonpositive_is_hold_with_supported_pass_pairs():
    ctx, drop, add, analyze = optimizer_context()
    add.components.player_value = 1
    result = analyze(ctx)
    assert result.decision == "HOLD"
    assert result.best_transaction is None
    assert result.supported_pair_count == 1
    assert result.top_supported_transactions[0].decision == "PASS"
    assert result.top_supported_transactions[0].comparison.net_improvement < 0
    assert result.watch_transactions == []


@pytest.mark.parametrize("mode", ["this_week", "next_7_days", "ros"])
@pytest.mark.parametrize("games", [0, 2, 5])
def test_optimizer_history_never_bypasses_current_gate(mode, games):
    ctx, drop, add, analyze = optimizer_context(games)
    ctx.mode = mode
    add.ros.games = drop.ros.games = 82
    add.ranking_value.historical_games = 82
    result = analyze(ctx)
    assert result.best_transaction is None
    assert result.decision == "HOLD"
    assert result.excluded_pair_count == result.evaluated_pair_count == 1
    assert result.supported_pair_count == 0
    if games:
        assert result.watch_pair_count == 1
        assert result.watch_transactions[0].decision == "WATCH"
    else:
        assert result.watch_pair_count == 0


@pytest.mark.parametrize("field", ["settings", "roster", "recent", "availability", "status"])
def test_optimizer_critical_stale_excluded_from_strong_pool(field):
    ctx, drop, add, analyze = optimizer_context()
    target = ctx.quality if field in {"settings", "roster"} else add.data_quality
    target[field] = Evidence(state="stale", source="Fixture", as_of=NOW - timedelta(days=8), detail="Stale")
    result = analyze(ctx)
    assert result.best_transaction is None
    assert result.supported_pair_count == 0
    assert result.excluded_pair_count == 1
    assert result.excluded_pair_reasons


def test_optimizer_mode_changes_best_supported_pair_and_stream_needs_evidence():
    ctx, drop, add, analyze = optimizer_context()
    other = add.model_copy(deep=True, update={"player_id": 3, "player_name": "Other add"})
    other.components.player_value = 80
    other.components.schedule = 100
    add.components.schedule = 1
    for row in (add, other):
        row.schedule.games_remaining = 4
    ctx.players[3] = other
    ctx.weights = {**WEIGHTS, "player_value": .1, "schedule": .7}
    ctx.mode = "next_7_days"
    assert analyze(ctx).best_transaction.add_player.player_id == 3
    assert analyze(ctx).best_transaction.decision == "STREAM"
    other.data_quality["schedule"].state = "missing"
    assert all(row.add_player.player_id != 3 for row in analyze(ctx).top_supported_transactions)
    other.data_quality["schedule"].state = "available"
    other.data_quality["opportunity"].state = "missing"
    assert all(row.add_player.player_id != 3 for row in analyze(ctx).top_supported_transactions)
    ctx.mode = "ros"
    ctx.weights = {**WEIGHTS, "schedule": 0}
    assert analyze(ctx).best_transaction.add_player.player_id == add.player_id
    assert analyze(ctx).best_transaction.decision == "ADD"


@pytest.mark.parametrize("status", ["O", "NA", "Q", "P", None])
def test_optimizer_yahoo_status_contract(status):
    ctx, drop, add, analyze = optimizer_context()
    add.yahoo_status = status
    add.eligible = status not in {"O", "NA"}
    result = analyze(ctx)
    if status in {"Q", "P"}:
        assert result.best_transaction.add_player.yahoo_status == status
        assert result.best_transaction.decision == "ADD"
    else:
        assert result.best_transaction is None
    assert result.acquisition_context.current_priority is None
    assert result.acquisition_context.weekly_adds_used is None
    assert result.acquisition_context.weekly_adds_remaining is None
    assert result.acquisition_context.claim_clear_at is None
    assert all(row.add_player.components.acquisition_value is None for row in result.top_supported_transactions)


def test_optimizer_positive_tie_uses_add_then_drop_id():
    ctx, drop, add, analyze = optimizer_context()
    twin_drop = drop.model_copy(deep=True, update={"player_id": 3})
    twin_add = add.model_copy(deep=True, update={"player_id": 4})
    ctx.players.update({3: twin_drop, 4: twin_add})
    ctx.roster_ids = [3, 1]
    result = analyze(ctx)
    assert [(row.add_player.player_id, row.drop_player.player_id) for row in result.top_supported_transactions] == [(2, 1), (2, 3), (4, 1), (4, 3)]
    assert result.evaluated_pair_count == 4
    assert result.supported_pair_count + result.excluded_pair_count == 4


def test_transactions_endpoint_loads_once_select_only_and_matches_selected_drop(persisted, monkeypatch):
    import app.features.waivers.service as service
    calls = []
    original = service.load_context
    async def load(*args, **kwargs):
        calls.append(1)
        return await original(*args, **kwargs)
    monkeypatch.setattr(service, "load_context", load)
    statements = []
    def guard(connection, cursor, statement, parameters, context, executemany):
        assert statement.lstrip().upper().startswith("SELECT"), statement
        statements.append(statement)
    event.listen(engine.sync_engine, "before_cursor_execute", guard)
    try:
        response = persisted.client.get("/api/v1/waivers/transactions", params={"mode": "next_7_days"})
        assert response.status_code == 200, response.text
        result = response.json()
        assert calls == [1]
        assert result["team_key"] == persisted.team1
        assert result["decision"] == "HOLD"
        assert result["best_transaction"] is None
        assert result["evaluated_pair_count"] > 2
        assert result["supported_pair_count"] + result["excluded_pair_count"] == result["evaluated_pair_count"]
        watch = result["watch_transactions"][0]
        add_id, drop_id = watch["add_player"]["player_id"], watch["drop_player"]["player_id"]
        selected = board(persisted, mode="next_7_days", drop_player_id=drop_id)
        pair = next(row for row in selected["candidates"] if row["player_id"] == add_id)
        assert pair["comparison"] == watch["comparison"]
        impact = persisted.client.get(f"/api/v1/waivers/{add_id}/impact",
            params={"mode": "next_7_days", "drop_player_id": drop_id}).json()
        assert impact["comparison"] == watch["comparison"]
        assert len(statements) < 150
        assert persisted.client.get("/api/v1/waivers/transactions", params={"team_key": persisted.team2}).status_code == 422
        assert persisted.client.get("/api/v1/waivers/transactions", params={"mode": "fake"}).status_code == 422
        persisted.no_yahoo.assert_not_called()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", guard)

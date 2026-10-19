import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.features.draft.contracts import DraftUtilityRequest
from app.features.draft.models import DraftMarketData, DraftPlayerMetric
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.players.models import LeaguePlayer, PlayerIdentity
from app.services.draft.utility import _run_bonus, calculate_draft_utility
from schema_support import create_test_schema

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

# Persisted 2026-10-18 pick-7 sample: value, replacement, scarcity, durability, risk, upside, ADP.
SAMPLE = [
    ("Jalen Johnson", "SF,PF", 48.11, 16.77, 57.48188405797102, 87.8048780487805, 8.53658536585366, 94.86373406764497, 10.62),
    ("Tyrese Maxey", "PG", 48.82, 14.81, 78.69543650793652, 85.36585365853658, 10.243902439024396, 96.82442748091603, 10.21),
    ("Jayson Tatum", "SF,PF", 44.15, 12.81, 57.48188405797102, 19.51219512195122, 56.34146341463415, 94.78545784098435, 7.61),
    ("Donovan Mitchell", "PG,SG", 44.45, 10.44, 78.69543650793652, 85.36585365853658, 10.243902439024396, 97.232911568894, 14.73),
    ("Jaylen Brown", "SG,SF,PF", 45.23, 13.89, 57.48188405797102, 86.58536585365853, 9.390243902439032, 98.89589505850094, 41.37),
    ("Alperen Sengun", "PF,C", 44.08, 13.75, 100, 87.8048780487805, 8.53658536585366, 92.60013710248992, 19.08),
    ("Scottie Barnes", "SF,PF,C", 42.05, 11.72, 100, 97.5609756097561, 1.707317073170742, 87.21001080553522, 12.3),
    ("Kawhi Leonard", "SG,SF,PF", 45.88, 14.54, 57.48188405797102, 79.26829268292683, 14.512195121951223, 96.60306505396959, 29.55),
]


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Requires isolated PostgreSQL test database")
def test_actual_early_draft_sample_roster_market_and_run_invariants():
    assert "test" in (make_url(TEST_DATABASE_URL).database or "").lower()
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex[:10]
    league_key = f"actual-sample.{suffix}"
    manager = f"{league_key}.t.10"
    identities = []

    async def scenario():
        async with engine.begin() as connection:
            await create_test_schema(connection)
        try:
            async with factory() as session:
                session.add(League(league_key=league_key, game_key="fixture", league_name="Actual sample", season=2026, source_payload={}))
                await session.flush()
                session.add(LeagueSettings(
                    league_key=league_key, scoring_settings={},
                    roster_positions=[{"position": position, "count": count} for position, count in
                                      [("PG", 1), ("SG", 1), ("G", 1), ("SF", 1), ("PF", 1), ("F", 1), ("C", 2), ("Util", 2), ("BN", 3), ("IL", 3)]],
                    source_payload={},
                ))
                session.add_all([Team(team_key=f"{league_key}.t.{i}", league_key=league_key, team_name=f"Slot {i}", source_payload={}) for i in range(1, 13)])
                for index, sample in enumerate(SAMPLE):
                    name, position, value, replacement, scarcity, durability, risk, upside, adp = sample
                    identity = PlayerIdentity(yahoo_player_id=f"{suffix}-{index}", nba_player_id=f"sample-{suffix}-{index}", player_name=name, position=position)
                    session.add(identity)
                    await session.flush()
                    identities.append(identity)
                    session.add(LeaguePlayer(league_key=league_key, yahoo_player_id=identity.yahoo_player_id, player_identity_id=identity.id, source_payload={}))
                    session.add(DraftPlayerMetric(
                        league_key=league_key, player_identity_id=identity.id, season="2026-27",
                        fantasy_value=value, replacement_value=replacement, positional_scarcity=scarcity,
                        durability_score=durability, risk_score=risk, upside_score=upside,
                        sample_games={"Jalen Johnson": 72, "Tyrese Maxey": 70, "Jayson Tatum": 16, "Donovan Mitchell": 70, "Jaylen Brown": 71, "Alperen Sengun": 72, "Scottie Barnes": 80, "Kawhi Leonard": 65}[name], source_season="2025-26",
                        source_season_type="Regular Season", source_payload={},
                    ))
                    session.add(DraftMarketData(player_id=identity.id, season="2026-27", source="fantrax", adp=adp))
                await session.commit()
                request = DraftUtilityRequest(
                    league_key=league_key, team_key=manager, season="2026-27",
                    drafted_player_ids=[], available_player_ids=[p.id for p in identities],
                    draft_position=10, round_number=1, total_teams=12,
                )
                async def calculate(req=request):
                    return await calculate_draft_utility(session, req, manager_drafted_player_ids=[])
                fresh = await calculate()
                assert fresh == await calculate()
                assert fresh.best_pick.next_pick_survival_probability is not None
                assert fresh.best_pick.expected_wait_cost is not None
                scores = {p.player_identity_id: p.decision_score for p in fresh.ranked_players}
                roster_ids = [identities[1].id, identities[5].id]
                roster_request = request.model_copy(update={
                    "drafted_player_ids": roster_ids,
                    "available_player_ids": [p.id for p in identities if p.id not in roster_ids],
                })
                actual_roster = await calculate_draft_utility(
                    session, roster_request, manager_drafted_player_ids=roster_ids,
                )
                baseline = await calculate(roster_request)
                baseline_by_id = {p.player_identity_id: p for p in baseline.ranked_players}
                for rank, row in enumerate(actual_roster.ranked_players, start=1):
                    impact = row.roster_impact
                    assert impact is not None
                    empty_row = baseline_by_id[row.player_identity_id]
                    assert impact.rank_with_roster == rank
                    assert impact.rank_without_roster == empty_row.roster_impact.rank_with_roster
                    assert impact.score_without_roster == pytest.approx(empty_row.decision_score)
                    assert row.decision_score == pytest.approx(impact.score_without_roster + impact.score_change)
                    assert impact.score_change == pytest.approx(
                        impact.need_score_change + impact.scarcity_need_score_change + impact.construction_score_change
                    )
                assert any(abs(p.roster_impact.score_change) > 0 for p in actual_roster.ranked_players)
                chosen = fresh.best_pick.player_identity_id
                removed = await calculate(request.model_copy(update={
                    "drafted_player_ids": [chosen],
                    "available_player_ids": [p.id for p in identities if p.id != chosen],
                }))
                assert chosen not in {p.player_identity_id for p in removed.ranked_players}
                assert removed.best_pick.player_identity_id != chosen
                for identity in identities:
                    metric = await session.get(DraftPlayerMetric, (league_key, identity.id, "2026-27"))
                    assert all(0 <= value <= 100 for value in [metric.risk_score, metric.upside_score, metric.durability_score, metric.positional_scarcity])
                    pick = (await calculate(request.model_copy(update={"available_player_ids": [identity.id]}))).best_pick
                    assert 0 <= pick.positional_need_score <= 100
                    assert pick.mode_adjusted_utility_score == pytest.approx(pick.wait_utility_now + pick.run_bonus)
                run_request = request.model_copy(update={"drafted_player_ids": [p.id for p in identities[:3]], "available_player_ids": [p.id for p in identities[3:]], "recent_pick_player_ids": [p.id for p in identities[:3]]})
                runs = await calculate(run_request)
                for row in runs.ranked_players:
                    metric = await session.get(DraftPlayerMetric, (league_key, row.player_identity_id, "2026-27"))
                    bonus = _run_bonus(metric, set(row.positions), runs.draft_runs)
                    assert row.decision_score == pytest.approx(scores[row.player_identity_id] + bonus)
                for identity in identities:
                    row = await session.get(DraftMarketData, (identity.id, "2026-27", "fantrax"))
                    row.last_updated = datetime.now(timezone.utc) - timedelta(hours=49)
                await session.commit()
                stale = await calculate()
                assert stale.best_pick.decision_action == "insufficient_evidence"
                assert stale.best_pick.decision_confidence == "unavailable"
                assert stale.best_pick.next_pick_survival_probability is None
                assert stale.best_pick.expected_wait_cost is None
                assert all(p.data_freshness == "stale" and p.adp is None and p.market_data_as_of for p in stale.ranked_players)
                assert {p.player_identity_id: p.decision_score for p in stale.ranked_players} == scores
                await session.execute(delete(DraftMarketData).where(DraftMarketData.player_id.in_([p.id for p in identities])))
                await session.commit()
                missing = await calculate()
                assert missing.best_pick.decision_confidence == "unavailable"
                assert missing.best_pick.next_pick_survival_probability is None
                assert {p.player_identity_id: p.decision_score for p in missing.ranked_players} == scores
                excluded = next(p for p in identities if p.id == fresh.best_pick.player_identity_id)
                metric_before = await session.get(DraftPlayerMetric, (league_key, excluded.id, "2026-27"))
                values_before = (metric_before.fantasy_value, metric_before.risk_score, metric_before.upside_score)
                for identity in identities:
                    session.add(DraftMarketData(
                        player_id=identity.id, season="2026-27", source="fantrax",
                        adp=next(sample[-1] for sample in SAMPLE if sample[0] == identity.player_name),
                    ))
                for status in ("O", "NA"):
                    excluded.status = status
                    await session.commit()
                    gated = await calculate()
                    board_row = next(p for p in gated.ranked_players if p.player_identity_id == excluded.id)
                    assert board_row.yahoo_status == status
                    assert board_row.recommendation_eligibility == "excluded"
                    assert board_row.value_score == metric_before.fantasy_value
                    assert board_row.decision_score == scores[excluded.id]
                    assert board_row.expected_wait_cost is None
                    assert board_row.survival_probability is None
                    assert "Not eligible" in board_row.yahoo_status_reason
                    assert gated.best_pick.player_identity_id != excluded.id
                    assert excluded.id not in {p.player_identity_id for p in gated.best_pick.wait_fallbacks}
                    assert gated.best_value_before_next_pick is None or gated.best_value_before_next_pick.player_identity_id != excluded.id
                    assert [(p.player_identity_id, p.decision_score) for p in gated.ranked_players] == [
                        (p.player_identity_id, p.decision_score) for p in fresh.ranked_players
                    ]
                for status in ("Q", "P", "UNRECOGNIZED", None):
                    excluded.status = status
                    await session.commit()
                    allowed = await calculate()
                    assert allowed.best_pick.player_identity_id == excluded.id
                    assert allowed.best_pick.yahoo_status == status
                    assert allowed.best_pick.recommendation_eligibility == (
                        "uncertain" if status in {"Q", "P"} else "unknown"
                    )
                    if status in {None, "UNRECOGNIZED"}:
                        assert "unknown, not confirmed healthy" in allowed.best_pick.yahoo_status_reason
                assert (metric_before.fantasy_value, metric_before.risk_score, metric_before.upside_score) == values_before
        finally:
            async with factory() as session:
                await session.execute(delete(DraftMarketData).where(DraftMarketData.player_id.in_([p.id for p in identities])))
                await session.execute(delete(League).where(League.league_key == league_key))
                await session.execute(delete(PlayerIdentity).where(PlayerIdentity.id.in_([p.id for p in identities])))
                await session.commit()
            await engine.dispose()
    asyncio.run(scenario())

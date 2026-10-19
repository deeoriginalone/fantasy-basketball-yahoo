from app.services.draft.mock_simulation import (
    MockCandidate,
    choose_opponent_pick,
    generate_team_slots,
)
from app.features.draft.contracts import DraftMockBatchCreateRequest
from pydantic import ValidationError
import pytest


def _candidates() -> list[MockCandidate]:
    return [
        MockCandidate(
            player_id=1,
            adp=12.0,
            positions=("PG",),
            positional_scarcity=20.0,
            fantasy_value=20.0,
        ),
        MockCandidate(
            player_id=2,
            adp=15.0,
            positions=("C",),
            positional_scarcity=95.0,
            fantasy_value=21.0,
        ),
        MockCandidate(
            player_id=3,
            adp=None,
            positions=("SG",),
            positional_scarcity=40.0,
            fantasy_value=18.0,
        ),
    ]


def test_opponent_pick_is_repeatable_for_same_seed_and_state() -> None:
    candidates = _candidates()
    arguments = {
        "candidates": candidates,
        "roster_positions": [
            {"position": "PG", "count": 1, "is_starting_position": 1},
            {"position": "C", "count": 1, "is_starting_position": 1},
            {"position": "BN", "count": 2, "is_starting_position": 0},
        ],
        "drafted_positions": [],
        "overall_pick": 12,
        "total_teams": 12,
        "aggressiveness": 0.5,
        "seed": 1776,
    }

    assert choose_opponent_pick(**arguments) == choose_opponent_pick(**arguments)


def test_opponent_pick_uses_market_need_scarcity_and_aggressiveness() -> None:
    candidates = _candidates()
    roster_positions = [
        {"position": "PG", "count": 1, "is_starting_position": 1},
        {"position": "C", "count": 1, "is_starting_position": 1},
        {"position": "BN", "count": 2, "is_starting_position": 0},
    ]
    ordinary = choose_opponent_pick(
        candidates=candidates,
        roster_positions=roster_positions,
        drafted_positions=[],
        overall_pick=12,
        total_teams=12,
        aggressiveness=0.0,
        seed=42,
    )
    center_need = choose_opponent_pick(
        candidates=candidates,
        roster_positions=roster_positions,
        drafted_positions=[{"C"}],
        overall_pick=12,
        total_teams=12,
        aggressiveness=1.0,
        seed=42,
    )

    assert ordinary == 1
    assert center_need in {1, 3}


def test_missing_adp_uses_existing_utility_ranking_without_fabricating_adp() -> None:
    candidates = [
        MockCandidate(
            player_id=11,
            adp=None,
            positions=("PG",),
            positional_scarcity=30.0,
            fantasy_value=22.0,
            decision_score=8.0,
        ),
        MockCandidate(
            player_id=12,
            adp=None,
            positions=("PG",),
            positional_scarcity=30.0,
            fantasy_value=21.0,
            decision_score=18.0,
        ),
    ]

    picked = choose_opponent_pick(
        candidates=candidates,
        roster_positions=[{"position": "PG", "count": 1}],
        drafted_positions=[],
        overall_pick=1,
        total_teams=2,
        aggressiveness=0.0,
        seed=71,
    )

    assert picked == 12
    assert all(candidate.adp is None for candidate in candidates)


def test_opponent_randomness_can_change_tied_market_selections() -> None:
    candidates = [
        MockCandidate(
            player_id=player_id,
            adp=10.0,
            positions=("PG",),
            positional_scarcity=50.0,
            fantasy_value=20.0,
        )
        for player_id in range(1, 13)
    ]

    selections = {
        choose_opponent_pick(
            candidates=candidates,
            roster_positions=[{"position": "PG", "count": 12}],
            drafted_positions=[],
            overall_pick=1,
            total_teams=12,
            aggressiveness=1.0,
            seed=seed,
        )
        for seed in range(50)
    }

    assert len(selections) > 1


def test_opponent_pick_rejects_invalid_aggressiveness_and_empty_candidates() -> None:
    arguments = {
        "candidates": _candidates(),
        "roster_positions": [],
        "drafted_positions": [],
        "overall_pick": 1,
        "total_teams": 12,
        "aggressiveness": -0.1,
        "seed": 1,
    }
    try:
        choose_opponent_pick(**arguments)
    except ValueError as error:
        assert "aggressiveness" in str(error)
    else:
        raise AssertionError("negative aggressiveness must be rejected")

    try:
        choose_opponent_pick(
            candidates=[],
            roster_positions=[],
            drafted_positions=[],
            overall_pick=1,
            total_teams=12,
            aggressiveness=0.5,
            seed=1,
        )
    except ValueError as error:
        assert "candidates" in str(error)
    else:
        raise AssertionError("empty candidate pool must be rejected")


def test_mock_batch_contract_caps_run_count_at_five_hundred() -> None:
    request = {
        "league_key": "478.l.test",
        "season": "2026-27",
        "manager_team_key": "478.l.test.t.1",
        "draft_position": 1,
        "total_teams": 2,
        "rounds": 13,
        "team_slots": {
            "478.l.test.t.1": 1,
            "478.l.test.t.2": 2,
        },
    }
    assert DraftMockBatchCreateRequest(**request, count=500).count == 500
    with pytest.raises(ValidationError):
        DraftMockBatchCreateRequest(**request, count=501)


def test_mock_team_order_keeps_manager_slot_fixed_and_repeats_by_seed() -> None:
    team_keys = [f"league.t.{index}" for index in range(1, 13)]
    first = generate_team_slots(
        team_keys=team_keys,
        manager_team_key=team_keys[8],
        draft_position=4,
        seed=90210,
    )
    second = generate_team_slots(
        team_keys=team_keys,
        manager_team_key=team_keys[8],
        draft_position=4,
        seed=90210,
    )

    assert first == second
    assert first[team_keys[8]] == 4
    assert sorted(first.values()) == list(range(1, 13))
    assert set(first) == set(team_keys)


def test_mock_advanced_order_must_preserve_manager_slot_and_unique_assignments() -> None:
    team_keys = ["league.t.1", "league.t.2", "league.t.3"]
    mapped = {"league.t.1": 2, "league.t.2": 1, "league.t.3": 3}
    assert generate_team_slots(
        team_keys=team_keys,
        manager_team_key="league.t.1",
        draft_position=2,
        seed=1,
        advanced_team_slots=mapped,
    ) == mapped
    try:
        generate_team_slots(
            team_keys=team_keys,
            manager_team_key="league.t.1",
            draft_position=2,
            seed=1,
            advanced_team_slots={"league.t.1": 1, "league.t.2": 1, "league.t.3": 3},
        )
    except ValueError as error:
        assert "unique" in str(error)
    else:
        raise AssertionError("duplicate advanced slots must be rejected")
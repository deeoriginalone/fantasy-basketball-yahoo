import pytest

from app.services.draft.utility import (
    _maximum_slot_matching,
    _roster_fit,
    calculate_utility_score,
)


def fit(candidate, roster, slots):
    return _roster_fit(candidate, roster, slots, _maximum_slot_matching(roster, slots))


def test_filled_guards_do_not_get_need_from_util_or_bench():
    slots = ["PG", "C", "UTIL", "UTIL", "BN", "BN", "BN"]
    roster = [{"PG"}]
    assert fit({"PG", "SG"}, roster, slots) == (0, 30, 5)
    assert fit({"C"}, roster, slots) == (100, 100, 6)
    assert fit({"PG"}, roster, ["PG", "C", "BN"])[:2] == (0, 10)


def test_augmenting_path_credits_newly_filled_slot_not_candidate_final_slot():
    slots = ["PG", "C", "UTIL", "BN"]
    roster = [{"PG"}, {"C"}]
    # The new PG displaces the old PG into UTIL rather than occupying UTIL itself.
    assert fit({"PG"}, roster, slots) == (0, 30, 2)
    assert fit({"C"}, roster, slots) == (0, 30, 2)


def test_flexible_incumbent_can_move_to_fill_required_center():
    assert fit({"PF"}, [{"PF", "C"}], ["PF", "C", "BN"]) == (100, 100, 1)


def test_bench_does_not_dilute_fixed_position_need():
    roster = [{"PG"}]
    assert fit({"C"}, roster, ["PG", "C"])[:2] == (100, 100)
    assert fit({"C"}, roster, ["PG", "C", "BN", "BN", "UTIL"])[:2] == (100, 100)


def test_filling_fixed_slot_removes_need_and_bounds_flex_credit():
    slots = ["PG", "C", "UTIL", "BN"]
    assert fit({"C"}, [{"PG"}], slots)[:2] == (100, 100)
    assert fit({"C"}, [{"PG"}, {"C"}], slots)[:2] == (0, 30)
    assert fit({"C"}, [{"PG"}, {"C"}, {"SG"}], slots)[:2] == (0, 10)


def test_full_roster_and_missing_position_have_no_need_or_construction():
    assert fit({"C"}, [{"PG"}, {"C"}], ["PG", "C"]) == (0, 0, 0)
    assert fit(set(), [], ["PG", "C", "UTIL", "BN"]) == (0, 0, 0)


def test_bench_only_candidates_rank_by_value_not_position_label():
    def score(positions, value):
        need, construction, _ = fit(positions, [], ["BN", "BN"])
        return calculate_utility_score(
            fantasy_value=value, replacement_value=0, positional_scarcity=100,
            durability_score=50, risk_score=50, upside_score=50,
            positional_need_score=need, roster_construction_score=construction,
        )
    assert score({"PG"}, 30) == score({"C"}, 30)
    assert score({"PG"}, 31) > score({"C"}, 30)
    assert score({"PG"}, 30) == pytest.approx(30 * 1.025 + 30 * 0.005)


def test_exact_seven_player_roster_has_center_need_not_guard_need():
    roster = [
        {"PG", "SG"}, {"PG"}, {"PF", "SF"}, {"PG", "SG"},
        {"C", "PF"}, {"C"}, {"PF"},
    ]
    slots = ["PG", "SG", "G", "SF", "PF", "F", "C", "C",
             "UTIL", "UTIL", "BN", "BN", "BN"]
    assert fit({"PG", "SG"}, roster, slots) == (0, 30, 5)
    assert fit({"C"}, roster, slots) == (100, 100, 6)
    assert fit({"C"}, roster, slots) == fit({"C"}, roster, slots)

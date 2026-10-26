from datetime import datetime, timedelta, timezone

import pytest

from app.features.waivers.reconciliation import (
    ACCEPTANCE_NAMES,
    FORMULA,
    REQUIRED_STATS,
    classify_mismatch,
    compare_overlapping_fields,
    fantasy_ppg,
    normalize_identity,
    numeric_stats,
)


NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
STATS = {"PTS": 20.0, "REB": 5.0, "AST": 4.0, "STL": 1.0, "BLK": 1.0, "TOV": 2.0}


def pair(**yahoo_changes):
    yahoo = {
        "player_name": "Keegan Murray",
        "team": "SAC",
        "season": "2026-27",
        "stat_type": "Regular Season",
        "games_played": 10,
        "minutes_per_game": 30.0,
        "stats": dict(STATS),
        "imported_at": NOW,
    }
    nba = dict(yahoo)
    nba["stats"] = dict(STATS)
    yahoo.update(yahoo_changes)
    return yahoo, nba


def test_formula_requires_all_six_inputs_and_maps_turnovers():
    assert set(FORMULA) == set(REQUIRED_STATS)
    assert FORMULA["TOV"] == -1
    assert numeric_stats({"PTS": "20", "TO": "2"}) == {"PTS": 20, "TOV": 2}
    assert fantasy_ppg(STATS) == 20 + 1.2 * 5 + 1.5 * 4 + 3 + 3 - 2
    assert fantasy_ppg({key: value for key, value in STATS.items() if key != "TOV"}) is None


def test_reconciliation_compares_only_shared_persisted_fields():
    overlap, mismatches = compare_overlapping_fields(
        {"PTS": 20, "REB": 5}, {"PTS": 20.02, "REB": 8}, ("PTS", "REB", "AST"), .05,
    )
    assert overlap == ("PTS", "REB")
    assert mismatches == ("REB",)
    yahoo, nba = pair()
    yahoo["stats"] = {}
    assert classify_mismatch(yahoo, nba, NOW) == "NO_COMPARABLE_STAT_FIELDS"
    yahoo["stats"] = {"PTS": 20}
    assert classify_mismatch(yahoo, nba, NOW) == "PARTIAL_STAT_OVERLAP"


def test_acceptance_names_normalize_without_player_specific_corrections():
    assert tuple(ACCEPTANCE_NAMES) == ("Keegan Murray", "Bilal Coulibaly", "Kris Dunn", "Jrue Holiday")
    assert normalize_identity("Jrue Holiday") == normalize_identity("jrue-holiday")
    assert normalize_identity("Bilal Coulibaly") == normalize_identity("Bilal  Coulibaly")


@pytest.mark.parametrize(("change", "expected"), [
    ({"player_name": "Different Player"}, "IDENTITY_MAPPING_MISMATCH"),
    ({"team": "LAL"}, "TEAM_MAPPING_MISMATCH"),
    ({"team": ""}, "TEAM_MAPPING_UNVERIFIED"),
    ({"season": "2025-26"}, "SEASON_MISMATCH"),
    ({"stat_type": "Playoffs"}, "STAT_TYPE_MISMATCH"),
    ({"games_played": 9}, "GAME_SET_MISMATCH"),
    ({"imported_at": NOW - timedelta(days=8)}, "IMPORT_STALE"),
    ({"stats": {"PTS": 20}}, "PARTIAL_STAT_OVERLAP"),
    ({"stats": {**STATS, "PTS": 20.02}}, "ROUNDING_ONLY"),
    ({"definition": "per-player possessions"}, None),
])
def test_classifies_known_mismatch_sources(change, expected):
    yahoo, nba = pair()
    if "definition" in change:
        yahoo["definition"] = change["definition"]
        nba["definition"] = "box-score possessions"
        assert classify_mismatch(yahoo, nba, NOW) == "PROVIDER_DEFINITION_DIFFERENCE"
        return
    yahoo.update(change)
    assert classify_mismatch(yahoo, nba, NOW) == expected


def test_unexplained_large_stat_delta_remains_unknown():
    yahoo, nba = pair()
    yahoo["stats"] = {**STATS, "PTS": 25.0}
    assert classify_mismatch(yahoo, nba, NOW) == "UNKNOWN"

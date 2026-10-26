from collections import defaultdict
from collections.abc import Iterable
from math import isfinite
from statistics import median
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.features.championship.contracts import (
    CategoryCoverageStatus,
    CategorySourceImport,
    ComparisonExclusion,
    LeagueRelativeCategoryResult,
    MissingCategoryPlayer,
    TeamCategoryBaselineResponse,
    TeamCategoryResult,
    TeamIdentityMethod,
    TeamIdentityBaseline,
)
from app.features.leagues.models import League
from app.features.nba.models import NbaPlayerSeasonStats
from app.features.players.models import RosterEntry
from app.features.players.service import list_roster_baselines, roster_data_status

COUNTING_FIELDS_BY_ID = {
    "3": "FGM",
    "4": "FGA",
    "6": "FTM",
    "7": "FTA",
    "9": "FG3M",
    "12": "PTS",
    "13": "OREB",
    "14": "DREB",
    "15": "REB",
    "16": "AST",
    "17": "STL",
    "18": "BLK",
    "19": "TOV",
}
PERCENTAGE_FIELDS_BY_ID = {
    "5": ("FGM", "FGA"),
    "8": ("FTM", "FTA"),
}
COUNTING_FIELDS_BY_NAME = {
    "FGM": "FGM",
    "FIELD GOALS MADE": "FGM",
    "FGA": "FGA",
    "FIELD GOALS ATTEMPTED": "FGA",
    "FTM": "FTM",
    "FREE THROWS MADE": "FTM",
    "FTA": "FTA",
    "FREE THROWS ATTEMPTED": "FTA",
    "3PM": "FG3M",
    "3PTM": "FG3M",
    "THREE-POINTERS MADE": "FG3M",
    "POINTS": "PTS",
    "PTS": "PTS",
    "OREB": "OREB",
    "OFFENSIVE REBOUNDS": "OREB",
    "DREB": "DREB",
    "DEFENSIVE REBOUNDS": "DREB",
    "REB": "REB",
    "REBOUNDS": "REB",
    "TOTAL REBOUNDS": "REB",
    "AST": "AST",
    "ASSISTS": "AST",
    "ST": "STL",
    "STL": "STL",
    "STEALS": "STL",
    "BLK": "BLK",
    "BLOCKS": "BLK",
    "BLOCKED SHOTS": "BLK",
    "TO": "TOV",
    "TOV": "TOV",
    "TURNOVERS": "TOV",
}
PERCENTAGE_FIELDS_BY_NAME = {
    "FG%": ("FGM", "FGA"),
    "FG PCT": ("FGM", "FGA"),
    "FIELD GOAL %": ("FGM", "FGA"),
    "FIELD GOAL PERCENTAGE": ("FGM", "FGA"),
    "FIELD GOALS PERCENTAGE": ("FGM", "FGA"),
    "FT%": ("FTM", "FTA"),
    "FT PCT": ("FTM", "FTA"),
    "FREE THROW %": ("FTM", "FTA"),
    "FREE THROW PERCENTAGE": ("FTM", "FTA"),
    "FREE THROWS PERCENTAGE": ("FTM", "FTA"),
}
NBA_STAT_SOURCE_TABLE = "nba_player_season_stats"
TEAM_IDENTITY_CALCULATION_VERSION = "team-identity-relative-v1"
MINIMUM_COMPARABLE_TEAMS = 3
STRENGTH_THRESHOLD = 75.0
WEAKNESS_THRESHOLD = 25.0


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _season_year(season: str) -> int | None:
    try:
        return int(season[:4])
    except (TypeError, ValueError):
        return None


def _configured_categories(scoring_settings: dict[str, Any]) -> list[dict[str, Any]]:
    categories = scoring_settings.get("categories")
    if not isinstance(categories, list):
        return []
    result = []
    for category in categories:
        if not isinstance(category, dict) or category.get("stat_id") is None:
            continue
        result.append({
            "stat_id": str(category["stat_id"]),
            "name": str(category["name"]) if category.get("name") is not None else None,
            "configured_value": category.get("value"),
        })
    return result


def _category_definition(category: dict[str, Any]) -> tuple[str, str | tuple[str, str]] | None:
    stat_id = category["stat_id"]
    if stat_id in PERCENTAGE_FIELDS_BY_ID:
        return "weighted_percentage_from_season_makes_attempts", PERCENTAGE_FIELDS_BY_ID[stat_id]
    if stat_id in COUNTING_FIELDS_BY_ID:
        return "sum_of_player_per_game_rates", COUNTING_FIELDS_BY_ID[stat_id]
    name = (category.get("name") or "").strip().upper()
    if name in PERCENTAGE_FIELDS_BY_NAME:
        return "weighted_percentage_from_season_makes_attempts", PERCENTAGE_FIELDS_BY_NAME[name]
    if name in COUNTING_FIELDS_BY_NAME:
        return "sum_of_player_per_game_rates", COUNTING_FIELDS_BY_NAME[name]
    return None


def _category_direction(category: dict[str, Any], field_name: str | None) -> str:
    configured_value = _numeric(category.get("configured_value"))
    if (configured_value is not None and configured_value < 0) or field_name == "TOV":
        return "lower_is_better"
    return "higher_is_better"


def _category_meaning(fields: str | tuple[str, str], direction: str) -> str:
    if isinstance(fields, tuple):
        category_name = "field-goal percentage" if fields[0] == "FGM" else "free-throw percentage"
        return f"Weighted {category_name} from season makes and attempts."
    meanings = {
        "FGM": "Field goals made per game, summed across contributing roster players.",
        "FGA": "Field-goal attempts per game, summed across contributing roster players.",
        "FTM": "Free throws made per game, summed across contributing roster players.",
        "FTA": "Free-throw attempts per game, summed across contributing roster players.",
        "FG3M": "Three-pointers made per game, summed across contributing roster players.",
        "PTS": "Points per game, summed across contributing roster players.",
        "OREB": "Offensive rebounds per game, summed across contributing roster players.",
        "DREB": "Defensive rebounds per game, summed across contributing roster players.",
        "REB": "Rebounds per game, summed across contributing roster players.",
        "AST": "Assists per game, summed across contributing roster players.",
        "STL": "Steals per game, summed across contributing roster players.",
        "BLK": "Blocks per game, summed across contributing roster players.",
        "TOV": "Turnovers per game, summed across contributing roster players.",
    }
    meaning = meanings.get(fields, "Configured category total from persisted player rates.")
    if direction == "lower_is_better":
        return f"{meaning} Lower values are treated as better by the category settings."
    return meaning


def _source_season(
    rows: Iterable[NbaPlayerSeasonStats],
    league_season: int | None,
) -> str | None:
    seasons = {
        row.season
        for row in rows
        if row.season_type.strip().lower() == "regular season"
        and row.games_played > 0
        and _season_year(row.season) is not None
        and (league_season is None or _season_year(row.season) <= league_season)
    }
    return max(seasons, key=lambda season: (_season_year(season) or 0, season), default=None)


def _comparison_coverage_status(
    team: TeamIdentityBaseline,
    category: TeamCategoryResult,
) -> CategoryCoverageStatus:
    if team.roster_data_status == "stale":
        return "stale"
    return category.status


def _comparison_exclusion(
    team: TeamIdentityBaseline,
    category: TeamCategoryResult,
    additional_reasons: list[str] | None = None,
) -> ComparisonExclusion:
    coverage_status = _comparison_coverage_status(team, category)
    reasons = []
    if team.roster_data_status == "stale":
        reasons.append("stale_roster_snapshot")
    if category.status == "partial":
        reasons.append("partial_category_coverage")
    elif category.status == "unavailable":
        reasons.append(category.reason or "category_unavailable")
    elif category.status == "unsupported":
        reasons.append("unsupported_category")
    reasons.extend(additional_reasons or [])
    return ComparisonExclusion(
        team_key=team.team_key,
        team_name=team.team_name,
        coverage_status=coverage_status,
        reasons=reasons or ["not_comparable"],
    )


def _identity_label(
    normalized_position: float | None,
    enough_evidence: bool,
) -> Literal["strength", "neutral", "weakness", "insufficient_evidence"]:
    if not enough_evidence or normalized_position is None:
        return "insufficient_evidence"
    if normalized_position >= STRENGTH_THRESHOLD:
        return "strength"
    if normalized_position <= WEAKNESS_THRESHOLD:
        return "weakness"
    return "neutral"


def _apply_league_relative_comparisons(
    teams: list[TeamIdentityBaseline],
    source_season: str | None,
    source_stat_type: str | None,
) -> None:
    teams_by_league: dict[str, list[TeamIdentityBaseline]] = defaultdict(list)
    for team in teams:
        teams_by_league[team.league_key].append(team)
    for league_teams in teams_by_league.values():
        _apply_league_relative_comparisons_within_league(
            league_teams,
            source_season,
            source_stat_type,
        )


def _apply_league_relative_comparisons_within_league(
    teams: list[TeamIdentityBaseline],
    source_season: str | None,
    source_stat_type: str | None,
) -> None:
    category_ids = {
        category.category_id
        for team in teams
        for category in team.categories
    }
    for category_id in category_ids:
        category_by_team = {
            team.team_key: category
            for team in teams
            for category in team.categories
            if category.category_id == category_id
        }
        template = next(iter(category_by_team.values()))
        calculation_type = template.calculation_type
        direction = template.direction
        comparable: list[tuple[TeamIdentityBaseline, TeamCategoryResult]] = []
        excluded: list[ComparisonExclusion] = []
        for team in teams:
            category = category_by_team.get(team.team_key)
            if category is None:
                excluded.append(ComparisonExclusion(
                    team_key=team.team_key,
                    team_name=team.team_name,
                    coverage_status="unavailable",
                    reasons=["configured_category_missing"],
                ))
                continue
            same_contract = (
                category.category_id == category_id
                and category.calculation_type == calculation_type
                and category.direction == direction
                and source_season is not None
                and source_stat_type is not None
            )
            fully_covered = category.status == "available" and team.roster_data_status == "available"
            if same_contract and fully_covered and category.raw_value is not None:
                comparable.append((team, category))
            else:
                reasons = []
                if source_season is None:
                    reasons.append("source_season_unavailable")
                if source_stat_type is None:
                    reasons.append("source_stat_type_unavailable")
                if category.calculation_type != calculation_type or category.direction != direction:
                    reasons.append("calculation_contract_mismatch")
                excluded.append(_comparison_exclusion(team, category, reasons))

        values = [
            float(category.raw_value)
            for _, category in comparable
            if category.raw_value is not None
        ]
        comparable_count = len(comparable)
        enough_evidence = comparable_count >= MINIMUM_COMPARABLE_TEAMS
        minimum = min(values) if enough_evidence else None
        maximum = max(values) if enough_evidence else None
        category_median = float(median(values)) if enough_evidence else None
        for team in teams:
            category = category_by_team.get(team.team_key)
            if category is None:
                continue
            coverage_status = _comparison_coverage_status(team, category)
            eligible = any(candidate.team_key == team.team_key for candidate, _ in comparable)
            rank = None
            normalized_position = None
            label = _identity_label(None, False)
            if enough_evidence and eligible and category.raw_value is not None:
                assert minimum is not None and maximum is not None
                if direction == "lower_is_better":
                    rank = 1 + sum(value < category.raw_value for value in values)
                    span = maximum - minimum
                    normalized_position = (
                        50.0 if span == 0 else 100.0 * (maximum - category.raw_value) / span
                    )
                else:
                    rank = 1 + sum(value > category.raw_value for value in values)
                    span = maximum - minimum
                    normalized_position = (
                        50.0 if span == 0 else 100.0 * (category.raw_value - minimum) / span
                    )
                label = _identity_label(normalized_position, True)
            else:
                rank = None

            category_definition = _category_definition({
                "stat_id": category.category_id,
                "name": category.category_name,
                "configured_value": category.configured_value,
            })
            fields = category_definition[1] if category_definition is not None else None
            category.league_relative = LeagueRelativeCategoryResult(
                calculation_version=TEAM_IDENTITY_CALCULATION_VERSION,
                minimum_comparable_teams=MINIMUM_COMPARABLE_TEAMS,
                strength_threshold=STRENGTH_THRESHOLD,
                weakness_threshold=WEAKNESS_THRESHOLD,
                comparison_status="sufficient" if enough_evidence else "insufficient",
                comparable_team_count=comparable_count,
                rank=rank,
                minimum=minimum,
                maximum=maximum,
                median=category_median,
                normalized_position=normalized_position,
                direction=direction,
                label=label,
                coverage_status=coverage_status,
                excluded_teams=excluded,
                category_meaning=(
                    _category_meaning(fields, direction or "higher_is_better")
                    if fields is not None
                    else None
                ),
            )


def _source_imports(
    source_counts: dict[tuple[str, str, Any], tuple[int, int]],
) -> list[CategorySourceImport]:
    imports = [
        CategorySourceImport(
            season=season,
            stat_type=stat_type,
            imported_at=imported_at,
            player_count_with_source_stats=player_count,
            contributing_player_count=contributing_count,
        )
        for (season, stat_type, imported_at), (player_count, contributing_count) in source_counts.items()
    ]
    return sorted(imports, key=lambda source: (source.season, source.stat_type, source.imported_at))


def _category_result(
    category: dict[str, Any],
    roster_entries: list[RosterEntry],
    stats_by_nba_id: dict[str, NbaPlayerSeasonStats],
    source_season: str | None,
    roster_status: str,
    roster_imported: bool,
) -> TeamCategoryResult:
    category_fields = _category_definition(category)
    if category_fields is None:
        return TeamCategoryResult(
            category_id=category["stat_id"],
            category_name=category["name"],
            configured_value=category.get("configured_value"),
            status="unsupported",
            reason="unsupported_yahoo_category",
            calculation_type=None,
            direction=None,
            raw_value=None,
            numerator_total=None,
            denominator_total=None,
            contributing_player_count=0,
            missing_or_unmapped_player_count=0,
            missing_denominator_player_count=0,
            missing_players=[],
            source_table=None,
            source_imports=[],
        )

    calculation_type, fields = category_fields
    is_percentage = isinstance(fields, tuple)
    field_name = fields if isinstance(fields, str) else None
    numerator_field, denominator_field = fields if is_percentage else (None, None)
    mapped_direction = _category_direction(category, field_name)
    numerator_total = 0.0
    denominator_total = 0.0
    raw_total = 0.0
    raw_value: float | None = None
    contributors = 0
    missing_denominator_count = 0
    missing_players: list[MissingCategoryPlayer] = []
    source_counts: dict[tuple[str, str, Any], list[int]] = defaultdict(lambda: [0, 0])

    if not roster_imported:
        status = "unavailable"
        reason = "roster_not_imported"
    elif not roster_entries:
        status = "unavailable"
        reason = "empty_roster"
    else:
        for entry in roster_entries:
            identity = entry.identity
            if not identity.nba_player_id:
                missing_players.append(MissingCategoryPlayer(
                    yahoo_player_id=entry.yahoo_player_id,
                    player_name=identity.player_name,
                    reason="unmapped_nba_identity",
                ))
                continue
            stats = stats_by_nba_id.get(identity.nba_player_id)
            if stats is None:
                missing_players.append(MissingCategoryPlayer(
                    yahoo_player_id=entry.yahoo_player_id,
                    player_name=identity.player_name,
                    reason="no_stats_for_selected_source",
                ))
                continue
            source_key = (stats.season, stats.season_type, stats.imported_at)
            source_counts[source_key][0] += 1
            base_stats = stats.base_stats if isinstance(stats.base_stats, dict) else {}
            if is_percentage:
                numerator = _numeric(base_stats.get(numerator_field))
                denominator = _numeric(base_stats.get(denominator_field))
                if numerator is None or denominator is None:
                    if denominator is None:
                        missing_denominator_count += 1
                    missing_players.append(MissingCategoryPlayer(
                        yahoo_player_id=entry.yahoo_player_id,
                        player_name=identity.player_name,
                        reason=(
                            "missing_percentage_numerator_and_denominator"
                            if numerator is None and denominator is None
                            else "missing_percentage_numerator"
                            if numerator is None
                            else "missing_percentage_denominator"
                        ),
                    ))
                    continue
                numerator_total += numerator * stats.games_played
                denominator_total += denominator * stats.games_played
            else:
                value = _numeric(base_stats.get(field_name))
                if value is None:
                    missing_players.append(MissingCategoryPlayer(
                        yahoo_player_id=entry.yahoo_player_id,
                        player_name=identity.player_name,
                        reason=f"missing_stat_{field_name}",
                    ))
                    continue
                raw_total += value

            contributors += 1
            source_counts[source_key][1] += 1

        missing_count = len(missing_players)
        if is_percentage:
            raw_value = numerator_total / denominator_total if denominator_total else None
            if raw_value is None:
                status = "unavailable"
                reason = "zero_aggregate_denominator" if contributors else "no_valid_percentage_components"
            else:
                status = "partial" if missing_count or roster_status == "stale" else "available"
                reason = "missing_roster_contributors" if missing_count else "stale_roster_snapshot" if roster_status == "stale" else None
        else:
            raw_value = raw_total if contributors else None
            if not contributors:
                status = "unavailable"
                reason = "no_category_contributors"
            else:
                status = "partial" if missing_count or roster_status == "stale" else "available"
                reason = "missing_roster_contributors" if missing_count else "stale_roster_snapshot" if roster_status == "stale" else None

    if source_season is None and roster_imported and roster_entries and status == "unavailable":
        reason = "no_eligible_regular_season_source"

    source_imports = _source_imports({
        source: (counts[0], counts[1])
        for source, counts in source_counts.items()
    })
    return TeamCategoryResult(
        category_id=category["stat_id"],
        category_name=category["name"],
        configured_value=category.get("configured_value"),
        status=status,
        reason=reason,
        calculation_type=calculation_type,
        direction=mapped_direction,
        raw_value=raw_value,
        numerator_total=numerator_total if is_percentage else None,
        denominator_total=denominator_total if is_percentage else None,
        contributing_player_count=contributors,
        missing_or_unmapped_player_count=len(missing_players),
        missing_denominator_player_count=missing_denominator_count,
        missing_players=missing_players,
        source_table=NBA_STAT_SOURCE_TABLE if source_counts else None,
        source_imports=source_imports,
    )


async def get_team_category_baseline(
    session: AsyncSession,
    league_key: str,
) -> TeamCategoryBaselineResponse:
    league = await session.scalar(
        select(League)
        .where(League.league_key == league_key)
        .options(selectinload(League.settings))
    )
    if league is None:
        raise HTTPException(status_code=404, detail="Persisted Yahoo league was not found")

    settings = league.settings
    categories = _configured_categories(settings.scoring_settings if settings else {})
    teams_with_rosters = await list_roster_baselines(session, league_key)
    roster_entries = [
        entry
        for _, roster in teams_with_rosters
        if roster is not None
        for entry in roster.roster_entries
    ]
    nba_ids = {
        entry.identity.nba_player_id
        for entry in roster_entries
        if entry.identity.nba_player_id
    }
    all_stats = list((await session.scalars(
        select(NbaPlayerSeasonStats).where(NbaPlayerSeasonStats.nba_player_id.in_(nba_ids))
    )).all()) if nba_ids else []
    selected_source_season = _source_season(all_stats, league.season)
    season_stats = [
        row
        for row in all_stats
        if selected_source_season is not None
        and row.season == selected_source_season
        and row.season_type.strip().lower() == "regular season"
        and row.games_played > 0
    ]
    source_stat_type = min(
        (row.season_type for row in season_stats),
        key=lambda value: (value.casefold(), value),
        default=None,
    )
    selected_stats = [row for row in season_stats if row.season_type == source_stat_type]
    stats_by_nba_id = {row.nba_player_id: row for row in selected_stats}

    teams = []
    for team, roster in teams_with_rosters:
        status = roster_data_status(team, roster)
        team_entries = roster.roster_entries if roster else []
        mapped_count = sum(bool(entry.identity.nba_player_id) for entry in team_entries)
        teams.append(TeamIdentityBaseline(
            league_key=team.league_key,
            team_key=team.team_key,
            team_name=team.team_name,
            roster_data_status=status,
            roster_as_of=roster.imported_at if roster else None,
            roster_player_count=len(team_entries) if roster else None,
            mapped_player_count=mapped_count if roster else None,
            unmapped_player_count=len(team_entries) - mapped_count if roster else None,
            categories=[
                _category_result(
                    category,
                    team_entries,
                    stats_by_nba_id,
                    selected_source_season,
                    status,
                    roster is not None,
                )
                for category in categories
            ],
        ))

    _apply_league_relative_comparisons(
        teams,
        selected_source_season,
        source_stat_type,
    )
    return TeamCategoryBaselineResponse(
        league_key=league.league_key,
        league_season=league.season,
        settings_imported_at=settings.imported_at if settings else None,
        selected_source_season=selected_source_season,
        selected_source_stat_type=source_stat_type,
        source_season_selection="latest_eligible_season_with_rostered_player_stats",
        identity_method=TeamIdentityMethod(
            calculation_version=TEAM_IDENTITY_CALCULATION_VERSION,
            minimum_comparable_teams=MINIMUM_COMPARABLE_TEAMS,
            strength_threshold=STRENGTH_THRESHOLD,
            weakness_threshold=WEAKNESS_THRESHOLD,
        ),
        teams=teams,
    )

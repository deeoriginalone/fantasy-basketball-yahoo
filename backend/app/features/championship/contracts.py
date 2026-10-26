from datetime import datetime
from typing import Literal

from pydantic import BaseModel

CategoryCoverageStatus = Literal["available", "partial", "stale", "unavailable", "unsupported"]


class CategorySourceImport(BaseModel):
    season: str
    stat_type: str
    imported_at: datetime
    player_count_with_source_stats: int
    contributing_player_count: int


class MissingCategoryPlayer(BaseModel):
    yahoo_player_id: str
    player_name: str
    reason: str


class ComparisonExclusion(BaseModel):
    team_key: str
    team_name: str | None
    coverage_status: CategoryCoverageStatus
    reasons: list[str]


class LeagueRelativeCategoryResult(BaseModel):
    calculation_version: str
    minimum_comparable_teams: int
    strength_threshold: float
    weakness_threshold: float
    comparison_status: Literal["sufficient", "insufficient"]
    comparable_team_count: int
    rank: int | None
    minimum: float | None
    maximum: float | None
    median: float | None
    normalized_position: float | None
    direction: Literal["higher_is_better", "lower_is_better"] | None
    label: Literal["strength", "neutral", "weakness", "insufficient_evidence"]
    coverage_status: CategoryCoverageStatus
    excluded_teams: list[ComparisonExclusion]
    category_meaning: str | None


class TeamIdentityMethod(BaseModel):
    calculation_version: str
    minimum_comparable_teams: int
    strength_threshold: float
    weakness_threshold: float


class TeamCategoryResult(BaseModel):
    category_id: str
    category_name: str | None
    configured_value: int | float | str | None
    status: Literal["available", "partial", "unavailable", "unsupported"]
    reason: str | None
    calculation_type: str | None
    direction: Literal["higher_is_better", "lower_is_better"] | None
    raw_value: float | None
    numerator_total: float | None
    denominator_total: float | None
    contributing_player_count: int
    missing_or_unmapped_player_count: int
    missing_denominator_player_count: int
    missing_players: list[MissingCategoryPlayer]
    source_table: str | None
    source_imports: list[CategorySourceImport]
    league_relative: LeagueRelativeCategoryResult | None = None


class TeamIdentityBaseline(BaseModel):
    league_key: str
    team_key: str
    team_name: str | None
    roster_data_status: Literal["available", "stale", "not_imported"]
    roster_as_of: datetime | None
    roster_player_count: int | None
    mapped_player_count: int | None
    unmapped_player_count: int | None
    categories: list[TeamCategoryResult]


class TeamCategoryBaselineResponse(BaseModel):
    league_key: str
    league_season: int | None
    settings_imported_at: datetime | None
    selected_source_season: str | None
    selected_source_stat_type: str | None
    source_season_selection: Literal["latest_eligible_season_with_rostered_player_stats"]
    identity_method: TeamIdentityMethod
    teams: list[TeamIdentityBaseline]

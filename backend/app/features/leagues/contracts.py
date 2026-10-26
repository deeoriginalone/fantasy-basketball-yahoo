from datetime import datetime
from typing import Any

from pydantic import BaseModel


class LeagueTeamResponse(BaseModel):
    team_key: str
    team_name: str | None


class LeagueResponse(BaseModel):
    league_key: str
    league_name: str
    season: int | None
    league_imported_at: datetime
    settings_imported_at: datetime | None
    draft_pick_time_seconds: int | None = None
    scoring_settings: dict[str, Any]
    roster_positions: list[dict[str, Any]]
    teams: list[LeagueTeamResponse]


class LeagueImportSummary(BaseModel):
    league_key: str
    league_name: str
    season: int | None
    team_count: int


class LeagueImportResult(BaseModel):
    game_key: str
    imported_count: int
    team_count: int
    leagues: list[LeagueImportSummary]
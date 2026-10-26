"""Read-only waiver analysis over imported Yahoo and NBA evidence."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from math import isfinite
from statistics import mean, median
from typing import Any, Callable
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.championship.service import _numeric
from app.features.leagues.models import League
from app.features.nba.models import (
    NbaGame, NbaPlayer, NbaPlayerSeasonStats, NbaTeam, PlayerGameLog, PlayerSchedule,
)
from app.features.players.models import LeaguePlayer, PlayerIdentity
from app.features.players.normalization import _positions
from app.features.players.service import list_roster_baselines, roster_data_status
from app.features.waivers.contracts import (
    AcquisitionContext,
    AcquisitionCoverage,
    Candidate,
    Components,
    CoverageMetric,
    CoverageScope,
    CoverageSlice,
    CurrentRole,
    DataGap,
    DataGapCategory,
    DropOption,
    Evidence,
    IdentityCoverage,
    MappingWorklistItem,
    Mode,
    Opportunity,
    PotentialNbaMatch,
    ProductionCoverage,
    RankingEvidence,
    RootCause,
    RoleCoverage,
    RoleMetric,
    RoleWindow,
    SampleLabel,
    Schedule,
    ScheduleCoverage,
    StartsEvidence,
    StatusCoverage,
    SwapAnalysis,
    TransactionAnalysis,
    ValueEvidence,
    WaiverBoard,
    WaiverCoverage,
    WaiverImpact,
)
from app.services.draft.metrics import _category_field, _selected_position_positions
from app.services.draft.player_status import (
    recommendation_eligibility,
    status_is_supported,
    yahoo_status_reason,
)
from app.services.draft.utility import _maximum_slot_matching
from app.services.nba.player_importer import _name_key
from app.services.yahoo.normalization import extract_yahoo_records, _merge_settings, normalize_yahoo_settings

COMPONENTS = tuple(Components.model_fields)
RESOLVED_IDENTITY_STATES = {
    "EXACT_ID", "EXACT_NAME_TEAM", "NORMALIZED_NAME_TEAM",
    "KNOWN_ALIAS_TEAM", "TEAM_CHANGE_SUPPORTED",
}
WAIVER_TIMEZONE = ZoneInfo("America/Los_Angeles")
BASE_LIMITATIONS = [
    "Scores are descriptive heuristic indices, not predicted fantasy points or predictive accuracy.",
    "Season Evidence is historical per-game production, not a projection. No injury return dates are inferred.",
    "Acquisition value is unavailable until current rolling priority and transaction evidence are verified; it never affects ranking.",
    "Category-level waiver scoring and category swap impact are unavailable; no category values are simulated.",
    "Schedule counts describe persisted games, not guaranteed complete coverage or lineup starts. Matchup difficulty is unavailable.",
    "This Week uses today through Sunday in Pacific Time (PST/PDT), not a verified Yahoo matchup period.",
    "Next 7 Days includes Pacific today and the following six dates, not a Yahoo matchup week.",
    "Current-season samples below seven games cannot support ADD, STREAM or MUST ADD. Evidence quality is not probability.",
    "No Yahoo transactions are executed. Roster locks and transaction eligibility must be checked in Yahoo.",
]


def evidence(state: str, source: str, as_of: datetime | None, detail: str) -> Evidence:
    return Evidence(state=state, source=source, as_of=as_of, detail=detail)


def freshness(as_of: datetime | None, now: datetime, days: int = 1) -> str:
    if as_of is None:
        return "missing"
    return "stale" if now - as_of > timedelta(days=days) else "available"


def coverage_metric(count: int, total: int) -> CoverageMetric:
    return CoverageMetric(
        count=count,
        total=total,
        percentage=round(count / total * 100, 2) if total else 0,
    )


def identity_is_supported(player: Candidate) -> bool:
    return player.identity_mapping_state in RESOLVED_IDENTITY_STATES


def identity_mapping(
    identity: PlayerIdentity,
    nba_player: NbaPlayer | None,
    players_by_name: dict[str, list[NbaPlayer]],
    abbreviations: dict[str, str],
    yahoo_team_source: str | None,
) -> tuple[str, str, list[PotentialNbaMatch]]:
    key = _name_key(identity.player_name)
    potential = [
        PotentialNbaMatch(
            nba_player_id=row.nba_player_id,
            player_name=row.player_name,
            team=(abbreviations.get(row.team_id) if row.team_id else None) or row.team_abbreviation,
        )
        for row in players_by_name.get(key, [])
    ]
    yahoo_team = (yahoo_team_source or identity.team or "").strip().upper() or None
    nba_team = (
        abbreviations.get(nba_player.team_id)
        if nba_player and nba_player.team_id else None
    )
    if nba_player is None:
        if not identity.nba_player_id:
            if not potential:
                return "NO_MATCH", "No NBA player has the same normalized name in the persisted NBA player table.", potential
            same_team = [row for row in potential if row.team and yahoo_team == row.team.upper()]
            if len(same_team) == 1:
                return "MISSING_MAPPING", "A same-name/team NBA candidate exists, but the identity link is absent; no automatic mapping was made.", potential
            return "AMBIGUOUS", "Same-name NBA candidates exist, but the persisted evidence does not establish a unique same-team identity.", potential
        return "MISSING_MAPPING", f"NBA identity link {identity.nba_player_id} does not resolve to a persisted NBA player.", potential
    if not key or _name_key(nba_player.player_name) != key:
        return "AMBIGUOUS", "The linked NBA player name does not match the Yahoo name under the established normalization; identity requires review.", potential
    if not yahoo_team or not nba_team:
        return "AMBIGUOUS", "Name matches, but Yahoo or NBA team evidence is missing; identity cannot be confirmed.", potential
    if yahoo_team != nba_team.upper():
        return "AMBIGUOUS", f"Yahoo team {yahoo_team} conflicts with NBA team {nba_team}; a trade or stale identity is not assumed.", potential
    if identity.player_name.strip().casefold() == nba_player.player_name.strip().casefold():
        return "EXACT_NAME_TEAM", "Yahoo and NBA names and team abbreviations match.", potential
    return "NORMALIZED_NAME_TEAM", "Yahoo and NBA names match under established normalization and team abbreviations agree.", potential


def resolve_schedule(
    rows: list[PlayerSchedule],
    today: date,
    window_end: date,
    now: datetime,
    daily_games: Counter,
    abbreviations: dict[str, str],
    *,
    nba_mapped: bool,
    team_mapped: bool,
) -> Schedule:
    valid_rows = [
        row for row in rows
        if not any(word in (row.game_status or "").lower() for word in ("postpon", "cancel", "final"))
    ]
    window_rows = [row for row in valid_rows if today <= row.game_date <= window_end]
    next_7_days = [row for row in valid_rows if today <= row.game_date <= today + timedelta(days=6)]
    imported_at = min((row.imported_at for row in rows), default=None)
    schedule_freshness = freshness(imported_at, now, 7)
    if not nba_mapped:
        diagnostic = "NBA_ID_UNMAPPED"
    elif not team_mapped:
        diagnostic = "TEAM_MAPPING_MISSING"
    elif not rows:
        diagnostic = "NO_PLAYER_SCHEDULE_ROWS"
    elif schedule_freshness == "stale":
        diagnostic = "SCHEDULE_STALE"
    elif window_rows:
        diagnostic = "SCHEDULE_ROWS_PRESENT"
    else:
        diagnostic = "SCHEDULE_SOURCE_INCOMPLETE"
    dates = {row.game_date for row in window_rows}
    return Schedule(
        games_remaining=len(window_rows) if window_rows and schedule_freshness != "stale" else None,
        off_day_games=(
            sum(daily_games[row.game_date] <= 5 for row in window_rows)
            if window_rows and schedule_freshness != "stale" else None
        ),
        back_to_backs=(
            sum(day - timedelta(days=1) in dates for day in dates)
            if window_rows and schedule_freshness != "stale" else None
        ),
        next_7_days_games=(
            len(next_7_days) if next_7_days and schedule_freshness != "stale" else None
        ),
        opponents=[abbreviations.get(row.opponent_team_id, "Unknown") for row in window_rows],
        source_row_count=len(rows),
        window_start=today,
        window_end=window_end,
        imported_at=imported_at,
        freshness=(
            "stale" if schedule_freshness == "stale"
            else "fresh" if imported_at is not None
            else "unknown"
        ),
        coverage=(
            "STALE" if schedule_freshness == "stale" and rows
            else "PARTIAL" if window_rows
            else "UNKNOWN"
        ),
        diagnostic_reason=diagnostic,
    )


def identity_chain_diagnostic(
    *,
    yahoo_id: str | None,
    nba_id: str | None,
    nba_player_present: bool,
    team_mapped: bool,
    has_game_logs: bool,
    has_season_stats: bool,
    has_schedule_rows: bool,
    schedule_stale: bool,
) -> str:
    if not yahoo_id:
        return "YAHOO_ID_MISSING"
    if not nba_id:
        return "NBA_ID_UNMAPPED"
    if not nba_player_present:
        return "NBA_PLAYER_MISSING"
    if not team_mapped:
        return "TEAM_MAPPING_MISSING"
    if not has_game_logs:
        return "GAME_LOGS_MISSING"
    if not has_season_stats:
        return "SEASON_STATS_MISSING"
    if not has_schedule_rows:
        return "SCHEDULE_ROWS_MISSING"
    if schedule_stale:
        return "SCHEDULE_STALE"
    return "COMPLETE_MAPPING"


def validated_weights(weights: dict[str, float]) -> dict[str, float]:
    if set(weights) != set(COMPONENTS) or any(
        isinstance(v, bool) or not isfinite(v) or v < 0 for v in weights.values()
    ) or sum(weights.values()) <= 0:
        raise ValueError("WAIVER_WEIGHTS must contain all five components with finite nonnegative weights and a positive sum")
    total = sum(weights.values())
    return {key: value / total for key, value in weights.items()}


def aggregate(components: Components, weights: dict[str, float]) -> tuple[float | None, dict[str, float]]:
    values = components.model_dump()
    if values["player_value"] is None or values["roster_fit"] is None:
        return None, {}
    total = sum(weights[key] for key, value in values.items() if value is not None)
    if total <= 0:
        return None, {}
    effective = {key: weights[key] / total for key, value in values.items() if value is not None and weights[key] > 0}
    return round(sum(values[key] * weight for key, weight in effective.items()), 6), effective


def percentile(value: float | None, distribution: list[float]) -> float | None:
    if value is None or not distribution:
        return None
    # Midrank preserves equal scores for ties and is independent of input order.
    return 100 * (sum(item < value for item in distribution) + sum(item == value for item in distribution) / 2) / len(distribution)


def scoring_fields(scoring: dict[str, Any]) -> dict[str, float] | None:
    if "point" not in str(scoring.get("scoring_type", "")).lower():
        return None
    categories = scoring.get("categories")
    if not isinstance(categories, list) or not categories:
        return None
    fields: dict[str, float] = defaultdict(float)
    for category in categories:
        if not isinstance(category, dict):
            return None
        modifier = _numeric(category.get("value"))
        if modifier is None:
            return None
        try:
            field = _category_field(category)
        except HTTPException:
            return None
        fields[field] += modifier
    return dict(fields)


def production(stats: dict[str, float], fields: dict[str, float] | None) -> float | None:
    if not fields or any(field not in stats for field, weight in fields.items() if weight != 0):
        return None
    return sum(stats[field] * weight for field, weight in fields.items() if weight != 0)


def production_detail(
    stats: dict[str, float],
    fields: dict[str, float] | None,
    window: str,
    observations: int,
) -> str:
    if fields is None:
        return f"{window} production is unsupported because persisted Yahoo points modifiers are unavailable."
    if observations == 0:
        return f"{window} production is missing because no eligible persisted NBA game/stat observations exist in the selected window."
    missing = sorted(field for field, weight in fields.items() if weight != 0 and field not in stats)
    if missing:
        return f"{window} production is unavailable because persisted NBA observations lack required scoring fields: {', '.join(missing)}."
    return f"{window} production is unavailable because complete numeric scoring inputs could not be calculated."


def verify_league_contract(league: League) -> list[str]:
    if league.league_key != "478.l.50505":
        return []
    settings = league.settings
    if settings is None:
        raise HTTPException(409, "Persisted Driveway Dudes settings missing; waiver analysis blocked")
    records = extract_yahoo_records(settings.source_payload, "league", "league_key")
    record = next((row for row in records if str(row.get("league_key")) == league.league_key), {})
    rules = _merge_settings(record.get("settings"))
    expected = {"scoring_type": "headpoint", "max_teams": "12", "uses_faab": "0",
        "waiver_type": "R", "waiver_rule": "all", "waiver_time": "2",
        "max_weekly_adds": "4", "post_draft_players": "W"}
    mismatches = [f"{key}: persisted {rules.get(key)!r}, expected {value!r}"
        for key, value in expected.items() if str(rules.get(key)) != value]
    for key, value in {"num_teams": "12", "weekly_deadline": "intraday", "allow_add_to_dl_extra_pos": "1"}.items():
        if str(record.get(key)) != value:
            mismatches.append(f"{key}: persisted {record.get(key)!r}, expected {value!r}")
    for source in (record, league.source_payload):
        for key, value in {"name": "Driveway Dudes", "scoring_type": "headpoint", "num_teams": "12",
            "max_teams": "12", "weekly_deadline": "intraday", "allow_add_to_dl_extra_pos": "1"}.items():
            if key in source and str(source[key]) != value:
                mismatches.append(f"league metadata {key}: persisted {source[key]!r}, expected {value!r}")
    # Yahoo omits max_adds when there is no season acquisition limit.
    if rules.get("max_adds") not in (None, "", "none", "None", "-1", -1):
        mismatches.append(f"max_adds: unexpected season limit {rules['max_adds']!r}")
    expected_fields = {"PTS": 1, "REB": 1.2, "AST": 1.5, "BLK": 3, "STL": 3, "TOV": -1}
    raw_scoring, raw_positions = normalize_yahoo_settings(league.league_key, settings.source_payload)
    if scoring_fields(settings.scoring_settings) != expected_fields or scoring_fields(raw_scoring) != expected_fields:
        mismatches.append("Yahoo scoring modifiers disagree with the verified points formula")
    expected_slots = Counter({"PG": 1, "SG": 1, "G": 1, "SF": 1, "PF": 1, "F": 1, "C": 2, "UTIL": 2, "BN": 3, "IL": 3})
    for positions in (settings.roster_positions, raw_positions):
        actual: Counter[str] = Counter()
        for slot in positions:
            actual[str(slot.get("position", "")).upper()] += _numeric(slot.get("count")) or 0
        if actual != expected_slots:
            mismatches.append("Yahoo roster positions disagree with the verified 16-slot roster")
    if league.league_name != "Driveway Dudes" or league.source_payload.get("scoring_type") != "headpoint":
        mismatches.append("Persisted league identity/scoring type disagrees with Driveway Dudes H2H Points")
    if mismatches:
        raise HTTPException(409, {"message": "Persisted league contract mismatch; waiver analysis blocked", "mismatches": mismatches})
    return ["Continual rolling list", "Standard waiver mode", "2-day waiver period", "4 adds/week",
        "No season acquisition maximum", "Daily - Today deadline",
        "Post-draft players follow waiver rules", "Injured available players may be added directly to an injury slot"]


def numeric_stats(payload: dict[str, Any]) -> dict[str, float]:
    return {key: number for key, value in payload.items() if (number := _numeric(value)) is not None}


def log_average(logs: list[PlayerGameLog]) -> dict[str, float]:
    if not logs:
        return {}
    fields = set.intersection(*(set(numeric_stats(row.stats_payload)) for row in logs))
    return {field: mean(float(row.stats_payload[field]) for row in logs) for field in fields}


ROLE_METHOD = (
    "Latest three vs preceding three persisted current-season regular-season games within the 14-day lookback. "
    "Each side needs three valid fresh observations. Minutes threshold: +/-3.0; usage threshold: +/-0.02 (2 percentage points). "
    "Mean and median changes must agree at the threshold, preventing a single-game outlier from establishing direction. "
    "Minutes establish role support; supported usage may add direction, but opposing material directions are insufficient evidence. "
    "No future minutes, usage or starting role is inferred."
)


def role_metric(logs: list[PlayerGameLog], field: str, now: datetime, today: date) -> RoleMetric:
    ordered = sorted(logs, key=lambda row: (row.game_date, row.game_id))[-6:]
    recent_rows, comparison_rows = ordered[-3:], ordered[:-3]
    def window(rows: list[PlayerGameLog]) -> RoleWindow:
        supported = []
        missing, stale = [], []
        for row in rows:
            value = _numeric(row.stats_payload.get(field))
            if value is None or value < 0 or (field == "USG_PCT" and value > 1):
                missing.append(row.game_id)
            elif freshness(row.imported_at, now, 7) != "available":
                stale.append(row.game_id)
            else:
                supported.append((row, value))
        return RoleWindow(
            average=mean(value for _, value in supported) if supported else None,
            median=median(value for _, value in supported) if supported else None,
            games=len(supported), game_ids=[row.game_id for row, _ in supported],
            window_start=min((row.game_date for row in rows), default=None),
            window_end=max((row.game_date for row in rows), default=None),
            as_of=min((row.imported_at for row in rows), default=None),
            missing_game_ids=missing, stale_game_ids=stale,
        )
    recent, comparison = window(recent_rows), window(comparison_rows)
    outdated = bool(ordered) and (ordered[-1].game_date < today - timedelta(days=7)
        or bool(recent.stale_game_ids or comparison.stale_game_ids))
    complete = recent.games == comparison.games == 3
    state = "stale" if outdated else "available" if complete else "partial" if recent.games or comparison.games else "unavailable"
    detail = (f"{field}: three valid fresh observations on each side required. "
        f"Recent {recent.games}/3; comparison {comparison.games}/3. "
        f"Missing/invalid: {len(recent.missing_game_ids) + len(comparison.missing_game_ids)}; "
        f"stale imports: {len(recent.stale_game_ids) + len(comparison.stale_game_ids)}. "
        "Windows are fixed by game date; missing/stale inputs are not zero-filled or backfilled.")
    return RoleMetric(quality=Evidence(state=state, source="NBA player_game_logs",
        as_of=min((row.imported_at for row in ordered), default=None),
        detail=detail, sample_count=recent.games + comparison.games),
        recent=recent, comparison=comparison,
        delta=round(recent.average - comparison.average, 6) if complete and not outdated else None,
        median_delta=round(recent.median - comparison.median, 6) if complete and not outdated else None,
        unit="minutes" if field == "MIN" else "fraction (multiply by 100 for percent / percentage-point delta)")


def current_role(logs: list[PlayerGameLog], season_stats: NbaPlayerSeasonStats | None,
    season: str, now: datetime, today: date) -> Opportunity:
    minutes, usage = (role_metric(logs, field, now, today) for field in ("MIN", "USG_PCT"))
    current = season_stats if season_stats and season_stats.season == season else None
    starter_payload = current.source_payload.get("starter_filter") if current else None
    explicit_starts = _numeric(starter_payload.get("GP")) if isinstance(starter_payload, dict) else None
    valid_starts = current is not None and current.games_played > 0 and explicit_starts is not None and explicit_starts.is_integer() and (
        0 <= explicit_starts <= current.games_played and explicit_starts == current.games_started)
    starts_state = (freshness(current.imported_at, now, 7) if valid_starts
        else "unavailable")
    if starts_state == "available" and current.games_played < 3:
        starts_state = "partial"
    starts = StartsEvidence(
        quality=Evidence(state=starts_state, source="NBA current-season starter-filter GP",
            as_of=current.imported_at if current else None,
            sample_count=current.games_played if valid_starts else 0,
            detail="Explicit starter-filter GP must match saved games_started; an absent starter row is not zero starts."),
        season=current.season if current else None,
        season_starts=int(explicit_starts) if valid_starts else None,
        season_games=current.games_played if valid_starts else None,
    )
    season_usage = _numeric(current.advanced_stats.get("USG_PCT")) if current else None
    if season_usage is None or not 0 <= season_usage <= 1:
        season_usage = None
    usage_quality = Evidence(
        state=freshness(current.imported_at, now, 7) if season_usage is not None else "unavailable",
        source="NBA current-season advanced statistics",
        as_of=current.imported_at if current else None,
        sample_count=current.games_played if season_usage is not None else 0,
        detail="Season usage is context only; it is not game-level recent usage or a comparison window.",
    )
    direction = "INSUFFICIENT EVIDENCE"
    state = minutes.quality.state
    def supported_direction(metric: RoleMetric, threshold: float) -> int | None:
        def band(value: float) -> int:
            return 1 if value >= threshold else -1 if value <= -threshold else 0
        average_band, median_band = band(metric.delta), band(metric.median_delta)
        return average_band if average_band == median_band else None
    if state == "available":
        minute_direction = supported_direction(minutes, 3)
        usage_direction = supported_direction(usage, .02) if usage.delta is not None else 0
        if minute_direction is None or usage_direction is None or minute_direction * usage_direction == -1:
            state = "partial"
        else:
            direction = "RISING" if max(minute_direction, usage_direction) > 0 else "FALLING" if min(minute_direction, usage_direction) < 0 else "STABLE"
    role = CurrentRole(minutes=minutes, usage=usage, starts=starts,
        quality=Evidence(state=state, source="Persisted NBA role windows", as_of=minutes.quality.as_of,
            sample_count=minutes.quality.sample_count,
            detail="Role requires qualified minutes windows. Missing usage/starts remain independent limitations; mean/median disagreement or opposing supported directions are insufficient evidence."),
        trend=direction, season_usage=season_usage, season_usage_quality=usage_quality,
        method=ROLE_METHOD, limitations=[
            "Role intelligence describes measured games only, not future minutes, usage, coach intent or injury replacement permanence.",
            "Recent game-level starts are unavailable; season starts do not establish the current lineup.",
            "No supported game-level usage means recent usage and usage delta remain unavailable; season usage is not substituted.",
        ])
    parts = {}
    if role.quality.state == "available":
        parts["minutes_level"] = min(100, max(0, minutes.recent.average / 36 * 100))
        if usage.delta is not None:
            parts["usage_change"] = min(100, max(0, 50 + usage.delta * 100))
        if starts.quality.state == "available":
            parts["season_start_rate"] = starts.season_starts / starts.season_games * 100
    return Opportunity(minutes=minutes.recent.average, minutes_trend=minutes.delta,
        usage_trend=usage.delta, historical_start_rate=starts.season_starts / starts.season_games if valid_starts else None,
        role=role.trend, score=mean(parts.values()) if parts else None, score_parts=parts, current_role=role)


def slot_positions(slot: str) -> set[str]:
    if slot in {"UTIL", "UT"}:
        return {"PG", "SG", "SF", "PF", "C"}
    return _selected_position_positions(slot)


@lru_cache(maxsize=4096)
def _matched_positions(positions: tuple[str, ...], slots: tuple[str, ...]) -> int:
    return len(_maximum_slot_matching(
        [_selected_position_positions(position) for position in positions], list(slots),
    ))


def matched_slots(roster: list[Candidate], slots: list[str]) -> int:
    return _matched_positions(tuple(sorted(player.position or "" for player in roster)), tuple(slots))


def coverage(roster: list[Candidate], slots: list[str]) -> float | None:
    if not slots or any(not _selected_position_positions(player.position or "") for player in roster):
        return None
    return 100.0 * matched_slots(roster, slots) / len(slots)


def roster_fit(player: Candidate, roster: list[Candidate], slots: list[str]) -> float | None:
    return coverage([row for row in roster if row.player_id != player.player_id] + [player], slots)


def sample_label(games: int) -> SampleLabel:
    return ("EXCELLENT" if games >= 20 else "GOOD" if games >= 10 else "LIMITED" if games >= 7
        else "VERY LIMITED" if games >= 4 else "INSUFFICIENT FOR STRONG RECOMMENDATION" if games >= 1
        else "NO CURRENT-SEASON EVIDENCE")


def sufficient_sample(player: Candidate, mode: Mode) -> bool:
    value = player.ros if mode == "ros" else player.recent
    quality = player.data_quality.get("ros" if mode == "ros" else "recent")
    return player.current_season_games >= 7 and value.games >= 7 and quality is not None and quality.state == "available"


def window_end_date(today: date, season_year: int, mode: Mode) -> date:
    if mode == "this_week":
        return today + timedelta(days=6 - today.weekday())
    if mode == "next_7_days":
        return today + timedelta(days=6)
    return max(today, today.replace(year=season_year + 1, month=6, day=30))


@dataclass
class Context:
    league: League
    team_key: str
    mode: Mode
    now: datetime
    players: dict[int, Candidate]
    roster_ids: list[int]
    slots: list[str]
    capacity: int | None
    roster_ready: bool
    weights: dict[str, float]
    quality: dict[str, Evidence]
    mapping_worklist: list[MappingWorklistItem] = field(default_factory=list)
    pool_ids: set[int] | None = None
    non_injury_roster_count: int | None = None
    comparison_keys: list[str] | None = None


def _coverage_metric(rows: list[Candidate], predicate: Callable[[Candidate], bool]) -> CoverageMetric:
    return coverage_metric(sum(predicate(row) for row in rows), len(rows))


def _coverage_slice(rows: list[Candidate]) -> CoverageSlice:
    identity_good = {
        "EXACT_ID", "EXACT_NAME_TEAM", "NORMALIZED_NAME_TEAM",
        "KNOWN_ALIAS_TEAM", "TEAM_CHANGE_SUPPORTED",
    }
    recent = _coverage_metric(rows, lambda row: row.data_quality["recent"].state == "available")
    recent_stale = _coverage_metric(rows, lambda row: row.data_quality["recent"].state == "stale")
    season = _coverage_metric(rows, lambda row: row.data_quality["ros"].state == "available")
    season_stale = _coverage_metric(rows, lambda row: row.data_quality["ros"].state == "stale")
    schedule_supported = _coverage_metric(rows, lambda row: row.schedule.coverage == "PARTIAL")
    schedule_unknown = _coverage_metric(rows, lambda row: row.schedule.coverage == "UNKNOWN")
    schedule_stale = _coverage_metric(rows, lambda row: row.schedule.coverage == "STALE")
    schedule_incomplete = _coverage_metric(
        rows, lambda row: row.schedule.diagnostic_reason == "SCHEDULE_SOURCE_INCOMPLETE",
    )
    explicit_status = _coverage_metric(rows, lambda row: bool(row.raw_yahoo_status and row.raw_yahoo_status.strip()))
    blank_status = _coverage_metric(rows, lambda row: row.status_diagnostic == "YAHOO_SUPPLIED_BLANK")
    stale_status = _coverage_metric(rows, lambda row: row.status_diagnostic == "STALE_PLAYER_POOL_IMPORT")
    minutes_qualified = _coverage_metric(rows, lambda row: row.opportunity.current_role is not None
        and row.opportunity.current_role.minutes.quality.state == "available")
    usage_supported = _coverage_metric(rows, lambda row: row.opportunity.current_role is not None
        and row.opportunity.current_role.usage.quality.state == "available")
    game_starts = _coverage_metric(rows, lambda row: row.opportunity.current_role is not None
        and row.opportunity.current_role.starts.recent_starts is not None)
    season_starts = _coverage_metric(rows, lambda row: row.opportunity.current_role is not None
        and row.opportunity.current_role.starts.season_starts is not None)
    insufficient_sample = _coverage_metric(rows, lambda row: row.opportunity.current_role is not None
        and row.opportunity.current_role.minutes.quality.state == "partial")
    missing_role_inputs = _coverage_metric(rows, lambda row: row.opportunity.current_role is not None and (
        row.opportunity.current_role.minutes.quality.state != "available"
        or row.opportunity.current_role.usage.quality.state != "available"
        or row.opportunity.current_role.starts.recent_starts is None
    ))
    return CoverageSlice(
        identity=IdentityCoverage(
            complete=_coverage_metric(rows, lambda row: row.identity_mapping_state in identity_good),
            unresolved=_coverage_metric(rows, lambda row: row.identity_mapping_state not in identity_good),
            resolution_counts=dict(sorted(Counter(row.identity_mapping_state for row in rows).items())),
        ),
        production=ProductionCoverage(
            recent_supported=recent,
            recent_missing=coverage_metric(len(rows) - recent.count - recent_stale.count, len(rows)),
            recent_stale=recent_stale,
            season_supported=season,
            season_missing=coverage_metric(len(rows) - season.count - season_stale.count, len(rows)),
            season_stale=season_stale,
        ),
        schedule=ScheduleCoverage(
            supported=schedule_supported,
            unknown=schedule_unknown,
            stale=schedule_stale,
            source_incomplete=schedule_incomplete,
        ),
        status=StatusCoverage(explicit=explicit_status, yahoo_blank=blank_status, stale=stale_status),
        role=RoleCoverage(
            minutes_qualified=minutes_qualified,
            usage_supported=usage_supported,
            game_level_starts_supported=game_starts,
            season_starts_supported=season_starts,
            insufficient_sample=insufficient_sample,
            missing_inputs=missing_role_inputs,
        ),
    )


def board_coverage(ctx: Context) -> tuple[WaiverCoverage, list[DataGap]]:
    rows = (
        [ctx.players[player_id] for player_id in ctx.pool_ids if player_id in ctx.players]
        if ctx.pool_ids is not None else list(ctx.players.values())
    )
    candidates = [
        row for row in rows
        if row.availability in {"free_agent", "waivers", "unrostered"} and row.eligible
    ]
    roster = [ctx.players[player_id] for player_id in ctx.roster_ids]
    pool_coverage = _coverage_slice(rows)
    candidate_coverage = _coverage_slice(candidates)
    roster_coverage = _coverage_slice(roster)
    acquisition_available = ctx.quality["acquisition_value"].state == "available"
    coverage = WaiverCoverage(
        population=CoverageScope(total=len(rows), candidates=len(candidates), roster=len(roster)),
        pool=pool_coverage,
        candidates=candidate_coverage,
        roster=roster_coverage,
        acquisition=AcquisitionCoverage(
            supported=coverage_metric(int(acquisition_available), 1),
            unsupported=coverage_metric(int(not acquisition_available), 1),
        ),
        mapping_worklist=[
            item for item in ctx.mapping_worklist
            if ctx.pool_ids is None or item.internal_id in ctx.pool_ids
        ],
    )
    gaps: list[DataGap] = []

    categories: dict[RootCause, DataGapCategory] = {
        "RESOLVABLE_INTERNAL_DEFECT": "FIXABLE DATA ISSUE",
        "STALE_EXISTING_SOURCE": "FIXABLE DATA ISSUE",
        "MISSING_MAPPING": "FIXABLE DATA ISSUE",
        "MISSING_EXISTING_SOURCE_FIELD": "SOURCE DOES NOT SUPPLY",
        "SOURCE_DOES_NOT_SUPPLY": "SOURCE DOES NOT SUPPLY",
        "SOURCE_CONTRACT_UNVERIFIED": "SOURCE CONTRACT UNVERIFIED",
        "REQUIRES_MORE_GAMES": "WAITING FOR MORE GAMES",
        "REQUIRES_NEW_SOURCE": "NEW SOURCE REQUIRED",
        "INTENTIONALLY_UNSUPPORTED": "INTENTIONALLY UNSUPPORTED",
    }

    def add_gap(
        root_cause: RootCause,
        field_name: str,
        count: int,
        total: int,
        reason: str,
    ) -> None:
        if count:
            gaps.append(DataGap(
                category=categories[root_cause],
                field=field_name,
                count=count,
                total=total,
                percentage=round(count / total * 100, 2) if total else 0,
                reason=reason,
                root_cause=root_cause,
            ))

    unresolved = [
        row for row in rows
        if row.identity_mapping_state not in RESOLVED_IDENTITY_STATES
    ]
    add_gap(
        "MISSING_MAPPING", "Yahoo ↔ NBA identity mapping",
        sum(row.identity_mapping_state != "NON_NBA_PLAYER" for row in unresolved),
        len(rows),
        "Persisted names/teams do not establish a unique mapping. Review the mapping worklist; no identity or team was changed automatically.",
    )

    for field_name, quality_key in (("Recent production", "recent"), ("Season Evidence", "ros")):
        evidence = [row.data_quality[quality_key] for row in candidates]
        for state, root_cause, reason in (
            ("stale", "STALE_EXISTING_SOURCE", "Persisted production evidence is outside the supported freshness window; stale values are not used for scoring."),
            ("unsupported", "SOURCE_CONTRACT_UNVERIFIED", "Persisted Yahoo scoring modifiers are unavailable; the production calculation contract cannot be verified."),
        ):
            add_gap(root_cause, field_name, sum(item.state == state for item in evidence), len(candidates), reason)
        no_observations = sum(
            item.state == "missing" and "no eligible persisted NBA game/stat observations" in item.detail
            for item in evidence
        )
        missing_fields = sum(
            item.state == "missing" and "lack required scoring fields" in item.detail
            for item in evidence
        )
        internal_defects = sum(
            item.state == "missing" and "complete numeric scoring inputs could not be calculated" in item.detail
            for item in evidence
        )
        if no_observations:
            add_gap(
                "REQUIRES_MORE_GAMES", field_name, no_observations, len(candidates),
                "No eligible persisted game/stat observations exist in the selected window; this is an evidence/sample limitation.",
            )
        add_gap(
            "MISSING_EXISTING_SOURCE_FIELD", field_name, missing_fields, len(candidates),
            "Persisted NBA observations lack one or more required Yahoo-scoring stat fields; missing values are not zero-filled.",
        )
        add_gap(
            "RESOLVABLE_INTERNAL_DEFECT", field_name, internal_defects, len(candidates),
            "Complete numeric scoring inputs were persisted but the calculation could not be completed; investigate the calculation path.",
        )

    no_schedule_rows = [
        row for row in rows
        if row.schedule.diagnostic_reason == "NO_PLAYER_SCHEDULE_ROWS"
    ]
    add_gap(
        "MISSING_MAPPING", "Player schedule rows blocked by identity",
        sum(not identity_is_supported(row) for row in no_schedule_rows), len(rows),
        "The NBA identity chain is unresolved, so player schedule rows cannot be attributed safely.",
    )
    add_gap(
        "MISSING_EXISTING_SOURCE_FIELD", "Player schedule rows missing",
        sum(identity_is_supported(row) for row in no_schedule_rows), len(rows),
        "No per-player schedule rows are persisted for this resolved identity; no games are inferred from team-wide schedules.",
    )
    add_gap(
        "STALE_EXISTING_SOURCE", "Stale player schedule",
        pool_coverage.schedule.stale.count, pool_coverage.schedule.stale.total,
        "Persisted player schedule rows are older than the supported freshness window; counts are withheld until refreshed.",
    )
    add_gap(
        "STALE_EXISTING_SOURCE", "Stale Yahoo status",
        pool_coverage.status.stale.count, pool_coverage.status.stale.total,
        "The Yahoo player-pool observation is older than the status freshness limit; retain the raw status but do not treat it as current.",
    )
    add_gap(
        "SOURCE_CONTRACT_UNVERIFIED", "Schedule completeness",
        pool_coverage.schedule.source_incomplete.count, pool_coverage.schedule.source_incomplete.total,
        "Player schedule rows exist, but there is no verified completeness manifest. An empty requested window is UNKNOWN, not a verified zero.",
    )
    add_gap(
        "SOURCE_CONTRACT_UNVERIFIED", "Unrecognized Yahoo status token",
        sum(row.status_diagnostic == "UNRECOGNIZED_STATUS" for row in rows), len(rows),
        "This nonblank Yahoo status token is not in the verified status set; it remains UNKNOWN and cannot support a strong action.",
    )
    add_gap(
        "SOURCE_CONTRACT_UNVERIFIED", "Game-level usage",
        len(rows) - pool_coverage.role.usage_supported.count, len(rows),
        "Existing adapter capability for game-level USG_PCT is unverified; season usage is not substituted for game-level role evidence.",
    )
    add_gap(
        "SOURCE_CONTRACT_UNVERIFIED", "Recent game-level starts",
        len(rows) - pool_coverage.role.game_level_starts_supported.count, len(rows),
        "Existing adapter capability for explicit game-level starter status is unverified; season-level starts do not prove the current lineup.",
    )
    add_gap(
        "SOURCE_CONTRACT_UNVERIFIED", "Acquisition and matchup context",
        int(not acquisition_available), 1,
        "Current priority, weekly adds, claim timing, matchup period, manager identity, and transaction history are not verified from persisted Yahoo evidence.",
    )
    unverified_claim_state = sum(row.availability in {"unknown", "unrostered"} for row in candidates)
    add_gap(
        "SOURCE_CONTRACT_UNVERIFIED", "Free-agent vs waiver-claim state",
        unverified_claim_state, len(candidates),
        "Absence from fresh league rosters is labeled unrostered; it does not establish current free-agent status or waiver-claim timing.",
    )
    return coverage, gaps


def has_open_slot(ctx: Context) -> bool:
    count = ctx.non_injury_roster_count if ctx.non_injury_roster_count is not None else len(ctx.roster_ids)
    return ctx.roster_ready and ctx.capacity is not None and count < ctx.capacity


def roster_components(ctx: Context, roster: list[Candidate], keys: list[str]) -> Components:
    values: dict[str, float | None] = {}
    for key in keys:
        measured = [getattr(player.components, key) for player in roster]
        values[key] = coverage(roster, ctx.slots) if key == "roster_fit" else (
            mean(measured) if measured and all(value is not None for value in measured) else None
        )
    return Components(**values)


def compare(ctx: Context, player: Candidate, drop_id: int | None) -> DropOption:
    if drop_id is not None and drop_id not in ctx.roster_ids:
        raise HTTPException(422, "Drop player must belong to the configured manager roster")
    roster = [ctx.players[pid] for pid in ctx.roster_ids]
    after = [row for row in roster if row.player_id != drop_id] + [player]
    # A fixed common mask and normalization basis is used on BOTH sides of a swap.
    keys = ctx.comparison_keys if ctx.comparison_keys is not None else [
        key for key in COMPONENTS if ctx.weights[key] > 0
        and all(row.components.model_dump()[key] is not None for row in [*roster, player])
    ]
    before_total = roster_components(ctx, roster, keys)
    after_total = roster_components(ctx, after, keys)
    before_score = after_score = net = None
    deltas = Components()
    effective: dict[str, float] = {}
    if ctx.roster_ready and player.eligible and {"roster_fit", "player_value"} <= set(keys):
        before_values, after_values = before_total.model_dump(), after_total.model_dump()
        if all(before_values[key] is not None and after_values[key] is not None for key in keys):
            denominator = sum(ctx.weights[key] for key in keys)
            effective = {key: ctx.weights[key] / denominator for key in keys}
            before_score = round(sum(before_values[key] * effective[key] for key in keys), 6)
            after_score = round(sum(after_values[key] * effective[key] for key in keys), 6)
            net = round(after_score - before_score, 6)
            deltas = Components(**{key: round(after_values[key] - before_values[key], 6) for key in keys})
    return DropOption(
        player_id=drop_id, player_name=ctx.players[drop_id].player_name if drop_id is not None else "No drop (open roster slot)",
        before_score=before_score, after_score=after_score, net_improvement=net,
        component_deltas=deltas,
        component_before=before_total, component_after=after_total, effective_weights=effective,
        starting_slots_before=matched_slots(roster, ctx.slots) if coverage(roster, ctx.slots) is not None else None,
        starting_slots_after=matched_slots(after, ctx.slots) if coverage(after, ctx.slots) is not None else None,
        starting_slots_required=len(ctx.slots) or None,
        reasons=[
            "Before/after scores are 0-100 roster indices: mean player components, with positional fit measured once as the percentage of starting slots coverable.",
            "Both sides use the same weights and fixed league production percentiles. Fully covered lineups receive no extra fit gain from reassignment.",
            f"Common measured components: {', '.join(keys)}.",
            "Net improvement is a model-index difference, not a forecast of fantasy points.",
        ] if net is not None else ["Swap impact unavailable: fresh manager roster, positional eligibility and supported player values for every roster member are required."],
    )


def enrich(ctx: Context, player: Candidate, drop_id: int | None = None) -> Candidate:
    result = player.model_copy(update={"reasons": list(player.reasons)})
    options = [compare(ctx, player, pid) for pid in ([drop_id] if drop_id is not None else ctx.roster_ids)]
    options.sort(key=lambda row: (row.net_improvement is None, -(row.net_improvement or 0), row.player_id))
    result.best_drop_options = options[:3]
    result.comparison = options[0] if drop_id is not None else compare(ctx, player, None) if has_open_slot(ctx) else next(iter(options), None)
    result.net_improvement = result.comparison.net_improvement if result.comparison else None
    selected = ctx.players.get(result.comparison.player_id) if result.comparison else None
    blockers = []
    status_unverified = False
    for key in ("settings", "roster"):
        if ctx.quality.get(key) is None or ctx.quality[key].state != "available":
            blockers.append(f"{key} evidence is missing or stale")
    compared = [result] + ([selected] if selected else [])
    for row in compared:
        if not identity_is_supported(row):
            blockers.append(f"{row.player_name}: Yahoo-to-NBA identity is unresolved; NBA-derived evidence is not decision-eligible")
        status = row.data_quality.get("status")
        status_unverified = status_unverified or (
            not status_is_supported(row.yahoo_status)
            or not row.yahoo_status
            or status is None
            or status.state in {"missing", "stale", "unknown", "unavailable"}
            or freshness(status.as_of, ctx.now) != "available"
        )
        for key in (("recent", "ros") if ctx.mode == "ros" else ("recent",)):
            if row.data_quality.get(key) is None or row.data_quality[key].state != "available":
                blockers.append(f"{row.player_name}: {key} evidence is missing, incomplete or stale")
    if result.data_quality.get("availability") is None or result.data_quality["availability"].state != "available":
        blockers.append("fresh availability evidence is required")
    if not result.eligible or result.overall_score is None or not ctx.roster_ready or result.net_improvement is None or blockers:
        result.recommended_action = "INSUFFICIENT EVIDENCE"
        result.reasons.extend(blockers)
    elif result.net_improvement <= 0:
        if status_unverified:
            result.recommended_action = "INSUFFICIENT EVIDENCE"
            result.reasons.append("Current Yahoo status is unknown, unrecognized or stale; strong recommendations are blocked.")
        else:
            result.recommended_action = "PASS"
    elif not sufficient_sample(result, ctx.mode) or (selected and not sufficient_sample(selected, ctx.mode)):
        result.recommended_action = "WATCH" if result.current_season_games > 0 else "INSUFFICIENT EVIDENCE"
        result.reasons.append("Below seven supported current-season games: discovery only; prior history cannot bypass the sample gate.")
    elif status_unverified:
        result.recommended_action = "INSUFFICIENT EVIDENCE"
        result.reasons.append("Current Yahoo status is unverified; strong recommendations are blocked.")
    else:
        comparison = result.comparison
        gains = {key: max(0, getattr(comparison.component_deltas, key) or 0) * weight
            for key, weight in comparison.effective_weights.items()}
        short_term = ctx.mode != "ros" and (
            result.hold_type == "streamer" or
            gains.get("schedule", 0) + gains.get("opportunity", 0) > gains.get("player_value", 0) + gains.get("roster_fit", 0)
        )
        role_supported = all(
            row.opportunity.current_role is not None
            and row.opportunity.current_role.quality.state == "available"
            and row.opportunity.current_role.trend != "INSUFFICIENT EVIDENCE"
            and freshness(row.opportunity.current_role.quality.as_of, ctx.now, 7) == "available"
            for row in compared
        )
        opportunity_material = gains.get("opportunity", 0) > sum(
            value for key, value in gains.items() if key != "opportunity")
        if short_term:
            schedule_quality = result.data_quality.get("schedule")
            opportunity_quality = result.data_quality.get("opportunity")
            result.recommended_action = "STREAM" if (
                schedule_quality is not None and schedule_quality.state in {"available", "partial"}
                and freshness(schedule_quality.as_of, ctx.now, 7) == "available"
                and result.schedule.games_remaining is not None
                and opportunity_quality is not None and opportunity_quality.state == "available"
                and freshness(opportunity_quality.as_of, ctx.now, 7) == "available"
                and result.opportunity.minutes is not None
                and role_supported
            ) else "INSUFFICIENT EVIDENCE"
            if result.recommended_action == "INSUFFICIENT EVIDENCE":
                result.reasons.append("Schedule/opportunity-driven swaps require fresh measured schedule and qualified role evidence for both players for STREAM.")
        elif opportunity_material and not role_supported:
            result.recommended_action = "INSUFFICIENT EVIDENCE"
            result.reasons.append("Opportunity materially drives this swap; qualified fresh role evidence for both players is required.")
        else:
            result.recommended_action = "ADD"
    return result


def transaction_blockers(ctx: Context, add: Candidate, drop: Candidate) -> list[str]:
    blockers = []
    if not ctx.roster_ready:
        blockers.append("Manager roster is unavailable or stale")
    for key in ("settings", "roster"):
        if key not in ctx.quality or ctx.quality[key].state != "available":
            blockers.append(f"{key} evidence is missing or stale")
    if not add.eligible:
        blockers.append("Add availability or Yahoo status excludes recommendation")
    if add.data_quality.get("availability") is None or add.data_quality["availability"].state != "available":
        blockers.append("Fresh add availability is unverified")
    for row in (add, drop):
        if not identity_is_supported(row):
            blockers.append(f"{row.player_name}: Yahoo-to-NBA identity is unresolved")
        if not sufficient_sample(row, ctx.mode):
            blockers.append("Insufficient fresh current-season sample for add or drop")
        for key in (("recent", "ros") if ctx.mode == "ros" else ("recent",)):
            if key not in row.data_quality or row.data_quality[key].state != "available":
                blockers.append("Required production evidence is missing, incomplete or stale")
        status = row.data_quality.get("status")
        if not status_is_supported(row.yahoo_status) or not row.yahoo_status or status is None or status.state in {"missing", "stale", "unknown", "unavailable"} or freshness(status.as_of, ctx.now) != "available":
            blockers.append("Add or drop Yahoo status is unknown, unrecognized or stale")
    return sorted(set(blockers))


def analyze_transactions(ctx: Context) -> TransactionAnalysis:
    supported: list[SwapAnalysis] = []
    watch: list[SwapAnalysis] = []
    excluded_reasons: Counter[str] = Counter()
    evaluated = excluded = 0
    adds = [row for row in ctx.players.values()
        if row.availability in {"free_agent", "waivers", "unrostered", "unknown"}]
    for add in sorted(adds, key=lambda row: row.player_id):
        for drop_id in sorted(ctx.roster_ids):
            evaluated += 1
            drop = ctx.players[drop_id]
            pair = enrich(ctx, add, drop_id)
            blockers = transaction_blockers(ctx, pair, drop)
            comparison = pair.comparison
            if comparison is None or comparison.net_improvement is None:
                blockers.append("Numeric swap impact is unavailable")
            if pair.recommended_action == "INSUFFICIENT EVIDENCE":
                blockers.append("Phase-1 decision is INSUFFICIENT EVIDENCE")
            is_supported = not blockers and pair.recommended_action in {"ADD", "STREAM", "MUST ADD", "PASS"}
            if not is_supported:
                excluded += 1
                excluded_reasons.update(set(blockers) or {"Phase-1 evidence does not support a strong transaction"})
            if comparison is None:
                continue
            if is_supported or (pair.recommended_action == "WATCH" and comparison.net_improvement is not None and comparison.net_improvement > 0):
                swap = SwapAnalysis(add_player=pair, drop_player=drop, mode=ctx.mode,
                    decision=pair.recommended_action, comparison=comparison,
                    reasons=list(dict.fromkeys(pair.reasons + comparison.reasons + blockers)),
                    limitations=list(dict.fromkeys(BASE_LIMITATIONS + drop.limitations)))
                (supported if is_supported else watch).append(swap)
    def order(swap: SwapAnalysis) -> tuple[float, int, int]:
        return (-(swap.comparison.net_improvement or 0), swap.add_player.player_id, swap.drop_player.player_id)
    supported.sort(key=order)
    watch.sort(key=order)
    best = next((swap for swap in supported if swap.comparison.net_improvement > 0
        and swap.decision in {"ADD", "STREAM", "MUST ADD"}), None)
    settings_quality = ctx.quality["settings"]
    rules = verify_league_contract(ctx.league) if settings_quality.state == "available" else []
    decision_reasons = (
        list(dict.fromkeys(best.reasons))[:4]
        if best else ["No add/drop pair cleared all current evidence gates."]
    )
    if best is None:
        decision_reasons.extend(
            f"{reason} ({count} pairs)." for reason, count in
            sorted(excluded_reasons.items(), key=lambda item: (-item[1], item[0]))[:2]
        )
        if watch:
            decision_reasons.append(
                "Positive WATCH comparisons remain below the supported recommendation threshold."
            )
        decision_reasons = decision_reasons[:4]
    return TransactionAnalysis(league_key=ctx.league.league_key, team_key=ctx.team_key,
        mode=ctx.mode, generated_at=ctx.now, model_version="waiver-evidence-phase3",
        decision=best.decision if best else "HOLD", decision_reasons=decision_reasons,
        best_transaction=best, top_supported_transactions=supported[:5],
        watch_transactions=watch[:5], evaluated_pair_count=evaluated,
        supported_pair_count=len(supported), watch_pair_count=len(watch),
        excluded_pair_count=excluded, excluded_pair_reasons=dict(sorted(excluded_reasons.items())),
        data_quality=ctx.quality,
        acquisition_context=AcquisitionContext(rules=rules, data_quality=settings_quality),
        limitations=BASE_LIMITATIONS + [
            "Hypothetical add/drop analysis only; no Yahoo transaction is executed.",
            "Excluded pairs are excluded from the supported pool; WATCH is a separate subset. Exclusion reason counts can overlap.",
            "Top supported and WATCH lists are limited to five pairs each; all pairs are evaluated.",
        ])


async def get_transactions(session: AsyncSession, league_key: str, team_key: str, mode: Mode) -> TransactionAnalysis:
    return analyze_transactions(await load_context(session, league_key, team_key, mode))


async def load_context(session: AsyncSession, league_key: str, team_key: str, mode: Mode) -> Context:
    now = datetime.now(timezone.utc)
    league = await session.get(League, league_key)
    if league is None:
        raise HTTPException(404, "Persisted Yahoo league was not found")
    verify_league_contract(league)
    baselines = await list_roster_baselines(session, league_key)
    manager = next(((team, roster) for team, roster in baselines if team.team_key == team_key), None)
    if manager is None:
        raise HTTPException(404, "Team does not belong to the selected Yahoo league")
    team, roster = manager
    settings = league.settings
    settings_state = freshness(settings.imported_at, now) if settings else "missing"
    fields = scoring_fields(settings.scoring_settings) if settings_state == "available" else None
    roster_state = roster_data_status(team, roster)
    if roster_state == "available":
        roster_state = freshness(roster.imported_at, now)
    ready = roster_state == "available"
    all_rosters_ready = bool(baselines) and all(
        row is not None and roster_data_status(owner, row) == "available"
        and freshness(row.imported_at, now) == "available" for owner, row in baselines
    )
    rostered_ids = {
        entry.player_identity_id for _, row in baselines if row for entry in row.roster_entries
    }
    manager_ids = [entry.player_identity_id for entry in roster.roster_entries] if roster else []
    observations = list((await session.execute(
        select(LeaguePlayer, PlayerIdentity).join(PlayerIdentity, LeaguePlayer.player_identity_id == PlayerIdentity.id)
        .where(LeaguePlayer.league_key == league_key).order_by(PlayerIdentity.id)
    )).all())
    identities = {
        identity.id: (identity, observation.source_payload, observation.imported_at)
        for observation, identity in observations
    }
    yahoo_pool_ids = set(identities)
    if roster:
        for entry in roster.roster_entries:
            observed = identities.get(entry.player_identity_id)
            if observed is None:
                identities[entry.player_identity_id] = (
                    entry.identity, entry.source_payload, entry.imported_at,
                )
                continue
            identity, player_pool_payload, player_pool_imported_at = observed
            roster_payload = {**player_pool_payload, **entry.source_payload}
            for key in ("status", "status_full"):
                if key in player_pool_payload:
                    roster_payload[key] = player_pool_payload[key]
            identities[entry.player_identity_id] = (
                identity, roster_payload, player_pool_imported_at,
            )
    nba_ids = {identity.nba_player_id for identity, _, _ in identities.values() if identity.nba_player_id}
    today = now.astimezone(WAIVER_TIMEZONE).date()
    season_year = league.season or today.year
    season = f"{season_year}-{str(season_year + 1)[-2:]}"
    window_end = window_end_date(today, season_year, mode)
    stats_rows = list((await session.scalars(
        select(NbaPlayerSeasonStats).where(NbaPlayerSeasonStats.nba_player_id.in_(nba_ids),
            NbaPlayerSeasonStats.season_type == "Regular Season", NbaPlayerSeasonStats.games_played > 0,
            NbaPlayerSeasonStats.season <= season)
    )).all())
    stats_by_id: dict[str, NbaPlayerSeasonStats] = {}
    prior_by_id: dict[str, NbaPlayerSeasonStats] = {}
    for row in sorted(stats_rows, key=lambda row: row.season):
        stats_by_id[row.nba_player_id] = row
        if row.season < season:
            prior_by_id[row.nba_player_id] = row
    logs = list((await session.scalars(select(PlayerGameLog).where(
        PlayerGameLog.nba_player_id.in_(nba_ids), PlayerGameLog.season == season,
        PlayerGameLog.season_type == "Regular Season",
        PlayerGameLog.game_date >= today - timedelta(days=14), PlayerGameLog.game_date <= today,
    ).order_by(PlayerGameLog.game_date, PlayerGameLog.game_id))).all())
    logs_by_id: dict[str, list[PlayerGameLog]] = defaultdict(list)
    for log in logs:
        logs_by_id[log.nba_player_id].append(log)
    teams = list((await session.scalars(select(NbaTeam))).all())
    abbreviations = {row.nba_team_id: row.abbreviation for row in teams}
    nba_players = list((await session.scalars(select(NbaPlayer))).all())
    nba_players_by_id = {row.nba_player_id: row for row in nba_players}
    nba_players_by_name: dict[str, list[NbaPlayer]] = defaultdict(list)
    for row in nba_players:
        if key := _name_key(row.player_name):
            nba_players_by_name[key].append(row)
    schedule_rows = list((await session.scalars(select(PlayerSchedule).where(
        PlayerSchedule.nba_player_id.in_(nba_ids), PlayerSchedule.season == season,
    ).order_by(PlayerSchedule.game_date, PlayerSchedule.game_id))).all())
    schedules_by_id: dict[str, list[PlayerSchedule]] = defaultdict(list)
    for row in schedule_rows:
        schedules_by_id[row.nba_player_id].append(row)
    games = list((await session.scalars(select(NbaGame).where(
        NbaGame.season == season, NbaGame.game_date >= today, NbaGame.game_date <= window_end,
    ).order_by(NbaGame.game_date, NbaGame.game_id))).all())
    games = [row for row in games if not any(word in (row.game_status or "").lower() for word in ("postpon", "cancel", "final"))]
    daily_games = Counter(row.game_date for row in games)
    slots: list[str] = []
    capacity = 0
    positions_valid = settings_state == "available" and bool(settings.roster_positions)
    for slot in settings.roster_positions if settings else []:
        position = str(slot.get("position") or "").upper()
        count = _numeric(slot.get("count"))
        if count is None or count < 0 or not count.is_integer():
            positions_valid = False
            continue
        if position not in {"IL", "IL+", "IR", "IR+"}:
            capacity += int(count)
        if slot_positions(position) and str(slot.get("is_starting_position", 1)) != "0":
            slots.extend([position] * int(count))
    if not positions_valid:
        slots = []
    quality = {
        "league": evidence(freshness(league.imported_at, now), "Yahoo league", league.imported_at, f"Imported league season: {league.season}. Missing season uses the current Pacific year only as a historical-data cutoff."),
        "roster": evidence("missing" if roster_state == "not_imported" else roster_state, "Yahoo rosters", roster.imported_at if roster else None, "Manager roster must be imported and refreshed within 24 hours; later league/team/settings imports invalidate older snapshots."),
        "settings": evidence(settings_state, "Yahoo settings", settings.imported_at if settings else None, "Scoring modifiers and roster slots must have been imported within 24 hours."),
        "availability": evidence("available" if all_rosters_ready else "partial", "Yahoo rosters", min((row.imported_at for _, row in baselines if row), default=None), "Absence means available only when every league team has a fresh imported roster."),
        "category_scoring": evidence("unsupported", "Waiver model", None, "Category waiver scoring is not implemented; existing category baselines remain available in Championship HQ."),
        "acquisition_value": evidence("missing", "Yahoo rolling waivers", None, "Current rolling priority and transaction evidence are unverified; excluded from all scores."),
    }
    players: dict[int, Candidate] = {}
    mapping_worklist: list[MappingWorklistItem] = []
    for pid, (identity, payload, imported_at) in identities.items():
        raw_status_value = payload.get("status")
        raw_status = str(raw_status_value) if raw_status_value is not None else None
        status = (raw_status or "").strip().upper() or None
        position = _positions(payload) or identity.position
        yahoo_team = str(payload.get("editorial_team_abbr") or identity.team or "").strip().upper() or None
        ownership = payload.get("ownership")
        ownership_type = str(ownership.get("ownership_type") or "").lower() if isinstance(ownership, dict) else ""
        availability = "unknown"
        availability_detail = "No fresh affirmative Yahoo availability evidence."
        availability_as_of = imported_at
        if pid in rostered_ids or ownership_type == "team":
            availability = "rostered"
            availability_detail = "Present in a persisted Yahoo league roster or Yahoo team ownership."
        elif freshness(imported_at, now) == "available" and ownership_type in {"freeagents", "waivers"}:
            availability = "free_agent" if ownership_type == "freeagents" else "waivers"
            availability_detail = f"Persisted Yahoo ownership_type={ownership_type}."
        elif all_rosters_ready and freshness(imported_at, now) == "available":
            availability = "unrostered"
            availability_as_of = min(row.imported_at for _, row in baselines if row)
            availability_detail = "Absent from every fresh imported Yahoo league roster; free-agent vs waiver-claim timing is unknown."
        recent_logs = logs_by_id.get(identity.nba_player_id, [])
        recent_stats = log_average(recent_logs)
        historical = stats_by_id.get(identity.nba_player_id)
        historical_stats = numeric_stats(historical.base_stats) if historical else {}
        recent = ValueEvidence(value=production(recent_stats, fields), games=len(recent_logs), season=season,
            per_game_stats=recent_stats, label="Last 14 calendar days of persisted regular-season NBA games; points per game under Yahoo rules",
            sample_label=sample_label(len(recent_logs)))
        ros = ValueEvidence(value=production(historical_stats, fields), games=historical.games_played if historical else 0,
            season=historical.season if historical else None, per_game_stats=historical_stats,
            label="Season Evidence: persisted regular-season historical fantasy points per game; not a projection",
            sample_label=sample_label(historical.games_played if historical else 0))
        for value_evidence in (recent, ros):
            value_evidence.scoring_weights = fields or {}
            if value_evidence.value is not None and fields:
                value_evidence.scoring_contributions = {
                    field: value_evidence.per_game_stats[field] * weight
                    for field, weight in fields.items() if weight != 0
                }
        current_games = historical.games_played if historical and historical.season == season else len(recent_logs)
        opportunity = current_role(recent_logs, historical, season, now, today)
        role = opportunity.current_role
        nba_player = nba_players_by_id.get(identity.nba_player_id) if identity.nba_player_id else None
        nba_team = (
            (abbreviations.get(nba_player.team_id) if nba_player and nba_player.team_id else None)
            or (nba_player.team_abbreviation if nba_player else None)
        )
        mapping_state, mapping_reason, potential_matches = identity_mapping(
            identity, nba_player, nba_players_by_name, abbreviations, yahoo_team,
        )
        if mapping_state not in {"EXACT_ID", "EXACT_NAME_TEAM", "NORMALIZED_NAME_TEAM", "KNOWN_ALIAS_TEAM", "TEAM_CHANGE_SUPPORTED"}:
            mapping_worklist.append(MappingWorklistItem(
                internal_id=pid,
                yahoo_player_id=identity.yahoo_player_id,
                yahoo_name=identity.player_name,
                yahoo_team=yahoo_team,
                normalized_name=_name_key(identity.player_name),
                potential_nba_matches=potential_matches,
                conflict_reason=mapping_reason,
                resolution_state=mapping_state,
            ))
        player_schedule = schedules_by_id.get(identity.nba_player_id, []) if identity.nba_player_id else []
        schedule = resolve_schedule(
            player_schedule, today, window_end, now, daily_games, abbreviations,
            nba_mapped=bool(identity.nba_player_id and nba_player),
            team_mapped=bool(nba_player and nba_player.team_id and nba_player.team_id in abbreviations),
        )
        schedule_as_of = schedule.imported_at
        mapping_diagnostic = identity_chain_diagnostic(
            yahoo_id=identity.yahoo_player_id,
            nba_id=identity.nba_player_id,
            nba_player_present=nba_player is not None,
            team_mapped=bool(nba_player and nba_player.team_id and nba_player.team_id in abbreviations),
            has_game_logs=bool(identity.nba_player_id and logs_by_id.get(identity.nba_player_id)),
            has_season_stats=bool(identity.nba_player_id and stats_by_id.get(identity.nba_player_id)),
            has_schedule_rows=bool(player_schedule),
            schedule_stale=schedule.freshness == "stale",
        )
        status_diagnostic = (
            "MISSING_PLAYER_OBSERVATION" if imported_at is None else
            "STALE_PLAYER_POOL_IMPORT" if freshness(imported_at, now) == "stale" else
            "YAHOO_SUPPLIED_BLANK" if status is None else
            "UNRECOGNIZED_STATUS" if not status_is_supported(status) else
            "STATUS_PRESENT"
        )
        recent_as_of = min((row.imported_at for row in recent_logs), default=None)
        recent_state = freshness(recent_as_of, now, 7)
        if recent_logs and max(row.game_date for row in recent_logs) < today - timedelta(days=7):
            recent_state = "stale"
        recent_quality_state = (
            "unsupported" if fields is None
            else "stale" if recent_state == "stale"
            else "available" if recent.value is not None
            else "missing"
        )
        season_freshness = freshness(historical.imported_at, now, 7) if historical else "missing"
        season_quality_state = (
            "unsupported" if fields is None
            else "stale" if season_freshness == "stale"
            else "available" if ros.value is not None
            else "missing"
        )
        value = ros if mode == "ros" else recent
        eligible = availability in {"free_agent", "waivers", "unrostered"} and recommendation_eligibility(status) != "excluded"
        quality_fields = {
            "identity": evidence("available" if mapping_state in {"EXACT_ID", "EXACT_NAME_TEAM", "NORMALIZED_NAME_TEAM", "KNOWN_ALIAS_TEAM", "TEAM_CHANGE_SUPPORTED"} else "partial", "Yahoo/NBA identity mapping", imported_at, mapping_reason),
            "status": Evidence(state="stale" if status_diagnostic == "STALE_PLAYER_POOL_IMPORT" else "unknown" if not status_is_supported(status) else "partial" if status in {"Q", "P"} else "available",
                source="Yahoo player import", as_of=imported_at, sample_count=1 if imported_at else 0,
                detail=(
                    "Yahoo supplied a blank status; blank is unknown, not healthy."
                    if status_diagnostic == "YAHOO_SUPPLIED_BLANK"
                    else "Status came from a stale player-pool import."
                    if status_diagnostic == "STALE_PLAYER_POOL_IMPORT"
                    else yahoo_status_reason(status)
                )),
            "availability": evidence("unknown" if availability == "unknown" else freshness(availability_as_of, now), "Yahoo ownership / rosters", availability_as_of, availability_detail),
            "recent": evidence(recent_quality_state, "NBA player_game_logs", recent_as_of,
                production_detail(recent_stats, fields, "Recent", len(recent_logs))),
            "ros": evidence(season_quality_state, "NBA season statistics", historical.imported_at if historical else None,
                production_detail(historical_stats, fields, "Season Evidence", historical.games_played if historical else 0)),
            "opportunity": Evidence(state=role.quality.state if opportunity.score is not None else "stale" if role.quality.state == "stale" else "unavailable",
                source="Persisted NBA role evidence", as_of=role.quality.as_of, sample_count=role.quality.sample_count,
                detail="Score requires qualified role windows: minutes level counted once, optional supported usage delta and explicit season start rate. No separate minutes-delta score."),
            "role": role.quality,
            "minutes": role.minutes.quality,
            "usage": role.usage.quality,
            "starts": role.starts.quality,
            "schedule": Evidence(state="stale" if schedule.coverage == "STALE" else "partial" if schedule.games_remaining is not None else "unavailable",
                source="NBA player schedule", as_of=schedule_as_of, sample_count=schedule.games_remaining or 0,
                detail=(
                    f"{schedule.diagnostic_reason}: {schedule.source_row_count} persisted player schedule rows; requested-window zero is not asserted because source completeness is unverified."
                    if schedule.diagnostic_reason == "SCHEDULE_SOURCE_INCOMPLETE"
                    else "No completeness manifest: coverage PARTIAL with rows, UNKNOWN without rows, never COMPLETE. Off-day means at most five persisted NBA games that date. Opponents are identities, not difficulty estimates."
                )),
            "roster_fit": quality["roster"],
            "acquisition_value": quality["acquisition_value"],
        }
        ranking = RankingEvidence(label="Historical Season Evidence per-game value, not a projection" if mode == "ros" else "Recent per-game value; no supported independent prior-season history")
        if quality_fields["ros" if mode == "ros" else "recent"].state != "available":
            value_score = None
        else:
            value_score = value.value
            if mode != "ros":
                ranking.recent_weight = 1.0
                prior = prior_by_id.get(identity.nba_player_id)
                prior_value = production(numeric_stats(prior.base_stats), fields) if prior else None
                if prior is not None and prior_value is not None and recent.value is not None and freshness(prior.imported_at, now, 7) == "available":
                    # Ten historical-equivalent games shrink small samples without forecasting.
                    weight = recent.games / (recent.games + 10)
                    value_score = weight * recent.value + (1 - weight) * prior_value
                    ranking = RankingEvidence(recent_weight=weight, historical_value=prior_value,
                        historical_games=prior.games_played, historical_season=prior.season,
                        label="Descriptive blend: recent PPG weighted n/(n+10), independent prior-season PPG weighted 10/(n+10); not a projection or calibrated confidence")
        ranking.value = value_score
        players[pid] = Candidate(
            player_id=pid, yahoo_player_id=identity.yahoo_player_id, player_name=identity.player_name,
            position=position, yahoo_team=yahoo_team, nba_team=nba_team,
            raw_yahoo_status=raw_status, yahoo_status=status,
            identity_mapping_state=mapping_state, identity_mapping_reason=mapping_reason,
            mapping_diagnostic=mapping_diagnostic, status_diagnostic=status_diagnostic,
            availability=availability, eligible=eligible,
            recent=recent, ros=ros, opportunity=opportunity, schedule=schedule,
            ranking_value=ranking,
            components=Components(player_value=value_score, opportunity=opportunity.score),
            recommended_action="INSUFFICIENT EVIDENCE", hold_type="undetermined",
            current_season_games=current_games, evidence_quality=sample_label(current_games),
            reasons=[yahoo_status_reason(status), availability_detail],
            limitations=list(BASE_LIMITATIONS), data_quality=quality_fields,
        )
    value_distribution = [row.components.player_value for row in players.values() if row.components.player_value is not None]
    schedule_distribution = [row.schedule.games_remaining for row in players.values() if row.schedule.games_remaining is not None and row.data_quality["schedule"].state != "stale"]
    weights = validated_weights(get_settings().waiver_weights)
    ctx = Context(league, team_key, mode, now, players, manager_ids, slots,
        capacity if positions_valid else None, ready, weights, quality, mapping_worklist,
        pool_ids=yahoo_pool_ids)
    if roster:
        ctx.non_injury_roster_count = sum((entry.roster_position or "").upper() not in {"IL", "IL+", "IR", "IR+"} for entry in roster.roster_entries)
    manager_roster = [players[pid] for pid in manager_ids]
    historical_distribution = [row.ros.value for row in players.values()
        if row.ros.value is not None and row.data_quality["ros"].state == "available"]
    for player in players.values():
        player.components.player_value = percentile(player.components.player_value, value_distribution)
        player.components.schedule = percentile(player.schedule.games_remaining, schedule_distribution) if player.data_quality["schedule"].state != "stale" else None
        player.components.roster_fit = roster_fit(player, manager_roster, slots) if ready else None
        player.overall_score, player.effective_weights = aggregate(player.components, weights)
        player.data_quality["overall_score"] = evidence("partial" if player.overall_score is not None else "missing", "Waiver model", now, "Missing components are omitted and measured weights renormalized; a supported player value and roster fit are mandatory.")
        player.data_quality["roster_fit"] = evidence("available" if player.components.roster_fit is not None else "missing", "Yahoo positions / manager roster", roster.imported_at if roster else None, "Positional slot coverage only; replacement value is measured by the before/after swap model. Category fit is unavailable.")
        player.reasons.append(f"Starting-slot coverage with player: {player.components.roster_fit}/100; eligibility coverage is not player quality.")
        selected_value = player.ros if mode == "ros" else player.recent
        player.reasons.append(f"{selected_value.sample_label}: {selected_value.games} games. No predictive superiority is established.")
        player.reasons.append(player.ranking_value.label)
        player.reasons.append(
            f"{'Season Evidence' if mode == 'ros' else 'Recent'} Yahoo-rule value: {selected_value.value} fantasy points/game from {selected_value.games} persisted games, season {selected_value.season}; not a projection."
            if selected_value.value is not None else "Player value unavailable: supported Yahoo points modifiers and complete persisted production are required."
        )
        player.reasons.append(
            f"Persisted schedule: {player.schedule.games_remaining} games, {player.schedule.off_day_games} off-day games; coverage is partial."
            if player.schedule.games_remaining is not None else "Schedule is unknown; no zero-game assumption is made."
        )
        if player.opportunity.minutes is not None:
            player.reasons.append(f"Measured recent minutes/game: {player.opportunity.minutes:.1f}; current role: {player.opportunity.role.lower()}.")
        player.reasons.extend([
            f"Current role evidence: {player.opportunity.role}. {role_detail}"
            for role_detail in [
                player.opportunity.current_role.minutes.quality.detail,
                player.opportunity.current_role.usage.quality.detail,
                player.opportunity.current_role.starts.quality.detail,
            ]
        ])
        if player.opportunity.minutes_trend is not None:
            player.reasons.append(f"Minutes changed by {player.opportunity.minutes_trend:+.2f} over the measured three-game windows.")
        if player.opportunity.usage_trend is not None:
            player.reasons.append(f"Usage changed by {player.opportunity.usage_trend * 100:+.2f} percentage points over the measured windows.")
        historical_percentile = percentile(player.ros.value, historical_distribution)
        if sufficient_sample(player, mode) and player.data_quality["ros"].state == "available" and historical_percentile is not None and historical_percentile >= 60 and player.ros.games >= 20 and player.components.opportunity is not None and player.opportunity.minutes is not None and player.opportunity.minutes >= 24:
            player.hold_type = "longer_term_hold"
        elif sufficient_sample(player, mode) and mode != "ros" and player.components.schedule is not None and player.components.schedule >= 60 and player.data_quality["schedule"].state in {"available", "partial"} and player.data_quality["opportunity"].state == "available" and player.components.opportunity is not None and player.components.player_value is not None and player.opportunity.minutes_trend is not None and player.opportunity.minutes_trend > 0:
            player.hold_type = "streamer"
        player.reasons.append(f"Hold classification: {player.hold_type}; a descriptive evidence label, not a future role prediction.")
    comparable = manager_roster + [row for row in players.values()
        if row.eligible and row.components.player_value is not None and row.components.roster_fit is not None]
    ctx.comparison_keys = [key for key in COMPONENTS if weights[key] > 0
        and comparable and all(getattr(row.components, key) is not None for row in comparable)]
    return ctx


async def get_waivers(session: AsyncSession, league_key: str, team_key: str, mode: Mode, drop_id: int | None = None) -> WaiverBoard:
    ctx = await load_context(session, league_key, team_key, mode)
    if drop_id is not None and drop_id not in ctx.roster_ids:
        raise HTTPException(422, "Drop player must belong to the configured manager roster")
    candidates = [enrich(ctx, row, drop_id) for row in ctx.players.values() if row.availability in {"free_agent", "waivers", "unrostered"} and row.eligible]
    candidates.sort(key=lambda row: (row.net_improvement is None, -(row.net_improvement or 0), row.player_id)
        if drop_id is not None else (row.overall_score is None, -(row.overall_score or 0), row.player_id))
    scored = [row for row in candidates if row.overall_score is not None]
    best_overall = max((row for row in candidates if row.components.player_value is not None),
        key=lambda row: (row.components.player_value, -row.player_id), default=None)
    actionable = [row for row in scored if row.recommended_action in {"ADD", "STREAM", "MUST ADD"}
        and row.net_improvement is not None and row.net_improvement > 0]
    top_measured = max((row for row in scored if row.net_improvement is not None),
        key=lambda row: (row.net_improvement, row.overall_score, -row.player_id), default=None)
    best_add = max(actionable, key=lambda row: (row.net_improvement, row.overall_score, -row.player_id), default=None)
    manager = [ctx.players[pid] for pid in ctx.roster_ids]
    for player in manager:
        supported = [compare(ctx, row, player.player_id) for row in ctx.players.values() if row.eligible]
        measured = [option.net_improvement for option in supported if option.net_improvement is not None]
        if ctx.roster_ready and measured:
            player.roster_decision = "review_replacement" if any(
                enrich(ctx, row, player.player_id).recommended_action in {"ADD", "STREAM", "MUST ADD"}
                for row in ctx.players.values() if row.eligible
            ) else "keep_on_measured_model" if max(measured) <= 0 else "unavailable"
    needs = [
        f"{matched_slots(manager, ctx.slots)} of {len(ctx.slots)} starting slots can be covered by the imported positional eligibility (not a daily lineup optimizer).",
        "Category needs unavailable in waiver scoring; see persisted category baselines in Championship HQ.",
    ] if ctx.roster_ready and ctx.slots else ["Team needs unavailable until a fresh manager roster and Yahoo roster slots are imported."]
    coverage, data_gaps = board_coverage(ctx)
    return WaiverBoard(
        league_key=league_key, team_key=team_key, mode=mode, generated_at=ctx.now, weights=ctx.weights,
        best_overall_available_id=best_overall.player_id if best_overall else None,
        best_add_for_team_id=best_add.player_id if best_add else None, team_needs=needs, candidates=candidates,
        top_measured_candidate_id=top_measured.player_id if top_measured else None,
        roster=manager, selected_drop_player_id=drop_id,
        waiver_rules=verify_league_contract(ctx.league) if ctx.quality["settings"].state == "available" else [],
        selected_player_result=(
            f"HOLD {ctx.players[drop_id].player_name}" if drop_id is not None and top_measured and top_measured.net_improvement <= 0
            else best_add.recommended_action if best_add
            else "WATCH" if any(row.recommended_action == "WATCH" for row in candidates)
            else "INSUFFICIENT EVIDENCE"
        ),
        excluded_count=sum(row.availability in {"free_agent", "waivers", "unrostered"} and not row.eligible for row in ctx.players.values()),
        unknown_availability_count=sum(row.availability == "unknown" for row in ctx.players.values()),
        limitations=BASE_LIMITATIONS, data_quality=ctx.quality,
        coverage=coverage, data_gaps=data_gaps,
    )


async def get_impact(session: AsyncSession, league_key: str, team_key: str, player_id: int, drop_id: int | None, mode: Mode) -> WaiverImpact:
    ctx = await load_context(session, league_key, team_key, mode)
    player = ctx.players.get(player_id)
    if player is None:
        raise HTTPException(404, "Player is not in the persisted Yahoo league pool")
    if player.availability == "rostered":
        raise HTTPException(409, "Player is already rostered in the selected league")
    if drop_id is not None and drop_id not in ctx.roster_ids:
        raise HTTPException(422, "Drop player must belong to the selected manager roster")
    candidate = enrich(ctx, player, drop_id)
    comparison = compare(ctx, player, drop_id) if drop_id is not None else compare(ctx, player, None) if has_open_slot(ctx) else next(iter(candidate.best_drop_options), None)
    return WaiverImpact(league_key=league_key, team_key=team_key, mode=mode,
        model_version="waiver-evidence-phase3",
        candidate=candidate, comparison=comparison, limitations=BASE_LIMITATIONS)

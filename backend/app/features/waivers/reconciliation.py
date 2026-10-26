"""Read-only reconciliation of persisted Yahoo waiver evidence and NBA statistics."""

import argparse
import asyncio
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

REQUIRED_STATS = ("PTS", "REB", "AST", "STL", "BLK", "TOV")
FORMULA = {"PTS": 1.0, "REB": 1.2, "AST": 1.5, "BLK": 3.0, "STL": 3.0, "TOV": -1.0}
TOLERANCES = {"counting_stat": 0.05, "fantasy_ppg": 0.05, "minutes_per_game": 0.10}
ACCEPTANCE_NAMES = ("Keegan Murray", "Bilal Coulibaly", "Kris Dunn", "Jrue Holiday")
STAT_ALIASES = {
    "PTS": ("PTS", "POINTS"),
    "REB": ("REB", "REBOUNDS"),
    "AST": ("AST", "ASSISTS"),
    "STL": ("STL", "ST", "STEALS"),
    "BLK": ("BLK", "BLOCKS"),
    "TOV": ("TOV", "TO", "TURNOVERS"),
}


def normalize_identity(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ascii_name.casefold())


def numeric_stats(payload: Any) -> dict[str, float]:
    if not isinstance(payload, dict):
        return {}
    normalized = {str(key).strip().upper(): value for key, value in payload.items()}
    result: dict[str, float] = {}
    for field, aliases in STAT_ALIASES.items():
        for alias in aliases:
            raw_value = normalized.get(alias)
            if isinstance(raw_value, bool) or raw_value is None:
                continue
            try:
                result[field] = float(raw_value)
            except (TypeError, ValueError):
                continue
            break
    return result


def fantasy_ppg(stats: dict[str, float]) -> float | None:
    if any(field not in stats for field in REQUIRED_STATS):
        return None
    return sum(stats[field] * FORMULA[field] for field in REQUIRED_STATS)


def compare_overlapping_fields(
    left: dict[str, float],
    right: dict[str, float],
    fields: tuple[str, ...],
    tolerance: float,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    overlap = tuple(field for field in fields if field in left and field in right)
    mismatches = tuple(
        field for field in overlap
        if abs(left[field] - right[field]) > tolerance
    )
    return overlap, mismatches


def classify_mismatch(yahoo: dict[str, Any], nba: dict[str, Any], now: datetime) -> str | None:
    yahoo_name = normalize_identity(yahoo.get("player_name"))
    nba_name = normalize_identity(nba.get("player_name"))
    if not yahoo_name or yahoo_name != nba_name:
        return "IDENTITY_MAPPING_MISMATCH"
    yahoo_team = str(yahoo.get("team") or "").strip().upper()
    nba_team = str(nba.get("team") or "").strip().upper()
    if not yahoo_team or not nba_team:
        return "TEAM_MAPPING_UNVERIFIED"
    if yahoo_team != nba_team:
        return "TEAM_MAPPING_MISMATCH"
    if yahoo.get("season") and nba.get("season") and yahoo["season"] != nba["season"]:
        return "SEASON_MISMATCH"
    if yahoo.get("stat_type") and nba.get("stat_type") and yahoo["stat_type"] != nba["stat_type"]:
        return "STAT_TYPE_MISMATCH"
    if yahoo.get("definition") and nba.get("definition") and yahoo["definition"] != nba["definition"]:
        return "PROVIDER_DEFINITION_DIFFERENCE"
    if yahoo.get("games_played") is not None and nba.get("games_played") is not None:
        if yahoo["games_played"] != nba["games_played"]:
            return "GAME_SET_MISMATCH"
    yahoo_stats, nba_stats = yahoo.get("stats") or {}, nba.get("stats") or {}
    overlap, mismatches = compare_overlapping_fields(
        yahoo_stats, nba_stats, REQUIRED_STATS, TOLERANCES["counting_stat"],
    )
    if not overlap:
        return "NO_COMPARABLE_STAT_FIELDS"
    timestamps = [value for value in (yahoo.get("imported_at"), nba.get("imported_at")) if value]
    if any(now - value > timedelta(days=7) for value in timestamps):
        return "IMPORT_STALE"
    if yahoo.get("minutes_per_game") is not None and nba.get("minutes_per_game") is not None:
        if abs(yahoo["minutes_per_game"] - nba["minutes_per_game"]) > TOLERANCES["minutes_per_game"]:
            return "UNKNOWN"
    if mismatches:
        return "UNKNOWN"
    if len(overlap) != len(REQUIRED_STATS):
        return "PARTIAL_STAT_OVERLAP"
    yahoo_ppg, nba_ppg = fantasy_ppg(yahoo_stats), fantasy_ppg(nba_stats)
    if yahoo_ppg is None or nba_ppg is None:
        return "NO_COMPARABLE_STAT_FIELDS"
    if abs(yahoo_ppg - nba_ppg) > TOLERANCES["fantasy_ppg"]:
        return "UNKNOWN"
    if yahoo_stats != nba_stats or yahoo_ppg != nba_ppg:
        return "ROUNDING_ONLY"
    return None


def extract_yahoo_stats(payload: Any) -> dict[str, float]:
    if not isinstance(payload, dict):
        return {}
    for key in ("yahoo_stats", "player_stats", "stats"):
        stats = numeric_stats(payload.get(key))
        if stats:
            return stats
    return numeric_stats(payload)


async def build_report(league_key: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                league = (await connection.execute(text(
                    "SELECT season FROM leagues WHERE league_key = :league_key"
                ), {"league_key": league_key})).mappings().one_or_none()
                if league is None:
                    raise ValueError(f"Persisted league {league_key!r} was not found")
                season_year = int(league["season"] or now.year)
                season = f"{season_year}-{(season_year + 1) % 100:02d}"
                rows = (await connection.execute(text("""
                    SELECT p.yahoo_player_id, p.source_payload AS yahoo_payload,
                           p.imported_at AS yahoo_imported_at,
                           i.player_name, COALESCE(p.source_payload->>'editorial_team_abbr', i.team) AS yahoo_team,
                           i.nba_player_id,
                           n.player_name AS nba_player_name,
                           COALESCE(nt.abbreviation, n.team_abbreviation) AS nba_team,
                           n.imported_at AS nba_player_imported_at,
                           s.season AS stats_season, s.season_type AS stats_type,
                           s.games_played, s.minutes_per_game, s.base_stats,
                           s.imported_at AS stats_imported_at
                    FROM players p
                    JOIN player_identity i ON i.id = p.player_identity_id
                    LEFT JOIN players_nba n ON n.nba_player_id = i.nba_player_id
                    LEFT JOIN nba_teams nt ON nt.nba_team_id = n.team_id
                    LEFT JOIN LATERAL (
                        SELECT season, season_type, games_played, minutes_per_game,
                               base_stats, imported_at
                        FROM nba_player_season_stats
                        WHERE nba_player_id = i.nba_player_id
                          AND season_type = 'Regular Season'
                          AND season <= :season
                        ORDER BY season DESC
                        LIMIT 1
                    ) s ON TRUE
                    WHERE p.league_key = :league_key
                    ORDER BY lower(i.player_name), p.yahoo_player_id
                """), {"league_key": league_key, "season": season})).mappings().all()
                players = []
                classifications: dict[str, int] = {}
                comparable_count = 0
                stat_field_coverage = {
                    field: {"yahoo": 0, "nba": 0, "overlap": 0}
                    for field in REQUIRED_STATS
                }
                for row in rows:
                    yahoo_stats = extract_yahoo_stats(row["yahoo_payload"])
                    nba_stats = numeric_stats(row["base_stats"])
                    for field in REQUIRED_STATS:
                        if field in yahoo_stats:
                            stat_field_coverage[field]["yahoo"] += 1
                        if field in nba_stats:
                            stat_field_coverage[field]["nba"] += 1
                        if field in yahoo_stats and field in nba_stats:
                            stat_field_coverage[field]["overlap"] += 1
                    nba_ppg = fantasy_ppg(nba_stats)
                    yahoo = {
                        "player_name": row["player_name"],
                        "team": row["yahoo_team"],
                        "season": row["yahoo_payload"].get("season") if isinstance(row["yahoo_payload"], dict) else None,
                        "stat_type": row["yahoo_payload"].get("stat_type") if isinstance(row["yahoo_payload"], dict) else None,
                        "games_played": row["yahoo_payload"].get("games_played") if isinstance(row["yahoo_payload"], dict) else None,
                        "minutes_per_game": row["yahoo_payload"].get("minutes_per_game") if isinstance(row["yahoo_payload"], dict) else None,
                        "stats": yahoo_stats,
                        "imported_at": row["yahoo_imported_at"],
                    }
                    nba = {
                        "player_name": row["nba_player_name"],
                        "team": row["nba_team"],
                        "season": row["stats_season"],
                        "stat_type": row["stats_type"],
                        "games_played": row["games_played"],
                        "minutes_per_game": row["minutes_per_game"],
                        "stats": nba_stats,
                        "imported_at": row["stats_imported_at"],
                    }
                    cause = classify_mismatch(yahoo, nba, now) if row["nba_player_id"] and nba["player_name"] else (
                        "NBA_PLAYER_RECORD_MISSING" if row["nba_player_id"] else "IDENTITY_MAPPING_MISMATCH"
                    )
                    if (all(field in yahoo_stats and field in nba_stats for field in REQUIRED_STATS)
                        and cause in {None, "UNKNOWN", "ROUNDING_ONLY"}):
                        comparable_count += 1
                    if cause:
                        classifications[cause] = classifications.get(cause, 0) + 1
                    players.append({
                        "yahoo_player_id": row["yahoo_player_id"],
                        "player_name": row["player_name"],
                        "yahoo_team": row["yahoo_team"],
                        "nba_player_id": row["nba_player_id"],
                        "nba_player_name": row["nba_player_name"],
                        "nba_team": row["nba_team"],
                        "games_played": {"yahoo": yahoo["games_played"], "nba": nba["games_played"]},
                        "fantasy_points_total": {"yahoo": None, "nba": None},
                        "fantasy_ppg": {"yahoo": fantasy_ppg(yahoo_stats), "nba": nba_ppg},
                        "minutes_per_game": {"yahoo": yahoo["minutes_per_game"], "nba": nba["minutes_per_game"]},
                        "stats": {
                            field: {"yahoo": yahoo_stats.get(field), "nba": nba_stats.get(field)}
                            for field in REQUIRED_STATS
                        },
                        "source_season": {"yahoo": yahoo["season"], "nba": nba["season"]},
                        "source_stat_type": {"yahoo": yahoo["stat_type"], "nba": nba["stat_type"]},
                        "source_timestamps": {
                            "yahoo_player_import": row["yahoo_imported_at"].isoformat() if row["yahoo_imported_at"] else None,
                            "nba_player_import": row["nba_player_imported_at"].isoformat() if row["nba_player_imported_at"] else None,
                            "nba_stats_import": row["stats_imported_at"].isoformat() if row["stats_imported_at"] else None,
                        },
                        "classification": cause,
                    })
                available_names = {normalize_identity(row["player_name"]) for row in players}
                return {
                    "report_version": "waiver-stats-reconciliation-v2",
                    "generated_at": now.isoformat(),
                    "access": "persisted-only/read-only; no Yahoo or NBA provider calls",
                    "league_key": league_key,
                    "formula": "PTS + 1.2*REB + 1.5*AST + 3*BLK + 3*STL - TO (Yahoo TO -> NBA TOV)",
                    "tolerances": TOLERANCES,
                    "candidate_count": len(players),
                    "comparable_count": comparable_count,
                    "stat_field_coverage": stat_field_coverage,
                    "classification_counts": classifications,
                    "acceptance_fixture": {
                        name: name in available_names for name in ACCEPTANCE_NAMES
                    },
                    "players": players,
                }
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _main(league_key: str) -> None:
    print(json.dumps(await build_report(league_key), indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--league-key",
        default=get_settings().waiver_manager_team_key.rsplit(".t.", 1)[0],
        help="Persisted Yahoo league key; defaults to the configured waiver manager league.",
    )
    asyncio.run(_main(parser.parse_args().league_key))

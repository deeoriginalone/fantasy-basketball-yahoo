from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Literal
from urllib.parse import quote

from app.services.yahoo.client import YahooFantasyClient


@dataclass(frozen=True)
class NormalizedDraftResultPick:
    overall_pick: int
    round_number: int | None
    team_key: str
    yahoo_player_id: str
    retrieved_at: datetime
    source: Literal["yahoo_draftresults", "mock_yahoo_snapshot"]
    source_evidence: dict[str, Any]


def _text(value: object) -> str | None:
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    normalized = str(value).strip()
    return normalized or None


def _player_id(record: dict[str, Any]) -> str | None:
    player_id = _text(record.get("yahoo_player_id"))
    if player_id:
        return player_id
    player_key = _text(record.get("player_key"))
    if player_key:
        match = re.search(r"(?:^|\.)p\.([^.]*)$", player_key)
        if match:
            return match.group(1)
    for value in record.values():
        if isinstance(value, dict):
            nested = _player_id(value)
            if nested:
                return nested
    return None


def _records(value: object) -> list[dict[str, Any]]:
    if isinstance(value, list):
        results = []
        for nested in value:
            results.extend(_records(nested))
        return results
    if not isinstance(value, dict):
        return []
    if any(key in value for key in ("pick", "overall_pick", "overall_pick_number")):
        return [value]
    results = []
    for key, nested in value.items():
        if key != "count":
            results.extend(_records(nested))
    return results


def _find_draft_results(value: object) -> tuple[bool, object | None]:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "draft_results":
                return True, nested
        for nested in value.values():
            found, result = _find_draft_results(nested)
            if found:
                return found, result
    elif isinstance(value, list):
        for nested in value:
            found, result = _find_draft_results(nested)
            if found:
                return found, result
    return False, None


def normalize_yahoo_draft_results(
    payload: dict[str, Any],
    *,
    retrieved_at: datetime,
    source: Literal["yahoo_draftresults", "mock_yahoo_snapshot"] = "yahoo_draftresults",
) -> list[NormalizedDraftResultPick]:
    if not isinstance(payload, dict):
        raise ValueError("Yahoo draftresults payload must be an object")
    found, result_collection = _find_draft_results(payload)
    if not found:
        raise ValueError("Yahoo response omitted the draft_results collection")
    if not isinstance(result_collection, (dict, list)):
        raise ValueError("Yahoo draft_results collection is malformed")
    if isinstance(result_collection, dict) and "count" in result_collection:
        try:
            count = int(result_collection["count"])
        except (TypeError, ValueError) as error:
            raise ValueError("Yahoo draft_results count is invalid") from error
        if count < 0:
            raise ValueError("Yahoo draft_results count is invalid")
    else:
        count = None

    raw_records = _records(result_collection)
    if count == 0 and raw_records:
        raise ValueError("Yahoo draft_results count contradicts its records")
    if count and not raw_records:
        raise ValueError("Yahoo draft_results contains no parseable records")

    normalized: list[NormalizedDraftResultPick] = []
    seen_picks: set[int] = set()
    seen_players: set[str] = set()
    for record in raw_records:
        raw_pick = (
            record.get("overall_pick")
            or record.get("overall_pick_number")
            or record.get("pick")
        )
        try:
            overall_pick = int(raw_pick)
        except (TypeError, ValueError) as error:
            raise ValueError("Yahoo draft result has an invalid overall pick") from error
        if overall_pick < 1 or overall_pick in seen_picks:
            raise ValueError("Yahoo draft results contain a missing or duplicate overall pick")

        raw_round = record.get("round")
        try:
            round_number = int(raw_round) if raw_round is not None else None
        except (TypeError, ValueError) as error:
            raise ValueError("Yahoo draft result has an invalid round") from error
        if round_number is not None and round_number < 1:
            raise ValueError("Yahoo draft result has an invalid round")

        team_key = _text(record.get("team_key"))
        if not team_key:
            team = record.get("team")
            team_key = _text(team.get("team_key")) if isinstance(team, dict) else None
        yahoo_player_id = _player_id(record)
        if not team_key or not yahoo_player_id:
            raise ValueError("Yahoo draft result omitted its team or Yahoo player ID")
        if yahoo_player_id in seen_players:
            raise ValueError("Yahoo draft results contain a duplicate drafted player")
        seen_picks.add(overall_pick)
        seen_players.add(yahoo_player_id)
        source_evidence = {
            "source": source,
            "overall_pick": overall_pick,
            "retrieved_at": retrieved_at.isoformat(),
        }
        raw_evidence = record.get("source_evidence")
        if source == "mock_yahoo_snapshot" and isinstance(raw_evidence, dict):
            source_evidence.update(raw_evidence)
        normalized.append(NormalizedDraftResultPick(
            overall_pick=overall_pick,
            round_number=round_number,
            team_key=team_key,
            yahoo_player_id=yahoo_player_id,
            retrieved_at=retrieved_at,
            source=source,
            source_evidence=source_evidence,
        ))

    normalized.sort(key=lambda pick: pick.overall_pick)
    if normalized and [pick.overall_pick for pick in normalized] != list(range(1, len(normalized) + 1)):
        raise ValueError("Yahoo draft results contain gaps in overall pick order")
    if count is not None and count != len(normalized):
        raise ValueError("Yahoo draft_results count does not match its records")
    return normalized


async def fetch_yahoo_draft_results(
    client: YahooFantasyClient,
    access_token: str,
    league_key: str,
) -> dict[str, Any]:
    encoded_league_key = quote(league_key, safe="._")
    return await client.get_json(f"league/{encoded_league_key}/draftresults", access_token)


def make_yahoo_draftresults_snapshot(
    league_key: str,
    picks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "fantasy_content": {
            "league": {
                "league_key": league_key,
                "draft_results": {
                    **{
                        str(index): {
                            "draft_result": {
                                "pick": str(pick["overall_pick"]),
                                **({"round": str(pick["round_number"])} if pick.get("round_number") else {}),
                                "team_key": pick["team_key"],
                                "player_key": f"nba.p.{pick['yahoo_player_id']}",
                                **(
                                    {"source_evidence": pick["source_evidence"]}
                                    if isinstance(pick.get("source_evidence"), dict)
                                    else {}
                                ),
                            }
                        }
                        for index, pick in enumerate(picks)
                    },
                    "count": len(picks),
                },
            }
        }
    }

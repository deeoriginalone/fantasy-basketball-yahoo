import asyncio
from datetime import datetime, timezone

import pytest
import httpx

from app.services.yahoo.draft_results import (
    make_yahoo_draftresults_snapshot,
    normalize_yahoo_draft_results,
)
from app.services.yahoo.client import YahooFantasyClient


def _payload(*records):
    return {
        "fantasy_content": {
            "league": {
                "draft_results": {
                    **{
                        str(index): {"draft_result": record}
                        for index, record in enumerate(records)
                    },
                    "count": len(records),
                }
            }
        }
    }


def test_normalize_yahoo_draft_results_uses_yahoo_player_key_and_preserves_evidence():
    retrieved_at = datetime(2026, 10, 15, tzinfo=timezone.utc)
    payload = _payload(
        {"pick": "1", "round": "1", "team_key": "league.l.1.t.1", "player_key": "nba.p.123"},
        {"pick": "2", "round": "1", "team_key": "league.l.1.t.2", "player_key": "nba.p.456"},
    )

    picks = normalize_yahoo_draft_results(payload, retrieved_at=retrieved_at)

    assert [(pick.overall_pick, pick.yahoo_player_id) for pick in picks] == [
        (1, "123"),
        (2, "456"),
    ]
    assert picks[0].round_number == 1
    assert picks[0].source_evidence["source"] == "yahoo_draftresults"
    assert picks[0].retrieved_at == retrieved_at


def test_mock_snapshot_uses_the_same_normalizer_contract():
    retrieved_at = datetime(2026, 10, 15, tzinfo=timezone.utc)
    payload = make_yahoo_draftresults_snapshot("league.l.1", [{
        "overall_pick": 1,
        "round_number": 1,
        "team_key": "league.l.1.t.1",
        "yahoo_player_id": "123",
    }])

    picks = normalize_yahoo_draft_results(
        payload,
        retrieved_at=retrieved_at,
        source="mock_yahoo_snapshot",
    )

    assert len(picks) == 1
    assert picks[0].yahoo_player_id == "123"
    assert picks[0].source == "mock_yahoo_snapshot"


@pytest.mark.parametrize(
    ("records", "message"),
    [
        (
            (
                {"pick": "1", "team_key": "t1", "player_key": "nba.p.123"},
                {"pick": "3", "team_key": "t2", "player_key": "nba.p.456"},
            ),
            "gaps",
        ),
        (
            (
                {"pick": "1", "team_key": "t1", "player_key": "nba.p.123"},
                {"pick": "2", "team_key": "t2", "player_key": "nba.p.123"},
            ),
            "duplicate drafted player",
        ),
    ],
)
def test_normalize_rejects_gaps_and_duplicate_players(records, message):
    with pytest.raises(ValueError, match=message):
        normalize_yahoo_draft_results(
            _payload(*records),
            retrieved_at=datetime.now(timezone.utc),
        )


def test_normalize_rejects_payload_without_draft_results_collection():
    with pytest.raises(ValueError, match="omitted"):
        normalize_yahoo_draft_results({}, retrieved_at=datetime.now(timezone.utc))


def test_yahoo_client_uses_the_supplied_bearer_token():
    observed_authorization = None

    async def respond(request):
        nonlocal observed_authorization
        observed_authorization = request.headers["Authorization"]
        return httpx.Response(200, json={"fantasy_content": {}})

    async def scenario():
        client = YahooFantasyClient(transport=httpx.MockTransport(respond))
        await client.get_json("league/league.l.1/draftresults", "token-for-test")

    asyncio.run(scenario())

    assert observed_authorization == "Bearer token-for-test"

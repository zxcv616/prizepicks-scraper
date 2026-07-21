import json
from pathlib import Path

import pytest

from prizepicks_scraper.parse import parse_projections
from prizepicks_scraper.leagues import parse_leagues, resolve_league_id


def test_resolve_league_id_case_insensitive():
    assert resolve_league_id("LoL") == 121
    assert resolve_league_id("lol") == 121
    assert resolve_league_id("NBA") == 7
    assert resolve_league_id("nba") == 7
    assert resolve_league_id("121") == 121   # numeric id passes through
    with pytest.raises(ValueError):
        resolve_league_id("notaleague")

FIXTURE = Path(__file__).parent / "fixtures" / "sample_projections.json"


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text())


def test_parses_all_projections(payload):
    rows = parse_projections(payload)
    assert len(rows) == 3


def test_joins_player_and_stat(payload):
    rows = {r.projection_id: r for r in parse_projections(payload)}
    lebron = rows["1001"]
    assert lebron.player_name == "LeBron James"
    assert lebron.team == "LAL"
    assert lebron.position == "F"
    assert lebron.league == "NBA"
    assert lebron.stat_type == "Points"
    assert lebron.line_score == 25.5
    assert lebron.odds_type == "standard"


def test_demon_and_goblin_odds_types(payload):
    rows = {r.projection_id: r for r in parse_projections(payload)}
    assert rows["1002"].odds_type == "demon"
    assert rows["1002"].stat_type == "Assists"
    assert rows["1003"].odds_type == "goblin"
    assert rows["1003"].is_promo is True


def test_line_score_coerced_to_float(payload):
    rows = {r.projection_id: r for r in parse_projections(payload)}
    # fixture 1003 has line_score as the string "1.5"
    assert rows["1003"].line_score == 1.5
    assert isinstance(rows["1003"].line_score, float)


def test_shared_scraped_at_timestamp(payload):
    rows = parse_projections(payload, scraped_at="2026-07-20T12:00:00+00:00")
    assert all(r.scraped_at == "2026-07-20T12:00:00+00:00" for r in rows)


def test_missing_included_is_tolerated():
    payload = {
        "data": [{
            "type": "projection", "id": "9",
            "attributes": {"line_score": 3.5},
            "relationships": {"new_player": {"data": {"type": "new_player", "id": "x"}}},
        }],
        "included": [],
    }
    rows = parse_projections(payload)
    assert len(rows) == 1
    assert rows[0].player_name is None
    assert rows[0].line_score == 3.5


def test_ignores_non_projection_data():
    payload = {"data": [{"type": "something_else", "id": "1"}], "included": []}
    assert parse_projections(payload) == []


def test_parse_leagues():
    payload = {"data": [
        {"type": "league", "id": "7", "attributes": {"name": "NBA", "active": True}},
        {"type": "league", "id": "2", "attributes": {"name": "MLB", "active": True}},
    ]}
    leagues = parse_leagues(payload)
    assert {l["name"] for l in leagues} == {"NBA", "MLB"}

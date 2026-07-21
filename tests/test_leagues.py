import pytest

from prizepicks_scraper.leagues import (
    leagues_name_map,
    load_leagues_cache,
    resolve_league_id,
    save_leagues_cache,
)


def test_resolve_with_extra_map_beats_hardcoded():
    live = {"UFC": "12", "F1": "125", "LOL": "999"}
    assert resolve_league_id("UFC", extra=live) == "12"
    assert resolve_league_id("f1", extra=live) == "125"        # case-insensitive
    assert resolve_league_id("LoL", extra=live) == "999"       # extra wins over hardcoded
    assert resolve_league_id("121", extra=live) == 121         # numeric passthrough


def test_resolve_unknown_raises():
    with pytest.raises(ValueError):
        resolve_league_id("NOTALEAGUE", extra={"UFC": "12"})


def test_leagues_name_map_includes_name_and_display():
    parsed = [
        {"id": "12", "name": "UFC", "display_name": "Mixed Martial Arts"},
        {"id": "125", "name": "F1", "display_name": None},
    ]
    m = leagues_name_map(parsed)
    assert m["UFC"] == "12"
    assert m["MIXED MARTIAL ARTS"] == "12"
    assert m["F1"] == "125"


def test_cache_roundtrip(tmp_path):
    path = tmp_path / "leagues.json"
    parsed = [{"id": "12", "name": "UFC", "display_name": None}]
    save_leagues_cache(parsed, path)
    loaded = load_leagues_cache(path)
    assert loaded["UFC"] == "12"
    # missing file -> empty map, no error
    assert load_leagues_cache(tmp_path / "nope.json") == {}

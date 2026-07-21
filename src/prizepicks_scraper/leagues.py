"""League id helpers.

PrizePicks assigns a numeric ``league_id`` to each sport. These ids are stable
but the *available* set changes seasonally. Use :func:`fetch_leagues` (via a
client) to discover the live list; the constants below are common defaults for
convenience. Always verify against ``/leagues`` if a name lookup misses.
"""
from __future__ import annotations

import json
from pathlib import Path

# Disk cache of the live name->id map, written whenever we fetch /leagues.
# Lets `scrape UFC` resolve any of the ~100+ live leagues offline after the
# first fetch, instead of only the small hardcoded set below.
LEAGUES_CACHE = Path.home() / ".cache" / "pps" / "leagues.json"

# Commonly-seen ids. Verify with `pps leagues` since these can change.
DEFAULT_LEAGUE_IDS: dict[str, int] = {
    "NBA": 7,
    "NFL": 9,
    "MLB": 2,
    "NHL": 8,
    "SOCCER": 82,
    "PGA": 20,
    "TENNIS": 5,
    "CS2": 265,
    "LoL": 121,
    "VAL": 138,
}

LEAGUES_URL = "https://api.prizepicks.com/leagues"
PROJECTIONS_URL = "https://api.prizepicks.com/projections"


def projections_url(league_id: int | str, per_page: int = 250,
                    single_stat: bool = True) -> str:
    """Build a projections request URL for a league."""
    single = "true" if single_stat else "false"
    return (f"{PROJECTIONS_URL}?league_id={league_id}"
            f"&per_page={per_page}&single_stat={single}")


def resolve_league_id(name_or_id: str, extra: dict | None = None) -> int | str:
    """Resolve a league name (e.g. ``NBA``, ``UFC``) or numeric id to an id.

    Matching is case-insensitive. ``extra`` is an optional live/cached
    name->id map (upper-cased keys) that takes precedence over the small
    hardcoded set, so any of the ~100+ live leagues can be resolved by name.
    """
    s = str(name_or_id).strip()
    if s.isdigit():
        return int(s)
    key = s.upper()
    if extra and key in extra:
        return extra[key]
    hardcoded = {k.upper(): v for k, v in DEFAULT_LEAGUE_IDS.items()}
    if key in hardcoded:
        return hardcoded[key]
    raise ValueError(
        f"Unknown league '{name_or_id}'. Pass a numeric id (e.g. 121 for LoL), "
        f"or run `pps leagues` to refresh the live list."
    )


def leagues_name_map(leagues: list[dict]) -> dict[str, str]:
    """Build an upper-cased name->id map from parsed /leagues output."""
    out: dict[str, str] = {}
    for lg in leagues:
        lid = lg.get("id")
        if lid is None:
            continue
        for label in (lg.get("name"), lg.get("display_name")):
            if label:
                out[str(label).upper()] = str(lid)
    return out


def save_leagues_cache(leagues: list[dict], path: Path = LEAGUES_CACHE) -> None:
    """Persist the live name->id map so name lookups work offline next time."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(leagues_name_map(leagues)))
    except OSError:
        pass  # caching is best-effort; never fail a scrape over it


def load_leagues_cache(path: Path = LEAGUES_CACHE) -> dict[str, str]:
    """Load the cached name->id map (upper-cased keys), or {} if missing."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def parse_leagues(payload: dict) -> list[dict]:
    """Flatten a ``/leagues`` payload to ``[{id, name, ...}]``."""
    out = []
    for item in payload.get("data", []):
        if item.get("type") != "league":
            continue
        attrs = item.get("attributes", {}) or {}
        out.append({
            "id": str(item.get("id")),
            "name": attrs.get("name"),
            "display_name": attrs.get("display_name"),
            "active": attrs.get("active"),
        })
    return out

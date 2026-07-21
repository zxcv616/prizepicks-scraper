"""League id helpers.

PrizePicks assigns a numeric ``league_id`` to each sport. These ids are stable
but the *available* set changes seasonally. Use :func:`fetch_leagues` (via a
client) to discover the live list; the constants below are common defaults for
convenience. Always verify against ``/leagues`` if a name lookup misses.
"""
from __future__ import annotations

# Commonly-seen ids. Verify with `prizepicks leagues` since these can change.
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


def resolve_league_id(name_or_id: str) -> int | str:
    """Resolve a league name (e.g. ``NBA``) or numeric id to an id."""
    s = str(name_or_id).strip()
    if s.isdigit():
        return int(s)
    upper = s.upper()
    if upper in DEFAULT_LEAGUE_IDS:
        return DEFAULT_LEAGUE_IDS[upper]
    raise ValueError(
        f"Unknown league '{name_or_id}'. Pass a numeric id, or run "
        f"`prizepicks leagues` to list live ids."
    )


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

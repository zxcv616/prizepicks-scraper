"""prizepicks_scraper — fetch and parse PrizePicks projections.

Public API:
    parse_projections(payload)  -> list[Projection]
    BrowserClient               -> browser-backed fetcher (needs Playwright)
"""
from .models import Projection, FIELDS
from .parse import parse_projections
from .leagues import (
    resolve_league_id,
    projections_url,
    parse_leagues,
    DEFAULT_LEAGUE_IDS,
)

__all__ = [
    "Projection",
    "FIELDS",
    "parse_projections",
    "parse_leagues",
    "resolve_league_id",
    "projections_url",
    "DEFAULT_LEAGUE_IDS",
    "__version__",
]

__version__ = "0.1.0"

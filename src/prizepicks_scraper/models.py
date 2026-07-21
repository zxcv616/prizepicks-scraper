"""Typed data models for PrizePicks projections."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass(frozen=True)
class Projection:
    """A single flattened PrizePicks projection (one player + one stat line).

    This is the denormalized join of a JSON:API ``projection`` record with its
    related ``new_player``, ``league`` and ``stat_type`` resources.
    """

    projection_id: str
    scraped_at: str          # ISO 8601 UTC timestamp of when we captured it
    league: Optional[str]
    league_id: Optional[str]
    player_id: Optional[str]
    player_name: Optional[str]
    team: Optional[str]
    position: Optional[str]
    stat_type: Optional[str]
    line_score: Optional[float]
    # PrizePicks "odds_type": standard | demon | goblin (payout-adjusted lines)
    odds_type: Optional[str]
    start_time: Optional[str]
    status: Optional[str]
    description: Optional[str]
    is_promo: Optional[bool]

    def as_dict(self) -> dict:
        return asdict(self)


# Column order used by the CSV / SQLite writers.
FIELDS = list(Projection.__annotations__.keys())

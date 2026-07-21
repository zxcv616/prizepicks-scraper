"""Parse PrizePicks' JSON:API ``/projections`` payload into flat rows.

The endpoint returns JSON:API format:

    {
      "data":     [ { "type": "projection", "id": ..., "attributes": {...},
                      "relationships": {...} }, ... ],
      "included": [ { "type": "new_player", "id": ..., "attributes": {...} },
                    { "type": "league",     "id": ..., "attributes": {...} },
                    { "type": "stat_type",  "id": ..., "attributes": {...} }, ... ]
    }

Related resources (player, league, stat type) live in ``included`` and are
referenced from each projection's ``relationships`` by ``(type, id)``. This
module builds an index of ``included`` and joins everything into
:class:`~prizepicks_scraper.models.Projection` rows.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from .models import Projection


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _index_included(included: Iterable[dict]) -> dict[tuple[str, str], dict]:
    """Index included resources by ``(type, id)`` for O(1) relationship lookup."""
    index: dict[tuple[str, str], dict] = {}
    for res in included or []:
        rtype, rid = res.get("type"), res.get("id")
        if rtype is not None and rid is not None:
            index[(rtype, str(rid))] = res
    return index


def _rel_ref(rel_block: dict | None, name: str) -> tuple[str, str] | None:
    """Extract the ``(type, id)`` reference for relationship ``name``."""
    if not rel_block:
        return None
    data = (rel_block.get(name) or {}).get("data")
    if not data:
        return None
    rtype, rid = data.get("type"), data.get("id")
    if rtype is None or rid is None:
        return None
    return (rtype, str(rid))


def _lookup(index: dict, ref: tuple[str, str] | None) -> dict:
    if ref is None:
        return {}
    return index.get(ref, {})


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_projections(payload: dict, scraped_at: str | None = None) -> list[Projection]:
    """Denormalize a raw ``/projections`` payload into :class:`Projection` rows.

    ``scraped_at`` lets callers pin a single timestamp across one capture batch;
    if omitted, the current UTC time is used.
    """
    scraped_at = scraped_at or _utcnow_iso()
    index = _index_included(payload.get("included", []))
    rows: list[Projection] = []

    for item in payload.get("data", []):
        if item.get("type") != "projection":
            continue
        attrs = item.get("attributes", {}) or {}
        rels = item.get("relationships", {}) or {}

        player = _lookup(index, _rel_ref(rels, "new_player"))
        p_attrs = player.get("attributes", {}) or {}

        league = _lookup(index, _rel_ref(rels, "league"))
        l_attrs = league.get("attributes", {}) or {}

        stat = _lookup(index, _rel_ref(rels, "stat_type"))
        s_attrs = stat.get("attributes", {}) or {}

        # stat_type name can come from the included stat_type resource or, on
        # some payloads, directly off the projection attributes.
        stat_type_name = s_attrs.get("name") or attrs.get("stat_type")

        rows.append(
            Projection(
                projection_id=str(item.get("id")),
                scraped_at=scraped_at,
                league=l_attrs.get("name") or p_attrs.get("league"),
                league_id=(league.get("id") and str(league["id"])) or None,
                player_id=(player.get("id") and str(player["id"])) or None,
                player_name=p_attrs.get("name") or p_attrs.get("display_name"),
                team=p_attrs.get("team") or p_attrs.get("team_name"),
                position=p_attrs.get("position"),
                stat_type=stat_type_name,
                line_score=_to_float(attrs.get("line_score")),
                odds_type=attrs.get("odds_type"),
                start_time=attrs.get("start_time"),
                status=attrs.get("status"),
                description=attrs.get("description"),
                is_promo=attrs.get("is_promo"),
            )
        )
    return rows

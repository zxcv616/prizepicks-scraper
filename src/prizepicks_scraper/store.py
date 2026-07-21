"""Persistence: append projection snapshots to SQLite / CSV / JSON.

Line movement is the interesting signal, so storage is *append-only and
timestamped*: every capture inserts new rows keyed by
``(projection_id, scraped_at)``. Re-running the scraper builds a time series
rather than overwriting.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from .models import FIELDS, Projection

_CREATE = f"""
CREATE TABLE IF NOT EXISTS projections (
    {", ".join(f"{f} TEXT" if f not in ("line_score",) else f"{f} REAL"
               for f in FIELDS)},
    PRIMARY KEY (projection_id, scraped_at)
);
"""


def write_sqlite(rows: Sequence[Projection], db_path: str | Path) -> int:
    """Insert rows into a SQLite db (created if needed). Returns rows written."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(_CREATE)
        placeholders = ", ".join("?" for _ in FIELDS)
        sql = (f"INSERT OR IGNORE INTO projections ({', '.join(FIELDS)}) "
               f"VALUES ({placeholders})")
        data = [tuple(getattr(r, f) for f in FIELDS) for r in rows]
        conn.executemany(sql, data)
        conn.commit()
        return conn.total_changes
    finally:
        conn.close()


def latest_snapshot_age(db_path: str | Path, league_id) -> float | None:
    """Seconds since the most recent stored snapshot for ``league_id``.

    Returns None if the output isn't a SQLite db, doesn't exist yet, or has no
    rows for that league (caching only applies to the append-only SQLite store).
    """
    path = Path(db_path)
    if path.suffix.lower() not in (".db", ".sqlite", ".sqlite3") or not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            "SELECT MAX(scraped_at) FROM projections WHERE league_id = ?",
            (str(league_id),),
        ).fetchone()
    except sqlite3.OperationalError:
        return None  # table not created yet
    finally:
        conn.close()
    if not row or not row[0]:
        return None
    try:
        ts = datetime.fromisoformat(row[0])
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds()


def write_csv(rows: Iterable[Projection], csv_path: str | Path) -> int:
    """Write rows to CSV (overwrites). Returns rows written."""
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow(r.as_dict())
            n += 1
    return n


def write_json(rows: Iterable[Projection], json_path: str | Path) -> int:
    """Write rows to a JSON array (overwrites). Returns rows written."""
    json_path = Path(json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    data = [r.as_dict() for r in rows]
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return len(data)

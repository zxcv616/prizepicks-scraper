import json
import sqlite3
from pathlib import Path

import pytest

from prizepicks_scraper.parse import parse_projections
from prizepicks_scraper.store import write_sqlite, write_csv, write_json

FIXTURE = Path(__file__).parent / "fixtures" / "sample_projections.json"


@pytest.fixture
def rows():
    payload = json.loads(FIXTURE.read_text())
    return parse_projections(payload, scraped_at="2026-07-20T12:00:00+00:00")


def test_sqlite_roundtrip_and_append(rows, tmp_path):
    db = tmp_path / "p.db"
    n1 = write_sqlite(rows, db)
    assert n1 == 3
    # Re-inserting the same snapshot is idempotent (same PK).
    n2 = write_sqlite(rows, db)
    assert n2 == 0

    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM projections").fetchone()[0]
    line = conn.execute(
        "SELECT line_score FROM projections WHERE projection_id='1001'"
    ).fetchone()[0]
    conn.close()
    assert count == 3
    assert line == 25.5  # stored as REAL


def test_sqlite_new_snapshot_appends(rows, tmp_path):
    db = tmp_path / "p.db"
    write_sqlite(rows, db)
    payload = json.loads(FIXTURE.read_text())
    later = parse_projections(payload, scraped_at="2026-07-20T13:00:00+00:00")
    n = write_sqlite(later, db)
    assert n == 3  # different scraped_at -> new rows
    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM projections").fetchone()[0]
    conn.close()
    assert count == 6


def test_csv_writer(rows, tmp_path):
    out = tmp_path / "p.csv"
    n = write_csv(rows, out)
    assert n == 3
    text = out.read_text()
    assert "projection_id" in text.splitlines()[0]
    assert "LeBron James" in text


def test_json_writer(rows, tmp_path):
    out = tmp_path / "p.json"
    n = write_json(rows, out)
    assert n == 3
    data = json.loads(out.read_text())
    assert data[0]["player_name"] == "LeBron James"

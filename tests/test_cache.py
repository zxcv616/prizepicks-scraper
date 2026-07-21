import argparse
import json
from pathlib import Path

import prizepicks_scraper.cli as cli
from prizepicks_scraper.cli import _parse_duration
from prizepicks_scraper.parse import parse_projections
from prizepicks_scraper.store import latest_snapshot_age, write_sqlite

FIXTURE = Path(__file__).parent / "fixtures" / "sample_projections.json"


def test_parse_duration():
    assert _parse_duration(None) == 0
    assert _parse_duration("0") == 0
    assert _parse_duration("30s") == 30
    assert _parse_duration("10m") == 600
    assert _parse_duration("1h") == 3600
    assert _parse_duration("2d") == 172800
    assert _parse_duration("45") == 45  # bare seconds


def test_latest_snapshot_age(tmp_path):
    db = tmp_path / "p.db"
    rows = parse_projections(json.loads(FIXTURE.read_text()))
    write_sqlite(rows, db)
    age = latest_snapshot_age(db, 7)     # NBA present in fixture
    assert age is not None and age >= 0
    assert latest_snapshot_age(db, 99999) is None   # league not present
    assert latest_snapshot_age(tmp_path / "nope.db", 7) is None
    assert latest_snapshot_age(tmp_path / "x.csv", 7) is None  # non-sqlite


class _FakeClient:
    def __init__(self, payload, calls):
        self.payload, self.calls = payload, calls
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def fetch_projections(self, lid, per_page=250):
        self.calls.append(lid)
        return self.payload


def test_scrape_uses_cache(tmp_path, monkeypatch):
    payload = json.loads(FIXTURE.read_text())
    calls = []
    monkeypatch.setattr(cli, "_client", lambda args: _FakeClient(payload, calls))
    # Isolate from the real on-disk league-name cache.
    monkeypatch.setattr(cli, "load_leagues_cache", lambda: {})
    monkeypatch.setattr(cli, "save_leagues_cache", lambda lgs: None)
    db = tmp_path / "p.db"

    def scrape(max_age):
        cli.cmd_scrape(argparse.Namespace(
            league=["MLB"], out=str(db), per_page=250, save_raw=None, max_age=max_age))

    scrape(None)
    assert calls == [2]           # fetched once (hardcoded MLB -> 2)

    calls.clear()
    scrape("1h")
    assert calls == []            # fresh snapshot -> no fetch

    calls.clear()
    scrape("0")
    assert calls == [2]           # cache off -> fetch again

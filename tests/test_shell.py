import argparse
from pathlib import Path

from prizepicks_scraper.shell import PrizePicksShell, _initial_state

FIXTURE = Path(__file__).parent / "fixtures" / "sample_projections.json"


def _blank_args(**kw):
    base = dict(unlocker=None, api_key=None, unlocker_template=None, out=None,
                per_page=None, save_raw=None, proxy=None, cdp=None, profile=None,
                headful=None, channel=None, no_chrome=None, backend=None,
                max_age=None)
    base.update(kw)
    return argparse.Namespace(**base)


def test_initial_state_seeds_from_args():
    state = _initial_state(_blank_args(unlocker="zenrows"))
    assert state["unlocker"] == "zenrows"
    assert state["out"] == "data/projections.db"  # default retained


def test_set_bool_and_int_coercion():
    s = PrizePicksShell(_blank_args())
    s.onecmd("set headful true")
    assert s.state["headful"] is True
    s.onecmd("set per_page 50")
    assert s.state["per_page"] == 50


def test_set_none_clears():
    s = PrizePicksShell(_blank_args(proxy="http://x"))
    s.onecmd("set proxy none")
    assert s.state["proxy"] is None


def test_set_unknown_key_ignored():
    s = PrizePicksShell(_blank_args())
    before = dict(s.state)
    s.onecmd("set nonsense value")
    assert s.state == before


def test_parse_file_through_shell(tmp_path):
    out = tmp_path / "o.csv"
    s = PrizePicksShell(_blank_args())
    s.onecmd(f"parse-file {FIXTURE} {out}")
    assert out.exists()
    assert "LeBron James" in out.read_text()


def test_exit_returns_true():
    s = PrizePicksShell(_blank_args())
    assert s.onecmd("exit") is True
    assert s.onecmd("quit") is True


def test_set_backend_free_and_provider():
    s = PrizePicksShell(_blank_args())
    s.onecmd("set backend free")
    assert s.state["backend"] == "browser"
    assert s._ns().unlocker is None            # free -> no unlocker
    s.onecmd("set backend zenrows")
    assert s.state["backend"] == "zenrows"
    assert s._ns().unlocker == "zenrows"        # provider -> unlocker


def test_set_backend_rejects_unknown():
    s = PrizePicksShell(_blank_args())
    s.onecmd("set backend nonsense")
    assert s.state["backend"] is None           # unchanged


def test_backend_seeded_from_launch_flag():
    s = PrizePicksShell(_blank_args(unlocker="scraperapi"))
    assert s.state["backend"] == "scraperapi"   # chooser will be skipped


def test_banner_lines_are_aligned(monkeypatch):
    import prizepicks_scraper.shell as sh
    monkeypatch.setattr(sh, "_use_color", lambda: True)
    banner = sh._banner(dict(sh._DEFAULTS))
    widths = {sh._vis_len(line) for line in banner.split("\n")}
    assert len(widths) == 1  # every bordered row is the same visible width


def test_results_reads_db(tmp_path, capsys):
    import json
    from prizepicks_scraper.parse import parse_projections
    from prizepicks_scraper.store import write_sqlite

    payload = json.loads(FIXTURE.read_text())
    rows = parse_projections(payload, scraped_at="2026-07-21T00:00:00+00:00")
    db = tmp_path / "p.db"
    write_sqlite(rows, db)

    s = PrizePicksShell(_blank_args(out=str(db)))
    s.onecmd("results NBA")
    out = capsys.readouterr().out
    assert "LeBron James" in out
    assert "Aaron Judge" not in out   # filtered to NBA
    assert "2 row(s)" in out


def test_results_no_file(capsys):
    s = PrizePicksShell(_blank_args(out="does/not/exist.db"))
    s.onecmd("results")
    assert "no data yet" in capsys.readouterr().out


def test_banner_plain_when_no_color(monkeypatch):
    import prizepicks_scraper.shell as sh
    monkeypatch.setattr(sh, "_use_color", lambda: False)
    banner = sh._banner(dict(sh._DEFAULTS))
    assert "\x1b[" not in banner  # no ANSI codes when color disabled

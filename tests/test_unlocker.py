import json
import urllib.parse
from pathlib import Path

import pytest

from prizepicks_scraper.unlocker import UnlockerClient, UnlockerError, PROVIDERS

FIXTURE = Path(__file__).parent / "fixtures" / "sample_projections.json"


def _decode_target(req_url: str, param: str) -> str:
    q = urllib.parse.urlparse(req_url).query
    return urllib.parse.parse_qs(q)[param][0]


def test_zenrows_url_has_residential_and_antibot():
    c = UnlockerClient("zenrows", "KEY123")
    url = c._build_url("https://api.prizepicks.com/leagues")
    assert url.startswith("https://api.zenrows.com/v1/?")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["apikey"] == ["KEY123"]
    assert q["premium_proxy"] == ["true"]   # residential — required for DataDome
    assert q["antibot"] == ["true"]
    assert _decode_target(url, "url") == "https://api.prizepicks.com/leagues"


def test_scraperapi_uses_ultra_premium():
    c = UnlockerClient("scraperapi", "K")
    url = c._build_url("https://api.prizepicks.com/leagues")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["ultra_premium"] == ["true"]
    assert q["api_key"] == ["K"]


def test_generic_template_substitution():
    c = UnlockerClient("generic", "SECRET",
                       template="https://x.test/?u={url}&k={key}")
    url = c._build_url("https://api.prizepicks.com/leagues?league_id=7")
    # target and key are percent-encoded into the template
    assert "SECRET" in url
    assert "https%3A%2F%2Fapi.prizepicks.com" in url


def test_generic_requires_template():
    with pytest.raises(ValueError):
        UnlockerClient("generic", "K")


def test_unknown_provider_rejected():
    with pytest.raises(ValueError):
        UnlockerClient("nope", "K")


def test_fetch_parses_json(monkeypatch):
    payload = json.loads(FIXTURE.read_text())

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(payload).encode()

    def fake_urlopen(req, timeout=0):
        return FakeResp()

    import prizepicks_scraper.unlocker as u
    monkeypatch.setattr(u.urllib.request, "urlopen", fake_urlopen)

    c = UnlockerClient("zenrows", "K", request_delay=0)
    data = c.fetch_projections("NBA")
    assert len(data["data"]) == 3


def test_fetch_retries_then_raises_on_antibot_html(monkeypatch):
    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"<html>blocked</html>"

    calls = {"n": 0}

    def fake_urlopen(req, timeout=0):
        calls["n"] += 1
        return FakeResp()

    import prizepicks_scraper.unlocker as u
    monkeypatch.setattr(u.urllib.request, "urlopen", fake_urlopen)

    c = UnlockerClient("zenrows", "K", request_delay=0, max_retries=2)
    # make backoff instant
    monkeypatch.setattr(u.time, "sleep", lambda *_: None)
    with pytest.raises(UnlockerError):
        c.fetch_leagues()
    assert calls["n"] == 2  # retried

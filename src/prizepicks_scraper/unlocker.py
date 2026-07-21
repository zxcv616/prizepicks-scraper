"""Fully-automated fetching via a commercial "web unlocker" API.

DataDome blocks on IP reputation + browser fingerprint, so a hands-off scraper
needs a trusted residential IP. Web-unlocker services do this for you: you send
one HTTP request with the target URL and your API key; the service runs a real
browser behind rotating **residential** proxies, solves the DataDome challenge,
and returns the final response body (here: the PrizePicks JSON). No browser and
no human interaction on your side.

This client is provider-agnostic. Built-in presets: ``zenrows``, ``scraperapi``,
``scrapingbee``. Use ``generic`` with ``--unlocker-template`` for anything else
(including Bright Data / Oxylabs, which are usually integrated as proxies — see
README).

The public interface mirrors :class:`~prizepicks_scraper.client.BrowserClient`
(context manager + ``fetch_leagues`` / ``fetch_projections``) so the CLI and
callers are identical regardless of backend.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Callable, Optional

from .leagues import LEAGUES_URL, projections_url


class UnlockerError(RuntimeError):
    """Raised when the unlocker service returns a non-JSON / error response."""


def _zenrows(target: str, key: str, extra: dict) -> str:
    params = {
        "apikey": key,
        "url": target,
        "js_render": "true",
        "antibot": "true",
        "premium_proxy": "true",  # residential — required for DataDome
    }
    params.update(extra)
    return "https://api.zenrows.com/v1/?" + urllib.parse.urlencode(params)


def _scraperapi(target: str, key: str, extra: dict) -> str:
    params = {
        "api_key": key,
        "url": target,
        "render": "true",
        "ultra_premium": "true",  # residential + hardened antibot (DataDome)
    }
    params.update(extra)
    return "https://api.scraperapi.com/?" + urllib.parse.urlencode(params)


def _scrapingbee(target: str, key: str, extra: dict) -> str:
    params = {
        "api_key": key,
        "url": target,
        "render_js": "true",
        "premium_proxy": "true",
        "stealth_proxy": "true",  # strongest tier for advanced antibot
    }
    params.update(extra)
    return "https://app.scrapingbee.com/api/v1/?" + urllib.parse.urlencode(params)


# provider -> (target, key, extra) -> request URL
PROVIDERS: dict[str, Callable[[str, str, dict], str]] = {
    "zenrows": _zenrows,
    "scraperapi": _scraperapi,
    "scrapingbee": _scrapingbee,
}


class UnlockerClient:
    """Fetch PrizePicks endpoints through a web-unlocker API (no local browser).

    Usage::

        with UnlockerClient("zenrows", api_key="...") as client:
            payload = client.fetch_projections("NBA")
    """

    def __init__(
        self,
        provider: str,
        api_key: str,
        extra: Optional[dict] = None,
        template: Optional[str] = None,
        timeout: int = 90,
        request_delay: float = 1.0,
        max_retries: int = 3,
    ):
        self.provider = provider
        self.api_key = api_key
        self.extra = extra or {}
        self.template = template  # for provider == "generic": uses {url} {key}
        self.timeout = timeout
        self.request_delay = request_delay
        self.max_retries = max_retries
        if provider == "generic":
            if not template:
                raise ValueError("provider 'generic' requires a --unlocker-template "
                                 "containing {url} and (optionally) {key}.")
        elif provider not in PROVIDERS:
            raise ValueError(
                f"Unknown unlocker provider '{provider}'. "
                f"Choose from: {', '.join(sorted(PROVIDERS))}, generic."
            )

    # -- lifecycle (no-op; here for a uniform interface) -------------------
    def __enter__(self) -> "UnlockerClient":
        return self

    def __exit__(self, *exc) -> None:
        return None

    # -- request building --------------------------------------------------
    def _build_url(self, target: str) -> str:
        if self.provider == "generic":
            return (self.template
                    .replace("{url}", urllib.parse.quote(target, safe=""))
                    .replace("{key}", urllib.parse.quote(self.api_key, safe="")))
        return PROVIDERS[self.provider](target, self.api_key, self.extra)

    # -- fetching ----------------------------------------------------------
    def _get_json(self, target: str) -> dict:
        req_url = self._build_url(target)
        last_err = ""
        for attempt in range(1, self.max_retries + 1):
            try:
                req = urllib.request.Request(req_url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8", "replace")
                data = json.loads(body)
                time.sleep(self.request_delay)
                return data
            except json.JSONDecodeError:
                last_err = f"non-JSON response (antibot page?): {body[:200]}"
            except urllib.error.HTTPError as e:
                last_err = f"HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}"
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"
            if attempt < self.max_retries:
                time.sleep(2 * attempt)  # backoff between retries
        raise UnlockerError(
            f"Unlocker '{self.provider}' failed to fetch {target} after "
            f"{self.max_retries} attempts. Last error: {last_err}"
        )

    def fetch_leagues(self) -> dict:
        return self._get_json(LEAGUES_URL)

    def fetch_projections(
        self, league_id: int | str, per_page: int = 250, single_stat: bool = True
    ) -> dict:
        return self._get_json(projections_url(league_id, per_page, single_stat))

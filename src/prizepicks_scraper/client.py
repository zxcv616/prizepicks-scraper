"""Browser-backed client that fetches the PrizePicks JSON API past DataDome.

PrizePicks' ``api.prizepicks.com`` is protected by DataDome bot mitigation.
A plain HTTP request (even with TLS impersonation) is rejected with a 403
challenge page. The reliable approach is to drive a real browser:

1. Launch a *persistent* Chromium context (so a solved DataDome clearance
   cookie is reused across runs).
2. Navigate to the PrizePicks web app so the anti-bot script runs and issues
   a valid ``datadome`` cookie for this browser fingerprint + IP.
3. Fetch the API endpoints *through that same authenticated context*
   (``page.request.get``), which carries the cookies and a matching TLS/JS
   fingerprint — no fragile cookie transplant to a separate HTTP client.

If DataDome serves a challenge instead of clearing (common on datacenter /
VPN IPs), run with ``headful=True`` so you can solve any interactive check
once; the persistent profile then keeps you cleared.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

from .leagues import LEAGUES_URL, projections_url

WEB_APP_URL = "https://app.prizepicks.com/"
# Default: let Playwright use the browser's own matching User-Agent. Overriding
# it with a mismatched version is a fingerprint inconsistency DataDome can flag.
DEFAULT_UA = None


class DataDomeBlocked(RuntimeError):
    """Raised when the API returns a bot-challenge instead of JSON."""


class BrowserClient:
    """Fetches PrizePicks endpoints through an authenticated browser context.

    Use as a context manager::

        with BrowserClient(headful=True) as client:
            payload = client.fetch_projections(7)
    """

    def __init__(
        self,
        profile_dir: str | Path = ".pp_profile",
        headful: bool = False,
        user_agent: Optional[str] = DEFAULT_UA,
        warmup_ms: int = 6000,
        request_delay: float = 1.5,
        proxy: Optional[str] = None,
        clearance_timeout: Optional[int] = None,
        cdp_url: Optional[str] = None,
        channel: Optional[str] = "chrome",
        auto_headful: bool = True,
    ):
        self.profile_dir = Path(profile_dir)
        self.headful = headful
        self.user_agent = user_agent
        self.warmup_ms = warmup_ms
        self.request_delay = request_delay
        self.proxy = proxy
        # If a headless run is blocked by DataDome, automatically reopen a
        # visible window so the user can solve the challenge once, then continue
        # in the same command. The persistent profile remembers the clearance.
        self.auto_headful = auto_headful
        # Attach to an already-running real browser over the DevTools protocol
        # instead of launching one. This inherits the genuine fingerprint and
        # session — the most reliable way past DataDome.
        self.cdp_url = cdp_url
        # Use the real installed Chrome ("chrome") rather than Playwright's
        # bundled Chromium, which DataDome fingerprints more aggressively.
        self.channel = channel
        # How long to wait for a DataDome clearance. In headful mode this is
        # the window to solve an interactive challenge, so default it generous.
        if clearance_timeout is None:
            clearance_timeout = 180 if headful else 20
        self.clearance_timeout = clearance_timeout
        self._pw = None
        self._ctx = None
        self._page = None
        self._warmed = False
        self._clearance = None  # cached /leagues payload from the clearance probe

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> "BrowserClient":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _sync_playwright(self):
        # Prefer patchright (a patched Playwright that removes the CDP
        # Runtime.enable leak DataDome keys on) when it is installed.
        try:
            from patchright.sync_api import sync_playwright
            self._driver = "patchright"
            return sync_playwright()
        except ImportError:
            pass
        try:
            from playwright.sync_api import sync_playwright
            self._driver = "playwright"
            return sync_playwright()
        except ImportError:
            raise RuntimeError(
                "The browser backend needs Playwright, which isn't installed.\n"
                "This is the free path (uses your own Chrome + home IP, no account).\n"
                "Install it once:\n"
                "  pip install -e \".[browser]\"\n"
                "  playwright install chromium\n"
                "Then re-run. (Or use --unlocker <provider> for the paid API path.)"
            ) from None

    def start(self) -> None:
        self._pw = self._sync_playwright().start()

        if self.cdp_url:
            # Attach to a real Chrome the user launched with
            # --remote-debugging-port. Reuse its existing context/page.
            # Force IPv4: "localhost" often resolves to ::1, but Chrome's debug
            # port listens on 127.0.0.1, giving ECONNREFUSED ::1.
            cdp_url = self.cdp_url.replace("://localhost", "://127.0.0.1")
            try:
                browser = self._pw.chromium.connect_over_cdp(cdp_url)
            except Exception as exc:
                raise RuntimeError(
                    f"Could not connect to Chrome at {cdp_url}. Make sure you "
                    f"(1) fully quit Chrome first, then (2) launched it with "
                    f"--remote-debugging-port=9222 --user-data-dir=/tmp/pp-chrome, "
                    f"and (3) left that window open. Verify with: "
                    f"curl {cdp_url}/json/version . Original error: {exc}"
                ) from exc
            self._ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
            return

        self._launch_persistent()

    def _launch_persistent(self) -> None:
        """Launch the persistent-context browser using current self.headful."""
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        launch_kwargs = dict(
            user_data_dir=str(self.profile_dir),
            headless=not self.headful,
            locale="en-US",
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        if self.channel:
            launch_kwargs["channel"] = self.channel
        if self.user_agent:  # only override if explicitly requested
            launch_kwargs["user_agent"] = self.user_agent
        if self.proxy:
            launch_kwargs["proxy"] = {"server": self.proxy}
        try:
            self._ctx = self._pw.chromium.launch_persistent_context(**launch_kwargs)
        except Exception:
            # Real Chrome not installed? Fall back to bundled Chromium.
            if self.channel:
                launch_kwargs.pop("channel", None)
                self._ctx = self._pw.chromium.launch_persistent_context(**launch_kwargs)
            else:
                raise
        # Hide the most obvious automation tell (patchright handles more).
        self._ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def close(self) -> None:
        # Don't close a browser we merely attached to over CDP.
        if self._ctx and not self.cdp_url:
            self._ctx.close()
        self._ctx = None
        if self._pw:
            self._pw.stop()
            self._pw = None

    # -- fetching ----------------------------------------------------------
    @staticmethod
    def _is_challenge(status: int, body: str) -> bool:
        return status != 200 or body.lstrip().startswith("<")

    def _navigate_and_poll(self, timeout: float) -> tuple[bool, str]:
        """Load the web app, then poll the API until cleared or timeout.

        Returns (cleared, last_response_snippet).
        """
        self._page.goto(WEB_APP_URL, wait_until="domcontentloaded", timeout=60000)
        self._page.wait_for_timeout(self.warmup_ms)
        deadline = time.monotonic() + timeout
        last = ""
        while time.monotonic() < deadline:
            resp = self._page.request.get(LEAGUES_URL, timeout=45000)
            body = resp.text()
            if not self._is_challenge(resp.status, body):
                self._clearance = json.loads(body)  # cache: often the first call
                return True, ""
            last = f"HTTP {resp.status}: {body[:160]}".replace("\n", " ")
            time.sleep(3)
        return False, last

    def _warmup(self) -> None:
        """Ensure the session is cleared past DataDome before fetching.

        Tries the current (usually headless) mode first. If that's blocked and
        auto_headful is on, it reopens a visible Chrome window so the user can
        solve the challenge once, then continues in the same command. The
        persistent profile remembers the clearance, so later runs are headless.
        """
        if self._warmed:
            return
        cleared, last = self._navigate_and_poll(self.clearance_timeout)

        can_open_window = self.auto_headful and not self.headful \
            and not self.cdp_url and sys.stdin.isatty()
        if not cleared and can_open_window:
            print("\nDataDome blocked the headless request. Opening a Chrome "
                  "window — solve any check there and it will continue "
                  "automatically...", flush=True)
            self.close()
            self._pw = self._sync_playwright().start()
            self.headful = True
            self.clearance_timeout = max(self.clearance_timeout, 180)
            self._launch_persistent()
            cleared, last = self._navigate_and_poll(self.clearance_timeout)

        if not cleared:
            raise DataDomeBlocked(
                f"Never cleared DataDome. Last response: {last}\n"
                "Try again on a residential IP, or use --unlocker for the paid path."
            )
        self._warmed = True

    def _get_json(self, url: str) -> dict:
        self._warmup()
        # Reuse the clearance probe result if it's the same endpoint.
        if url == LEAGUES_URL and getattr(self, "_clearance", None) is not None:
            payload, self._clearance = self._clearance, None
            time.sleep(self.request_delay)
            return payload
        resp = self._page.request.get(url, timeout=45000)
        body = resp.text()
        if self._is_challenge(resp.status, body):
            snippet = body[:200].replace("\n", " ")
            raise DataDomeBlocked(
                f"Blocked fetching {url} (HTTP {resp.status}). "
                f"DataDome served a challenge mid-session. Retry with "
                f"headful=True on a residential IP. Body: {snippet}"
            )
        time.sleep(self.request_delay)  # be polite between calls
        return json.loads(body)

    def fetch_leagues(self) -> dict:
        """Return the raw ``/leagues`` payload."""
        return self._get_json(LEAGUES_URL)

    def fetch_projections(
        self, league_id: int | str, per_page: int = 250, single_stat: bool = True
    ) -> dict:
        """Return the raw ``/projections`` payload for one league."""
        return self._get_json(projections_url(league_id, per_page, single_stat))

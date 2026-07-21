"""Command-line interface: ``prizepicks <command>``.

Commands:
    leagues                       List live league ids.
    scrape --league NBA           Fetch + parse + store projections.
    parse-file raw.json           Parse a saved raw payload (offline, no network).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .leagues import parse_leagues, resolve_league_id
from .parse import parse_projections
from .store import write_csv, write_json, write_sqlite


def _utcstamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _client(args):
    # Fully-automated backend: a web-unlocker API (no local browser).
    key = args.api_key or os.environ.get("PP_UNLOCKER_KEY")
    if args.unlocker:
        if not key:
            raise SystemExit("--unlocker needs an API key: pass --api-key or set "
                             "PP_UNLOCKER_KEY.")
        from .unlocker import UnlockerClient
        return UnlockerClient(
            provider=args.unlocker,
            api_key=key,
            template=args.unlocker_template,
        )
    # Browser backend (local Chrome / CDP-attach). Imported lazily so
    # `parse-file` and the unlocker path don't require Playwright.
    from .client import BrowserClient
    return BrowserClient(
        profile_dir=args.profile,
        headful=args.headful,
        proxy=args.proxy,
        cdp_url=args.cdp,
        channel=None if args.no_chrome else args.channel,
    )


def cmd_leagues(args) -> int:
    with _client(args) as client:
        payload = client.fetch_leagues()
    leagues = parse_leagues(payload)
    leagues.sort(key=lambda x: (x.get("name") or "").upper())
    for lg in leagues:
        active = "" if lg.get("active") in (None, True) else " (inactive)"
        print(f"{lg['id']:>6}  {lg.get('name') or lg.get('display_name')}{active}")
    print(f"\n{len(leagues)} leagues", file=sys.stderr)
    return 0


def _store_rows(rows, args) -> None:
    out = Path(args.out)
    ext = out.suffix.lower()
    if ext in (".db", ".sqlite", ".sqlite3"):
        n = write_sqlite(rows, out)
        print(f"Wrote {n} new rows -> {out} (SQLite, append-only)")
    elif ext == ".csv":
        n = write_csv(rows, out)
        print(f"Wrote {n} rows -> {out} (CSV)")
    else:
        n = write_json(rows, out)
        print(f"Wrote {n} rows -> {out} (JSON)")


def cmd_scrape(args) -> int:
    league_ids = [resolve_league_id(x) for x in args.league]
    scraped_at = _utcstamp()
    all_rows = []
    raw_dir = Path(args.save_raw) if args.save_raw else None

    with _client(args) as client:
        for lid in league_ids:
            payload = client.fetch_projections(lid, per_page=args.per_page)
            if raw_dir:
                raw_dir.mkdir(parents=True, exist_ok=True)
                rawf = raw_dir / f"league_{lid}_{scraped_at.replace(':', '-')}.json"
                rawf.write_text(json.dumps(payload))
            rows = parse_projections(payload, scraped_at=scraped_at)
            print(f"league {lid}: {len(rows)} projections", file=sys.stderr)
            all_rows.extend(rows)

    if not all_rows:
        print("No projections returned (off-season or blocked).", file=sys.stderr)
    _store_rows(all_rows, args)
    return 0


def cmd_parse_file(args) -> int:
    payload = json.loads(Path(args.file).read_text())
    rows = parse_projections(payload)
    _store_rows(rows, args)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="prizepicks", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profile", default=".pp_profile",
                   help="Browser profile dir (persists DataDome clearance).")
    p.add_argument("--headful", action="store_true",
                   help="Show the browser window (solve a challenge once).")
    p.add_argument("--proxy", default=None, help="Proxy URL, e.g. http://user:pass@host:port")
    p.add_argument("--cdp", default=None,
                   help="Attach to a running Chrome via CDP, e.g. http://localhost:9222 "
                        "(most reliable past DataDome; see README).")
    p.add_argument("--channel", default="chrome",
                   help="Browser channel to launch (default: real 'chrome').")
    p.add_argument("--no-chrome", action="store_true",
                   help="Use Playwright's bundled Chromium instead of real Chrome.")
    g = p.add_argument_group("fully-automated web-unlocker backend")
    g.add_argument("--unlocker", default=None,
                   choices=["zenrows", "scraperapi", "scrapingbee", "generic"],
                   help="Fetch via a web-unlocker API (residential proxies + "
                        "DataDome handled remotely; no local browser, no human).")
    g.add_argument("--api-key", default=None,
                   help="Unlocker API key (or set env PP_UNLOCKER_KEY).")
    g.add_argument("--unlocker-template", default=None,
                   help="For --unlocker generic: URL template with {url} and {key}.")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("leagues", help="List live league ids.")
    sp.set_defaults(func=cmd_leagues)

    sp = sub.add_parser("scrape", help="Fetch, parse and store projections.")
    sp.add_argument("--league", "-l", nargs="+", required=True,
                    help="League name(s) or id(s), e.g. NBA NFL 7")
    sp.add_argument("--out", "-o", default="projections.db",
                    help="Output file: .db/.sqlite, .csv, or .json")
    sp.add_argument("--per-page", type=int, default=250)
    sp.add_argument("--save-raw", default=None,
                    help="Also save raw JSON payloads to this dir.")
    sp.set_defaults(func=cmd_scrape)

    sp = sub.add_parser("parse-file", help="Parse a saved raw payload (offline).")
    sp.add_argument("file", help="Path to a raw /projections JSON file.")
    sp.add_argument("--out", "-o", default="projections.csv")
    sp.set_defaults(func=cmd_parse_file)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # keep CLI output clean; no traceback dump
        # DataDomeBlocked lives in client (imported lazily); match by name.
        name = type(exc).__name__
        if name == "DataDomeBlocked":
            print(f"\nBlocked by DataDome bot protection.\n{exc}\n\n"
                  "Tips:\n"
                  "  * Fully automated: --unlocker zenrows --api-key ... (residential\n"
                  "    proxies + DataDome handled remotely; no browser, no human).\n"
                  "  * Or --proxy http://user:pass@host:port with a residential proxy.\n"
                  "  * Or --headful and solve the challenge once (.pp_profile/ remembers).",
                  file=sys.stderr)
            return 2
        if name == "UnlockerError":
            print(f"\nWeb-unlocker request failed.\n{exc}\n\n"
                  "Tips:\n"
                  "  * Check the API key and that your plan has the residential /\n"
                  "    antibot tier enabled (DataDome needs it).\n"
                  "  * Some providers need higher tiers (e.g. ScraperAPI ultra_premium).",
                  file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main())

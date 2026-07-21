# prizepicks-scraper

Fetch and parse [PrizePicks](https://www.prizepicks.com) projections (player prop
lines) into clean, timestamped rows you can analyze. Handles the site's
**DataDome** bot protection by fetching through a real browser session, and
denormalizes PrizePicks' JSON:API response into flat records.

> ⚠️ **Read [Legal / responsible use](#legal--responsible-use) first.** This is
> for personal, educational use. PrizePicks has no public API and their Terms of
> Service prohibit automated access. Use gently and at your own risk.

## What it does

- Pulls the undocumented `api.prizepicks.com/projections` endpoint the web app uses.
- Gets past **DataDome** by driving a real Chromium session (Playwright) and
  fetching the API through that authenticated context — no fragile cookie
  transplanting.
- Denormalizes the JSON:API `data` + `included` structure into flat rows:
  player, team, position, league, stat type, line, `odds_type`
  (`standard` / `demon` / `goblin`), start time, status.
- Stores **append-only, timestamped snapshots** to SQLite (or CSV / JSON) so you
  can track line movement over time.

## Install

```bash
git clone <your-repo-url> prizepicks-scraper
cd prizepicks-scraper
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install chromium      # one-time browser download
```

## Usage

### List live league ids
```bash
prizepicks leagues
```

### Scrape projections
```bash
# One league to SQLite (append-only snapshots)
prizepicks scrape --league NBA --out data/projections.db

# Multiple leagues, by name or numeric id, to CSV
prizepicks scrape --league NBA NFL 2 --out data/props.csv

# Also keep the raw JSON payloads (great for re-parsing / debugging)
prizepicks scrape --league NBA --out data/projections.db --save-raw raw/
```

## Fully automated (no human in the loop)

`api.prizepicks.com` is behind **DataDome**, which blocks on **IP reputation +
browser fingerprint**. Hands-off operation therefore requires a *trusted
residential IP* — there is no free, purely-local bypass. Two automated options:

### Option A — Web-unlocker API (most efficient, no browser)
One request per fetch; the service runs residential proxies + a real browser +
DataDome solving remotely and returns the JSON. Works headless, unattended, e.g.
from `cron`. Providers offer free trial credits.

```bash
export PP_UNLOCKER_KEY=your_key_here
prizepicks --unlocker zenrows     scrape --league NBA NFL --out data/props.db
prizepicks --unlocker scraperapi  scrape --league NBA     --out data/props.db
# any other provider via a URL template:
prizepicks --unlocker generic --unlocker-template \
  'https://api.provider.com/?token={key}&render=true&url={url}' \
  scrape --league NBA -o data/props.db
```
Supported presets (`--unlocker`): `zenrows`, `scraperapi`, `scrapingbee`,
`generic`. Make sure your plan has the **residential / antibot** tier enabled —
DataDome needs it (ScraperAPI: `ultra_premium`; ZenRows: `premium_proxy` +
`antibot`; both are set for you). Bright Data / Oxylabs unlockers are used as
proxies — plug their endpoint into `--proxy` on the browser backend below.

### Option B — Residential proxy + built-in stealth browser
Run the local browser (real Chrome + [patchright]) through a **residential**
proxy, headless and unattended. On a clean residential IP DataDome usually
passes with no challenge:
```bash
prizepicks --proxy http://user:pass@residential-host:port \
  scrape --league NBA --out data/projections.db
```

Rough guide: a web-unlocker is simplest and most reliable (~$1.5–5 per 1k
requests); a residential proxy is cheaper at volume (~$/GB, and the board JSON
is tiny) but you own the stealth. Both are fully hands-off.

---

### Manual / interactive fallbacks

If you'd rather not pay for a proxy/unlocker, these need a one-time human step.
`api.prizepicks.com` fingerprints automation aggressively; escalate in order:

**1. Real Chrome + patched driver (default).** By default the tool launches your
real installed Chrome (`--channel chrome`) and auto-uses
[patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) if installed
(removes the automation leaks DataDome keys on):
```bash
pip install patchright && patchright install chromium
prizepicks --headful scrape --league NBA --out data/projections.db
```

**2. Attach to your own Chrome over CDP (most reliable).** Drive your genuine
browser past the wall yourself, then let the tool fetch through that session —
real fingerprint, real cookies. Fully quit Chrome first, then:
```bash
# macOS (use a scratch profile so it can enable remote debugging):
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 --user-data-dir=/tmp/pp-chrome

# In that Chrome window, browse to https://app.prizepicks.com and make sure the
# board loads (solve any challenge). Then, in another terminal:
prizepicks --cdp http://localhost:9222 scrape --league NBA --out data/projections.db
```

**3. Change IP / go automated.** Datacenter/VPN IPs (and IPs just flagged by
repeated attempts) are blocked. Wait for a cooldown, switch networks, or use the
[fully-automated](#fully-automated-no-human-in-the-loop) residential options above.

> DataDome evasion is an arms race — no method is guaranteed, and what works can
> change. CDP-attach is the most durable free method (nothing is synthetic); a
> web-unlocker is the most reliable automated one.

[patchright]: https://github.com/Kaliiiiiiiiii-Vinyzu/patchright

### Parse a saved payload offline (no network, no browser)
```bash
prizepicks parse-file raw/league_7_2026-07-20.json --out out.csv
```

Output columns: `projection_id, scraped_at, league, league_id, player_id,
player_name, team, position, stat_type, line_score, odds_type, start_time,
status, description, is_promo`.

## Use as a library

```python
from prizepicks_scraper import parse_projections
from prizepicks_scraper.client import BrowserClient

with BrowserClient(headful=True) as client:
    payload = client.fetch_projections("NBA")   # or a numeric id
rows = parse_projections(payload)
for r in rows[:5]:
    print(r.player_name, r.stat_type, r.line_score, r.odds_type)
```

## How it works

```
app.prizepicks.com  ──(Playwright, real browser)──►  DataDome clearance cookie
        │                                                   │
        ▼                                                   ▼
api.prizepicks.com/projections  ◄── page.request.get (same authenticated ctx)
        │
        ▼
JSON:API  { data:[projection…], included:[new_player, league, stat_type…] }
        │
   parse.py  (join data ↔ included by (type,id))
        │
        ▼
flat Projection rows ──►  SQLite / CSV / JSON  (append-only, timestamped)
```

- `client.py` — browser-backed fetcher (persistent profile keeps you cleared).
- `parse.py` — JSON:API denormalizer. **Fully unit-tested against fixtures**, so
  the data pipeline is verifiable offline even when the live site is unreachable.
- `store.py` — SQLite (append-only, PK `projection_id + scraped_at`) / CSV / JSON.
- `leagues.py`, `models.py`, `cli.py`.

## Development

```bash
pip install -e ".[dev]"
pytest           # parser + storage tests run offline, no network
```

## Legal / responsible use

- PrizePicks provides **no public API**; their
  [Terms of Service](https://www.prizepicks.com/help-center/terms-of-service)
  prohibit automated access/scraping. This project is provided for **personal,
  educational** use only and is **not affiliated with or endorsed by PrizePicks**.
- Only public board data is fetched — **do not** use this to access an account,
  place entries, or defeat security measures.
- Be polite: the scraper is single-threaded with a delay between requests. Don't
  hammer the endpoint.
- Anti-bot protection and the endpoint shape can change at any time and break
  this tool. Expect maintenance.
- If you need reliable, licensed PrizePicks lines for anything serious, use a
  commercial odds API (e.g. OpticOdds, The Odds API) instead.
- MIT licensed — no warranty. You are responsible for how you use it.

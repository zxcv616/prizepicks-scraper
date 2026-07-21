# prizepicks-scraper

![pps interactive shell](assets/banner.png)

Fetch PrizePicks projections (player prop lines) and store them as clean,
timestamped rows. Handles the site's DataDome bot protection and denormalizes
the JSON:API response into flat records you can query.

Personal/educational use. Not affiliated with PrizePicks. See [Notes](#notes).

## Install

```bash
git clone https://github.com/zxcv616/prizepicks-scraper
cd prizepicks-scraper
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

For the local-browser backend only (not needed for the unlocker backend):

```bash
pip install playwright patchright && playwright install chromium
```

## Usage

Two equivalent ways: an interactive shell, or direct commands.

### Interactive shell

Run with no arguments to open the shell:

```
$ pps

pps ❯ set unlocker zenrows
pps ❯ scrape LoL CS2
pps ❯ show
pps ❯ exit
```

- `leagues` - list league ids
- `scrape <league...>` - fetch and store (names or ids: `scrape LoL 2 CS2`)
- `results [league] [N]` - show recent scraped rows (`results LoL 20`)
- `set <key> <value>` - change a setting (`set out data/lol.csv`, `set unlocker zenrows`)
- `show` - print current settings
- `help`, `exit`

### Direct commands

```bash
pps leagues
pps scrape --league LoL CS2 --out data/projections.db
pps scrape --league MLB --out data/mlb.csv
pps parse-file raw.json --out out.csv     # parse a saved payload, offline
```

Output format follows the file extension: `.db`/`.sqlite` (SQLite, append-only
snapshots), `.csv`, or `.json`.

## Getting data past DataDome

`api.prizepicks.com` blocks on IP reputation + browser fingerprint, so you need
a trusted residential IP. Pick one backend.

### Web-unlocker API (recommended, fully automated)

One API call per fetch; residential proxies and DataDome handled remotely. No
browser, no manual steps. Works headless and on a schedule.

```bash
export PP_UNLOCKER_KEY=your_key
pps --unlocker zenrows scrape --league LoL --out data/projections.db
```

Providers: `zenrows`, `scraperapi`, `scrapingbee`, or `generic` with
`--unlocker-template 'https://api.provider.com/?token={key}&url={url}'`.
The residential/antibot tier each provider needs is enabled automatically.

### Local browser

Runs real Chrome via Playwright. Needs a residential IP to pass reliably.

```bash
# Residential proxy, headless, unattended:
pps --proxy http://user:pass@host:port scrape --league LoL -o data/props.db

# Or attach to a Chrome you drive yourself (most reliable, one-time manual):
#   1. /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
#        --remote-debugging-port=9222 --user-data-dir=/tmp/pp-chrome
#   2. In that window, load https://app.prizepicks.com
pps --cdp http://127.0.0.1:9222 scrape --league LoL -o data/props.db
```

## Output columns

`projection_id, scraped_at, league, league_id, player_id, player_name, team,
position, stat_type, line_score, odds_type, start_time, status, description,
is_promo`

`odds_type` is `standard`, `demon`, or `goblin` (the last two are
payout-adjusted lines). Rows are keyed by `(projection_id, scraped_at)`, so
re-running builds a history of line movement.

Query a SQLite result:

```bash
sqlite3 data/projections.db "select player_name, stat_type, line_score, odds_type
  from projections limit 10"
```

## Library use

```python
from prizepicks_scraper import parse_projections
from prizepicks_scraper.unlocker import UnlockerClient

with UnlockerClient("zenrows", api_key="...") as c:
    payload = c.fetch_projections("LoL")
for r in parse_projections(payload):
    print(r.player_name, r.stat_type, r.line_score, r.odds_type)
```

## Development

```bash
pip install -e ".[dev]"
pytest            # runs offline, no network
```

## Notes

- No public API exists; PrizePicks' Terms of Service prohibit automated access.
  This is for personal, educational use only. Fetches public board data only -
  no accounts, no entries.
- Keep requests gentle. The scraper is single-threaded with a delay between calls.
- Anti-bot protection and the endpoint can change and break this tool.
- Never commit your API key. Pass it via `PP_UNLOCKER_KEY` or `--api-key`.
- MIT licensed. No warranty. You are responsible for how you use it.
```

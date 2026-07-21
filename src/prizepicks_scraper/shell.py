"""Interactive shell (REPL) for prizepicks.

Launched when ``prizepicks`` is run with no subcommand. Holds backend/output
settings as session state you can change with ``set``, and dispatches to the
same command functions as the direct CLI, so behavior is identical either way.
"""
from __future__ import annotations

import argparse
import cmd
import os
import re
import shlex
import shutil
import sys

from . import __version__
from .cli import cmd_leagues, cmd_parse_file, cmd_scrape, run_command

# --- terminal styling (no dependencies) -------------------------------------
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _use_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(code: str) -> str:
    return f"\x1b[{code}m" if _use_color() else ""


ORANGE = "38;5;208"
DIM = "2"
BOLD = "1"
RESET = "0"

# Block-letter "pps".
_LOGO = r"""
 ██████╗  ██████╗  ███████╗
 ██╔══██╗ ██╔══██╗ ██╔════╝
 ██████╔╝ ██████╔╝ ███████╗
 ██╔═══╝  ██╔═══╝  ╚════██║
 ██║      ██║      ███████║
 ╚═╝      ╚═╝      ╚══════╝
""".strip("\n").splitlines()


def _vis_len(s: str) -> int:
    """Visible length, ignoring ANSI color codes."""
    return len(_ANSI_RE.sub("", s))


def _banner(state: dict) -> str:
    width = min(shutil.get_terminal_size((80, 24)).columns, 80)
    inner = width - 2
    o, d, b, r = _c(ORANGE), _c(DIM), _c(BOLD), _c(RESET)

    title = f"{b}{o}pps{r}{d} v{__version__}{r}"
    right = [
        f"{b}prizepicks-scraper{r}",
        f"{d}PrizePicks projections scraper{r}",
    ]
    backend = state["unlocker"] or ("cdp" if state["cdp"] else "browser")

    # Assemble the content rows: logo on the left, labels on the right.
    rows: list[str] = [""]
    for i, line in enumerate(_LOGO):
        rlabel = right[i - 1] if 1 <= i <= len(right) else ""
        rows.append(f"  {o}{line}{r}   {rlabel}")
    rows += [
        "",
        f"  {d}backend{r} {backend}    {d}output{r} {state['out']}",
        f"  {d}commands{r} leagues · scrape <league...> · set · show · help · exit",
        "",
    ]

    # Draw the rounded box, padding each row to the inner width.
    top = f"{o}╭─{r} {title} {o}" + "─" * max(0, inner - _vis_len(title) - 3) + f"╮{r}"
    out = [top]
    for row in rows:
        pad = max(0, inner - _vis_len(row))
        out.append(f"{o}│{r}{row}{' ' * pad}{o}│{r}")
    out.append(f"{o}╰{'─' * inner}╯{r}")
    return "\n".join(out)

# Session settings and their defaults. `set <key> <value>` changes these.
_DEFAULTS = {
    "unlocker": None,        # zenrows | scraperapi | scrapingbee | generic | None
    "api_key": None,         # falls back to $PP_UNLOCKER_KEY
    "unlocker_template": None,
    "out": "data/projections.db",
    "per_page": 250,
    "save_raw": None,
    "proxy": None,
    "cdp": None,
    "profile": ".pp_profile",
    "headful": False,
    "channel": "chrome",
    "no_chrome": False,
}

_BOOL_KEYS = {"headful", "no_chrome"}
_INT_KEYS = {"per_page"}


def _initial_state(args) -> dict:
    """Seed session state from any global flags passed at launch."""
    state = dict(_DEFAULTS)
    for k in state:
        v = getattr(args, k, None)
        if v is not None and v != argparse.SUPPRESS:
            state[k] = v
    return state


class PrizePicksShell(cmd.Cmd):
    intro = ""  # printed manually in run_shell so we can style it

    def __init__(self, args):
        super().__init__()
        self.state = _initial_state(args)
        # Styled prompt. Non-printing sequences are wrapped in \001..\002 so
        # readline counts the visible width correctly.
        if _use_color():
            self.prompt = f"\001\x1b[{ORANGE}m\002pps ❯\001\x1b[0m\002 "
        else:
            self.prompt = "pps> "

    # -- helpers -----------------------------------------------------------
    def _ns(self, **overrides) -> argparse.Namespace:
        """Build an args namespace from session state + per-command overrides."""
        data = dict(self.state)
        data.update(overrides)
        return argparse.Namespace(**data)

    def _run(self, func, **overrides) -> None:
        ns = self._ns(func=func, **overrides)
        try:
            run_command(ns)
        except Exception as exc:  # never kill the shell on an error
            print(f"error: {exc}", file=sys.stderr)

    # -- commands ----------------------------------------------------------
    def do_leagues(self, arg):
        "leagues            List live league ids."
        self._run(cmd_leagues)

    def do_scrape(self, arg):
        "scrape LoL CS2 ..  Fetch, parse and store projections for the given leagues."
        leagues = shlex.split(arg)
        if not leagues:
            print("usage: scrape <league> [league ...]   e.g. scrape LoL CS2 MLB")
            return
        self._run(cmd_scrape, league=leagues)

    def do_parse_file(self, arg):
        "parse-file PATH    Parse a saved raw JSON payload (offline)."
        parts = shlex.split(arg)
        if not parts:
            print("usage: parse-file <path.json>")
            return
        self._run(cmd_parse_file, file=parts[0],
                  out=parts[1] if len(parts) > 1 else self.state["out"])

    def do_set(self, arg):
        "set KEY VALUE      Change a setting (e.g. set unlocker zenrows, set out mlb.csv)."
        parts = shlex.split(arg)
        if len(parts) < 2:
            print("usage: set <key> <value>   (see 'show' for keys)")
            return
        key, value = parts[0], " ".join(parts[1:])
        if key not in self.state:
            print(f"unknown setting '{key}'. keys: {', '.join(self.state)}")
            return
        if key in _BOOL_KEYS:
            value = value.lower() in ("1", "true", "yes", "on")
        elif key in _INT_KEYS:
            value = int(value)
        elif value.lower() in ("none", "null", ""):
            value = None
        self.state[key] = value
        print(f"{key} = {self._display(key, value)}")

    def do_show(self, arg):
        "show               Show current settings."
        for k in self.state:
            print(f"  {k:18} {self._display(k, self.state[k])}")

    do_config = do_show

    def _display(self, key, value):
        if key == "api_key":
            eff = value or os.environ.get("PP_UNLOCKER_KEY")
            if not eff:
                return "(unset)"
            return "****" + eff[-4:] + (" (from $PP_UNLOCKER_KEY)" if not value else "")
        return "(unset)" if value is None else value

    def do_exit(self, arg):
        "exit               Quit."
        return True

    do_quit = do_exit

    def do_EOF(self, arg):
        print()
        return True

    def parseline(self, line):
        # Allow hyphenated command names, e.g. `parse-file` -> `parse_file`.
        # Rewrite the leading token before cmd's own tokenizer splits on "-".
        head, sep, rest = line.strip().partition(" ")
        if head and "-" in head:
            line = head.replace("-", "_") + sep + rest
        return super().parseline(line)

    def emptyline(self):
        pass  # do nothing on empty input

    def default(self, line):
        print(f"unknown command: {line.split()[0]!r}. type 'help'.")


def run_shell(args) -> int:
    if not sys.stdin.isatty():
        # Non-interactive stdin with no command: show usage instead of hanging.
        from .cli import build_parser
        build_parser().print_help()
        return 0
    shell = PrizePicksShell(args)
    if _use_color():
        sys.stdout.write("\x1b[2J\x1b[3J\x1b[H")  # clear screen + scrollback
    print(_banner(shell.state))
    print()
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        print()
    return 0

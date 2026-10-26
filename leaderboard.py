"""
leaderboard.py

A local leaderboard, stored as a JSON file next to the game. No server,
no internet - it just needs to survive between play sessions on the
Batocera box.

One entry per PLAYER per match (a 2-player match produces two entries,
one per player, each with their own name and score - so both players'
personal bests rank against everyone else's in the "2 spelers" board).

File format (leaderboard.json):
[
  {"id": "a1b2c3...", "name": "Emma", "score": 890, "mode": "1",
   "game": "klok", "tables": [1,2,3], "som_type": "Keer (x)",
   "date": "2026-09-26T14:03:00"},   (Memory and Hoeden rows also carry "time_ms";
                                       Plus en min rows carry "exercises": ["te_plus_e_to20_zb", ...]
                                       with "tables": [] and "som_type": "Plus en min")
  ...
]

Self-healing: earlier versions of this game used different schemas
(no "players"/"name"/"mode"/"id"/"game" fields at all, at various
points - "game" was added when Ballon joined Klok as a second
minigame). load() fills in sensible defaults for anything missing and
re-saves once, so an old leaderboard.json never crashes the game - it
just gets quietly migrated the first time it's read. Entries written
before "game" existed default to "klok", the only game there was then.
"""

import json
import os
import paths
import uuid
from datetime import datetime, timedelta

# The students' scores: written by the game, must survive restarts (see paths.py).
DEFAULT_PATH = paths.data_path("leaderboard.json")

PERIOD_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}  # "all" = no cutoff

# Games where a LOWER score is better (Memory counts turns). Every other
# game counts points, where higher is better.
LOWER_IS_BETTER = {"memory"}

# Co-op games: both players share one match and one leaderboard row, named
# "Jan & Sam". main.py reads this too, so there is one list to maintain.
COOP_GAMES = {"memory"}


def format_time(ms):
    """A hidden-timer value as m:ss, or "-" for rows that have none (all
    data from before the timers existed). Shared by the leaderboard screen
    and the name-entry screen so both always show the same thing."""
    if ms is None:
        return "-"
    total_seconds = int(ms // 1000)
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


def _name_key(entry):
    """What counts as "the same player(s)" when collapsing repeat names.
    Case and surrounding spaces never matter ("Emma" == "emma "). For a
    co-op pair the ORDER does not matter either: "Jan & Sam" and
    "Sam & Jan" are the same pair. (The on-screen keyboard has no "&" key,
    so a real name can never contain one and be split by mistake.)"""
    name = entry["name"].strip().lower()
    if entry.get("game") in COOP_GAMES and "&" in name:
        return " & ".join(sorted(part.strip() for part in name.split("&")))
    return name


def _rank_key(entry):
    """Sort key: the entry with the SMALLEST key ranks first.

    Memory: fewer turns first, then the hidden time as tie-breaker
    (turns always win: 10 turns in 5 min beats 12 turns in 2 min).
    Other games: higher score first. Hoeden also stores a hidden time, and
    there too it only breaks ties (less time ranks higher). Entries
    without a time (all old data) sort after entries with one when
    everything else is equal.
    """
    time_ms = entry.get("time_ms")
    time_key = float("inf") if time_ms is None else time_ms
    if entry.get("game") in LOWER_IS_BETTER:
        return (entry["score"], time_key)
    return (-entry["score"], time_key)


def _normalize_entry(raw):
    """Fills in anything missing from an older schema version so nothing
    ever KeyErrors on a file written by a previous version of this game."""
    changed = False
    entry = dict(raw)

    if "id" not in entry:
        entry["id"] = uuid.uuid4().hex
        changed = True
    if "name" not in entry:
        entry["name"] = "Speler"
        changed = True
    if "mode" not in entry:
        # Best guess from whatever old data is present.
        players = entry.get("players")
        if isinstance(players, dict) and len(players) == 2:
            entry["mode"] = "2"
        else:
            entry["mode"] = "1"
        changed = True
    if "score" not in entry:
        entry["score"] = 0
        changed = True
    if "tables" not in entry:
        entry["tables"] = []
        changed = True
    if "som_type" not in entry:
        entry["som_type"] = ""
        changed = True
    if "game" not in entry:
        entry["game"] = "klok"  # the only game that existed before Ballon
        changed = True
    if "date" not in entry:
        entry["date"] = datetime.now().isoformat(timespec="seconds")
        changed = True
    entry.pop("players", None)  # superseded by one-row-per-player + "mode"
    # Plus en min rows list their exercise types; anything malformed is dropped
    # (rows from before Plus en min simply have no such field - and keep none).
    if "exercises" in entry:
        ex = entry["exercises"]
        if isinstance(ex, list) and all(isinstance(k, str) for k in ex) and ex:
            entry["exercises"] = sorted(ex)
        else:
            entry.pop("exercises")
            changed = True

    return entry, changed


def load(path=DEFAULT_PATH):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_entries = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    entries = []
    any_changed = False
    for raw in raw_entries:
        entry, changed = _normalize_entry(raw)
        entries.append(entry)
        any_changed = any_changed or changed

    if any_changed:
        _save(entries, path)  # migrate the file once, quietly

    return entries


def _save(entries, path=DEFAULT_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def add_score(name, score, mode, tables, som_type, game="klok", time_ms=None,
              exercises=None, path=DEFAULT_PATH):
    """mode: "1" or "2" (as a string, matching num_players). game: "klok"
    or "ballon" - keeps the two minigames' scores from ever mixing, since
    their scoring models aren't comparable. One call per player - a
    2-player match calls this twice, once per player (except co-op games
    like Memory, where main.py makes ONE call for the pair).
    time_ms: optional hidden play time, used only as tie-breaker.
    exercises: the ticked Plus en min exercise keys (then tables is [] and
    som_type is "Plus en min"); leave None for the multiplication tables."""
    entries = load(path)
    entry = {
        "id": uuid.uuid4().hex,
        "name": name.strip() or "Speler",
        "score": score,
        "mode": str(mode),
        "game": game,
        "tables": sorted(tables),
        "som_type": som_type,
        "date": datetime.now().isoformat(timespec="seconds"),
    }
    # The hidden Memory timer. Only stored when there is one, so old rows
    # (and games without a timer) keep their exact shape.
    if time_ms is not None:
        entry["time_ms"] = int(time_ms)
    if exercises:
        entry["exercises"] = sorted(exercises)
    entries.append(entry)
    _save(entries, path)
    return entries


def top(n=10, mode=None, game=None, period="all", tables=None, som_type=None,
        unique_names=False, path=DEFAULT_PATH, exercises=None):
    """mode: "1", "2", or None for both. game: "klok", "ballon", or None
    for both (leaderboard_screen.py always passes the game just played,
    same reasoning as tables/som_type below - Klok's draining-bank score
    and Ballon's +10-per-pop score aren't comparable). period: "day"/
    "week"/"month"/"year"/"all". tables + som_type: when both given,
    only entries whose table-set and exercise type EXACTLY match are
    included - comparing a "tables [2]" run against a "tables [1..10]"
    run isn't a fair ranking, so leaderboard_screen.py always passes
    these for an honest, lesson-specific board rather than one mixed bag
    of every combination ever played.

    exercises: a list of Plus en min exercise keys. When given, only entries
    with EXACTLY that exercise selection are included (same reasoning as the
    tables: "E + E ZB" alone and "E + E ZB + TE + E ZB" are different
    lessons) - and the tables/som_type filters are not used for them. Without
    it, Plus en min entries never show up on a tables board (a tables filter
    excludes them); calls with no filter at all, like the admin overlay's
    list, still see every entry.

    unique_names: when True, collapses repeat names down to each
    name's single best entry before ranking - for kids who play the
    same combination over and over, so the board shows ten different
    names instead of one enthusiastic kid's last ten attempts. Matching
    is case/whitespace-insensitive ("Emma" and "emma " are the same
    person), and for co-op games the order of a pair doesn't matter
    ("Jan & Sam" == "Sam & Jan"); the row shows the best attempt's name
    as it was typed. Each returned entry also gets an "attempts" field: how many
    total tries that name has within this same filtered view - since the
    table/type filter is now exact, that's a more useful column than
    repeating the table list on every row. Leave unique_names False for
    admin/delete views, where every individual attempt needs to stay
    visible so a specific cheated run can still be found and removed."""
    entries = load(path)

    if mode is not None:
        entries = [e for e in entries if e["mode"] == str(mode)]

    if game is not None:
        entries = [e for e in entries if e["game"] == game]

    if exercises is not None:
        wanted_ex = sorted(exercises)
        entries = [e for e in entries if e.get("exercises") == wanted_ex]
    elif tables is not None:
        # A tables board never contains Plus en min rows (their "tables" is
        # empty, which would otherwise match an empty tables filter).
        entries = [e for e in entries if not e.get("exercises")]

    if tables is not None and exercises is None:
        wanted = sorted(tables)
        entries = [e for e in entries if sorted(e["tables"]) == wanted]

    if som_type is not None and exercises is None:
        entries = [e for e in entries if e["som_type"] == som_type]

    if period != "all" and period in PERIOD_DAYS:
        cutoff = datetime.now() - timedelta(days=PERIOD_DAYS[period])
        entries = [e for e in entries
                   if _safe_parse_date(e["date"]) >= cutoff]

    if unique_names:
        best_per_name = {}
        attempt_counts = {}
        for e in entries:
            key = _name_key(e)
            attempt_counts[key] = attempt_counts.get(key, 0) + 1
            current_best = best_per_name.get(key)
            if current_best is None or _rank_key(e) < _rank_key(current_best):
                best_per_name[key] = e
        entries = []
        for key, e in best_per_name.items():
            e = dict(e)  # copy - never mutate the stored record
            e["attempts"] = attempt_counts[key]
            entries.append(e)

    return sorted(entries, key=_rank_key)[:n]


def _safe_parse_date(date_str):
    try:
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return datetime.min


def delete_entry(entry_id, path=DEFAULT_PATH):
    """Removes exactly one entry by its id - for pulling a single cheated
    score without wiping the whole board. Returns True if something was
    actually removed."""
    entries = load(path)
    new_entries = [e for e in entries if e["id"] != entry_id]
    removed = len(new_entries) != len(entries)
    if removed:
        _save(new_entries, path)
    return removed


def reset_all(mode=None, game=None, path=DEFAULT_PATH):
    """Wipes the leaderboard. mode=None and game=None wipes everything;
    passing either narrows what gets wiped (e.g. mode="1", game="ballon"
    wipes only the 1-player Ballon board, leaving Klok and 2-player
    Ballon untouched)."""
    if mode is None and game is None:
        _save([], path)
        return
    entries = load(path)
    entries = [e for e in entries
               if (mode is not None and e["mode"] != str(mode))
               or (game is not None and e["game"] != game)]
    _save(entries, path)

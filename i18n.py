"""
i18n.py - the app's language support.

Every piece of text the player sees comes from a LANGUAGE FILE: one small JSON
file per language in the lang/ folder (lang/nl.json, lang/en.json, ...). To add
a language, copy lang/en.json to lang/<code>.json, translate the values, and
that is all - the language then shows up on the language button of the
choice screen by itself. docs/TRANSLATING.md has the full guide (including a
prompt to hand to an AI assistant), and `python check_translation.py <code>`
checks a translation file for mistakes.

Using it in code:

    from i18n import t
    t("choice.start")                       -> "Start"
    t("hud.round", n=3, total=10)           -> "Ronde 3 / 10"   (or "Round 3 / 10")

LOOKUP: the current language, then English, then the key itself. So a
half-finished translation never crashes anything: missing texts simply show
up in English, and a typo in a key shows the key (easy to spot).

WHAT IS *NOT* TRANSLATED: internal ids that are saved in settings.json and on
the leaderboard (such as the exercise type "Keer (x)" or exercise keys like
"te_plus_e_to20_zb"). Only what is DISPLAYED is translated, so switching
language never invalidates saved scores, and old files keep working.
"""

import json
import os
import re

import paths

# The languages that ship with the game (read-only; inside the app when packaged).
LANG_DIR = paths.resource_path("lang")
# A folder named "lang" next to the game's settings (see paths.py) is read TOO,
# after the built-in one: drop a new language file in there to add a language to
# an installed/packaged game without rebuilding it - or to improve a built-in
# one (a file with the same code replaces it).
def _user_lang_dir():
    return paths.data_path("lang")

# Language used on the very first start, before anything is saved. Change to
# "en" for an English-speaking classroom.
DEFAULT_LANGUAGE = "nl"
# Texts missing from a language are shown in this one.
FALLBACK_LANGUAGE = "en"

_tables = None            # code -> {key: text}, loaded on first use
_current = DEFAULT_LANGUAGE


def _load_all():
    """Read every lang/*.json. A broken file is skipped with a message on the
    console (the game must start even if someone's translation has a typo)."""
    global _tables
    _tables = {}
    folders = [LANG_DIR]
    user_dir = _user_lang_dir()
    if os.path.abspath(user_dir) != os.path.abspath(LANG_DIR):
        folders.append(user_dir)            # read last, so it can add or replace languages
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for filename in sorted(os.listdir(folder)):
            if not filename.endswith(".json") or filename.startswith("_"):
                continue
            code = filename[:-5]
            try:
                with open(os.path.join(folder, filename), "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict) or not isinstance(data.get("_language_name"), str):
                    raise ValueError('missing "_language_name"')
                _tables[code] = {k: v for k, v in data.items() if isinstance(v, str)}
            except (OSError, ValueError) as e:
                print(f"[i18n] Skipping {os.path.join(folder, filename)}: {e}")


def reload():
    """Forget what was loaded and read lang/ again (used by tests and tools)."""
    global _tables
    _tables = None


def _ensure_loaded():
    if _tables is None:
        _load_all()


def available_languages():
    """[(code, native name)] for every language file found, ordered by code."""
    _ensure_loaded()
    return [(code, table["_language_name"]) for code, table in sorted(_tables.items())]


def table(code):
    """The raw {key: text} table of a language file (a copy), or None if there is none."""
    _ensure_loaded()
    return dict(_tables[code]) if code in _tables else None


def language():
    return _current


def language_name(code=None):
    _ensure_loaded()
    table = _tables.get(code or _current, {})
    return table.get("_language_name", code or _current)


def set_language(code):
    """Switch language. Returns False (and changes nothing) for an unknown code."""
    global _current
    _ensure_loaded()
    if code in _tables:
        _current = code
        return True
    return False


def next_language(code=None):
    """The code after `code` (default: the current one), wrapping around."""
    codes = [c for c, _ in available_languages()]
    if not codes:
        return code or _current
    code = code or _current
    if code not in codes:
        return codes[0]
    return codes[(codes.index(code) + 1) % len(codes)]


def t(key, **values):
    """The text for `key` in the current language ({placeholders} filled in)."""
    _ensure_loaded()
    text = _tables.get(_current, {}).get(key)
    if text is None:
        text = _tables.get(FALLBACK_LANGUAGE, {}).get(key, key)
    if values:
        try:
            return text.format(**values)
        except (KeyError, IndexError, ValueError):
            return text           # a broken placeholder must never crash a screen
    return text


# --------------------------------------------------------------------------
# Exercise labels (the chips): "TE + E" over "MB".
# The exercise types are defined with the Dutch abbreviations (E = eenheid,
# T = tiental, TE, ZB = zonder brug, MB = met brug). To show them in another
# language every abbreviation is looked up as a token in the language file
# (exercise.token.E, ...), so "TE + E / MB" can become "TU + U / WB".
_TOKEN = re.compile(r"\b(TE|T|E|ZB|MB)\b")


def localize_exercise_text(text):
    """Replace the abbreviations in an exercise label by the current language's."""
    return _TOKEN.sub(lambda m: t(f"exercise.token.{m.group(1)}"), text)


def exercise_lines(etype):
    """(line 1, line 2) of an exercise type's chip label in the current language."""
    return localize_exercise_text(etype.line1), localize_exercise_text(etype.line2)


def exercise_label(etype):
    line1, line2 = exercise_lines(etype)
    return f"{line1} {line2}".strip()


# --------------------------------------------------------------------------
# Checking a translation (used by check_translation.py and the tests)
_PLACEHOLDER = re.compile(r"\{(\w*)\}")


def placeholders(text):
    return sorted(set(_PLACEHOLDER.findall(text)))


def validate(code):
    """Compare lang/<code>.json with the English reference.
    Returns a dict of problem lists: missing, extra, placeholders (mismatch),
    empty. All empty lists = a good translation."""
    _ensure_loaded()
    reference = _tables.get(FALLBACK_LANGUAGE, {})
    table = _tables.get(code)
    if table is None:
        raise KeyError(f"no language file for {code!r}")
    keys = lambda tbl: {k for k in tbl if not k.startswith("_")}
    return {
        "missing": sorted(keys(reference) - keys(table)),
        "extra": sorted(keys(table) - keys(reference)),
        "placeholders": sorted(k for k in keys(reference) & keys(table)
                               if placeholders(reference[k]) != placeholders(table[k])),
        "empty": sorted(k for k in keys(table) if not table[k].strip()),
    }

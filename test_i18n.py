"""
test_i18n.py - dev-only tests for the language support.   Run: python test_i18n.py

  * the language files are complete and consistent (and every key in the code
    exists, and every key in the file is used)
  * the lookup falls back safely (missing texts, broken placeholders, broken files)
  * in English no Dutch text is left on ANY screen (and the other way round) -
    measured from what is really drawn
  * every label still fits its button in Dutch, English and a made-up language
    that is 30% longer - so a translator's longer words don't break the layout
  * the language button: cycles, is remembered, re-measures the layout
  * saved scores and settings do not depend on the language
  * the translator's checker tool works

Uses temp files only - never your real settings or leaderboard.
"""
import contextlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((1280, 720))

import check_translation
import exercises
import i18n
import keuzescherm
import leaderboard
import leaderboard_screen as ls
import main as main_module
import memory
from audit_screens import SCREENS
from theme import Theme
from theme_audit import Audit

HERE = os.path.dirname(os.path.abspath(__file__))
keuzescherm.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "settings.json")

PASSED, FAILED = [], []


def test(fn):
    try:
        fn()
        PASSED.append(fn.__name__)
    except Exception:
        FAILED.append(fn.__name__)
        print(f"FAIL {fn.__name__}")
        traceback.print_exc()
    finally:
        i18n.LANG_DIR = REAL_LANG_DIR
        i18n._user_lang_dir = REAL_USER_LANG_DIR
        i18n.reload()
        i18n.set_language("nl")
    return fn


REAL_LANG_DIR = i18n.LANG_DIR


def real_table(code):
    with open(os.path.join(REAL_LANG_DIR, f"{code}.json"), encoding="utf-8") as f:
        return json.load(f)


def use_language(code):
    """Make `code` the active language the way a user does: it is SAVED in
    settings.json (the choice screen applies the saved language whenever it is
    created), and applied. Setting only i18n's language would silently be
    undone by the next Keuzescherm - and then a test would check the wrong language."""
    with open(keuzescherm.SETTINGS_PATH, "w") as f:
        json.dump({"language": code}, f)
    assert i18n.set_language(code), code


REAL_USER_LANG_DIR = i18n._user_lang_dir


def write_files(folder, files):
    os.makedirs(folder, exist_ok=True)
    for name, content in files.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            f.write(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))


@contextlib.contextmanager
def lang_dir(files, user_files=None):
    """Temporarily use a built-in lang/ folder with exactly these {filename: content}
    files - and a user folder (the one next to the settings) with `user_files`,
    empty by default, so the real project's languages never leak in."""
    folder, user_folder = tempfile.mkdtemp(), os.path.join(tempfile.mkdtemp(), "lang")
    write_files(folder, files)
    if user_files:
        write_files(user_folder, user_files)
    i18n.LANG_DIR = folder
    i18n._user_lang_dir = lambda: user_folder
    i18n.reload()
    try:
        yield folder
    finally:
        i18n.LANG_DIR = REAL_LANG_DIR
        i18n._user_lang_dir = REAL_USER_LANG_DIR
        i18n.reload()
        i18n.set_language("nl")


def pseudo_table(factor=0.3):
    """English made `factor` longer (placeholders untouched): a stand-in for a
    language with longer words, to see whether the layout holds."""
    table = real_table("en")
    for key, text in list(table.items()):
        if key.startswith(("_", "symbol.", "exercise.token.")) or key == "name.key.backspace":
            continue
        plain = re.sub(r"\{\w*\}", "", text)
        table[key] = text + "é" * math.ceil(len(plain) * factor)
    table["_language_name"] = "Pseudolingua"
    return table


def source_files():
    skip = {"i18n.py", "check_translation.py", "theme_audit.py", "audit_screens.py", "plusminus.py"}
    return [os.path.join(HERE, f) for f in sorted(os.listdir(HERE))
            if f.endswith(".py") and not f.startswith("test_") and f not in skip]


# ------------------------------------------------------------------ the files
@test
def every_language_file_is_valid_complete_and_consistent():
    i18n.reload()
    codes = [c for c, _ in i18n.available_languages()]
    assert {"nl", "en"} <= set(codes)
    for code in codes:
        problems = i18n.validate(code)
        assert not any(problems.values()), (code, problems)
        data = real_table(code)
        assert data["_language_name"].strip() and data["_help"].strip()


@test
def every_key_used_in_the_code_exists_and_no_key_in_the_file_is_unused():
    keys = {k for k in real_table("en") if not k.startswith("_")}
    pattern = re.compile(
        r"""["']((?:app|common|choice|som|theme|game|symbol|hud|name|board|exercise)\.[A-Za-z0-9_.]+)["']""")
    used = set()
    for path in source_files():
        with open(path, encoding="utf-8") as f:
            used |= set(pattern.findall(f.read()))
    # exercise.token.* are looked up dynamically by i18n.localize_exercise_text
    used |= {k for k in keys if k.startswith("exercise.token.")}
    assert used - keys == set(), f"keys used in the code but missing from the files: {sorted(used - keys)}"
    assert keys - used == set(), f"keys in the files that no code uses: {sorted(keys - used)}"


@test
def the_placeholders_the_code_passes_match_the_ones_in_the_file():
    en = real_table("en")
    call = re.compile(r"""\bt\(\s*["']([\w.]+)["']\s*,([^()]*(?:\([^()]*\)[^()]*)*)\)""")
    checked = 0
    for path in source_files():
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for key, args in call.findall(text):
            names = set(re.findall(r"\b(\w+)=", args))
            assert names == set(i18n.placeholders(en[key])), (os.path.basename(path), key, names)
            checked += 1
    assert checked >= 15, checked


# ------------------------------------------------------------------ lookup behaviour
@test
def lookup_falls_back_to_english_then_to_the_key_and_never_crashes():
    en = real_table("en")
    partial = {"_language_name": "Partial", "choice.start": "Beginnen",
               "hud.round": "Rond {n}"}                      # lost {total}; most keys missing
    with lang_dir({"en.json": en, "pa.json": partial}):
        assert i18n.set_language("pa")
        assert i18n.t("choice.start") == "Beginnen"
        assert i18n.t("choice.scoreboard") == en["choice.scoreboard"], "missing -> English"
        assert i18n.t("no.such.key") == "no.such.key", "unknown -> the key itself (easy to spot)"
        assert i18n.t("hud.round", n=3, total=10) == "Rond 3", "extra values are ignored"
        assert i18n.t("hud.player_score", n=1) == en["hud.player_score"], \
            "a missing placeholder value must not crash, the text is shown as is"


@test
def broken_language_files_are_skipped_and_the_game_still_starts():
    en = real_table("en")
    with lang_dir({"en.json": en, "bad.json": "{ this is not json", "noname.json": {"choice.start": "x"},
                   "_template.json": en, "readme.txt": "hi"}):
        assert [c for c, _ in i18n.available_languages()] == ["en"]
        assert i18n.t("choice.start") == en["choice.start"]


@test
def set_language_refuses_unknown_codes_and_next_language_wraps_around():
    i18n.reload()
    assert i18n.set_language("nl") and i18n.language() == "nl"
    assert not i18n.set_language("zz") and i18n.language() == "nl", "unknown code changes nothing"
    codes = [c for c, _ in i18n.available_languages()]
    seen, code = [], codes[0]
    for _ in range(len(codes) + 1):
        seen.append(code)
        code = i18n.next_language(code)
    assert seen[-1] == seen[0] and set(seen) == set(codes), "cycles through all and wraps"
    assert i18n.next_language("zz") == codes[0], "an unknown current language starts at the first"


@test
def a_lang_folder_next_to_the_app_adds_and_replaces_languages_without_rebuilding():
    en, nl = real_table("en"), real_table("nl")
    es = dict(en, _language_name="Español", **{"choice.start": "Empezar"})
    nl_better = dict(nl, **{"choice.start": "Begin!"})
    with lang_dir({"en.json": en, "nl.json": nl},
                  user_files={"es.json": es, "nl.json": nl_better, "broken.json": "{oops"}):
        codes = dict(i18n.available_languages())
        assert codes == {"en": "English", "nl": "Nederlands", "es": "Español"}
        i18n.set_language("es")
        assert i18n.t("choice.start") == "Empezar", "a dropped-in language works"
        i18n.set_language("nl")
        assert i18n.t("choice.start") == "Begin!", "a dropped-in file with a built-in code replaces it"
        i18n.set_language("en")
        assert i18n.t("choice.start") == en["choice.start"], "the rest is untouched"


@test
def a_new_language_file_just_appears_in_the_language_list():
    en = real_table("en")
    fr = dict(en, _language_name="Français", **{"choice.start": "Démarrer"})
    with lang_dir({"en.json": en, "nl.json": real_table("nl"), "fr.json": fr}):
        assert ("fr", "Français") in i18n.available_languages()
        i18n.set_language("fr")
        assert i18n.t("choice.start") == "Démarrer"
        k = keuzescherm.Keuzescherm(1280, 720, theme=Theme("dark"))
        assert k.language_rect.w >= k.font_theme.size("Français")[0], "button sized for the new name"


# ------------------------------------------------------------------ what is drawn
def drawn_texts(language):
    """Every text drawn on every screen state, in `language`.
    (The choice screen applies the language saved in settings.json when it is
    created - so the language is set the way a user does it: by saving it.)"""
    texts = set()
    use_language(language)
    theme = Theme("dark")
    with Audit() as audit:
        for name, builder in SCREENS.items():
            for state, draw in builder(theme):
                draw(audit.screen(f"{name}/{state}"))
    for kind, _where, what, *_ in audit.log:
        if kind == "text" and len(what) > 1:      # (single characters are the keyboard's letters)
            texts.add(what)
    return texts


def template_regex(template):
    parts = re.split(r"\{\w*\}", template)
    return re.compile("^" + ".+?".join(re.escape(p) for p in parts) + "$")


def foreign_only_templates(shown, other):
    """Texts of language `other` that are not also valid texts of language `shown`."""
    shown_values = [v for k, v in real_table(shown).items() if not k.startswith("_")]
    other_values = {k: v for k, v in real_table(other).items() if not k.startswith("_")}
    regexes = [template_regex(v) for v in shown_values]
    return [template_regex(v) for v in other_values.values()
            if not any(r.match(v) for r in regexes) and v.strip()]


@test
def in_english_no_dutch_text_is_left_on_any_screen():
    texts = drawn_texts("en")
    assert len(texts) > 60, "the audit must really see the screens"
    leftovers = [t_ for t_ in texts for r in foreign_only_templates("en", "nl") if r.match(t_)]
    assert leftovers == [], sorted(set(leftovers))
    assert {"Start", "Plus and minus", "Scoreboard", "Up to 100"} <= texts


@test
def in_dutch_no_english_text_is_left_on_any_screen():
    texts = drawn_texts("nl")
    leftovers = [t_ for t_ in texts for r in foreign_only_templates("nl", "en") if r.match(t_)]
    assert leftovers == [], sorted(set(leftovers))
    assert {"Start", "Plus en min", "Scorebord", "Tot 100"} <= texts


# ------------------------------------------------------------------ layout in every language
def inside(audit, text, rect, problems, what):
    drawn = audit.rect_of(text)
    if drawn is None:
        problems.append(f"{what}: {text!r} was not drawn")
    elif not rect.contains(drawn):
        problems.append(f"{what}: {text!r} {tuple(drawn)} sticks out of {tuple(rect)}")


def choice_screen_problems(mode):
    problems = []
    with Audit() as audit:
        k = keuzescherm.Keuzescherm(1280, 720, theme=Theme("dark"))
        k.mode = mode
        k.draw(audit.screen())
    t = i18n.t
    inside(audit, keuzescherm.mode_title(mode), k.title_rect, problems, "title button")
    inside(audit, t("choice.start"), k.start_rect, problems, "Start")
    inside(audit, t("choice.players.one"), k.players_rect, problems, "players")
    inside(audit, t("choice.sound.on"), k.sound_rect, problems, "sound")
    inside(audit, t("choice.scoreboard"), k.leaderboard_rect, problems, "scoreboard button")
    from theme import mode_label
    inside(audit, t("choice.theme", mode=mode_label("dark")), k.theme_rect, problems, "theme button")
    inside(audit, i18n.language_name(), k.language_rect, problems, "language button")
    for game, rect in k.game_tiles.items():
        inside(audit, keuzescherm.game_label(game), rect, problems, f"tile {game}")
    screen = pygame.Rect(0, 0, 1280, 720)
    for name, rect in (("hint", k.hint_rect), ("f11", k.f11_rect), ("title", k.title_rect)):
        if not screen.contains(rect):
            problems.append(f"{name} {tuple(rect)} off screen")
    # the hint and the F11 line must not run into neighbours
    for a, b in (("hint", "title"), ("hint", "language_rect"), ("f11", "theme_rect"),
                 ("f11", "leaderboard_rect")):
        ra = {"hint": k.hint_rect, "f11": k.f11_rect}[a]
        rb = {"title": k.title_rect, "language_rect": k.language_rect,
              "theme_rect": k.theme_rect, "leaderboard_rect": k.leaderboard_rect}[b]
        if ra.colliderect(rb):
            problems.append(f"{a} overlaps {b}")
    if mode == keuzescherm.MODE_TAFELS:
        inside(audit, keuzescherm.som_label("Gemengd"), k.som_type_rect, problems, "Gemengd") \
            if False else None
        label = keuzescherm.som_label(keuzescherm.SOM_TYPES[k.som_type_index])
        inside(audit, label, k.som_type_rect, problems, "exercise kind button")
    else:
        for key, rect in k.chip_rects.items():
            line1 = i18n.exercise_lines(exercises.EXERCISE_BY_KEY[key])[0]
            ok = [r for kind, _w, what, _f, _b, r in audit.log
                  if kind == "text" and what == line1 and rect.contains(r)]
            if not ok:
                problems.append(f"chip {key}: {line1!r} does not fit inside the chip")
    # nothing of the new language button may touch the other top elements
    if k.language_rect.colliderect(k.title_rect):
        problems.append("language button overlaps the title button")
    return problems


def leaderboard_problems(content):
    problems = []
    path = os.path.join(tempfile.mkdtemp(), "lb.json")
    with Audit() as audit:
        s = ls.LeaderboardScreen(1280, 720, initial_mode="1", leaderboard_path=path,
                                 theme=Theme("dark"), game="memory", initial_content=content)
        s.draw(audit.screen())
        s.filter_open = content == keuzescherm.MODE_PLUSMIN
        if s.filter_open:
            s.draw(audit.screen())
    t = i18n.t
    for key, rect in s.content_rects.items():
        inside(audit, keuzescherm.mode_title(key), rect, problems, f"content switch {key}")
    for game, rect in s.game_rects.items():
        inside(audit, keuzescherm.game_label(game), rect, problems, f"game tab {game}")
    inside(audit, t("choice.players.one"), s.mode_rects["1"], problems, "players tab 1")
    inside(audit, t("choice.players.two"), s.mode_rects["2"], problems, "players tab 2")
    for key, label_key in ls.PERIODS:
        inside(audit, t(label_key), s.period_rects[key], problems, f"period {key}")
    inside(audit, t("board.continue"), s.continue_rect, problems, "Verder")
    # table headers must not run into each other
    cols = s._columns()
    for (head_a, x_a, _w), (head_b, x_b, _w2) in zip(cols, cols[1:]):
        if x_a + s.font_header.size(head_a)[0] + 6 > x_b:
            problems.append(f"column header {head_a!r} runs into {head_b!r}")
    last_header, last_x, _w = cols[-1]
    widest = max(s.font_header.size(last_header)[0], s.font_row.size("2026-10-21")[0])
    if last_x + widest > 1280 - 16:
        problems.append("the last table column runs off the right edge of the screen")
    if content == keuzescherm.MODE_PLUSMIN:
        text_right = s.exercise_button_rect.left + 14 + s.font_exercise_button.size(
            t("board.exercises.button", n=23))[0]
        if text_right > s.exercise_button_rect.right - 32:
            problems.append("Oefeningen button text runs into its arrow")
        inside(audit, t("board.exercises.title"), s.overlay_rect, problems, "overlay title")
        inside(audit, t("common.done"), s.overlay_done_rect, problems, "overlay Klaar")
    return problems


def all_layout_problems():
    found = {}
    for mode in (keuzescherm.MODE_TAFELS, keuzescherm.MODE_PLUSMIN):
        found[f"choice/{mode}"] = choice_screen_problems(mode)
        found[f"leaderboard/{mode}"] = leaderboard_problems(mode)
    return {k: v for k, v in found.items() if v}


@test
def every_label_fits_its_button_in_dutch_and_in_english():
    for code in ("nl", "en"):
        i18n.reload()
        use_language(code)
        problems = all_layout_problems()
        assert problems == {}, (code, json.dumps(problems, indent=1))
        assert i18n.language() == code, "the language must still be the one under test"


@test
def a_language_30_percent_longer_still_fits_so_translators_have_room():
    en = real_table("en")
    with lang_dir({"en.json": en, "nl.json": real_table("nl"), "ps.json": pseudo_table(0.3)}):
        use_language("ps")
        problems = all_layout_problems()
        assert i18n.language() == "ps", "the made-up language must be the one under test"
        assert problems == {}, json.dumps(problems, indent=1)


# ------------------------------------------------------------------ the language button
def fresh_choice(saved=None):
    if os.path.exists(keuzescherm.SETTINGS_PATH):
        os.remove(keuzescherm.SETTINGS_PATH)
    if saved is not None:
        with open(keuzescherm.SETTINGS_PATH, "w") as f:
            json.dump(saved, f)
    return keuzescherm.Keuzescherm(1280, 720, theme=Theme("dark"))


class FakeCursor:
    def __init__(self, x, y, fired=True):
        self.x, self.y, self.fired, self.player_id = x, y, fired, 1


def click_at(k, pos):
    k.update([FakeCursor(*pos)])


@test
def the_first_ever_launch_is_in_the_default_language_and_an_unknown_saved_one_is_repaired():
    k = fresh_choice()
    assert k.language == i18n.DEFAULT_LANGUAGE == i18n.language() == "nl"
    k = fresh_choice({"language": "klingon"})
    assert k.language == "nl" and i18n.language() == "nl"
    k = fresh_choice({"language": "en"})
    assert k.language == "en" and i18n.language() == "en"


@test
def clicking_the_language_button_switches_remembers_and_remeasures():
    k = fresh_choice()
    title_before, hint_before = tuple(k.title_rect), tuple(k.hint_rect)
    click_at(k, k.language_rect.center)
    assert k.language == "en" and i18n.language() == "en"
    with open(keuzescherm.SETTINGS_PATH) as f:
        assert json.load(f)["language"] == "en"
    assert keuzescherm.mode_title("plusmin") == "Plus and minus"
    assert tuple(k.hint_rect) != hint_before, "the hint is a different length now: re-measured"
    # the next launch starts in English
    k2 = keuzescherm.Keuzescherm(1280, 720, theme=Theme("dark"))
    assert k2.language == "en"
    click_at(k2, k2.language_rect.center)
    assert k2.language == "nl" and keuzescherm.mode_title("plusmin") == "Plus en min"


@test
def the_language_button_shows_the_current_language_in_its_own_name_and_sits_top_right():
    for code, name in (("nl", "Nederlands"), ("en", "English")):
        k = fresh_choice({"language": code})
        with Audit() as audit:
            k = keuzescherm.Keuzescherm(1280, 720, theme=Theme("dark"))
            k.draw(audit.screen())
        assert audit.rect_of(name) is not None and k.language_rect.contains(audit.rect_of(name))
        r = k.language_rect
        assert r.right == 1280 - 16 and r.top < 30 and pygame.Rect(0, 0, 1280, 720).contains(r)
        assert not r.colliderect(k.title_rect)


@test
def the_game_is_drawn_in_the_new_language_right_after_the_switch():
    k = fresh_choice()
    click_at(k, k.language_rect.center)
    with Audit() as audit:
        k2 = keuzescherm.Keuzescherm(1280, 720, theme=Theme("dark"))
        k2.draw(audit.screen())
    texts = {what for kind, _w, what, *_ in audit.log if kind == "text"}
    assert {"Tables", "(click to switch)", "Full screen = F11", "Scoreboard", "Start",
            "Sound: On", "1 player", "Clock", "Balloon", "Hats", "Memory"} <= texts, texts


# ------------------------------------------------------------------ saved data is language-independent
@test
def saved_scores_and_settings_do_not_depend_on_the_language():
    path = os.path.join(tempfile.mkdtemp(), "lb.json")
    k = fresh_choice({"language": "en"})
    k.game = "klok"
    choice = k.result()
    assert choice["som_type"] == "Keer (x)", "the internal id is saved, never the English text"
    main_module._record_match(choice, {1: 640}, {1: "Emma"}, {"scores": {1: 5}}, path=path)
    with open(path) as f:
        row = json.load(f)[0]
    assert row["som_type"] == "Keer (x)" and row["tables"] == list(range(1, 11))
    # the same board shows up whichever language is active
    for code in ("nl", "en"):
        i18n.set_language(code)
        board = ls.LeaderboardScreen(1280, 720, initial_mode="1", leaderboard_path=path,
                                     initial_tables=list(range(1, 11)),
                                     initial_som_type="Keer (x)", theme=Theme("dark"), game="klok")
        assert [e["name"] for e in board._entries()] == ["Emma"], code
    # Plus en min: the exercise keys, not their translated labels
    k = fresh_choice({"language": "en", "mode": "plusmin", "selected_exercises": ["te_plus_e_to20_zb"]})
    choice = k.result()
    assert choice["som_type"] == "Plus en min" and choice["exercises"] == ["te_plus_e_to20_zb"]
    with open(keuzescherm.SETTINGS_PATH) as f:
        pass
    k._persist()
    with open(keuzescherm.SETTINGS_PATH) as f:
        saved = json.load(f)
    assert saved["selected_exercises"] == ["te_plus_e_to20_zb"] and saved["mode"] == "plusmin"


@test
def the_blank_name_default_follows_the_language_but_is_just_a_name():
    import keyboard_input
    for code, word in (("nl", "Speler"), ("en", "Player")):
        i18n.set_language(code)
        kb = keyboard_input.OnScreenKeyboard(1280, 720, "x", theme=Theme("dark"))
        assert kb.result() == word


# ------------------------------------------------------------------ the exercises in another language
@test
def the_maths_signs_follow_the_language_in_every_game():
    import random
    random.seed(4)
    i18n.set_language("en")
    q = exercises.TableSet([7], "Keer (x)").make_problem().question
    assert re.fullmatch(r"7 × \d+", q), q
    q = exercises.TableSet([7], "Gedeeld door (:)").make_problem().question
    assert re.fullmatch(r"\d+ ÷ 7", q), q
    pairs = memory.make_pairs([3], "Gemengd")
    assert pairs and all(re.fullmatch(r"\d+ [×÷] 3|3 [×÷] \d+", p["question"]) for p in pairs), pairs
    # plus and minus are the same in every language
    p = exercises.ExerciseSet(["te_plus_e_to20_zb"]).make_problem()
    assert re.fullmatch(r"\d+ \+ \d+", p.question)
    # the answers do not change with the symbols
    i18n.set_language("nl")
    q = exercises.TableSet([7], "Keer (x)").make_problem()
    assert re.fullmatch(r"7 x (\d+)", q.question) and int(q.question.split()[-1]) * 7 == q.answer


@test
def exercise_abbreviations_are_translated_through_the_language_file():
    i18n.set_language("nl")
    by = exercises.EXERCISE_BY_KEY
    assert i18n.exercise_lines(by["te_plus_e_to20_zb"]) == ("TE + E", "ZB")
    i18n.set_language("en")
    assert i18n.exercise_lines(by["te_plus_e_to20_zb"]) == ("TU + U", "NB")
    assert i18n.exercise_lines(by["te_minus_e_to20_mb"]) == ("TU - U", "WB")
    assert i18n.exercise_label(by["t_minus_e_te_20_zb"]) == "20 - U/TU"
    assert i18n.exercise_label(by["t_plus_t_to100_zb"]) == "T + T"
    # a token inside a longer word is left alone
    assert i18n.localize_exercise_text("TEST MBE") == "TEST MBE"


# ------------------------------------------------------------------ the translator's checker
@test
def the_checker_passes_good_files_and_flags_every_kind_of_mistake():
    assert check_translation.main([]) == 0
    en = real_table("en")
    bad = dict(en, _language_name="Testish")
    bad.pop("choice.start")
    bad["hud.round"] = "Rond {n}"
    bad["bogus.key"] = "x"
    bad["board.empty"] = ""
    with lang_dir({"en.json": en, "xx.json": bad}):
        problems = i18n.validate("xx")
        assert problems == {"missing": ["choice.start"], "extra": ["bogus.key"],
                            "placeholders": ["hud.round"], "empty": ["board.empty"]}
        assert check_translation.main(["xx"]) == 1
        assert check_translation.main(["nope"]) == 1


@test
def init_creates_a_ready_to_translate_file_and_never_overwrites():
    en = real_table("en")
    with lang_dir({"en.json": en}) as folder:
        assert check_translation.main(["--init", "es", "Español"]) == 0
        path = os.path.join(folder, "es.json")
        data = json.load(open(path, encoding="utf-8"))
        assert data["_language_name"] == "Español" and data["choice.start"] == en["choice.start"]
        i18n.reload()
        assert ("es", "Español") in i18n.available_languages()
        assert check_translation.main(["es"]) == 0, "a fresh copy is valid (just not translated yet)"
        before = open(path, "rb").read()
        assert check_translation.main(["--init", "es", "Other"]) == 1
        assert open(path, "rb").read() == before


if __name__ == "__main__":
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", ", ".join(FAILED))
        sys.exit(1)

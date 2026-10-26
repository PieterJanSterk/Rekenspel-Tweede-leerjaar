"""
audit_screens.py - dev-only. Builds every screen of the game in a representative
set of states, so tests can draw them all (pixel readability audit, language
checks, layout checks). Each builder returns [(state name, draw function)];
create the objects INSIDE the theme_audit.Audit context so their fonts are
measured.
"""
import os
import tempfile

import pygame

import ballon
import exercises
import hoeden
import keuzescherm
import keyboard_input
import klok
import leaderboard
import leaderboard_screen
import memory
from i18n import t

TABLES, SOM = [2, 3, 7], "Gemengd"


class C:
    def __init__(self, pid, x, y):
        self.player_id, self.x, self.y, self.fired = pid, x, y, True


# Each returns [(state name, draw function)]; objects are created INSIDE the
# Audit context so their fonts are measured.
def build_keuzescherm(theme):
    out = []
    for game in keuzescherm.GAMES:
        k = keuzescherm.Keuzescherm(1280, 720, theme=theme)
        k.game = game
        out.append((f"selected_{game}", k.draw))
    k = keuzescherm.Keuzescherm(1280, 720, theme=theme)
    k.selected_tables.clear()
    k.sound_on = False
    out.append(("nothing_selected_muted", k.draw))
    # Plus en min: a mixed selection, nothing ticked, and everything ticked -
    # all 23 chips, ticked and unticked, plus the title button.
    for label, keys in (("some", {"e_plus_e_to10_zb", "te_plus_e_to20_zb", "e_plus_e_to20_mb",
                                  "te_minus_e_to20_mb", "te_plus_e_to100_zb", "te_minus_te_to100_mb"}),
                        ("none", set()),
                        ("all", {t.key for t in exercises.EXERCISE_TYPES})):
        k = keuzescherm.Keuzescherm(1280, 720, theme=theme)
        k.mode = keuzescherm.MODE_PLUSMIN
        k.selected_exercises = set(keys)
        out.append((f"plusmin_{label}", k.draw))
    return out


def _run(g, ms=3000):
    for _ in range(ms // 16):
        g.update(16, [])


def build_klok(theme):
    out = []
    for players in (1, 2):
        g = klok.KlokGame(1280, 720, TABLES, SOM, players, None, theme)
        out.append((f"{players}p_start", g.draw))
        _run(g)
        out.append((f"{players}p_running", g.draw))
    return out


def build_ballon(theme):
    out = []
    for players in (1, 2):
        g = ballon.BallonGame(1280, 720, TABLES, SOM, players, None, theme)
        out.append((f"{players}p_start", g.draw))
        _run(g, 4000)
        out.append((f"{players}p_running", g.draw))
    return out


def build_hoeden(theme):
    out = []
    for players in (1, 2):
        g = hoeden.HoedenGame(1280, 720, TABLES, SOM, players, None, theme)
        out.append((f"{players}p_start", g.draw))
        guard = 0
        while g.phase != hoeden.PHASE_ANSWER and guard < 8000:
            g.update(16, [])
            guard += 1
        out.append((f"{players}p_answering", g.draw))
        wrong = next(h for h in g.hats if not h.is_correct)
        g.update(16, [C(1, *wrong.rect().center)])
        out.append((f"{players}p_after_wrong_click", g.draw))
    return out


def build_memory(theme):
    out = []
    for players in (1, 2):
        g = memory.MemoryGame(1280, 720, TABLES, SOM, players, None, theme)
        out.append((f"{players}p_start", g.draw))
        s = next(c for c in g.cards if c.kind == "sum")
        mate = next(c for c in g.cards if c.pair == s.pair and c is not s)
        g.update(1, [C(1, *s.rect.center)])
        g.update(1, [C(1, *mate.rect.center)])
        for _ in range(20):
            g.update(16, [])
        out.append((f"{players}p_match_shown", g.draw))
        s2 = next(c for c in g.cards if c.kind == "sum" and not c.gone and c.pair != s.pair)
        other = next(c for c in g.cards if c.kind == "sum" and not c.gone and c is not s2)
        while g.phase != memory.PHASE_PICK:
            g.update(16, [])
        g.update(1, [C(g.active_player, *s2.rect.center)])
        g.update(1, [C(g.active_player, *other.rect.center)])
        for _ in range(20):
            g.update(16, [])
        out.append((f"{players}p_miss_shown", g.draw))
    return out


def build_leaderboard(theme):
    path = os.path.join(tempfile.mkdtemp(), "lb.json")
    for game in ("klok", "ballon", "hoeden", "memory"):
        for i, (name, score) in enumerate([("Emma", 5), ("Noor & Finn", 7), ("Jan", 3)]):
            leaderboard.add_score(name, score, "1", TABLES, SOM, game=game,
                                  time_ms=30_000 + 9_000 * i, path=path)
    out = []
    for game in ("klok", "hoeden", "memory"):
        board = leaderboard_screen.LeaderboardScreen(
            1280, 720, initial_mode="1", leaderboard_path=path, initial_tables=TABLES,
            initial_som_type=SOM, theme=theme, game=game)
        out.append((f"board_{game}", board.draw))
    # Plus en min boards: with rows, with the chip overlay open, and with nothing ticked.
    keys = ["e_plus_e_to10_zb", "te_plus_e_to20_zb", "te_minus_e_to100_mb"]
    for game in ("hoeden", "memory"):
        for i, (name, score) in enumerate([("Emma", 5), ("Noor & Finn", 7)]):
            leaderboard.add_score(name, score, "1", [], "Plus en min", game=game,
                                  time_ms=30_000 + 9_000 * i, exercises=keys, path=path)
    plus = leaderboard_screen.LeaderboardScreen(
        1280, 720, initial_mode="1", leaderboard_path=path, theme=theme, game="hoeden",
        initial_content="plusmin", initial_exercises=keys)
    out.append(("plusmin_board", plus.draw))
    overlay = leaderboard_screen.LeaderboardScreen(
        1280, 720, initial_mode="1", leaderboard_path=path, theme=theme, game="memory",
        initial_content="plusmin", initial_exercises=keys)
    overlay.filter_open = True
    out.append(("plusmin_overlay", overlay.draw))
    empty = leaderboard_screen.LeaderboardScreen(
        1280, 720, initial_mode="1", leaderboard_path=path, theme=theme, game="klok",
        initial_content="plusmin", initial_exercises=keys)
    empty.filter_exercises.clear()
    out.append(("plusmin_nothing_ticked", empty.draw))
    admin = leaderboard_screen.LeaderboardScreen(
        1280, 720, initial_mode="1", leaderboard_path=path, initial_tables=TABLES,
        initial_som_type=SOM, theme=theme, game="memory")
    admin.settings_open = True
    out.append(("admin_overlay", admin.draw))
    return out


def build_name_entry(theme):
    one = keyboard_input.MultiNameEntry(1280, 720, 1, theme=theme, scores={1: 12},
                                        score_word=t("hud.score_word.memory"), times={1: 61_000})
    two = keyboard_input.MultiNameEntry(1280, 720, 2, theme=theme, scores={1: 8, 2: 3},
                                        score_word=t("hud.score_word.default"), times={1: 42_000, 2: 95_000},
                                        score_labels={1: "8/11", 2: "3/11"})
    plain = keyboard_input.MultiNameEntry(1280, 720, 2, theme=theme, scores={1: 300, 2: 250})
    return [("memory_1p", one.draw), ("hoeden_2p", two.draw), ("klok_2p", plain.draw)]


SCREENS = {
    "keuzescherm": build_keuzescherm, "klok": build_klok, "ballon": build_ballon,
    "hoeden": build_hoeden, "memory": build_memory, "leaderboard": build_leaderboard,
    "name_entry": build_name_entry,
}



"""
test_plusmin_board.py - dev-only tests for the Plus en min leaderboard: how
scores are stored and matched, the Tafels | Plus en min switch, the
"Oefeningen" overlay, and the whole chain from a finished match to a board row.
Run:  python test_plusmin_board.py     (uses temp files only - never your real data)
"""
import json
import os
import random
import sys
import tempfile
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((1280, 720))

import keuzescherm
import leaderboard
import leaderboard_screen as ls
import main as main_module
from theme import Theme

keuzescherm.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "settings.json")

PASSED, FAILED = [], []
TAFELS, PLUSMIN = keuzescherm.MODE_TAFELS, keuzescherm.MODE_PLUSMIN
A, B, C = "e_plus_e_to10_zb", "te_plus_e_to20_zb", "te_minus_e_to100_mb"


def test(fn):
    try:
        fn()
        PASSED.append(fn.__name__)
    except Exception:
        FAILED.append(fn.__name__)
        print(f"FAIL {fn.__name__}")
        traceback.print_exc()
    return fn


class FakeCursor:
    def __init__(self, x, y, fired=True):
        self.x, self.y, self.fired, self.player_id = x, y, fired, 1


def temp_lb():
    return os.path.join(tempfile.mkdtemp(), "lb.json")


def add(path, name, score, keys=None, game="klok", mode="1", time_ms=None, tables=(2,),
        som="Keer (x)"):
    if keys:
        leaderboard.add_score(name, score, mode, [], "Plus en min", game=game,
                              time_ms=time_ms, exercises=keys, path=path)
    else:
        leaderboard.add_score(name, score, mode, list(tables), som, game=game,
                              time_ms=time_ms, path=path)


def names(path, game="klok", mode="1", **filters):
    return [e["name"] for e in leaderboard.top(10, mode=mode, game=game, path=path, **filters)]


def screen_for(path, content=PLUSMIN, keys=(A,), game="klok", mode="1"):
    return ls.LeaderboardScreen(1280, 720, initial_mode=mode, leaderboard_path=path,
                                initial_tables=[2], initial_som_type="Keer (x)",
                                theme=Theme("dark"), game=game, initial_content=content,
                                initial_exercises=list(keys))


# ------------------------------------------------------------------ data rules
@test
def a_board_is_exactly_one_exercise_selection():
    p = temp_lb()
    add(p, "only_a", 5, [A])
    add(p, "a_and_b", 6, [B, A])           # order of the keys must not matter
    add(p, "only_b", 7, [B])
    add(p, "tafel", 8)
    assert names(p, exercises=[A]) == ["only_a"]
    assert names(p, exercises=[A, B]) == ["a_and_b"] and names(p, exercises=[B, A]) == ["a_and_b"]
    assert names(p, exercises=[B]) == ["only_b"]
    assert names(p, exercises=[C]) == [], "a selection nobody played has an empty board"
    stored = [e for e in json.load(open(p)) if e["name"] == "a_and_b"][0]
    assert stored["exercises"] == sorted([A, B]) and stored["tables"] == [] \
        and stored["som_type"] == "Plus en min"


@test
def tables_boards_never_show_plus_en_min_rows_but_the_admin_list_shows_everything():
    p = temp_lb()
    add(p, "tafel", 8)
    add(p, "plus", 9, [A])
    assert names(p, tables=[2], som_type="Keer (x)") == ["tafel"]
    assert names(p, tables=[], som_type=None) == [], "an empty tables filter shows nothing"
    assert sorted(names(p)) == ["plus", "tafel"], "no filter at all (admin overlay) sees both"


@test
def ranking_and_name_merging_work_inside_a_plus_en_min_board():
    p = temp_lb()
    add(p, "slow", 9, [A], game="hoeden", time_ms=90_000)
    add(p, "fast", 9, [A], game="hoeden", time_ms=30_000)
    add(p, "best", 10, [A], game="hoeden", time_ms=200_000)
    assert names(p, game="hoeden", exercises=[A]) == ["best", "fast", "slow"]
    # Memory: fewer turns first, co-op pairs merge whatever the order
    add(p, "Jan & Sam", 12, [A], game="memory", mode="2", time_ms=50_000)
    add(p, "sam & JAN", 10, [A], game="memory", mode="2", time_ms=90_000)
    rows = leaderboard.top(10, mode="2", game="memory", exercises=[A], unique_names=True, path=p)
    assert len(rows) == 1 and rows[0]["score"] == 10 and rows[0]["attempts"] == 2


@test
def old_files_are_untouched_and_malformed_exercise_fields_are_repaired():
    p = temp_lb()
    legacy = [{"id": "a", "name": "Anna", "score": 5, "mode": "1", "tables": [2],
               "som_type": "Keer (x)", "date": "2026-10-01T10:00:00", "game": "klok"}]
    json.dump(legacy, open(p, "w"))
    before = open(p, "rb").read()
    assert names(p, tables=[2], som_type="Keer (x)") == ["Anna"]
    assert open(p, "rb").read() == before, "reading an old file must not rewrite it"
    bad = dict(legacy[0], id="b", name="Bad", exercises="oops")
    json.dump(legacy + [bad], open(p, "w"))
    rows = {e["name"]: e for e in leaderboard.load(p)}
    assert "exercises" not in rows["Bad"] and rows["Anna"] == legacy[0]


# ------------------------------------------------------------------ recording
@test
def scores_are_recorded_with_their_exercises_for_every_kind_of_game():
    p = temp_lb()
    keys = [B, A]
    # per-player game (Hoeden, 2 players): one row each
    main_module._record_scores("hoeden", {1: 7, 2: 4}, {1: "Jan", 2: "Sam"}, [], "Plus en min",
                               results={"scores": {1: 7, 2: 4}, "times_ms": {1: 41_000, 2: 66_500}},
                               path=p, exercises=keys)
    # co-op game (Memory): one joined row
    main_module._record_scores("memory", {1: 8}, {1: "Jan", 2: "Sam"}, [], "Plus en min",
                               results={"scores": {1: 8, 2: 8}, "turns": 8, "time_ms": 70_000},
                               path=p, exercises=keys)
    rows = json.load(open(p))
    assert len(rows) == 3
    assert all(r["exercises"] == sorted(keys) and r["tables"] == [] and r["som_type"] == "Plus en min"
               for r in rows)
    assert {r["name"] for r in rows} == {"Jan", "Sam", "Jan & Sam"}
    # and tables games still store no exercises field
    main_module._record_scores("klok", {1: 640}, {1: "Emma"}, [3], "Keer (x)",
                               results={"scores": {1: 5}}, path=p)
    assert "exercises" not in json.load(open(p))[-1]


@test
def a_finished_match_is_stored_as_what_was_played_not_what_is_picked_now():
    p = temp_lb()
    k = keuzescherm.Keuzescherm(1280, 720, theme=Theme("dark"))
    k.game, k.selected_tables = "klok", {3, 4}
    k.selected_exercises = {A, B}
    k.mode = PLUSMIN
    played_plusmin = k.result()
    k.mode = TAFELS
    played_tables = k.result()
    # Plus en min was played, and the picks on the choice screen then change to Tafels:
    results = {"scores": {1: 5}, "bank_remaining": 640}
    main_module._record_match(played_plusmin, {1: 640}, {1: "Emma"}, results, path=p)
    main_module._record_match(played_tables, {1: 500}, {1: "Noor"}, results, path=p)
    rows = {r["name"]: r for r in json.load(open(p))}
    assert rows["Emma"]["tables"] == [] and rows["Emma"]["som_type"] == "Plus en min"
    assert rows["Emma"]["exercises"] == sorted([A, B])
    assert rows["Noor"]["tables"] == [3, 4] and rows["Noor"]["som_type"] == "Keer (x)"
    assert "exercises" not in rows["Noor"]


# ------------------------------------------------------------------ the screen
@test
def the_screen_starts_on_the_given_board_and_repairs_a_bad_selection():
    s = screen_for(temp_lb(), content=PLUSMIN, keys=[A, "gone_type"])
    assert s.content == PLUSMIN and s.filter_exercises == {A}
    s = ls.LeaderboardScreen(1280, 720, leaderboard_path=temp_lb(), theme=Theme("dark"))
    assert s.content == TAFELS and s.filter_exercises == set(keuzescherm.DEFAULT_EXERCISES)
    s = ls.LeaderboardScreen(1280, 720, leaderboard_path=temp_lb(), theme=Theme("dark"),
                             initial_content="nonsense")
    assert s.content == TAFELS


@test
def the_switch_changes_between_tafels_and_plus_en_min_boards():
    p = temp_lb()
    add(p, "tafel", 8)
    add(p, "plus", 9, [A])
    s = screen_for(p, content=TAFELS)
    assert [e["name"] for e in s._entries()] == ["tafel"]
    s.update([FakeCursor(*s.content_rects[PLUSMIN].center)])
    assert s.content == PLUSMIN and [e["name"] for e in s._entries()] == ["plus"]
    s.update([FakeCursor(*s.content_rects[TAFELS].center)])
    assert s.content == TAFELS and [e["name"] for e in s._entries()] == ["tafel"]


@test
def the_overlay_opens_toggles_chips_changes_the_board_and_closes():
    p = temp_lb()
    add(p, "only_a", 5, [A])
    add(p, "a_and_b", 6, [A, B])
    s = screen_for(p, keys=[A])
    assert [e["name"] for e in s._entries()] == ["only_a"]
    s.update([FakeCursor(*s.exercise_button_rect.center)])
    assert s.filter_open
    s.update([FakeCursor(*s.overlay_chips.chip_rects[B].center)])
    assert s.filter_exercises == {A, B} and [e["name"] for e in s._entries()] == ["a_and_b"]
    s.update([FakeCursor(*s.overlay_chips.chip_rects[A].center)])
    s.update([FakeCursor(*s.overlay_chips.chip_rects[B].center)])
    assert s.filter_exercises == set() and s._entries() == [], "nothing ticked shows nothing"
    s.update([FakeCursor(*s.overlay_chips.chip_rects[A].center)])
    s.update([FakeCursor(*s.overlay_done_rect.center)])
    assert not s.filter_open and [e["name"] for e in s._entries()] == ["only_a"]


@test
def the_open_overlay_is_modal():
    s = screen_for(temp_lb())
    s.update([FakeCursor(*s.exercise_button_rect.center)])
    assert s.filter_open
    before = (s.content, s.game, s.mode, s.period, set(s.filter_exercises))
    for pos in (s.content_rects[TAFELS].center, s.continue_rect.center, (640, 100), (60, 400)):
        s.update([FakeCursor(*pos)])
    assert s.filter_open and (s.content, s.game, s.mode, s.period, set(s.filter_exercises)) == before
    assert not getattr(s, "done", False), "Verder must not fire through the overlay"


@test
def the_tables_grid_and_the_exercise_button_belong_to_their_own_board_kind():
    s = screen_for(temp_lb(), content=TAFELS)
    xs = set(s.filter_x_tables)
    s.update([FakeCursor(*s.exercise_button_rect.center)])
    assert not s.filter_open, "no Oefeningen button on a Tafels board"
    s = screen_for(temp_lb(), content=PLUSMIN)
    xs = set(s.filter_x_tables)
    first = s.filter_x_rects[1]
    s.update([FakeCursor(*first.center)])
    assert set(s.filter_x_tables) == xs, "the tables grid is not there on a Plus en min board"


@test
def screen_layout_has_no_overlaps_and_the_overlay_fits():
    s = screen_for(temp_lb())
    screen = pygame.Rect(0, 0, 1280, 720)
    rects = dict(content_t=s.content_rects[TAFELS], content_p=s.content_rects[PLUSMIN],
                 gear=s.gear_rect, button=s.exercise_button_rect, verder=s.continue_rect)
    rects.update({f"game_{g}": r for g, r in s.game_rects.items()})
    names_ = list(rects)
    for i, a in enumerate(names_):
        assert screen.contains(rects[a]), a
        for b in names_[i + 1:]:
            assert not rects[a].colliderect(rects[b]), (a, b)
    assert screen.contains(s.overlay_rect) and s.overlay_rect.contains(s.overlay_done_rect)
    for key, r in s.overlay_chips.chip_rects.items():
        assert s.overlay_rect.contains(r), key
    assert s.overlay_chips.bottom < s.overlay_done_rect.top
    assert len(s.overlay_chips.chip_rects) == 23


@test
def the_oefeningen_caption_and_button_describe_what_is_ticked():
    from theme_audit import Audit
    with Audit() as audit:
        s = screen_for(temp_lb(), keys=[A, B])
        s.draw(audit.screen())
    texts = [what for kind, _w, what, *_ in audit.log if kind == "text"]
    assert "Oefeningen: 2 gekozen" in texts
    assert any(t.startswith("E + E ZB, TE + E ZB") for t in texts), texts
    assert "Plus en min" in texts and "Tafels" in texts
    with Audit() as audit:
        s = screen_for(temp_lb(), keys=[A])
        s.filter_exercises.clear()                 # the user un-ticks everything in the overlay
        s.draw(audit.screen())
    assert "Niets gekozen" in [what for kind, _w, what, *_ in audit.log if kind == "text"]
    assert "Oefeningen: 0 gekozen" in [what for kind, _w, what, *_ in audit.log if kind == "text"]


@test
def opening_with_no_exercises_picked_falls_back_to_the_easiest_two():
    # Like the tables filter falling back to all tables: an empty starting
    # selection would only ever show an empty board.
    s = screen_for(temp_lb(), keys=[])
    assert s.filter_exercises == set(keuzescherm.DEFAULT_EXERCISES)


# ------------------------------------------------------------------ the whole chain
@test
def from_a_finished_plus_en_min_match_to_the_right_board_row():
    random.seed(31)
    p = temp_lb()
    k = keuzescherm.Keuzescherm(1280, 720, theme=Theme("dark"))
    k.mode, k.game, k.num_players = PLUSMIN, "memory", 2
    k.selected_exercises = {"e_plus_e_to20_mb"}
    choice = k.result()
    assert choice["tables"] == [] and choice["som_type"] == "Plus en min"
    game = main_module._make_game(choice["game"], choice["tables"], choice["som_type"],
                                  choice["num_players"], None, Theme("dark"),
                                  exercises=choice["exercises"])
    for pair in range(game.num_pairs):
        s_ = next(c for c in game.cards if c.kind == "sum" and c.pair == pair)
        mate = next(c for c in game.cards if c.pair == pair and c is not s_)
        for card in (s_, mate):
            game.update(1, [type("C", (), dict(player_id=game.active_player, x=card.rect.centerx,
                                               y=card.rect.centery, fired=True))()])
        for _ in range(130):
            game.update(16, [])
    assert game.finished and game.num_pairs == 8
    results = game.results()
    final = main_module._final_scores(choice["game"], results, 2)
    main_module._record_scores(choice["game"], final, {1: "Jan", 2: "Sam"}, choice["tables"],
                               choice["som_type"], results=results, path=p,
                               exercises=choice["exercises"])
    board = ls.LeaderboardScreen(1280, 720, initial_mode="2", leaderboard_path=p,
                                 theme=Theme("dark"), game="memory", initial_content=PLUSMIN,
                                 initial_exercises=choice["exercises"])
    rows = board._entries()
    assert [(r["name"], r["score"]) for r in rows] == [("Jan & Sam", 8)]
    board.content = TAFELS
    assert board._entries() == [], "it is not on any tables board"
    board.content, board.filter_exercises = PLUSMIN, {A}
    assert board._entries() == [], "nor on another exercise selection's board"


@test
def the_leaderboard_opens_on_the_picked_kind_of_board_from_both_entry_points():
    k = keuzescherm.Keuzescherm(1280, 720, theme=Theme("dark"))
    k.mode, k.game, k.num_players = PLUSMIN, "hoeden", 2
    k.selected_exercises = {A, C}
    k.selected_tables = {3, 4}
    for screen in (main_module._leaderboard_for_choice(k, None, Theme("dark")),
                   main_module._make_leaderboard(k, None, Theme("dark"), "hoeden", PLUSMIN, 2)):
        assert screen.content == PLUSMIN and screen.game == "hoeden" and screen.mode == "2"
        assert screen.filter_exercises == {A, C}
        tables, som = screen._effective_filter()
        assert sorted(tables) == [3, 4], "switching to Tafels there starts from the tables picked"
    k.mode = TAFELS
    screen = main_module._leaderboard_for_choice(k, None, Theme("dark"))
    assert screen.content == TAFELS and screen.filter_exercises == {A, C}


if __name__ == "__main__":
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", ", ".join(FAILED))
        sys.exit(1)

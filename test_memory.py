"""
test_memory.py - dev-only tests for Memory and the leaderboard changes.

Run:  python test_memory.py      (no window needed; uses SDL dummy drivers)

These check HOW things behave (timing, who may click, what gets stored),
not merely that something changed. They NEVER touch your real
leaderboard.json or settings.json: every leaderboard test uses a temp file.
"""
import json
import os
import random
import re
import sys
import tempfile
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((1280, 720))

import memory
import leaderboard
import leaderboard_screen
import keyboard_input
import main as main_module
from memory import MemoryGame, make_pairs
from theme import (Theme, contrast_ratio, best_text_color, player_color,
                   SIGNAL_GREEN, random_readable_pair)

PASSED, FAILED = [], []


def test(fn):
    try:
        fn()
        PASSED.append(fn.__name__)
    except Exception:
        FAILED.append(fn.__name__)
        print(f"FAIL {fn.__name__}")
        traceback.print_exc()
    return fn


# ------------------------------------------------------------------ helpers
class FakeCursor:
    def __init__(self, player_id, x=0, y=0, fired=False):
        self.player_id, self.x, self.y, self.fired = player_id, x, y, fired


class RecordingSound:
    def __init__(self):
        self.events = []

    def play_click(self):
        self.events.append("klik")

    def play_correct(self):
        self.events.append("goed")

    def play_wrong(self):
        self.events.append("fout")


def click(game, card, player=1, dt=1):
    """One frame in which `player` fires at the centre of `card`."""
    game.update(dt, [FakeCursor(player, *card.rect.center, fired=True)])


def advance(game, ms, step=10):
    """Run `ms` of game time in small frames with nobody shooting."""
    done = 0
    while done < ms:
        game.update(step, [])
        done += step


def settle(game):
    """Let a whole turn resolve (hold + turn-back / vanish)."""
    advance(game, memory.REVEAL_HOLD_MS + memory.SETTLE_MS + 50)


def partner(game, card):
    return next(c for c in game.cards if c.pair == card.pair and c is not card)


def two_unmatched(game):
    """A sum card and an answer card that do NOT belong together."""
    s = next(c for c in game.cards if c.kind == "sum" and not c.gone)
    a = next(c for c in game.cards if c.kind == "answer" and c.pair != s.pair and not c.gone)
    return s, a


def new_game(players=1, tables=(2, 3), som="Keer (x)", sound=None):
    random.seed(1234)
    return MemoryGame(1280, 720, list(tables), som, num_players=players, sound_bank=sound)


# ------------------------------------------------------------------ problems
@test
def pairs_are_unique_and_correct_for_every_mode_and_table_set():
    sets = [[1], [10], [2, 10], list(range(1, 11)), [7]]
    for som in ("Keer (x)", "Gedeeld door (:)", "Gemengd"):
        for tables in sets:
            for _ in range(30):
                pairs = make_pairs(tables, som)
                assert len(pairs) == 10, (som, tables, len(pairs))
                answers = [p["answer"] for p in pairs]
                assert len(set(answers)) == 10, (som, tables, answers)
                for p in pairs:
                    if " x " in p["question"]:
                        other, table = map(int, p["question"].split(" x "))
                        assert other * table == p["answer"]
                        assert table in tables and 1 <= other <= 10
                    else:
                        dividend, table = map(int, p["question"].split(" : "))
                        assert dividend // table == p["answer"] and dividend % table == 0
                        assert table in tables and 1 <= p["answer"] <= 10


@test
def pair_text_follows_the_chosen_exercise_type():
    for _ in range(20):
        assert all(" x " in p["question"] for p in make_pairs([3, 4], "Keer (x)"))
        assert all(" : " in p["question"] for p in make_pairs([3, 4], "Gedeeld door (:)"))
    seen = set()
    for _ in range(40):
        for p in make_pairs([3, 4, 5], "Gemengd"):
            seen.add("x" if " x " in p["question"] else ":")
    assert seen == {"x", ":"}, "Gemengd should contain both kinds"


@test
def multiplication_is_written_other_x_table():
    # Table 7 only: the table must be the SECOND number, e.g. "4 x 7".
    for p in make_pairs([7], "Keer (x)"):
        assert p["question"].endswith(" x 7"), p["question"]


# ------------------------------------------------------------------ layout
@test
def sums_are_left_answers_are_right_and_nothing_overlaps():
    g = new_game()
    sums = [c for c in g.cards if c.kind == "sum"]
    answers = [c for c in g.cards if c.kind == "answer"]
    assert len(sums) == len(answers) == 10
    assert max(c.rect.right for c in sums) < min(c.rect.left for c in answers)
    rects = [c.rect for c in g.cards]
    for i, a in enumerate(rects):
        assert pygame.Rect(0, 0, 1280, 720).contains(a)
        assert a.top >= memory.BAR_H, "cards must not sit under the top bar"
        for b in rects[i + 1:]:
            assert not a.colliderect(b)


@test
def every_sum_has_exactly_one_matching_answer():
    g = new_game()
    for c in g.cards:
        mates = [o for o in g.cards if o.pair == c.pair and o is not c]
        assert len(mates) == 1 and mates[0].kind != c.kind


# ------------------------------------------------------------------ turn logic
@test
def a_matching_turn_scores_holds_blocks_clicks_then_removes_both():
    snd = RecordingSound()
    g = new_game(sound=snd)
    s = next(c for c in g.cards if c.kind == "sum")
    a = partner(g, s)
    click(g, s)
    assert g.turns == 0 and s.face_up
    click(g, a)
    assert g.turns == 1 and g.pairs_found == 1
    assert "goed" in snd.events
    # During the hold both stay face up and a third click is ignored.
    other = next(c for c in g.cards if c.kind == "sum" and c is not s)
    advance(g, memory.REVEAL_HOLD_MS - 100)
    assert s.face_up and a.face_up and not s.gone
    click(g, other)
    assert not other.face_up, "clicks must be ignored during the hold"
    settle(g)
    assert s.gone and a.gone
    assert g.phase == memory.PHASE_PICK


@test
def a_mismatch_turns_both_cards_back_and_stays_silent():
    snd = RecordingSound()
    g = new_game(sound=snd)
    s, a = two_unmatched(g)
    click(g, s)
    click(g, a)
    assert g.turns == 1 and g.pairs_found == 0
    assert "goed" not in snd.events and "fout" not in snd.events  # original: silent
    assert s.result == memory.RESULT_MISS and a.result == memory.RESULT_MISS
    settle(g)
    assert not s.face_up and not a.face_up and not s.gone and not a.gone
    assert s.flip == 0.0 and a.flip == 0.0, "cards must be fully turned back"
    assert s.result is None


@test
def two_sums_or_two_answers_are_never_a_match():
    g = new_game()
    sums = [c for c in g.cards if c.kind == "sum"][:2]
    click(g, sums[0])
    click(g, sums[1])
    assert g.pairs_found == 0 and g.turns == 1
    settle(g)
    answers = [c for c in g.cards if c.kind == "answer"][:2]
    click(g, answers[0])
    click(g, answers[1])
    assert g.pairs_found == 0 and g.turns == 2


@test
def the_same_card_cannot_be_flipped_twice():
    g = new_game()
    s = next(c for c in g.cards if c.kind == "sum")
    click(g, s)
    click(g, s)
    assert g.turns == 0 and len(g._picked) == 1, "second click on the same card must not count"


@test
def hold_is_time_based_not_frame_based():
    # The same real time must give the same result at 5 ms and at 50 ms frames.
    for step in (5, 16, 50):
        g = new_game()
        s, a = two_unmatched(g)
        click(g, s)
        click(g, a)
        advance(g, memory.REVEAL_HOLD_MS - 100, step=step)
        assert s.face_up, f"still held at {memory.REVEAL_HOLD_MS - 100} ms (step {step})"
        advance(g, memory.SETTLE_MS + 300, step=step)
        assert not s.face_up and g.phase == memory.PHASE_PICK, f"released (step {step})"


@test
def perfect_play_finishes_in_exactly_ten_turns():
    g = new_game()
    for pair in range(g.num_pairs):
        s = next(c for c in g.cards if c.kind == "sum" and c.pair == pair)
        click(g, s)
        click(g, partner(g, s))
        settle(g)
    assert g.finished and g.pairs_found == 10
    r = g.results()
    assert r["turns"] == 10 and r["scores"] == {1: 10}


@test
def finished_game_ignores_further_clicks_and_updates():
    g = new_game()
    for pair in range(g.num_pairs):
        s = next(c for c in g.cards if c.kind == "sum" and c.pair == pair)
        click(g, s)
        click(g, partner(g, s))
        settle(g)
    t = g.results()["time_ms"]
    advance(g, 3000)
    assert g.results()["time_ms"] == t and g.results()["turns"] == 10


# ------------------------------------------------------------------ co-op
@test
def coop_only_the_active_players_gun_counts_and_turns_alternate():
    g = new_game(players=2)
    assert g.active_player == 1
    s, a = two_unmatched(g)
    click(g, s, player=2)                       # wrong gun
    assert not s.face_up and not g._picked, "player 2 must be ignored on player 1's turn"
    click(g, s, player=1)
    click(g, a, player=1)
    settle(g)
    assert g.active_player == 2, "turn passes after a miss"
    s2 = next(c for c in g.cards if c.kind == "sum" and not c.gone)
    click(g, s2, player=1)                      # now player 1 is the wrong gun
    assert not s2.face_up
    click(g, s2, player=2)
    assert s2.face_up
    click(g, partner(g, s2), player=2)
    settle(g)
    assert g.active_player == 1, "turn passes after a match too (default)"


@test
def coop_match_keeps_turn_when_that_rule_is_switched_on():
    old = memory.MATCH_KEEPS_TURN
    memory.MATCH_KEEPS_TURN = True
    try:
        g = new_game(players=2)
        s = next(c for c in g.cards if c.kind == "sum")
        click(g, s, player=1)
        click(g, partner(g, s), player=1)
        settle(g)
        assert g.active_player == 1, "a match keeps the turn"
        s, a = two_unmatched(g)
        click(g, s, player=1)
        click(g, a, player=1)
        settle(g)
        assert g.active_player == 2, "a miss still passes the turn"
    finally:
        memory.MATCH_KEEPS_TURN = old


@test
def one_player_game_never_switches_player():
    g = new_game(players=1)
    s, a = two_unmatched(g)
    click(g, s)
    click(g, a)
    settle(g)
    assert g.active_player == 1


@test
def coop_results_share_one_turn_count():
    g = new_game(players=2)
    for pair in range(g.num_pairs):
        s = next(c for c in g.cards if c.kind == "sum" and c.pair == pair)
        pid = g.active_player
        click(g, s, player=pid)
        click(g, partner(g, s), player=pid)
        settle(g)
    r = g.results()
    assert r["scores"] == {1: 10, 2: 10} and r["turns"] == 10


# ------------------------------------------------------------------ hidden timer
@test
def timer_starts_at_first_flip_and_not_before():
    g = new_game()
    advance(g, 5000)
    assert g.elapsed_ms == 0, "reading time before the first flip must not count"
    s = next(c for c in g.cards if c.kind == "sum")
    click(g, s)
    assert g._timer_running
    advance(g, 2000)
    assert g.elapsed_ms == 2000, g.elapsed_ms


@test
def timer_keeps_running_through_holds_and_stops_when_the_last_pair_is_flipped():
    g = new_game()
    clock = {"ms": None}

    def step(dt, cursors=()):
        running = g._timer_running
        g.update(dt, list(cursors))
        if running and not g.finished:
            pass
        return running

    # Play perfectly, tracking expected time ourselves: every update call that
    # happens while the timer is running (before the last pair is flipped)
    # adds its dt.
    expected = 0
    first = True
    for pair in range(g.num_pairs):
        s = next(c for c in g.cards if c.kind == "sum" and c.pair == pair)
        a = partner(g, s)
        for card in (s, a):
            before = g._timer_running
            g.update(1, [FakeCursor(1, *card.rect.center, fired=True)])
            if before:
                expected += 1          # this frame was counted (timer was running)
            first = False
        if pair < g.num_pairs - 1:
            frames = (memory.REVEAL_HOLD_MS + memory.SETTLE_MS + 50) // 10
            for _ in range(frames):
                before = g._timer_running
                g.update(10, [])
                if before:
                    expected += 10
    final_time = g.results()["time_ms"]
    assert final_time == expected, (final_time, expected)
    # After the last flip the remaining hold must not add time.
    advance(g, 4000)
    assert g.results()["time_ms"] == final_time
    assert final_time > 9 * memory.REVEAL_HOLD_MS, "holds in between DO count"


@test
def timer_is_never_drawn_anywhere():
    g = new_game()
    seen = []

    class Spy:
        def __init__(self, font):
            self._f = font

        def render(self, text, aa, color, *a):
            seen.append(str(text))
            return self._f.render(text, aa, color, *a)

        def __getattr__(self, name):
            return getattr(self._f, name)

    for name in ("font_card", "font_back", "font_bar", "font_player"):
        setattr(g, name, Spy(getattr(g, name)))
    s = next(c for c in g.cards if c.kind == "sum")
    click(g, s)
    g.elapsed_ms = 754_321                     # 12:34.3 - must never appear
    surf = pygame.Surface((1280, 720))
    g.draw(surf)
    joined = " | ".join(seen)
    assert "754" not in joined and not re.search(r"\d+:\d\d", joined), joined
    g2 = new_game(players=2)
    for name in ("font_card", "font_back", "font_bar", "font_player"):
        setattr(g2, name, Spy(getattr(g2, name)))
    g2.elapsed_ms = 754_321
    g2.draw(surf)
    assert "754" not in " | ".join(seen) and not re.search(r"\d+:\d\d", " | ".join(seen))


# ------------------------------------------------------------------ leaderboard
def temp_lb():
    return os.path.join(tempfile.mkdtemp(), "lb.json")


@test
def memory_ranks_fewer_turns_first_then_faster_time():
    p = temp_lb()
    add = lambda n, t, ms: leaderboard.add_score(n, t, "1", [2], "Keer (x)",
                                                 game="memory", time_ms=ms, path=p)
    add("slowperfect", 10, 300_000)      # 10 turns, 5 minutes
    add("fastsloppy", 12, 120_000)       # 12 turns, 2 minutes
    add("fastperfect", 10, 90_000)
    add("tie_b", 11, 60_000)
    add("tie_a", 11, 50_000)
    names = [e["name"] for e in leaderboard.top(
        10, mode="1", game="memory", tables=[2], som_type="Keer (x)", path=p)]
    assert names == ["fastperfect", "slowperfect", "tie_a", "tie_b", "fastsloppy"], names


@test
def best_attempt_per_name_uses_turns_then_time():
    p = temp_lb()
    add = lambda t, ms: leaderboard.add_score("Emma", t, "1", [2], "Keer (x)",
                                              game="memory", time_ms=ms, path=p)
    add(12, 100_000)
    add(10, 200_000)
    add(10, 150_000)
    add(14, 30_000)
    rows = leaderboard.top(10, mode="1", game="memory", tables=[2],
                           som_type="Keer (x)", unique_names=True, path=p)
    assert len(rows) == 1 and rows[0]["score"] == 10 and rows[0]["time_ms"] == 150_000
    assert rows[0]["attempts"] == 4


@test
def other_games_still_rank_higher_is_better_and_old_rows_are_untouched():
    p = temp_lb()
    legacy = [
        {"id": "a", "name": "Anna", "score": 127, "mode": "1", "tables": [2],
         "som_type": "Gemengd", "date": "2026-10-01T10:00:00", "game": "klok"},
        {"id": "b", "name": "Bram", "score": 324, "mode": "1", "tables": [2],
         "som_type": "Gemengd", "date": "2026-10-01T10:01:00", "game": "klok"},
        {"id": "c", "name": "Cleo", "score": 324, "mode": "1", "tables": [2],
         "som_type": "Gemengd", "date": "2026-10-01T10:02:00", "game": "klok"},
    ]
    with open(p, "w", encoding="utf-8") as f:
        json.dump(legacy, f, indent=2)
    before = open(p, "rb").read()
    rows = leaderboard.top(10, mode="1", game="klok", tables=[2], som_type="Gemengd", path=p)
    assert [r["name"] for r in rows] == ["Bram", "Cleo", "Anna"], "ties keep insertion order"
    assert open(p, "rb").read() == before, "reading must not rewrite or add fields to old rows"
    assert all("time_ms" not in e for e in json.load(open(p)))


@test
def rows_without_time_sort_after_rows_with_time_on_equal_turns():
    p = temp_lb()
    leaderboard.add_score("old", 10, "1", [2], "Keer (x)", game="memory", path=p)
    leaderboard.add_score("timed", 10, "1", [2], "Keer (x)", game="memory",
                          time_ms=500_000, path=p)
    rows = leaderboard.top(10, mode="1", game="memory", tables=[2], som_type="Keer (x)", path=p)
    assert [r["name"] for r in rows] == ["timed", "old"]
    assert "time_ms" not in json.load(open(p))[0]


@test
def coop_match_is_recorded_as_one_row_named_with_both_players():
    p = temp_lb()
    g = new_game(players=2)
    for pair in range(g.num_pairs):
        s = next(c for c in g.cards if c.kind == "sum" and c.pair == pair)
        pid = g.active_player
        click(g, s, player=pid)
        click(g, partner(g, s), player=pid)
        settle(g)
    results = g.results()
    final = main_module._final_scores("memory", results, 2)
    assert final == {1: 10}, "name-entry shows ONE shared score box"
    main_module._record_scores("memory", final, {1: "Jan", 2: "Sam"}, [2, 3],
                               "Keer (x)", results=results, path=p)
    rows = json.load(open(p))
    assert len(rows) == 1, rows
    r = rows[0]
    assert r["name"] == "Jan & Sam" and r["score"] == 10 and r["mode"] == "2"
    assert r["game"] == "memory" and r["time_ms"] == results["time_ms"] > 0
    assert r["tables"] == [2, 3] and r["som_type"] == "Keer (x)"


@test
def one_player_memory_is_one_row_with_just_the_name_and_a_time():
    p = temp_lb()
    results = {"scores": {1: 14}, "turns": 14, "time_ms": 98_765}
    main_module._record_scores("memory", {1: 14}, {1: "Emma"}, [4], "Gemengd",
                               results=results, path=p)
    rows = json.load(open(p))
    assert len(rows) == 1 and rows[0]["name"] == "Emma" and rows[0]["mode"] == "1"
    assert rows[0]["score"] == 14 and rows[0]["time_ms"] == 98_765


@test
def other_games_still_record_one_row_per_player_without_time():
    p = temp_lb()
    main_module._record_scores("ballon", {1: 50, 2: 30}, {1: "A", 2: "B"}, [2],
                               "Keer (x)", results={"scores": {1: 50, 2: 30}}, path=p)
    rows = json.load(open(p))
    assert sorted((r["name"], r["score"]) for r in rows) == [("A", 50), ("B", 30)]
    assert all("time_ms" not in r for r in rows)
    assert main_module._final_scores("klok", {"scores": {1: 5, 2: 7}}, 2) == {1: 5, 2: 7}
    assert main_module._final_scores("klok", {"scores": {1: 5}, "bank_remaining": 640}, 1) == {1: 640}


@test
def memory_is_registered_everywhere_it_has_to_be():
    import keuzescherm
    assert "memory" in keuzescherm.GAMES and keuzescherm.game_label("memory") == "Memory"
    assert main_module.GAME_CLASSES["memory"] is MemoryGame
    assert main_module.score_word("memory") == "Beurten"
    assert leaderboard_screen.score_column_label("memory") == "Beurten"
    assert set(keuzescherm.GAMES) == set(main_module.GAME_CLASSES) == set(
        leaderboard_screen.SCORE_COLUMN_KEYS) == set(main_module.SCORE_WORD_KEYS)


@test
def coop_pair_order_and_case_do_not_matter_when_collapsing_names():
    p = temp_lb()
    add = lambda n, t, ms: leaderboard.add_score(n, t, "2", [2], "Keer (x)",
                                                 game="memory", time_ms=ms, path=p)
    add("Jan & Sam", 12, 50_000)
    add("sam & JAN ", 10, 90_000)        # same pair, other order/case/spaces: best attempt
    add("Sam & Jan", 14, 10_000)
    add("Jan & Emma", 11, 20_000)        # a different pair must stay separate
    rows = leaderboard.top(10, mode="2", game="memory", tables=[2],
                           som_type="Keer (x)", unique_names=True, path=p)
    assert len(rows) == 2, [(r["name"], r["attempts"]) for r in rows]
    best = rows[0]
    assert best["score"] == 10 and best["attempts"] == 3
    assert best["name"] == "sam & JAN", "shown as the best attempt was typed"
    assert rows[1]["name"] == "Jan & Emma" and rows[1]["attempts"] == 1


@test
def pair_merging_does_not_leak_into_single_names_or_other_games():
    p = temp_lb()
    # Memory 1 player: ordinary case-insensitive name collapsing only.
    for n in ("Emma", "emma "):
        leaderboard.add_score(n, 12, "1", [2], "Keer (x)", game="memory", time_ms=1, path=p)
    rows = leaderboard.top(10, mode="1", game="memory", tables=[2], som_type="Keer (x)",
                           unique_names=True, path=p)
    assert len(rows) == 1 and rows[0]["attempts"] == 2
    # A non-co-op game never splits on "&": these are two different names.
    for n in ("A & B", "B & A"):
        leaderboard.add_score(n, 5, "1", [2], "Keer (x)", game="klok", path=p)
    rows = leaderboard.top(10, mode="1", game="klok", tables=[2], som_type="Keer (x)",
                           unique_names=True, path=p)
    assert len(rows) == 2


# ------------------------------------------------------------------ screens
@test
def leaderboard_screen_shows_turns_time_and_fits_long_joined_names():
    p = temp_lb()
    long_name = "ABCDEFGHIJKL & MNOPQRSTUVWX"        # 27 chars, the worst case
    leaderboard.add_score(long_name, 10, "2", [2], "Keer (x)", game="memory",
                          time_ms=125_000, path=p)
    leaderboard.add_score("Jan & Sam", 12, "2", [2], "Keer (x)", game="memory",
                          time_ms=61_000, path=p)
    scr = leaderboard_screen.LeaderboardScreen(
        1280, 720, initial_mode="2", leaderboard_path=p, initial_tables=[2],
        initial_som_type="Keer (x)", theme=Theme("dark"), game="memory")
    surf = pygame.Surface((1280, 720))
    scr.draw(surf)
    cols = scr._columns()
    assert [c[0] for c in cols] == ["#", "Naam", "Beurten", "Tijd", "Pogingen", "Datum"]
    rows = scr._entries()
    assert [r["name"] for r in rows] == [long_name, "Jan & Sam"]
    values = scr._row_values(0, rows[0])
    assert values[3] == "2:05" and values[2] == "10"
    # The name column's text must end before the next column starts.
    (_, name_x, name_max), (_, next_x, _) = cols[1], cols[2]
    fitted = leaderboard_screen.fit_text(scr.font_row, long_name, name_max)
    assert scr.font_row.size(fitted)[0] <= name_max
    assert name_x + name_max < next_x
    short = leaderboard_screen.fit_text(scr.font_row, "Jan & Sam", name_max)
    assert short == "Jan & Sam", "short names are left alone"
    # Other games keep their exact old layout (no Tijd column).
    scr.game = "klok"
    assert [c[0] for c in scr._columns()] == ["#", "Naam", "Punten", "Pogingen", "Datum"]
    # The admin overlay renders for memory too.
    scr.game = "memory"
    scr.settings_open = True
    scr.draw(surf)
    assert "beurten" in scr._admin_row_text(rows[0]) and "2:05" in scr._admin_row_text(rows[0])


@test
def format_time_handles_missing_and_long_times():
    f = leaderboard_screen.format_time
    assert f(None) == "-" and f(0) == "0:00" and f(59_999) == "0:59"
    assert f(60_000) == "1:00" and f(754_321) == "12:34"


@test
def shared_score_box_stays_highlighted_while_player_two_types():
    kb = keyboard_input.OnScreenKeyboard(1280, 720, "Naam Speler 2:", theme=Theme("dark"),
                                         scores={1: 12}, active_player=2, score_word="Beurten")
    surf = pygame.Surface((1280, 720))
    kb.draw(surf)
    rect = kb.score_rects[1]
    assert tuple(surf.get_at((rect.left + 6, rect.centery)))[:3] == SIGNAL_GREEN
    # Two separate boxes still highlight only the active player's.
    kb2 = keyboard_input.OnScreenKeyboard(1280, 720, "Naam Speler 2:", theme=Theme("dark"),
                                          scores={1: 5, 2: 7}, active_player=2)
    kb2.draw(surf)
    assert tuple(surf.get_at((kb2.score_rects[2].left + 6, kb2.score_rects[2].centery)))[:3] == SIGNAL_GREEN
    assert tuple(surf.get_at((kb2.score_rects[1].left + 6, kb2.score_rects[1].centery)))[:3] != SIGNAL_GREEN


# ------------------------------------------------------------------ Hoeden: leaderboard + name entry
@test
def hoeden_ranks_higher_score_first_then_less_time_and_old_rows_after():
    p = temp_lb()
    add = lambda n, sc, ms: leaderboard.add_score(n, sc, "1", [2], "Keer (x)",
                                                  game="hoeden", time_ms=ms, path=p)
    add("slow8", 8, 90_000)
    add("fast8", 8, 30_000)
    add("best9", 9, 200_000)
    add("low5", 5, 1_000)
    leaderboard.add_score("old8", 8, "1", [2], "Keer (x)", game="hoeden", path=p)   # pre-timer row
    names = [e["name"] for e in leaderboard.top(
        10, mode="1", game="hoeden", tables=[2], som_type="Keer (x)", path=p)]
    assert names == ["best9", "fast8", "slow8", "old8", "low5"], names


@test
def hoeden_two_players_get_one_row_each_with_their_own_time():
    p = temp_lb()
    results = {"scores": {1: 7, 2: 4}, "times_ms": {1: 41_000, 2: 66_500}, "rounds_total": 11}
    main_module._record_scores("hoeden", {1: 7, 2: 4}, {1: "Jan", 2: "Sam"}, [2, 3],
                               "Keer (x)", results=results, path=p)
    rows = {r["name"]: r for r in json.load(open(p))}
    assert set(rows) == {"Jan", "Sam"}, "Hoeden stays competitive: no joined name"
    assert rows["Jan"]["score"] == 7 and rows["Jan"]["time_ms"] == 41_000
    assert rows["Sam"]["score"] == 4 and rows["Sam"]["time_ms"] == 66_500
    assert rows["Jan"]["mode"] == rows["Sam"]["mode"] == "2" and rows["Jan"]["game"] == "hoeden"


@test
def games_without_a_hidden_timer_still_store_no_time():
    p = temp_lb()
    main_module._record_scores("klok", {1: 640}, {1: "Emma"}, [2], "Keer (x)",
                               results={"scores": {1: 5}, "bank_remaining": 640}, path=p)
    assert "time_ms" not in json.load(open(p))[0]


@test
def name_entry_extras_per_game():
    hoed = {"scores": {1: 8, 2: 3}, "times_ms": {1: 42_000, 2: 95_000}, "rounds_total": 11}
    labels, times = main_module._name_entry_extras("hoeden", {1: 8, 2: 3}, hoed)
    assert labels == {1: "8/11", 2: "3/11"} and times == {1: 42_000, 2: 95_000}
    mem = {"scores": {1: 12, 2: 12}, "turns": 12, "time_ms": 61_000}
    labels, times = main_module._name_entry_extras("memory", {1: 12}, mem)
    assert labels is None and times == {1: 61_000}, "Memory: ONE shared time, bare turn count"
    assert main_module._name_entry_extras("klok", {1: 300}, {"scores": {1: 5}}) == (None, None)
    assert main_module._name_entry_extras("ballon", {1: 50, 2: 30}, {"scores": {1: 50, 2: 30}}) == (None, None)


class _Spy:
    def __init__(self, font, sink):
        self._f, self._sink = font, sink

    def render(self, text, aa, color, *a):
        self._sink.append(str(text))
        return self._f.render(text, aa, color, *a)

    def __getattr__(self, name):
        return getattr(self._f, name)


def _draw_keyboard(**kw):
    kb = keyboard_input.OnScreenKeyboard(1280, 720, "Naam:", theme=Theme("dark"), **kw)
    sink = []
    kb.font_score = _Spy(kb.font_score, sink)
    surf = pygame.Surface((1280, 720))
    kb.draw(surf)
    return kb, surf, sink


@test
def name_entry_shows_the_time_next_to_the_score_in_hoeden_and_memory():
    # Hoeden, two players: "Speler 1: 8/11" + stopwatch + "0:42", own time per player.
    kb, surf, strings = _draw_keyboard(scores={1: 8, 2: 3}, active_player=1, score_word="Score",
                                       times={1: 42_000, 2: 95_000},
                                       score_labels={1: "8/11", 2: "3/11"})
    assert "Speler 1: 8/11" in strings and "Speler 2: 3/11" in strings
    assert "0:42" in strings and "1:35" in strings
    # Memory, one shared box: "Beurten: 12" + time.
    kb, surf, strings = _draw_keyboard(scores={1: 12}, active_player=2, score_word="Beurten",
                                       times={1: 61_000})
    assert "Beurten: 12" in strings and "1:01" in strings
    # Hoeden, one player: "Score: 8/10".
    kb, surf, strings = _draw_keyboard(scores={1: 8}, active_player=1, score_word="Score",
                                       times={1: 42_000}, score_labels={1: "8/10"})
    assert "Score: 8/10" in strings and "0:42" in strings


@test
def name_entry_without_a_timer_looks_exactly_as_before():
    kb, surf, strings = _draw_keyboard(scores={1: 5, 2: 7}, active_player=1)
    assert "Speler 1: 5" in strings and "Speler 2: 7" in strings
    assert not any(re.search(r"\d+:\d\d", t) for t in strings)
    assert all(r.w == 220 for r in kb.score_rects.values()), "unchanged box width"
    kb, surf, strings = _draw_keyboard(scores={1: 300}, active_player=1, score_word="Score")
    assert strings.count("Score: 300") == 1 and kb.score_rects[1].w == 220


@test
def score_boxes_always_contain_their_content_and_never_collide():
    for times in ({1: 5_000, 2: 5_000}, {1: 599_000, 2: 3_599_000}):
        for labels in ({1: "8/11", 2: "11/11"}, {1: "10/10", 2: "0/11"}):
            kb, surf, strings = _draw_keyboard(scores={1: 8, 2: 3}, active_player=2,
                                               score_word="Score", times=times,
                                               score_labels=labels)
            screen = pygame.Rect(0, 0, 1280, 720)
            a, b = kb.score_rects[1], kb.score_rects[2]
            assert screen.contains(a) and screen.contains(b) and not a.colliderect(b)
            for pid, rect in kb.score_rects.items():
                assert kb._score_group_width(pid) + 40 <= rect.w, (pid, rect)
    # The stopwatch really is drawn: icon-coloured (white) pixels exist between
    # the score text and the time, which a box without a time doesn't have there.
    kb, surf, _ = _draw_keyboard(scores={1: 8}, active_player=1, score_word="Score",
                                 times={1: 42_000}, score_labels={1: "8/10"})
    rect = kb.score_rects[1]
    x0 = rect.centerx - kb._score_group_width(1) // 2
    text_w = kb.font_score.size(kb._score_text(1))[0]
    icon_box = pygame.Rect(x0 + text_w + kb._TIME_GAP, rect.top, kb._TIME_ICON_SIZE, rect.h)
    # (Icons are anti-aliased, so "white" means every channel above 230, not exactly 255.)
    whites = sum(1 for x in range(icon_box.left, icon_box.right) for y in range(icon_box.top, icon_box.bottom)
                 if min(surf.get_at((x, y))[:3]) > 230)
    assert whites > 40, whites
    # And with no time for this player, that same spot on the green box holds no white pixels.
    kb2, surf2, _ = _draw_keyboard(scores={1: 8}, active_player=1, score_word="Score",
                                   score_labels={1: "8/10"})
    r2 = kb2.score_rects[1]
    x2 = r2.centerx - kb2._score_group_width(1) // 2 + kb2.font_score.size(kb2._score_text(1))[0]
    assert not any(min(surf2.get_at((x, y))[:3]) > 230
                   for x in range(x2 + 5, r2.right - 5) for y in range(r2.top + 3, r2.bottom - 3))


@test
def score_is_called_score_everywhere_for_hoeden_never_bloemen():
    import keuzescherm
    assert main_module.score_word("hoeden") == "Score"
    assert leaderboard_screen.score_column_label("hoeden") == "Score"
    for game in keuzescherm.GAMES:
        for word in (main_module.score_word(game), leaderboard_screen.score_column_label(game)):
            assert "loem" not in word, (game, word)


@test
def leaderboard_screen_shows_score_and_time_for_hoeden():
    p = temp_lb()
    leaderboard.add_score("Emma", 9, "1", [2], "Keer (x)", game="hoeden", time_ms=42_000, path=p)
    leaderboard.add_score("Noor", 9, "1", [2], "Keer (x)", game="hoeden", time_ms=30_000, path=p)
    leaderboard.add_score("Oud", 9, "1", [2], "Keer (x)", game="hoeden", path=p)   # old row, no time
    scr = leaderboard_screen.LeaderboardScreen(
        1280, 720, initial_mode="1", leaderboard_path=p, initial_tables=[2],
        initial_som_type="Keer (x)", theme=Theme("dark"), game="hoeden")
    surf = pygame.Surface((1280, 720))
    scr.draw(surf)
    assert [c[0] for c in scr._columns()] == ["#", "Naam", "Score", "Tijd", "Pogingen", "Datum"]
    rows = scr._entries()
    assert [r["name"] for r in rows] == ["Noor", "Emma", "Oud"], "tie on score -> less time first, old row last"
    assert scr._row_values(0, rows[0])[3] == "0:30" and scr._row_values(2, rows[2])[3] == "-"
    scr.settings_open = True
    scr.draw(surf)
    assert scr._admin_row_text(rows[0]).startswith("Noor - 9 punten, 0:30")
    # The other timer-less games keep their original layout.
    scr.game = "ballon"
    assert [c[0] for c in scr._columns()] == ["#", "Naam", "Punten", "Pogingen", "Datum"]


# ------------------------------------------------------------------ readability
@test
def all_memory_text_meets_wcag_aa_in_dark_and_light():
    pairs = {
        "back dark": memory._BACK[0], "back light": memory._BACK[1],
        "face dark": memory._FACE[0], "face light": memory._FACE[1],
        "topbar dark": memory._TOPBAR[0], "topbar light": memory._TOPBAR[1],
        "background dark": memory._BACKGROUND[0], "background light": memory._BACKGROUND[1],
        "match face": (SIGNAL_GREEN, (255, 255, 255)),
    }
    for name, (bg, fg) in pairs.items():
        ratio = contrast_ratio(bg, fg)
        print(f"   contrast {name:18s} {ratio:5.2f}:1")
        assert ratio >= 4.5, (name, ratio)


@test
def turn_indicator_text_is_readable_on_every_bar_color():
    bars = [memory._TOPBAR[0][0], memory._TOPBAR[1][0]]
    for _ in range(300):
        bars.append(random_readable_pair()[0])     # regenboog bars
    worst = 99
    for bar in bars:
        for pid in (1, 2):
            fill = player_color(pid, bar)
            worst = min(worst, contrast_ratio(fill, best_text_color(fill)))
    print(f"   worst indicator text contrast over {len(bars)} bars: {worst:.2f}:1")
    assert worst >= 4.5


@test
def draws_in_every_theme_and_state_without_error():
    surf = pygame.Surface((1280, 720))
    for mode in ("dark", "light", "regenboog"):
        theme = Theme(mode)
        for players in (1, 2):
            g = MemoryGame(1280, 720, [2, 3], "Gemengd", num_players=players, theme=theme)
            g.draw(surf)
            s, a = two_unmatched(g)
            click(g, s, player=1)
            advance(g, memory.FLIP_ANIM_MS // 2)          # mid-flip
            g.draw(surf)
            click(g, a, player=1)
            advance(g, 200)
            g.draw(surf)                                    # miss outline
            settle(g)
            s = next(c for c in g.cards if c.kind == "sum" and not c.gone)
            click(g, s, player=g.active_player)
            click(g, partner(g, s), player=g.active_player)
            g.draw(surf)                                    # match (green)
            advance(g, memory.REVEAL_HOLD_MS + memory.VANISH_ANIM_MS // 2)
            g.draw(surf)                                    # mid-vanish
            theme.randomize()


@test
def indicator_highlights_the_active_player():
    g = new_game(players=2)
    surf = pygame.Surface((1280, 720))
    g.draw(surf)
    bar_color = memory._TOPBAR[0][0]
    left = g.screen_w // 2 - 200 - 12
    p1_box = pygame.Rect(left, (memory.BAR_H - 52) // 2, 200, 52)
    p2_box = pygame.Rect(left + 224, (memory.BAR_H - 52) // 2, 200, 52)
    inner = lambda r: (r.left + 10, r.top + 10)
    assert tuple(surf.get_at(inner(p1_box)))[:3] == player_color(1, bar_color), "P1 active = filled"
    assert tuple(surf.get_at(inner(p2_box)))[:3] == bar_color, "P2 inactive = just outlined"
    s, a = two_unmatched(g)
    click(g, s, player=1)
    click(g, a, player=1)
    settle(g)
    g.draw(surf)
    assert tuple(surf.get_at(inner(p2_box)))[:3] == player_color(2, bar_color), "now P2 is filled"
    assert tuple(surf.get_at(inner(p1_box)))[:3] == bar_color


if __name__ == "__main__":
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", ", ".join(FAILED))
        sys.exit(1)

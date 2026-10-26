"""
test_hoeden.py - dev-only tests for Hoeden's "Score: 4/6" display and its
hidden answer timer.   Run:  python test_hoeden.py

Checks HOW things behave (when the clock runs and stops, what is drawn),
not just that something changed.
"""
import os
import random
import re
import sys
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((1280, 720))

import hoeden
from hoeden import HoedenGame

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


class FakeCursor:
    def __init__(self, player_id, x, y, fired=True):
        self.player_id, self.x, self.y, self.fired = player_id, x, y, fired


def new_game(players=1):
    random.seed(99)
    return HoedenGame(1280, 720, [2, 3, 4], "Keer (x)", num_players=players)


STEP = 10   # ms per simulated frame (below hoeden.MAX_DT_MS, so nothing is capped)


def to_answer(g):
    """Run the intro / peek / shuffle until the hats become clickable."""
    elapsed = 0
    while g.phase != hoeden.PHASE_ANSWER:
        g.update(STEP, [])
        elapsed += STEP
        assert elapsed < 120_000, "never reached the answer phase"


def run(g, ms):
    for _ in range(ms // STEP):
        g.update(STEP, [])


def click_hat(g, hat, player=1):
    g.update(STEP, [FakeCursor(player, *hat.rect().center)])


def correct_hat(g):
    return next(h for h in g.hats if h.is_correct)


def wrong_hat(g):
    return next(h for h in g.hats if not h.is_correct and not h.clicked_wrong)


def finish_round_display(g):
    """Run the 'resolved' reveal until the next round starts (or the game ends)."""
    before = g.round_num
    guard = 0
    while not g.finished and g.round_num == before:
        g.update(STEP, [])
        guard += STEP
        assert guard < 20_000


class Spy:
    """Wraps a pygame Font and records every string rendered with it."""
    def __init__(self, font, sink):
        self._f, self._sink = font, sink

    def render(self, text, aa, color, *a):
        self._sink.append(str(text))
        return self._f.render(text, aa, color, *a)

    def __getattr__(self, name):
        return getattr(self._f, name)


def spy_on(g):
    sink = []
    for name in ("font_question", "font_value", "font_score", "font_progress"):
        setattr(g, name, Spy(getattr(g, name), sink))
    return sink


def drawn_strings(g):
    sink = spy_on(g)
    g.draw(pygame.Surface((1280, 720)))
    return sink


# ------------------------------------------------------------------ Score display
@test
def one_player_hud_reads_score_points_out_of_rounds_played():
    g = new_game(1)
    assert "Score: 0/0" in drawn_strings(g)
    to_answer(g)
    click_hat(g, correct_hat(g))                     # round 1: right
    assert "Score: 1/1" in drawn_strings(g)
    finish_round_display(g)
    to_answer(g)
    click_hat(g, wrong_hat(g))                       # round 2: wrong (1P: out for the round)
    assert g.phase == hoeden.PHASE_RESOLVED
    assert "Score: 1/2" in drawn_strings(g), "a wrong round still counts as played"


@test
def the_word_bloemen_is_gone_from_the_screen():
    for players in (1, 2):
        g = new_game(players)
        to_answer(g)
        click_hat(g, correct_hat(g), 1)
        strings = " | ".join(drawn_strings(g))
        assert "loem" not in strings, strings


@test
def two_player_hud_shows_each_players_score_out_of_rounds_played():
    g = new_game(2)
    to_answer(g)
    click_hat(g, correct_hat(g), player=2)
    strings = drawn_strings(g)
    assert "Speler 1: 0/1" in strings and "Speler 2: 1/1" in strings, strings
    finish_round_display(g)
    to_answer(g)
    click_hat(g, correct_hat(g), player=1)
    strings = drawn_strings(g)
    assert "Speler 1: 1/2" in strings and "Speler 2: 1/2" in strings, strings


@test
def the_denominator_can_be_switched_to_the_whole_match():
    old = hoeden.SCORE_SHOWS_ROUNDS_PLAYED
    hoeden.SCORE_SHOWS_ROUNDS_PLAYED = False
    try:
        g = new_game(1)
        assert "Score: 0/10" in drawn_strings(g)
        g2 = new_game(2)
        strings = drawn_strings(g2)
        assert "Speler 1: 0/11" in strings and "Speler 2: 0/11" in strings
    finally:
        hoeden.SCORE_SHOWS_ROUNDS_PLAYED = old


@test
def rounds_played_counts_each_decided_round_exactly_once():
    g = new_game(2)
    assert g.rounds_played == 0
    to_answer(g)
    click_hat(g, wrong_hat(g), 1)
    assert g.rounds_played == 0, "one wrong click does not decide a 2-player round"
    click_hat(g, wrong_hat(g), 2)
    assert g.rounds_played == 1 and g.phase == hoeden.PHASE_RESOLVED
    run(g, 500)
    assert g.rounds_played == 1, "must not count again while the reveal is shown"
    finish_round_display(g)
    to_answer(g)
    click_hat(g, correct_hat(g), 1)
    assert g.rounds_played == 2


# ------------------------------------------------------------------ Hidden timer
@test
def timer_ignores_the_fixed_animation_and_starts_when_hats_become_clickable():
    for start_round in (1, hoeden.SHUFFLE_START_ROUND):     # 9 includes the shuffle
        g = new_game(1)
        g.round_num = start_round
        g._start_round()
        to_answer(g)
        assert g.answer_time_ms == {1: 0}, (start_round, g.answer_time_ms)
        run(g, 1000)
        assert g.answer_time_ms == {1: 1000}


@test
def timer_stops_when_the_round_is_decided():
    g = new_game(1)
    to_answer(g)
    run(g, 700)
    click_hat(g, correct_hat(g))                    # this frame still counts (STEP ms)
    t = g.answer_time_ms[1]
    assert t == 700 + STEP, t
    run(g, 3000)                                    # reveal + start of next round's animation
    assert g.answer_time_ms[1] == t, "no time may be added after answering"


@test
def timer_adds_up_over_rounds_and_only_counts_answering():
    g = new_game(1)
    total = 0
    for wait in (300, 900, 1500):
        to_answer(g)
        run(g, wait)
        click_hat(g, correct_hat(g))
        total += wait + STEP
        finish_round_display(g)
        assert g.answer_time_ms[1] == total, (g.answer_time_ms, total)


@test
def two_player_clocks_follow_the_answer_time_rules():
    # P1 clicks a wrong hat at 500 ms; P2 keeps deciding and is right at 1200 ms.
    g = new_game(2)
    to_answer(g)
    run(g, 490)
    click_hat(g, wrong_hat(g), 1)
    assert g.answer_time_ms[1] == 500
    run(g, 690)
    click_hat(g, correct_hat(g), 2)
    assert g.answer_time_ms[1] == 500, "a player who answered wrong stops at that click"
    assert g.answer_time_ms[2] == 1200, g.answer_time_ms
    assert g.scores == {1: 0, 2: 1}


@test
def a_player_who_never_clicks_stops_when_the_round_ends():
    g = new_game(2)
    to_answer(g)
    run(g, 790)
    click_hat(g, correct_hat(g), 1)
    assert g.answer_time_ms == {1: 800, 2: 800}
    run(g, 2000)
    assert g.answer_time_ms == {1: 800, 2: 800}


@test
def one_stalled_frame_cannot_inflate_the_time():
    g = new_game(1)
    to_answer(g)
    g.update(5000, [])                              # window dragged for 5 s
    assert g.answer_time_ms[1] == hoeden.MAX_DT_MS


@test
def the_timer_is_never_drawn():
    for players in (1, 2):
        g = new_game(players)
        to_answer(g)
        for pid in g.answer_time_ms:
            g.answer_time_ms[pid] = 754_321          # 12:34 - must never show up
        strings = " | ".join(drawn_strings(g))
        assert "754" not in strings and not re.search(r"\d+:\d\d", strings), strings


# ------------------------------------------------------------------ Results
@test
def a_full_one_player_game_reports_score_time_and_round_count():
    g = new_game(1)
    for _ in range(g.total_rounds):
        to_answer(g)
        run(g, 400)
        click_hat(g, correct_hat(g))
        finish_round_display(g)
    assert g.finished and g.rounds_played == 10
    r = g.results()
    assert r["scores"] == {1: 10} and r["rounds_total"] == 10
    assert r["times_ms"] == {1: 10 * (400 + STEP)}
    assert all(isinstance(v, int) for v in r["times_ms"].values())


@test
def a_full_two_player_game_reports_both_players():
    g = new_game(2)
    for rnd in range(g.total_rounds):
        winner = 1 if rnd % 3 else 2
        to_answer(g)
        run(g, 300 + 100 * winner)
        click_hat(g, correct_hat(g), winner)
        finish_round_display(g)
    assert g.finished and g.rounds_played == 11
    r = g.results()
    assert sum(r["scores"].values()) == 11 and r["rounds_total"] == 11
    assert set(r["times_ms"]) == {1, 2} and all(v > 0 for v in r["times_ms"].values())


if __name__ == "__main__":
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", ", ".join(FAILED))
        sys.exit(1)

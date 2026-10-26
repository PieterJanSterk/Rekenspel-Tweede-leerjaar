"""
test_exercises.py - dev-only tests for exercises.py (the shared problem engine)
and for all four games running on plus-and-min exercises.   Run: python test_exercises.py

The rules of the 23 exercise types are restated here INDEPENDENTLY, as one
predicate per type written from the teacher's descriptions - not copied from
the generators - so a porting slip would be caught. If the original
plusminus.py sits next to this file, the generators are also compared with it.
"""
import importlib
import io
import contextlib
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

import ballon
import exercises
import hoeden
import klok
import memory
from exercises import (EXERCISE_BY_KEY, EXERCISE_TYPES, ExerciseSet, GROUPS, TableSet,
                       types_in, valid_keys)

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


def pure_ten(n):
    return n % 10 == 0 and n > 0


def multiple_of_ten(n):
    return n % 10 == 0


# The teacher's rules, one predicate per type: (a, b) -> bool, op fixed by type.
RULES = {
    "e_plus_e_to10_zb":   ("+", lambda a, b: 0 <= a <= 10 and 0 <= b <= 10 and a + b <= 10),
    "e_minus_e_to10_zb":  ("-", lambda a, b: 0 <= b <= a <= 10),
    "t_plus_e_to20_zb":   ("+", lambda a, b: (a == 10 and 0 <= b <= 10) or (b == 10 and 0 <= a <= 10)),
    "te_plus_e_to20_zb":  ("+", lambda a, b: 11 <= a + b <= 20 and ((a >= 10) != (b >= 10))
                           and a % 10 + b % 10 <= 10),
    "e_plus_e_to20_mb":   ("+", lambda a, b: 1 <= a <= 9 and 1 <= b <= 9 and a + b > 10),
    "t_minus_e_te_20_zb": ("-", lambda a, b: a == 20 and 0 <= b <= 20),
    "te_minus_e_to20_zb": ("-", lambda a, b: 11 <= a <= 20 and 0 <= b <= 10 and a - b >= 10),
    "te_minus_te_to20_zb": ("-", lambda a, b: 11 <= a <= 20 and 11 <= b <= 20 and a >= b
                            and a % 10 >= b % 10),
    "te_minus_e_to20_mb": ("-", lambda a, b: 11 <= a <= 19 and 1 <= b <= 9 and a - b < 10),
    "t_plus_t_to100_zb":  ("+", lambda a, b: multiple_of_ten(a) and multiple_of_ten(b) and a + b <= 100),
    "t_plus_e_to100_zb":  ("+", lambda a, b: pure_ten(a) and a <= 90 and 1 <= b <= 9),
    "te_plus_t_to100_zb": ("+", lambda a, b: 11 <= a <= 89 and a % 10 != 0 and pure_ten(b)
                           and b <= 80 and a + b <= 100),
    "te_plus_e_to100_zb": ("+", lambda a, b: 11 <= a <= 99 and a % 10 != 0 and 0 <= b <= 9
                           and a % 10 + b <= 10 and a + b <= 100),
    "te_plus_te_to100_zb": ("+", lambda a, b: 11 <= a <= 89 and 11 <= b <= 89 and a + b <= 100
                            and a % 10 + b % 10 <= 10),
    "te_plus_e_to100_mb": ("+", lambda a, b: 11 <= a <= 95 and a % 10 != 0 and 1 <= b <= 9
                           and a % 10 + b > 10 and a + b <= 100),
    "te_plus_te_to100_mb": ("+", lambda a, b: 11 <= a <= 80 and 11 <= b <= 80 and a + b <= 100
                            and a % 10 + b % 10 > 10),
    "t_minus_t_to100_zb": ("-", lambda a, b: multiple_of_ten(a) and multiple_of_ten(b)
                           and 0 <= b <= a <= 100),
    "t_minus_e_to100_zb": ("-", lambda a, b: pure_ten(a) and a <= 100 and 0 <= b <= 9),
    "te_minus_t_to100_zb": ("-", lambda a, b: 11 <= a <= 99 and a % 10 != 0 and pure_ten(b)
                            and b <= 90 and a >= b),
    "te_minus_e_to100_zb": ("-", lambda a, b: 11 <= a <= 100 and a % 10 != 0 and 0 <= b <= 9
                            and a % 10 >= b),
    "te_minus_te_to100_zb": ("-", lambda a, b: 11 <= a <= 100 and 11 <= b <= 100 and a >= b
                             and a % 10 >= b % 10),
    "te_minus_e_to100_mb": ("-", lambda a, b: 11 <= a <= 100 and a % 10 != 0 and 1 <= b <= 9
                            and a % 10 < b),
    "te_minus_te_to100_mb": ("-", lambda a, b: 11 <= a <= 100 and 11 <= b <= 99 and a > b
                             and a % 10 < b % 10),
}


# ------------------------------------------------------------------ the 23 types
@test
def there_are_23_types_laid_out_2_7_14_with_unique_keys():
    assert len(EXERCISE_TYPES) == 23 and len({t.key for t in EXERCISE_TYPES}) == 23
    assert set(RULES) == set(EXERCISE_BY_KEY), "every type needs a rule here"
    cells = {(g, s): len(types_in(g, s)) for g, _ in GROUPS for s in ("+", "-")}
    assert cells == {(10, "+"): 1, (10, "-"): 1, (20, "+"): 3, (20, "-"): 4,
                     (100, "+"): 7, (100, "-"): 7}, cells
    assert max(cells.values()) == 7, "at most 7 chips in a row on the selection screen"


@test
def every_exercise_follows_its_types_rule_and_stays_in_range():
    random.seed(3)
    for etype in EXERCISE_TYPES:
        op, rule = RULES[etype.key]
        assert etype.sign == op
        for _ in range(3000):
            a, got_op, b = etype.make()
            assert got_op == op, (etype.key, a, got_op, b)
            assert rule(a, b), (etype.key, a, got_op, b)
            answer = a + b if op == "+" else a - b
            assert 0 <= answer <= etype.group, (etype.key, a, op, b, answer)


@test
def every_type_produces_every_exercise_its_rule_allows():
    # Exhaustive over all operand pairs 0..100: the generator must reach each
    # legal exercise (no rule is accidentally narrower than documented) -
    # allowing for the generators' own operand ranges, which are part of the rules.
    random.seed(5)
    for etype in EXERCISE_TYPES:
        op, rule = RULES[etype.key]
        seen = {etype.make() for _ in range(30000)}
        legal = {(a, op, b) for a in range(0, 101) for b in range(0, 101) if rule(a, b)}
        assert seen <= legal, (etype.key, sorted(seen - legal)[:3])
        assert len(seen) / len(legal) > 0.97, (etype.key, len(seen), len(legal))


@test
def ported_generators_match_the_original_plusminus_file_if_present():
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    try:
        original = importlib.import_module("plusminus")
    except ImportError:
        print("   (plusminus.py not next to the tests - comparison skipped)")
        return
    random.seed(9)
    # Big enough that even the largest type (about 2,400 exercises) is covered
    # completely by chance with certainty (expected misses ~ 2400 * e^-50).
    SAMPLES = 120000
    for etype in EXERCISE_TYPES:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            getattr(original, etype.key)(SAMPLES)
        theirs = set()
        for line in buf.getvalue().splitlines():
            m = re.match(r"(\d+) ([+-]) (\d+) = ", line)
            theirs.add((int(m[1]), m[2], int(m[3])))
        ours = {etype.make() for _ in range(SAMPLES)}
        assert theirs == ours, (etype.key, sorted(theirs ^ ours)[:4])


# ------------------------------------------------------------------ ExerciseSet
@test
def exercise_set_makes_correct_problems_with_the_right_limit():
    random.seed(1)
    es = ExerciseSet([t.key for t in EXERCISE_TYPES])
    for _ in range(3000):
        p = es.make_problem()
        m = re.fullmatch(r"(\d+) ([+-]) (\d+)", p.question)
        assert m, p.question
        a, op, b = int(m[1]), m[2], int(m[3])
        assert p.answer == (a + b if op == "+" else a - b)
        assert p.limit in (10, 20, 100) and 0 <= p.answer <= p.limit


@test
def every_selected_type_is_used_about_equally():
    random.seed(2)
    keys = ["e_plus_e_to10_zb", "e_minus_e_to10_zb", "te_plus_te_to100_mb"]
    es = ExerciseSet(keys)
    counts = {"+10": 0, "-10": 0, "+100": 0}
    for _ in range(6000):
        p = es.make_problem()
        counts[("+" if "+" in p.question else "-") + str(p.limit)] += 1
    assert all(1700 < c < 2300 for c in counts.values()), counts


@test
def unknown_keys_are_dropped_and_an_empty_selection_is_refused():
    assert valid_keys(["e_plus_e_to10_zb", "nonsense"]) == ["e_plus_e_to10_zb"]
    es = ExerciseSet(["nonsense", "e_minus_e_to10_zb"])
    assert es.keys == ["e_minus_e_to10_zb"]
    for bad in ([], ["nonsense"]):
        try:
            ExerciseSet(bad)
        except ValueError:
            continue
        raise AssertionError("an empty selection must be refused")


@test
def unique_problems_have_all_different_answers_and_fewer_when_the_type_is_small():
    random.seed(4)
    big = ExerciseSet([t.key for t in EXERCISE_TYPES]).unique_problems(10)
    assert len(big) == 10 and len({p.answer for p in big}) == 10
    # The three small types of the teacher's list (measured earlier): 8, 8 and 9 answers.
    for key, expected in (("e_plus_e_to20_mb", 8), ("te_minus_e_to20_mb", 8),
                          ("te_minus_te_to20_zb", 9)):
        got = ExerciseSet([key]).unique_problems(10)
        assert len(got) == expected, (key, len(got))
        assert len({p.answer for p in got}) == expected
    # Types with plenty of answers always fill 10.
    for key in ("e_plus_e_to10_zb", "t_plus_t_to100_zb", "te_minus_te_to100_mb"):
        assert len(ExerciseSet([key]).unique_problems(10)) == 10, key


# ------------------------------------------------------------------ decoys
def check_decoys(problem_set, problem, count, lo=None, hi=None):
    d = problem_set.decoys(problem, count)
    assert len(d) == count and len(set(d)) == count, (problem, d)
    assert problem.answer not in d, (problem, d)
    assert all(isinstance(v, int) for v in d)
    if lo is not None:
        assert all(lo <= v <= hi for v in d), (problem, d)
    return d


@test
def plus_min_decoys_are_distinct_wrong_and_inside_the_exercises_range():
    random.seed(6)
    es = ExerciseSet([t.key for t in EXERCISE_TYPES])
    for _ in range(1500):
        p = es.make_problem()
        for count in (1, 2, 3, 4, 7):
            check_decoys(es, p, count, 0, p.limit)


@test
def decoys_work_in_the_tightest_case_an_answer_in_a_small_range():
    random.seed(8)
    for key in ("e_plus_e_to10_zb", "e_minus_e_to10_zb"):
        es = ExerciseSet([key])
        for _ in range(300):
            p = es.make_problem()
            check_decoys(es, p, 7, 0, 10)      # Ballon's maximum: 8 balloons -> 7 decoys in 0..10


@test
def plus_min_decoys_mix_near_misses_with_other_answers():
    random.seed(10)
    es = ExerciseSet(["te_plus_e_to100_mb"])
    p = exercises.Problem("47 + 8", 55, 100)
    near_counts = []
    for _ in range(400):
        d = check_decoys(es, p, 4, 0, 100)
        near_counts.append(sum(1 for v in d if abs(v - 55) in (1, 2, 10)))
    assert min(near_counts) >= 2, "at least half of the decoys are classic near misses"
    assert max(near_counts) <= 4
    # ...and the other half are real answers of this kind of exercise, so they vary.
    seen = set()
    for _ in range(400):
        seen.update(es.decoys(p, 4))
    assert len(seen) > 12, "decoys must not always be the same numbers"


@test
def near_misses_never_leave_the_range_at_the_edges():
    random.seed(11)
    es = ExerciseSet(["t_plus_t_to100_zb"])
    for answer in (0, 1, 2, 99, 100):
        p = exercises.Problem("x", answer, 100)
        for _ in range(100):
            check_decoys(es, p, 5, 0, 100)
    es10 = ExerciseSet(["e_plus_e_to10_zb"])
    for answer in (0, 10):
        check_decoys(es10, exercises.Problem("x", answer, 10), 6, 0, 10)


@test
def table_decoys_are_still_products_like_before():
    random.seed(12)
    ts = TableSet([3, 7], "Keer (x)")
    products = {t * o for t in range(1, 11) for o in range(1, 11)}
    for _ in range(300):
        p = ts.make_problem()
        d = check_decoys(ts, p, 5)
        assert all(v in products or 1 <= v <= 100 for v in d)
        assert sum(1 for v in d if v in products) >= 4, "wrong answers should look like tables answers"


@test
def table_set_keeps_the_original_question_formats():
    random.seed(13)
    for _ in range(100):
        assert re.fullmatch(r"7 x \d+", TableSet([7], "Keer (x)").make_problem().question)
        assert re.fullmatch(r"\d+ x 7", TableSet([7], "Keer (x)", other_first=True).make_problem().question)
        q = TableSet([7], "Gedeeld door (:)").make_problem()
        a, b = map(int, q.question.split(" : "))
        assert b == 7 and a // b == q.answer and a % b == 0
    assert len(TableSet([1], "Keer (x)").unique_problems(10)) == 10
    assert len(TableSet([1], "Gedeeld door (:)").unique_problems(10)) == 10


# ------------------------------------------------------------------ the games on plus/min
def es(*keys):
    return ExerciseSet(list(keys))


@test
def klok_plays_a_small_selection_with_fewer_cards_and_ends_after_the_last_one():
    random.seed(14)
    g = klok.KlokGame(1280, 720, [], "", 1, problems=es("e_plus_e_to20_mb"))
    assert g.total_slots == 8 and len(g.card_rects) == 8 and len(g.slots) == 8
    rects = g.card_rects
    for i, a in enumerate(rects):
        assert pygame.Rect(0, 0, 1280, 720).contains(a)
        assert not any(a.colliderect(b) for b in rects[i + 1:])
    for n in range(8):
        assert not g.finished
        idx = g.active_index
        question = g.slots[idx]["question"]
        assert re.fullmatch(r"\d+ \+ \d+", question) and eval(question) == g.slots[idx]["answer"]
        g.update(16, [FakeCursor(1, *g.card_rects[idx].center)])
        assert g.total_correct == n + 1
    assert g.finished and g.total_correct == 8
    surf = pygame.Surface((1280, 720))
    g.draw(surf)


@test
def klok_with_a_big_selection_still_has_ten_cards():
    g = klok.KlokGame(1280, 720, [], "", 1, problems=es(*[t.key for t in EXERCISE_TYPES]))
    assert g.total_slots == 10 and len({s["answer"] for s in g.slots}) == 10


@test
def klok_with_tables_is_unchanged_ten_unique_cards():
    for tables, som in (([1], "Keer (x)"), ([1], "Gedeeld door (:)"), ([2, 5], "Gemengd")):
        g = klok.KlokGame(1280, 720, tables, som, 1)
        assert g.total_slots == 10 and len({s["answer"] for s in g.slots}) == 10


@test
def ballon_balloons_are_distinct_include_the_answer_and_stay_plausible():
    random.seed(15)
    for key in ("e_plus_e_to10_zb", "te_plus_te_to100_mb", "te_minus_e_to20_mb"):
        g = ballon.BallonGame(1280, 720, [], "", 1, problems=es(key))
        for _ in range(60):
            g._spawn_round()
            values = [b.value for b in g.balloons]
            assert len(values) == len(set(values)) >= 4, values
            assert sum(1 for b in g.balloons if b.is_correct) == 1
            assert g.correct_value in values
            assert re.fullmatch(r"\d+ [+-] \d+", g.question)
            limit = EXERCISE_BY_KEY[key].group
            assert all(0 <= v <= limit for v in values), (key, values)
        g.draw(pygame.Surface((1280, 720)))


@test
def ballon_with_tables_is_unchanged_products():
    random.seed(16)
    g = ballon.BallonGame(1280, 720, [3, 4], "Keer (x)", 1)
    for _ in range(40):
        g._spawn_round()
        assert re.fullmatch(r"[34] x \d+", g.question)
        assert len({b.value for b in g.balloons}) == len(g.balloons)


@test
def hoeden_hats_hide_distinct_plausible_answers_in_every_round():
    random.seed(17)
    g = hoeden.HoedenGame(1280, 720, [], "", 1, problems=es("te_plus_e_to100_mb", "te_minus_e_to100_mb"))
    for rnd in range(1, 11):
        g.round_num = rnd
        g._start_round()
        values = [h.value for h in g.hats]
        assert len(values) == len(set(values)) == hoeden._hats_for_round(rnd)
        assert sum(1 for h in g.hats if h.is_correct) == 1
        assert re.fullmatch(r"\d+ [+-] \d+", g.question)
        assert all(0 <= v <= 100 for v in values)
    g.draw(pygame.Surface((1280, 720)))


@test
def memory_adapts_its_board_to_the_number_of_different_answers():
    random.seed(18)
    g = memory.MemoryGame(1280, 720, [], "", 1, problems=es("e_plus_e_to20_mb"))
    assert g.num_pairs == 8 and len(g.cards) == 16
    rects = [c.rect for c in g.cards]
    for i, a in enumerate(rects):
        assert pygame.Rect(0, 0, 1280, 720).contains(a) and a.top >= memory.BAR_H
        assert not any(a.colliderect(b) for b in rects[i + 1:])
    sums = [c for c in g.cards if c.kind == "sum"]
    answers = [c for c in g.cards if c.kind == "answer"]
    assert max(c.rect.right for c in sums) < min(c.rect.left for c in answers)
    # Plays through in exactly 8 turns.
    for pair in range(8):
        s = next(c for c in g.cards if c.kind == "sum" and c.pair == pair)
        mate = next(c for c in g.cards if c.pair == pair and c is not s)
        g.update(1, [FakeCursor(1, *s.rect.center)])
        g.update(1, [FakeCursor(1, *mate.rect.center)])
        for _ in range(130):
            g.update(16, [])
    assert g.finished and g.results()["turns"] == 8
    for c in g.cards:
        assert re.fullmatch(r"\d+ [+-] \d+|\d+", c.text)


@test
def memory_with_tables_keeps_other_x_table_and_ten_pairs():
    random.seed(19)
    g = memory.MemoryGame(1280, 720, [7], "Keer (x)", 1)
    assert g.num_pairs == 10
    assert all(re.fullmatch(r"\d+ x 7", p["question"]) for p in g.pairs)


if __name__ == "__main__":
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", ", ".join(FAILED))
        sys.exit(1)

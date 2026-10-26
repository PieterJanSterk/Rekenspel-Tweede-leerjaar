"""
exercises.py

WHAT THE GAMES PRACTISE. Every game (Klok, Ballon, Hoeden, Memory) asks one
shared object - a "problem set" - for its exercises instead of knowing about
multiplication tables itself. There are two kinds:

  TableSet     the multiplication / division tables (the original behaviour).
  ExerciseSet  plus-and-min exercises up to 10 / 20 / 100 ("Plus en min"),
               picked type by type: E + E ZB, TE - E MB, ...

Both offer the same three things:

  make_problem()               one Problem(question, answer, limit)
  unique_problems(count)       up to `count` problems with all-different answers
                               (Klok's cards, Memory's pairs). Returns FEWER when
                               the selection simply has fewer different answers
                               (e.g. "E + E MB" only has 8) - repetition is fine.
  decoys(problem, count)       `count` different WRONG answers for Ballon's
                               balloons / Hoeden's hats.

THE PLUS-AND-MIN RULES are the teacher's own (plusminus.py), unchanged: every
type below keeps exactly the same operand ranges and conditions as its
original generator. Only the output differs - they RETURN the exercise as
(a, "+" or "-", b) instead of printing it. Abbreviations: E = eenheid (a
single digit), T = tiental (a pure ten), TE = tiental + eenheid, ZB = zonder
brug (no bridge over the ten), MB = met brug (with bridge). 7 + 2 and 2 + 7
count as different exercises, and zeros are allowed.

DECOYS FOR PLUS AND MIN. The multiplication games draw wrong answers from
other products in the table. For plus/min that would be nonsense, so wrong
answers are plausible instead: "near misses" (one or two off, ten off - the
classic slips when bridging a ten) mixed with real answers of other exercises
from the same selection. They stay inside the number range of the exercise
(0-10, 0-20 or 0-100), so a first grader is never tempted by a 3-digit number.
"""

import random
from collections import namedtuple

from i18n import t

# One exercise as the games see it. `limit` is the top of the number range
# for plus/min (10, 20 or 100) and None for the tables.
Problem = namedtuple("Problem", "question answer limit")

MINUS = "-"      # plain ASCII on purpose: always in every font (incl. Batocera's)


# =====================================================================
# 1. The 23 plus/min exercise types (ported 1:1 from plusminus.py)
# =====================================================================
# Every generator returns ONE exercise (a, op, b) satisfying the type's
# rule, by rejection sampling over small ranges - exactly like the originals.

def _e_plus_e_to10_zb():
    while True:
        e1, e2 = random.randint(0, 10), random.randint(0, 10)
        if e1 + e2 <= 10:
            return e1, "+", e2


def _e_minus_e_to10_zb():
    while True:
        e1, e2 = random.randint(0, 10), random.randint(0, 10)
        if e1 >= e2:
            return e1, "-", e2


def _t_plus_e_to20_zb():
    e = random.randint(0, 10)
    if random.choice(["T+E", "E+T"]) == "T+E":
        return 10, "+", e
    return e, "+", 10


def _te_plus_e_to20_zb():
    while True:
        num1, num2 = random.randint(0, 20), random.randint(0, 20)
        if 11 <= num1 + num2 <= 20:
            if (num1 >= 10) ^ (num2 >= 10):                 # exactly one is >= 10
                if num1 % 10 + num2 % 10 <= 10:
                    return num1, "+", num2


def _e_plus_e_to20_mb():
    while True:
        e1, e2 = random.randint(1, 9), random.randint(1, 9)
        if e1 + e2 > 10:
            return e1, "+", e2


def _t_minus_e_te_20_zb():
    return 20, "-", random.randint(0, 20)


def _te_minus_e_to20_zb():
    while True:
        te, e = random.randint(11, 20), random.randint(0, 10)
        if te - e >= 10:
            return te, "-", e


def _te_minus_te_to20_zb():
    while True:
        te1, te2 = random.randint(11, 20), random.randint(11, 20)
        if te1 >= te2 and te1 % 10 >= te2 % 10:
            return te1, "-", te2


def _te_minus_e_to20_mb():
    while True:
        te, e = random.randint(11, 19), random.randint(1, 9)
        if te - e < 10:
            return te, "-", e


def _t_plus_t_to100_zb():
    while True:
        t1, t2 = random.randint(0, 10) * 10, random.randint(0, 10) * 10
        if t1 + t2 <= 100:
            return t1, "+", t2


def _t_plus_e_to100_zb():
    return random.randint(1, 9) * 10, "+", random.randint(1, 9)


def _te_plus_t_to100_zb():
    while True:
        te, t = random.randint(11, 89), random.randint(1, 8) * 10
        if te % 10 != 0 and te + t <= 100:
            return te, "+", t


def _te_plus_e_to100_zb():
    while True:
        te, e = random.randint(11, 99), random.randint(0, 9)
        if te + e <= 100 and te % 10 + e <= 10 and te % 10 != 0:
            return te, "+", e


def _te_plus_te_to100_zb():
    while True:
        te1, te2 = random.randint(11, 89), random.randint(11, 89)
        if te1 + te2 <= 100 and te1 % 10 + te2 % 10 <= 10:
            return te1, "+", te2


def _te_plus_e_to100_mb():
    while True:
        te, e = random.randint(11, 95), random.randint(1, 9)
        if te + e <= 100 and te % 10 + e > 10 and te % 10 != 0:
            return te, "+", e


def _te_plus_te_to100_mb():
    while True:
        te1, te2 = random.randint(11, 80), random.randint(11, 80)
        if te1 + te2 <= 100 and te1 % 10 + te2 % 10 > 10:
            return te1, "+", te2


def _t_minus_t_to100_zb():
    while True:
        t1, t2 = random.randint(0, 10) * 10, random.randint(0, 10) * 10
        if t1 >= t2:
            return t1, "-", t2


def _t_minus_e_to100_zb():
    return random.randint(1, 10) * 10, "-", random.randint(0, 9)


def _te_minus_t_to100_zb():
    while True:
        te, t = random.randint(11, 99), random.randint(1, 9) * 10
        if te % 10 != 0 and te >= t:
            return te, "-", t


def _te_minus_e_to100_zb():
    while True:
        te, e = random.randint(11, 100), random.randint(0, 9)
        if te % 10 != 0 and te % 10 >= e:
            return te, "-", e


def _te_minus_te_to100_zb():
    while True:
        te1, te2 = random.randint(11, 100), random.randint(11, 100)
        if te1 >= te2 and te1 % 10 >= te2 % 10:
            return te1, "-", te2


def _te_minus_e_to100_mb():
    while True:
        te, e = random.randint(11, 100), random.randint(1, 9)
        if te % 10 != 0 and te % 10 < e:
            return te, "-", e


def _te_minus_te_to100_mb():
    while True:
        te1, te2 = random.randint(11, 100), random.randint(11, 99)
        if te1 > te2 and te1 % 10 < te2 % 10:
            return te1, "-", te2


class ExerciseType:
    """One checkbox on the selection screen.
    key    stable id, saved in settings.json and on the leaderboard (it is the
           teacher's original function name, so it stays recognisable)
    group  the number range: 10, 20 or 100
    sign   "+" or "-" (which row of the selection screen it sits in)
    line1/line2   the label as shown on the chip, e.g. "TE + E" over "MB"
    make   the generator: () -> (a, op, b)"""

    def __init__(self, key, group, sign, line1, line2, make):
        self.key, self.group, self.sign = key, group, sign
        self.line1, self.line2, self.make = line1, line2, make

    @property
    def label(self):
        return f"{self.line1} {self.line2}".strip()


_T = ExerciseType
EXERCISE_TYPES = [
    # ---- up to 10
    _T("e_plus_e_to10_zb",   10,  "+", "E + E",    "ZB", _e_plus_e_to10_zb),
    _T("e_minus_e_to10_zb",  10,  "-", "E - E",    "ZB", _e_minus_e_to10_zb),
    # ---- up to 20, addition
    _T("t_plus_e_to20_zb",   20,  "+", "T + E",    "ZB", _t_plus_e_to20_zb),
    _T("te_plus_e_to20_zb",  20,  "+", "TE + E",   "ZB", _te_plus_e_to20_zb),
    _T("e_plus_e_to20_mb",   20,  "+", "E + E",    "MB", _e_plus_e_to20_mb),
    # ---- up to 20, subtraction
    _T("t_minus_e_te_20_zb", 20,  "-", "20 - E/TE", "",  _t_minus_e_te_20_zb),
    _T("te_minus_e_to20_zb", 20,  "-", "TE - E",   "ZB", _te_minus_e_to20_zb),
    _T("te_minus_te_to20_zb", 20, "-", "TE - TE",  "ZB", _te_minus_te_to20_zb),
    _T("te_minus_e_to20_mb", 20,  "-", "TE - E",   "MB", _te_minus_e_to20_mb),
    # ---- up to 100, addition
    _T("t_plus_t_to100_zb",  100, "+", "T + T",    "",   _t_plus_t_to100_zb),
    _T("t_plus_e_to100_zb",  100, "+", "T + E",    "",   _t_plus_e_to100_zb),
    _T("te_plus_t_to100_zb", 100, "+", "TE + T",   "",   _te_plus_t_to100_zb),
    _T("te_plus_e_to100_zb", 100, "+", "TE + E",   "ZB", _te_plus_e_to100_zb),
    _T("te_plus_te_to100_zb", 100, "+", "TE + TE", "ZB", _te_plus_te_to100_zb),
    _T("te_plus_e_to100_mb", 100, "+", "TE + E",   "MB", _te_plus_e_to100_mb),
    _T("te_plus_te_to100_mb", 100, "+", "TE + TE", "MB", _te_plus_te_to100_mb),
    # ---- up to 100, subtraction
    _T("t_minus_t_to100_zb", 100, "-", "T - T",    "",   _t_minus_t_to100_zb),
    _T("t_minus_e_to100_zb", 100, "-", "T - E",    "",   _t_minus_e_to100_zb),
    _T("te_minus_t_to100_zb", 100, "-", "TE - T",  "",   _te_minus_t_to100_zb),
    _T("te_minus_e_to100_zb", 100, "-", "TE - E",  "ZB", _te_minus_e_to100_zb),
    _T("te_minus_te_to100_zb", 100, "-", "TE - TE", "ZB", _te_minus_te_to100_zb),
    _T("te_minus_e_to100_mb", 100, "-", "TE - E",  "MB", _te_minus_e_to100_mb),
    _T("te_minus_te_to100_mb", 100, "-", "TE - TE", "MB", _te_minus_te_to100_mb),
]
EXERCISE_BY_KEY = {t.key: t for t in EXERCISE_TYPES}

# The selection screen's groups, in order: (number range, heading).
GROUPS = [(10, "Tot 10"), (20, "Tot 20"), (100, "Tot 100")]


def types_in(group, sign):
    """The exercise types of one cell of the selection screen (left to right)."""
    return [t for t in EXERCISE_TYPES if t.group == group and t.sign == sign]


def valid_keys(keys):
    """`keys` without anything unknown (e.g. from a hand-edited settings.json)."""
    return [k for k in keys if k in EXERCISE_BY_KEY]


# =====================================================================
# 2. Problem sets: what the games actually talk to
# =====================================================================
class TableSet:
    """Multiplication / division tables: the games' original behaviour.

    tables     list of tables, e.g. [2, 3, 7]
    som_type   "Keer (x)", "Gedeeld door (:)" or "Gemengd"
    other_first  True writes a multiplication as "other x table" ("7 x 3" for
               table 3, Memory's style); False as "table x other" (Klok,
               Ballon and Hoeden's style). Divisions are "product : table".
    """
    kind = "tafels"

    def __init__(self, tables, som_type, other_first=False):
        self.tables = list(tables)
        self.som_type = som_type
        self.other_first = other_first

    def _kinds(self):
        if "Gedeeld" in self.som_type:
            return [":"]
        if self.som_type == "Gemengd":
            return ["x", ":"]
        return ["x"]

    def _problem(self, other, table, kind):
        # The multiplication / division signs come from the language file
        # (Dutch "x" and ":", English "×" and "÷"); `kind` itself is internal.
        if kind == "x":
            times = t("symbol.times")
            question = (f"{other} {times} {table}" if self.other_first
                        else f"{table} {times} {other}")
            return Problem(question, table * other, None)
        return Problem(f"{table * other} {t('symbol.divide')} {table}", other, None)

    def make_problem(self):
        table = random.choice(self.tables)
        other = random.randint(1, 10)
        return self._problem(other, table, random.choice(self._kinds()))

    def unique_problems(self, count):
        """Up to `count` problems, all answers different. Shuffles every
        possible (other, table, kind) once and keeps the first of each answer:
        the same odds as picking at random and re-rolling duplicates, but it
        can never loop forever on a small selection."""
        candidates = [(other, table, kind)
                      for table in sorted(set(self.tables))
                      for other in range(1, 11)
                      for kind in self._kinds()]
        random.shuffle(candidates)
        problems, seen = [], set()
        for other, table, kind in candidates:
            problem = self._problem(other, table, kind)
            if problem.answer in seen:
                continue
            seen.add(problem.answer)
            problems.append(problem)
            if len(problems) == count:
                break
        return problems

    def decoys(self, problem, count):
        """`count` different wrong answers: mostly other products from the
        chosen tables (so they look genuinely like answers), as before."""
        values = {problem.answer}
        attempts = 0
        while len(values) < count + 1 and attempts < 200:
            attempts += 1
            t = random.choice(self.tables) if random.random() < 0.7 else random.randint(1, 10)
            values.add(t * random.randint(1, 10))
        while len(values) < count + 1:
            values.add(random.randint(1, 100))
        values.discard(problem.answer)
        return random.sample(sorted(values), count)


class ExerciseSet:
    """Plus-and-min exercises of the chosen types (see EXERCISE_TYPES).
    Each new exercise first picks one of the chosen types at random (all
    types equally likely, like the teacher's mix generators), then
    generates an exercise of that type."""
    kind = "plusmin"

    # How far off the classic mistakes are: one or two too many/few, and a
    # whole ten too many/few (forgetting or double-counting the bridge).
    NEAR_MISS_OFFSETS = (1, -1, 2, -2, 10, -10)

    def __init__(self, keys):
        keys = valid_keys(keys)
        if not keys:
            raise ValueError("ExerciseSet needs at least one valid exercise type")
        self.keys = sorted(set(keys))
        self.types = [EXERCISE_BY_KEY[k] for k in self.keys]

    def make_problem(self):
        etype = random.choice(self.types)
        a, op, b = etype.make()
        answer = a + b if op == "+" else a - b
        return Problem(f"{a} {op} {b}", answer, etype.group)

    def unique_problems(self, count, max_attempts=4000):
        """Up to `count` problems with all-different answers. Selections with
        few different answers (E + E MB has only 8) simply return fewer."""
        problems, seen = [], set()
        for _ in range(max_attempts):
            problem = self.make_problem()
            if problem.answer in seen:
                continue
            seen.add(problem.answer)
            problems.append(problem)
            if len(problems) == count:
                break
        return problems

    def decoys(self, problem, count):
        """`count` different plausible wrong answers within 0..limit: about
        half near misses (answer +-1, +-2, +-10), the rest real answers of
        other exercises from this selection, topped up with any number in
        range if that is still not enough."""
        lo, hi = 0, problem.limit or 100
        correct = problem.answer
        picks = []

        def take(value):
            if lo <= value <= hi and value != correct and value not in picks and len(picks) < count:
                picks.append(value)

        near = [correct + offset for offset in self.NEAR_MISS_OFFSETS]
        random.shuffle(near)
        near = [v for v in near if lo <= v <= hi]
        others = []
        for _ in range(60):
            answer = self.make_problem().answer
            if answer not in others:
                others.append(answer)
        random.shuffle(others)

        for value in near[:(count + 1) // 2]:         # near misses first (about half)
            take(value)
        for value in others:                          # then other exercises' answers
            take(value)
        for value in near:                            # then any remaining near misses
            take(value)
        rest = list(range(lo, hi + 1))
        random.shuffle(rest)
        for value in rest:                            # last resort: anything in range
            take(value)
        return picks


def make_problem_set(tables, som_type, exercise_keys=None, other_first=False):
    """The right problem set for a choice: plus/min when exercise keys are
    given, otherwise the multiplication tables."""
    if exercise_keys:
        return ExerciseSet(exercise_keys)
    return TableSet(tables, som_type, other_first=other_first)

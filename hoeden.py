"""
hoeden.py

Rebuild of the "Hoeden" (hats) minigame. It is a MEMORY / shell game
(three-card monte), and its appeal is mystery, remembering and suspense:

  1. A round starts with only the hats on screen. No exercise, no answers.
  2. One by one, left to right, each hat rises - revealing the answer
     that sits underneath it - and lowers again, hiding it. About a
     second per hat.
  3. From round 9 onward the hats then SHUFFLE: they physically orbit
     past each other across the screen, slowly, a few swaps.
  4. Only now is the exercise revealed. The player has to remember which
     answer was under which hat and click that hat.
  5. Afterwards the correct hat rises to show the answer.

Scoring: one point per correct round, shown as "Score: 4/6" (points out of
rounds played so far). The original counted these as flowers ("bloemen");
here they are simply the score.

HIDDEN TIMER (never drawn during play): every player has an "answer time",
the time from the moment the hats become clickable until that player clicks
or the round ends, added up over all rounds. The fixed animation (peeking,
shuffling, revealing) is NOT counted, so the number really measures how
long each player took to decide. It is stored on the leaderboard, shown
there and on the name-entry screen, and breaks ties between equal scores
(less time ranks higher). Details at ANSWER-TIME RULES below.

Because hats swap places, ALL HATS MUST BE THE SAME COLOR. If they
differed, a player could simply remember "the blue hat hides 12" and
the shuffle would be pointless. The hats still follow the UI theme
(dark / light / regenboog) - but as one shared color for all of them.
For the same reason the answers live on a plate that belongs to each
hat and travels with it: the answer is "under" the hat, wherever it goes.

Rules added for classroom play:
  - 2 players: 11 rounds, so a 6-5 split always decides it. 1 player: 10.
  - Difficulty by hat count: 3 hats, 4 from round 3, 5 from round 6.
  - Two players race: first correct click scores. A wrong click costs no
    points: the hat that was clicked rises to show what was under it, and
    that player is out for the round. The other player may still answer.
    When the round ends, the correct hat rises to reveal the answer.

Hat art is drawn procedurally rather than from an image, so it follows the
theme natively.
"""

import math
import random
import pygame
from theme import best_text_color, player_color
from exercises import TableSet
from i18n import t

ONE_PLAYER_ROUNDS = 10
TWO_PLAYER_ROUNDS = 11

# =====================================================================
# TUNING - the knobs you're most likely to want to touch while finding
# the right difficulty for your class. Everything is in real time
# (milliseconds), NOT frames, so a value feels the same on every
# computer: 1.0 means the same speed on Windows and on the Batocera box.
# =====================================================================

# How fast the hats glide during the shuffle (round 9 onward).
#   1.0 = default,  2.0 = twice as fast (harder),  0.5 = half speed (easier)
SHUFFLE_SPEED = 1.0

# How many swaps each shuffle consists of. More swaps = harder.
SHUFFLE_SWAP_COUNT = 4

# How long each answer stays visible while its hat is raised. This is the
# main "how hard is it to remember" knob: shorter = harder.
PEEK_HOLD_MS = 350

# The rest of the pacing.
LIFT_ANIM_MS = 400              # time for a hat to go fully up (or down)
INTRO_PAUSE_MS = 800            # just the hats on screen, nothing else
RESOLVED_SHOW_MS = 1500         # how long the revealed answer stays up

# =====================================================================

PEEK_PER_HAT_MS = LIFT_ANIM_MS * 2 + PEEK_HOLD_MS   # ~1.15s per hat

# --- the shuffle: hats orbit around the midpoint of each swapped pair ---
SHUFFLE_START_ROUND = 9
SHUFFLE_BASE_SWAP_MS = 1000     # an adjacent swap at SHUFFLE_SPEED 1.0
SHUFFLE_DISTANCE_FACTOR = 0.5   # +50% time per extra slot the hats travel
SHUFFLE_MIN_DEPTH_PX = 60       # how far a hat swings in front / behind,
SHUFFLE_MAX_DEPTH_PX = 130      # scaled with swap width between these

# Longest time step the game will accept in one update. If the window is
# dragged or the machine stalls, we'd rather slow down than silently skip
# a hat's peek or half the shuffle - unfair in a memory game.
MAX_DT_MS = 100

POINTS_PER_CORRECT = 1           # one point per correct round

# What the number after the slash in "Score: 4/6" means:
#   True  = rounds played SO FAR (4 right out of 6 played - grows as you go)
#   False = rounds in the whole match (4 out of 10, or out of 11 in 2P)
SCORE_SHOWS_ROUNDS_PLAYED = True

# Big on purpose: the answer is only visible for about a second, from across
# a classroom, and remembering it is the entire game.
HAT_SIZE = (160, 186)
HAT_ROW_Y = 470
LIFT_HEIGHT = 140                # how far a hat rises (clears the plate)
PLATE_SIZE = (104, 62)           # must stay narrower than the hat's crown
PLATE_OFFSET_Y = 10              # plate sits just below the hat's centre
SHADOW_OFFSET_Y = 82

PHASE_INTRO = "intro"
PHASE_PEEK = "peek"
PHASE_SHUFFLE = "shuffle"
PHASE_ANSWER = "answer"
PHASE_RESOLVED = "resolved"

_PLATE_NEUTRAL = ((235, 235, 245), (20, 20, 30)), ((255, 255, 255), (20, 20, 30))
_HAT_COLORS = ((70, 70, 110), (255, 255, 255)), ((95, 95, 160), (255, 255, 255))
_PLATE_WRONG = (200, 60, 60)
_PLATE_CORRECT = (60, 180, 90)
_PLATE_REVEAL = (230, 190, 60)   # nobody got it: neutral gold reveal


def _hats_for_round(round_num):
    if round_num < 3:
        return 3
    if round_num < 6:
        return 4
    return 5


def _is_shuffle_round(round_num):
    return round_num >= SHUFFLE_START_ROUND


def _smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _draw_hat(screen, center, body_color, band_color):
    w, h = HAT_SIZE
    x, y = center[0] - w // 2, center[1] - h // 2
    brim_h = int(h * 0.16)
    crown_w = int(w * 0.68)
    crown_x = x + (w - crown_w) // 2
    crown_h = int(h * 0.78)

    pygame.draw.ellipse(screen, body_color,
                        pygame.Rect(x, y + h - brim_h * 2, w, brim_h * 2))
    pygame.draw.rect(screen, body_color, pygame.Rect(crown_x, y, crown_w, crown_h),
                     border_radius=int(crown_w * 0.18))
    band_h = int(crown_h * 0.16)
    pygame.draw.rect(screen, band_color,
                     pygame.Rect(crown_x, y + crown_h - band_h, crown_w, band_h))
    # Highlight kept in the upper crown, for depth.
    highlight = tuple(min(255, c + 30) for c in body_color)
    pygame.draw.ellipse(screen, highlight,
                        pygame.Rect(crown_x + crown_w // 8, y + int(crown_h * 0.08),
                                    crown_w // 8, int(crown_h * 0.28)))


class Hat:
    def __init__(self, value, is_correct, slot_index):
        self.value = value                  # the answer hiding under this hat
        self.is_correct = is_correct
        self.slot_index = slot_index
        self.x = 0.0
        self.base_y = float(HAT_ROW_Y)      # floor level (arcs during a swap)
        self.lift = 0.0                     # 0 = lowered, 1 = fully raised
        self.lift_target = 0.0
        self.plate_state = None             # None / "wrong" / "correct" / "reveal"
        self.clicked_wrong = False

    def hat_y(self):
        return self.base_y - _smoothstep(self.lift) * LIFT_HEIGHT

    def rect(self):
        w, h = HAT_SIZE
        return pygame.Rect(int(self.x - w / 2), int(self.hat_y() - h / 2), w, h)


class HoedenGame:
    def __init__(self, screen_w, screen_h, tables, som_type, num_players=1,
                 sound_bank=None, theme=None, problems=None):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.tables = tables
        self.som_type = som_type
        # What the exercises are (tables, or plus/min): see exercises.py.
        self.problems = problems or TableSet(tables, som_type)
        self.num_players = num_players
        self.sound_bank = sound_bank
        self.theme = theme

        self.total_rounds = ONE_PLAYER_ROUNDS if num_players == 1 else TWO_PLAYER_ROUNDS
        self.round_num = 1
        self.rounds_played = 0            # rounds that have been decided so far
        self.scores = {1: 0, 2: 0} if num_players == 2 else {1: 0}
        self.finished = False

        # Hidden timer: milliseconds each player has spent deciding.
        # ANSWER-TIME RULES: a player's clock runs only while the hats are
        # clickable (PHASE_ANSWER) and stops for that player the moment they
        # click a hat (right OR wrong, a wrong click disqualifies them for
        # the round) or the round is decided - whichever comes first. So the
        # winner's clock stops at their click, a player who got it wrong
        # stops at their wrong click, and a player who never clicked stops
        # when the round ends.
        self.answer_time_ms = {pid: 0 for pid in self.scores}

        self.question = ""
        self.hats = []
        self.disqualified = set()
        self.phase = PHASE_INTRO
        self.phase_timer_ms = 0
        self._swap_queue = []
        self._swap_progress_ms = 0

        self.font_question = pygame.font.SysFont("arial", 48, bold=True)
        self.font_value = pygame.font.SysFont("arial", 46, bold=True)
        self.font_score = pygame.font.SysFont("arial", 30, bold=True)
        self.font_progress = pygame.font.SysFont("arial", 24)

        self._start_round()

    # ---------------------------------------------------------- setup
    def _slot_x(self, index, count):
        margin = 140
        slot_w = (self.screen_w - margin * 2) / count
        return margin + slot_w * (index + 0.5)

    def _start_round(self):
        problem = self.problems.make_problem()
        self.question, correct_value = problem.question, problem.answer
        count = _hats_for_round(self.round_num)

        # The correct answer plus count-1 different wrong ones (plausible
        # ones: other products for tables, near misses for plus/min).
        values = {correct_value, *self.problems.decoys(problem, count - 1)}

        value_list = list(values)
        random.shuffle(value_list)
        correct_index = value_list.index(correct_value)

        self.hats = []
        for i, value in enumerate(value_list):
            hat = Hat(value, i == correct_index, slot_index=i)
            hat.x = self._slot_x(i, count)
            self.hats.append(hat)

        self.disqualified = set()
        self.phase = PHASE_INTRO
        self.phase_timer_ms = 0

    def _hat_in_slot(self, slot_index):
        return next(h for h in self.hats if h.slot_index == slot_index)

    def question_visible(self):
        """The exercise only appears once every answer has been shown and
        hidden again (and any shuffle is over) - never before."""
        return self.phase in (PHASE_ANSWER, PHASE_RESOLVED)

    # ---------------------------------------------------------- phases
    def _update_peek(self):
        ordered = sorted(self.hats, key=lambda h: h.slot_index)
        for k, hat in enumerate(ordered):
            start = k * PEEK_PER_HAT_MS
            hat.lift_target = 1.0 if start <= self.phase_timer_ms < start + LIFT_ANIM_MS + PEEK_HOLD_MS else 0.0
        if self.phase_timer_ms >= len(ordered) * PEEK_PER_HAT_MS:
            for hat in ordered:
                hat.lift_target = 0.0
            if _is_shuffle_round(self.round_num):
                self._begin_shuffle()
            else:
                self._enter_answer()

    def swap_duration_ms(self, slot_i, slot_j):
        """Wider swaps take longer, so hats move at a similar pace whether
        they trade places with a neighbour or cross the whole row (the
        original shell-game demo does the same with separate narrow and
        wide rotation speeds). SHUFFLE_SPEED scales all of it."""
        slots_apart = abs(slot_i - slot_j)
        base = SHUFFLE_BASE_SWAP_MS * (1 + SHUFFLE_DISTANCE_FACTOR * (slots_apart - 1))
        return base / SHUFFLE_SPEED

    def _begin_shuffle(self):
        count = len(self.hats)
        queue = []
        while len(queue) < SHUFFLE_SWAP_COUNT:
            pair = tuple(random.sample(range(count), 2))
            # Never swap the same two in a row - that would just undo itself.
            if queue and set(pair) == set(queue[-1][:2]):
                continue
            # Random which of the two swings in front (like the demo's
            # random clockwise / counter-clockwise), so it's never the
            # same hat passing in front every time.
            queue.append((pair[0], pair[1], random.choice((1, -1))))
        self._swap_queue = queue
        self._swap_progress_ms = 0
        self.phase = PHASE_SHUFFLE
        self.phase_timer_ms = 0

    def _update_shuffle(self, dt_ms):
        count = len(self.hats)
        remaining = dt_ms
        # A loop, so a big tick completes several swaps instead of
        # silently dropping time.
        while remaining > 0 and self._swap_queue:
            self._swap_progress_ms += remaining
            slot_i, slot_j, orient = self._swap_queue[0]
            a, b = self._hat_in_slot(slot_i), self._hat_in_slot(slot_j)
            duration = self.swap_duration_ms(slot_i, slot_j)
            t = min(1.0, self._swap_progress_ms / duration)

            # The pair orbits half a turn around their midpoint, like the
            # shells in the shell-game demo. cos() gives the natural
            # ease-in/ease-out along the row; sin() swings one hat toward
            # the viewer and the other away, so they glide PAST each
            # other instead of through each other.
            xi, xj = self._slot_x(slot_i, count), self._slot_x(slot_j, count)
            mid, half = (xi + xj) / 2, (xj - xi) / 2
            theta = math.pi * t
            a.x = mid - half * math.cos(theta)
            b.x = mid + half * math.cos(theta)
            depth = min(SHUFFLE_MAX_DEPTH_PX, max(SHUFFLE_MIN_DEPTH_PX, 0.45 * abs(half)))
            swing = depth * math.sin(theta)
            a.base_y = HAT_ROW_Y + orient * swing
            b.base_y = HAT_ROW_Y - orient * swing

            if t >= 1.0:
                overshoot = self._swap_progress_ms - duration
                a.slot_index, b.slot_index = slot_j, slot_i
                a.x, b.x = xj, xi
                a.base_y = b.base_y = float(HAT_ROW_Y)
                self._swap_queue.pop(0)
                self._swap_progress_ms = 0
                remaining = overshoot
            else:
                remaining = 0
        if not self._swap_queue:
            self._enter_answer()

    def _enter_answer(self):
        self.phase = PHASE_ANSWER
        self.phase_timer_ms = 0

    def _resolve(self, winner_player_id, correct_hat):
        self.rounds_played += 1
        if winner_player_id is not None:
            self.scores[winner_player_id] = self.scores.get(winner_player_id, 0) + POINTS_PER_CORRECT
            correct_hat.plate_state = "correct"
            if self.sound_bank:
                self.sound_bank.play_correct()
        else:
            correct_hat.plate_state = "reveal"
        correct_hat.lift_target = 1.0      # the correct hat rises: the reveal
        self.phase = PHASE_RESOLVED
        self.phase_timer_ms = 0

    def _handle_click(self, cursor):
        if self.phase != PHASE_ANSWER or cursor.player_id in self.disqualified:
            return
        for hat in self.hats:
            if hat.clicked_wrong or not hat.rect().collidepoint((cursor.x, cursor.y)):
                continue
            if hat.is_correct:
                self._resolve(cursor.player_id, hat)
            else:
                hat.clicked_wrong = True
                hat.plate_state = "wrong"
                hat.lift_target = 1.0      # show what was under the wrong hat
                self.disqualified.add(cursor.player_id)
                if self.sound_bank:
                    self.sound_bank.play_wrong()
                if set(range(1, self.num_players + 1)) <= self.disqualified:
                    self._resolve(None, next(h for h in self.hats if h.is_correct))
            return

    def _update_resolved(self):
        if self.phase_timer_ms >= RESOLVED_SHOW_MS:
            for hat in self.hats:
                hat.lift_target = 0.0
        if self.phase_timer_ms >= RESOLVED_SHOW_MS + LIFT_ANIM_MS:
            self.round_num += 1
            if self.round_num > self.total_rounds:
                self.finished = True
            else:
                self._start_round()

    def _animate_lifts(self, dt_ms):
        step = dt_ms / LIFT_ANIM_MS
        for hat in self.hats:
            if hat.lift < hat.lift_target:
                hat.lift = min(hat.lift_target, hat.lift + step)
            elif hat.lift > hat.lift_target:
                hat.lift = max(hat.lift_target, hat.lift - step)

    def update(self, dt_ms, cursors):
        if self.finished:
            return
        dt_ms = min(dt_ms, MAX_DT_MS)
        self.phase_timer_ms += dt_ms

        if self.phase == PHASE_INTRO:
            if self.phase_timer_ms >= INTRO_PAUSE_MS:
                self.phase = PHASE_PEEK
                self.phase_timer_ms = 0
        elif self.phase == PHASE_PEEK:
            self._update_peek()
        elif self.phase == PHASE_SHUFFLE:
            self._update_shuffle(dt_ms)
        elif self.phase == PHASE_ANSWER:
            # Everyone who has not answered yet is still deciding. (dt was
            # capped above, so a stalled window never inflates anyone's time.)
            for player_id in self.answer_time_ms:
                if player_id not in self.disqualified:
                    self.answer_time_ms[player_id] += dt_ms
            for cursor in cursors:
                if cursor.fired:
                    self._handle_click(cursor)
        elif self.phase == PHASE_RESOLVED:
            self._update_resolved()

        self._animate_lifts(dt_ms)

    # ---------------------------------------------------------- drawing
    def hat_colors(self):
        """(body, band) - ONE pair shared by every hat. Hats swap places,
        so any difference between them would let a player track a hat by
        its color instead of by memory."""
        if self.theme:
            body, text = self.theme.get("hoeden_hat", *_HAT_COLORS)
            band = text if self.theme.mode == "regenboog" else (200, 60, 60)
        else:
            body, band = _HAT_COLORS[0][0], (200, 60, 60)
        return body, band

    def plate_colors(self, hat):
        """(plate, number_text) - the number's color is always chosen for
        contrast against whatever its plate currently is."""
        if hat.plate_state == "wrong":
            plate = _PLATE_WRONG
        elif hat.plate_state == "correct":
            plate = _PLATE_CORRECT
        elif hat.plate_state == "reveal":
            plate = _PLATE_REVEAL
        else:
            if self.theme:
                return self.theme.get("hoeden_plate", *_PLATE_NEUTRAL)
            return _PLATE_NEUTRAL[0]
        return plate, best_text_color(plate)

    def score_text(self, player_id):
        """The "4/6" part of the HUD: points out of rounds played so far (or
        out of the whole match, see SCORE_SHOWS_ROUNDS_PLAYED)."""
        outof = self.rounds_played if SCORE_SHOWS_ROUNDS_PLAYED else self.total_rounds
        return f"{self.scores.get(player_id, 0)}/{outof}"

    def draw(self, screen):
        bg_color, bg_text = self.theme.get(
            "background", ((25, 30, 45), (255, 255, 255)),
            ((235, 238, 245), (20, 20, 30))) if self.theme else ((25, 30, 45), (255, 255, 255))
        screen.fill(bg_color)

        topbar_color, topbar_text = self.theme.get(
            "hoeden_topbar", ((15, 15, 25), (255, 255, 255)),
            ((210, 212, 225), (20, 20, 30))) if self.theme else ((15, 15, 25), (255, 255, 255))
        pygame.draw.rect(screen, topbar_color, (0, 0, self.screen_w, 100))

        if self.num_players == 1:
            screen.blit(self.font_score.render(
                t("hud.score", value=self.score_text(1)), True, topbar_text), (30, 35))
        else:
            screen.blit(self.font_score.render(
                t("hud.player_score", n=1, value=self.score_text(1)), True, player_color(1, topbar_color)), (30, 35))
            p2 = self.font_score.render(
                t("hud.player_score", n=2, value=self.score_text(2)), True, player_color(2, topbar_color))
            screen.blit(p2, p2.get_rect(topright=(self.screen_w - 30, 35)))

        progress = self.font_progress.render(
            t("hud.round", n=self.round_num, total=self.total_rounds), True, topbar_text)
        screen.blit(progress, progress.get_rect(centerx=self.screen_w // 2, y=40))

        if self.question_visible():
            q = self.font_question.render(self.question, True, bg_text)
            screen.blit(q, q.get_rect(centerx=self.screen_w // 2, y=140))

        body, band = self.hat_colors()
        pw, ph = PLATE_SIZE
        # Back to front, so a hat gliding in front of another covers it.
        for hat in sorted(self.hats, key=lambda h: h.base_y):
            x, floor = int(hat.x), int(hat.base_y)
            lift = _smoothstep(hat.lift)

            shadow_w = int(HAT_SIZE[0] * (1 - 0.2 * lift))
            shadow = pygame.Surface((shadow_w, 30), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, 70), shadow.get_rect())
            screen.blit(shadow, shadow.get_rect(center=(x, floor + SHADOW_OFFSET_Y)))

            # The plate and its answer sit on the floor UNDER the hat and
            # travel with it; the lowered hat completely covers them.
            plate_color, number_color = self.plate_colors(hat)
            plate_rect = pygame.Rect(0, 0, pw, ph)
            plate_rect.center = (x, floor + PLATE_OFFSET_Y)
            pygame.draw.rect(screen, plate_color, plate_rect, border_radius=12)
            pygame.draw.rect(screen, (60, 60, 80), plate_rect, 3, border_radius=12)
            label = self.font_value.render(str(hat.value), True, number_color)
            screen.blit(label, label.get_rect(center=plate_rect.center))

            _draw_hat(screen, (x, int(hat.hat_y())), body, band)

    def results(self):
        """scores / times_ms: one entry per player (each gets their own
        leaderboard row). rounds_total: the "11" in "8/11" on name entry."""
        return {
            "scores": dict(self.scores),
            "times_ms": {pid: int(ms) for pid, ms in self.answer_time_ms.items()},
            "rounds_total": self.total_rounds,
        }

"""
ballon.py

Rebuild of the "Ballon" minigame, based on a full disassembly of the
original AS2 bytecode. The real mechanic, confirmed from the code:

  - One equation is shown, and several balloons rise from near the
    bottom of the screen at once, each labeled with a candidate number -
    exactly one is correct, the rest are real plausible distractors
    (same philosophy as Klok's cards: wrong answers look genuinely
    wrong, not random noise).
  - Pop the correct balloon: score, and a fresh equation + fresh set of
    balloons spawns immediately.
  - Pop a wrong balloon, or let the correct one rise off the top of the
    screen unpopped: costs a life (1-player) or just costs you the
    opportunity (2-player, which uses a timer instead of lives - see
    below).
  - The original increased difficulty by one "Level" (capped at 4) on
    every correct hit. Retuned here per direct classroom feedback: kids
    who are quick finished so fast that slower classmates barely got a
    turn. Difficulty now ramps on a fixed clock instead of on
    performance - every RAMP_INTERVAL_MS, one more balloon joins (up to
    MAX_BALLOONS) and the rise speed increases - so every player's round
    intensifies on the same schedule regardless of skill.

Scoring is a simple cumulative count this time (+10/pop), unlike Klok's
draining-bank mechanic - a deliberate difference matching the original,
which only ever incremented a plain Score variable.

Two-player: no lives system (awkward to share fairly), a fixed 60-second
clock instead - long enough for a couple of difficulty ramps to kick in,
short enough that a classroom can cycle through players quickly. Either
cursor can pop any balloon; first correct pop scores for that player.
"""

import random
import pygame
import icons
from theme import player_color, best_text_color
from exercises import TableSet
from i18n import t


STARTING_BALLOONS = 4
MAX_BALLOONS = 8
RAMP_INTERVAL_MS = 20_000          # one new balloon + more speed every 20s
BASE_RISE_SPEED = 60.0             # pixels/second at the start
SPEED_INCREMENT_PER_TIER = 25.0    # added per ramp tier, uncapped (5 lives
                                    # or the 60s clock naturally ends a round
                                    # long before this gets absurd)
STARTING_LIVES = 5
POINTS_PER_POP = 10
TWO_PLAYER_SECONDS = 60

SPAWN_Y = 640       # balloons start just below this, near the bottom
ESCAPE_Y = 150      # rising above this = escaped (just under the top bar)
BALLOON_SIZE = (88, 127)

# Balloon colors, cycled by position. Real balloons come in colors, and
# unlike Hoeden there's no memory trick here that different colors could
# spoil. Two palettes: bright ones for the dark theme, deeper ones for the
# light theme (the bright yellow/orange would be nearly invisible on a light
# background). In regenboog each balloon gets a random color instead - one
# that contrasts with the background it floats on, re-rolled on every click.
BALLOON_COLORS = [(220, 60, 60), (240, 160, 40), (240, 210, 50),
                  (60, 170, 90), (60, 130, 220), (160, 80, 200)]
BALLOON_COLORS_LIGHT = [(190, 30, 30), (190, 90, 0), (130, 100, 0),
                        (20, 130, 50), (30, 90, 200), (140, 50, 170)]
# A balloon is a big shape, so the 3:1 contrast WCAG asks of large graphics
# is enough; 3.3 leaves a margin for the tiny color shifts of the scaled
# picture. Its number is separately held to 4.5:1 against the balloon.
BALLOON_MIN_CONTRAST = 3.3


def _draw_heart(screen, center, size, color):
    """A small heart icon built from primitives, not a Unicode glyph -
    glyph coverage for things like U+2764 is inconsistent across fonts
    and platforms and was rendering as a broken box (same issue the gear
    icon in leaderboard_screen.py had, fixed the same way there)."""
    cx, cy = center
    r = size // 3
    pygame.draw.circle(screen, color, (cx - r, cy - r // 2), r)
    pygame.draw.circle(screen, color, (cx + r, cy - r // 2), r)
    points = [
        (cx - size // 2, cy - r // 4),
        (cx + size // 2, cy - r // 4),
        (cx, cy + size // 2),
    ]
    pygame.draw.polygon(screen, color, points)


class Balloon:
    def __init__(self, x, y, value, is_correct):
        self.x = x
        self.y = y
        self.value = value
        self.is_correct = is_correct
        self.active = True          # False once popped or escaped

    def rect(self):
        w, h = BALLOON_SIZE
        return pygame.Rect(int(self.x - w / 2), int(self.y - h / 2), w, h)


class BallonGame:
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

        self.elapsed_ms = 0
        self.lives = STARTING_LIVES                       # 1-player only
        self.time_left_ms = TWO_PLAYER_SECONDS * 1000      # 2-player only
        self.scores = {1: 0, 2: 0} if num_players == 2 else {1: 0}
        self.finished = False

        self.question = ""
        self.correct_value = None
        self.balloons = []
        self._flash = {}   # id(balloon) -> [color, frames_left]


        self.font_question = pygame.font.SysFont("arial", 48, bold=True)
        self.font_value = pygame.font.SysFont("arial", 28, bold=True)
        self.font_topbar = pygame.font.SysFont("arial", 36, bold=True)
        self.font_score = pygame.font.SysFont("arial", 30, bold=True)

        self._spawn_round()

    def _current_tier(self):
        return self.elapsed_ms // RAMP_INTERVAL_MS

    def _current_balloon_count(self):
        return min(STARTING_BALLOONS + self._current_tier(), MAX_BALLOONS)

    def _current_rise_speed(self):
        return BASE_RISE_SPEED + self._current_tier() * SPEED_INCREMENT_PER_TIER

    def _spawn_round(self):
        problem = self.problems.make_problem()
        self.question, self.correct_value = problem.question, problem.answer
        count = self._current_balloon_count()

        # The correct answer plus count-1 different wrong ones (plausible
        # ones: other products for tables, near misses for plus/min).
        values = {self.correct_value, *self.problems.decoys(problem, count - 1)}

        value_list = list(values)
        random.shuffle(value_list)
        correct_index = value_list.index(self.correct_value)

        # Evenly spaced columns with a little jitter so it doesn't look
        # robotic, matching the original's own small random y-offset.
        margin = 80
        usable_w = self.screen_w - margin * 2
        slot_w = usable_w / count
        self.balloons = []
        for i, value in enumerate(value_list):
            slot_center = margin + slot_w * (i + 0.5)
            x = slot_center + random.uniform(-slot_w * 0.15, slot_w * 0.15)
            y = SPAWN_Y + random.uniform(-20, 20)
            self.balloons.append(Balloon(x, y, value, i == correct_index))
        self._flash = {}

    def _pop(self, balloon, cursor):
        balloon.active = False
        if balloon.is_correct:
            self.scores[cursor.player_id] = self.scores.get(cursor.player_id, 0) + POINTS_PER_POP
            if self.sound_bank:
                self.sound_bank.play_correct()
            self._spawn_round()
        else:
            if self.sound_bank:
                self.sound_bank.play_wrong()
            self._flash[id(balloon)] = [(200, 70, 70), 10]
            if self.num_players == 1:
                self._lose_life()

    def _lose_life(self):
        self.lives -= 1
        if self.lives <= 0:
            self.lives = 0
            self.finished = True

    def _handle_click(self, cursor):
        for balloon in self.balloons:
            if balloon.active and balloon.rect().collidepoint((cursor.x, cursor.y)):
                self._pop(balloon, cursor)
                return  # one click, one balloon

    def update(self, dt_ms, cursors):
        if self.finished:
            return

        self.elapsed_ms += dt_ms

        if self.num_players == 2:
            self.time_left_ms -= dt_ms
            if self.time_left_ms <= 0:
                self.time_left_ms = 0
                self.finished = True
                return

        rise_speed = self._current_rise_speed()
        correct_escaped = False
        for balloon in self.balloons:
            if not balloon.active:
                continue
            balloon.y -= rise_speed * (dt_ms / 1000.0)
            if balloon.y <= ESCAPE_Y:
                balloon.active = False
                if balloon.is_correct:
                    correct_escaped = True

        if correct_escaped:
            if self.sound_bank:
                self.sound_bank.play_wrong()
            if self.num_players == 1:
                self._lose_life()
                if self.finished:
                    return
            self._spawn_round()

        for key in list(self._flash.keys()):
            self._flash[key][1] -= 1
            if self._flash[key][1] <= 0:
                del self._flash[key]

        for cursor in cursors:
            if cursor.fired:
                self._handle_click(cursor)

    def _balloon_color(self, idx, bg_color):
        """Color of balloon number idx: the next color of the theme's palette
        that contrasts with the background (rotating by position, so
        neighbours differ), or a random readable one in regenboog."""
        shift = idx % len(BALLOON_COLORS)
        rotate = lambda palette: palette[shift:] + palette[:shift]
        if not self.theme:
            return BALLOON_COLORS[shift]
        return self.theme.color_on(
            f"ballon_balloon_{idx}", bg_color,
            rotate(BALLOON_COLORS), rotate(BALLOON_COLORS_LIGHT),
            min_contrast=BALLOON_MIN_CONTRAST, with_text=True)

    def draw(self, screen):
        bg_color, bg_text = self.theme.get("background", ((25, 30, 45), (255, 255, 255)),
                                            ((235, 238, 245), (20, 20, 30))) \
            if self.theme else ((25, 30, 45), (255, 255, 255))
        screen.fill(bg_color)

        topbar_color, topbar_text = self.theme.get(
            "ballon_topbar", ((15, 15, 25), (255, 255, 255)),
            ((210, 212, 225), (20, 20, 30))) if self.theme else ((15, 15, 25), (255, 255, 255))
        pygame.draw.rect(screen, topbar_color, (0, 0, self.screen_w, 110))

        if self.num_players == 1:
            heart_size = 26
            gap = 10
            total_w = self.lives * heart_size + max(0, self.lives - 1) * gap
            start_x = self.screen_w // 2 - total_w // 2
            for i in range(self.lives):
                cx = start_x + i * (heart_size + gap) + heart_size // 2
                _draw_heart(screen, (cx, 15 + heart_size // 2), heart_size, (220, 70, 90))
            score_label = self.font_score.render(
                t("hud.score", value=self.scores.get(1, 0)), True, topbar_text)
            screen.blit(score_label, (30, 55))
        else:
            seconds = max(0, self.time_left_ms // 1000)
            clock_label = self.font_topbar.render(f"{seconds:02d}", True, topbar_text)
            screen.blit(clock_label, clock_label.get_rect(
                centerx=self.screen_w // 2, y=15))
            p1_label = self.font_score.render(
                t("hud.player_score", n=1, value=self.scores.get(1, 0)), True, player_color(1, topbar_color))
            screen.blit(p1_label, (30, 55))
            p2_label = self.font_score.render(
                t("hud.player_score", n=2, value=self.scores.get(2, 0)), True, player_color(2, topbar_color))
            screen.blit(p2_label, p2_label.get_rect(
                topright=(self.screen_w - 30, 55)))

        q_label = self.font_question.render(self.question, True, bg_text)
        screen.blit(q_label, q_label.get_rect(centerx=self.screen_w // 2, y=120))

        for idx, balloon in enumerate(self.balloons):
            if not balloon.active:
                continue
            flash = self._flash.get(id(balloon))
            if flash:
                # Wrong pop: a fixed red flash - feedback, not decoration.
                color = flash[0]
                text_color = best_text_color(color)
            else:
                color = self._balloon_color(idx, bg_color)
                text_color = best_text_color(color)
            rect = balloon.rect()
            screen.blit(icons.balloon(BALLOON_SIZE, color), rect.topleft)
            # The number sits in the middle of the round body, in the
            # color chosen for contrast against THIS balloon's color.
            label = self.font_value.render(str(balloon.value), True, text_color)
            screen.blit(label, label.get_rect(center=(
                rect.centerx,
                rect.top + int(rect.height * icons.BALLOON_BODY_CENTER_FRAC))))

    def results(self):
        return {"scores": dict(self.scores), "lives_left": self.lives}

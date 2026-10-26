"""
klok.py

Rebuild of the "Klok" minigame, based on a full disassembly of the
original AS2 bytecode plus direct feedback from someone who's actually
played the source game with students. The real structure:

  - At the start of a round, 10 DIFFERENT problems are generated, each
    with its own correct answer (the original's Antwoorden[]/Somtekst[]
    arrays, one entry per slot). All 10 answers are shown at once as
    clickable cards - and since each card is a genuinely correct answer
    to SOME problem, wrong options are real numbers, not made-up noise.
  - One slot is picked at random as the "active" question (KiesDeSom in
    the original) and its equation is displayed.
  - Click the card matching the active question: correct sound, that
    slot is answered and its card disappears for good (not replaced),
    then a new active question is picked from whatever's left.
  - Click any other still-visible card: wrong sound, nothing else,
    that card stays.
  - The board genuinely shrinks: 10 cards -> 9 -> 8 -> ... -> 0, which
    is where the rising tension comes from as a round nears its end.

Scoring is deliberately different for one vs. two players:

  ONE PLAYER (faithful to the original): a single points bank starts at
  1000 and drains by 1 every 100ms for the whole round, regardless of
  anything. Final score = whatever's left when all 10 are answered (or
  the bank hits 0 first, matching the original's early-exit).

  TWO PLAYERS: the single shared bank doesn't tell you who was faster,
  so instead each question carries its OWN pool starting at 100,
  draining the same way while that question is active. Whoever's
  cursor hits the correct card first claims whatever's left of THAT
  question's pool, added to their own running total. Pool resets to
  100 for the next question. 100 x 10 questions = 1000 max, same
  ceiling as the original's single-player bank, just distributed
  per-question so two players get a genuine head-to-head number.
  A pool hitting 0 does NOT end the round early in this mode (there's
  no shared constraint to fail) - the round only ends once all 10
  slots are answered.
"""

import random
import pygame
import icons
from theme import player_color
from exercises import TableSet
from i18n import t


# Fixed (dark_pair, light_pair) per themed slot - see theme.py. Flash
# colors (wrong-click red) and player identity colors (red/blue) are
# deliberately NOT themed, same reasoning as keuzescherm.py: they carry
# meaning a kid relies on.
_BACKGROUND = ((25, 30, 45), (255, 255, 255)), ((235, 238, 245), (20, 20, 30))
_TOPBAR = ((15, 15, 25), (255, 255, 255)), ((210, 212, 225), (20, 20, 30))
_CARD = ((90, 90, 140), (255, 255, 255)), ((225, 225, 235), (20, 20, 30))

TOTAL_SLOTS = 10
DRAIN_INTERVAL_MS = 100          # matches the original's setInterval(Veranderklok, 100)

GLOBAL_BANK_START = 1000         # 1-player: matches the original's Klokwaarde = 1000
QUESTION_POOL_MAX = 100          # 2-player: per-question pool (100 x 10 slots = 1000 ceiling)

# A wrong click costs this many points immediately, on top of the normal
# passive drain - added after kids were observed mashing every card at
# once to find the answer by brute force rather than reading the
# question. At 10 points/second passive drain, 20 points is roughly the
# cost of 2 extra seconds of honest thinking - enough that random
# guessing is clearly worse than reading the problem, without making one
# genuine wrong guess ruinous. Easy to retune after watching more play:
# bump this up (e.g. to 50) if spamming is still happening too cheaply.
WRONG_CLICK_PENALTY = 20

CARD_COLS = 5
CARD_ROWS = 2


def generate_batch(tables, som_type, problems=None):
    """
    Builds the slots for one round: up to TOTAL_SLOTS (10) independent
    problems, each with its own answer, all answers guaranteed unique
    (matching the original's duplicate-avoidance loop over Antwoorden[])
    since all of them are visible on the board at once.

    `problems` is the shared problem set (exercises.py); without one, the
    multiplication tables are used. A selection with fewer different
    answers than 10 (some plus/min types) simply gives fewer cards - the
    game then ends after that many correct answers.

    Returns a list of {"question": str, "answer": int} dicts.
    """
    problems = problems or TableSet(tables, som_type)
    return [{"question": p.question, "answer": p.answer}
            for p in problems.unique_problems(TOTAL_SLOTS)]


class KlokGame:
    def __init__(self, screen_w, screen_h, tables, som_type, num_players=1,
                 sound_bank=None, theme=None, problems=None):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.tables = tables
        self.som_type = som_type
        self.num_players = num_players
        self.sound_bank = sound_bank
        self.theme = theme

        self.problems = problems or TableSet(tables, som_type)
        self.slots = generate_batch(tables, som_type, self.problems)
        # Normally 10 cards; fewer when the chosen exercises have fewer
        # different answers. Everything below counts cards via this number.
        self.total_slots = len(self.slots)
        self.answered = [False] * self.total_slots
        self.active_index = random.randrange(self.total_slots)
        self.total_correct = 0
        self.finished = False

        # 1-player: single global bank, drains for the whole round.
        self.global_bank = GLOBAL_BANK_START
        # 2-player: per-question pool, resets every time a new question
        # becomes active.
        self.question_pool = QUESTION_POOL_MAX
        self._drain_accumulator_ms = 0

        self.scores = {1: 0, 2: 0} if num_players == 2 else {1: 0}

        self._flash = {}  # slot index -> [color, frames_left]

        self.card_rects = self._layout_rects()

        self.font_question = pygame.font.SysFont("arial", 54, bold=True)
        self.font_card = pygame.font.SysFont("arial", 36, bold=True)
        self.font_bank = pygame.font.SysFont("arial", 40, bold=True)
        self.font_score = pygame.font.SysFont("arial", 30, bold=True)


    def _layout_rects(self):
        margin_x, margin_y = 40, 40
        top = 220
        available_w = self.screen_w - margin_x * 2
        available_h = self.screen_h - top - margin_y
        card_w = (available_w - (CARD_COLS - 1) * 20) // CARD_COLS
        card_h = (available_h - (CARD_ROWS - 1) * 20) // CARD_ROWS

        rects = []
        for idx in range(self.total_slots):
            col = idx % CARD_COLS
            row = idx // CARD_COLS
            x = margin_x + col * (card_w + 20)
            y = top + row * (card_h + 20)
            rects.append(pygame.Rect(x, y, card_w, card_h))
        return rects

    def _pick_new_active(self):
        remaining = [i for i in range(self.total_slots) if not self.answered[i]]
        if not remaining:
            self.finished = True
            return
        self.active_index = random.choice(remaining)
        self.question_pool = QUESTION_POOL_MAX

    def _handle_click(self, cursor):
        for idx, rect in enumerate(self.card_rects):
            if self.answered[idx]:
                continue
            if rect.collidepoint((cursor.x, cursor.y)):
                if idx == self.active_index:
                    if self.num_players == 2:
                        self.scores[cursor.player_id] += self.question_pool
                    self.answered[idx] = True
                    self.total_correct += 1
                    if self.sound_bank:
                        self.sound_bank.play_correct()
                    if self.total_correct >= self.total_slots:
                        self.finished = True
                    else:
                        self._pick_new_active()
                else:
                    if self.sound_bank:
                        self.sound_bank.play_wrong()
                    self._flash[idx] = [(200, 70, 70), 12]
                    # Penalize wrong clicks so mashing every card is
                    # clearly worse than reading the question.
                    if self.num_players == 1:
                        self.global_bank = max(0, self.global_bank - WRONG_CLICK_PENALTY)
                        if self.global_bank <= 0:
                            self.finished = True
                    else:
                        self.question_pool = max(0, self.question_pool - WRONG_CLICK_PENALTY)
                return  # one click only ever hits the single topmost card

    def update(self, dt_ms, cursors):
        if self.finished:
            return

        self._drain_accumulator_ms += dt_ms
        while self._drain_accumulator_ms >= DRAIN_INTERVAL_MS:
            self._drain_accumulator_ms -= DRAIN_INTERVAL_MS
            if self.num_players == 1:
                self.global_bank -= 1
                if self.global_bank <= 0:
                    self.global_bank = 0
                    self.finished = True
                    return
            else:
                # Per-question pool: drains, but bottoming out doesn't end
                # the round - it just means this particular question is
                # worth 0 until someone finally hits it.
                self.question_pool = max(0, self.question_pool - 1)

        for idx in list(self._flash.keys()):
            color, frames = self._flash[idx]
            frames -= 1
            if frames <= 0:
                del self._flash[idx]
            else:
                self._flash[idx] = [color, frames]

        for cursor in cursors:
            if cursor.fired:
                self._handle_click(cursor)

    def draw(self, screen):
        bg_color, bg_text = self.theme.get("background", *_BACKGROUND) \
            if self.theme else _BACKGROUND[0]
        screen.fill(bg_color)

        topbar_color, topbar_text = self.theme.get("klok_topbar", *_TOPBAR) \
            if self.theme else _TOPBAR[0]
        pygame.draw.rect(screen, topbar_color, (0, 0, self.screen_w, 130))

        if self.num_players == 1:
            clock_value = self.global_bank
        else:
            clock_value = self.question_pool  # this question's live stake

        clock_label = self.font_bank.render(str(clock_value), True, topbar_text)
        # The stopwatch hand shows how much is left - the whole bank in
        # 1-player, this question's pool in 2-player - sweeping from 12
        # o'clock as it runs down. Drawn in the bar's own text color, so
        # it has the same guaranteed contrast as the number next to it.
        if self.num_players == 1:
            fraction = self.global_bank / GLOBAL_BANK_START
        else:
            fraction = self.question_pool / QUESTION_POOL_MAX
        icon = icons.stopwatch((52, 58), topbar_text, fraction)
        icon_rect = icon.get_rect(midright=(self.screen_w // 2 - 10, 42))
        screen.blit(icon, icon_rect)
        screen.blit(clock_label, clock_label.get_rect(
            midleft=(self.screen_w // 2 + 10, 40)))

        # Player identity colors (red/blue) - the variant that contrasts
        # best with the actual bar color (see theme.player_color), so
        # "my score" stays recognizable AND readable in every theme.
        p1_label = self.font_score.render(
            t("hud.player_score", n=1, value=self.scores.get(1, 0)), True, player_color(1, topbar_color))
        screen.blit(p1_label, (30, 30))
        if self.num_players == 2:
            p2_label = self.font_score.render(
                t("hud.player_score", n=2, value=self.scores.get(2, 0)), True, player_color(2, topbar_color))
            screen.blit(p2_label, p2_label.get_rect(
                topright=(self.screen_w - 30, 30)))

        progress = self.font_score.render(
            f"{self.total_correct} / {self.total_slots}", True, topbar_text)
        screen.blit(progress, progress.get_rect(
            centerx=self.screen_w // 2, y=85))

        question_text = self.slots[self.active_index]["question"]
        q_label = self.font_question.render(question_text, True, bg_text)
        screen.blit(q_label, q_label.get_rect(centerx=self.screen_w // 2, y=145))

        for idx, rect in enumerate(self.card_rects):
            if self.answered[idx]:
                continue  # the board genuinely shrinks - no placeholder drawn
            if idx in self._flash:
                # Wrong-click flash stays a fixed red regardless of theme -
                # it's feedback, not decoration.
                color, text_color = self._flash[idx][0], (255, 255, 255)
            else:
                color, text_color = self.theme.get(f"klok_card_{idx}", *_CARD) \
                    if self.theme else _CARD[0]
            pygame.draw.rect(screen, color, rect, border_radius=14)
            label = self.font_card.render(str(self.slots[idx]["answer"]), True,
                                           text_color)
            screen.blit(label, label.get_rect(center=rect.center))

    def results(self):
        return {
            "scores": dict(self.scores),
            "bank_remaining": self.global_bank,
            "total_correct": self.total_correct,
        }

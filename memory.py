"""
memory.py

Rebuild of the "Memory" minigame, based on a full disassembly of the
original AS2 bytecode (frame script, card buttons, card placements).

THE REAL MECHANIC (confirmed from the code)
  - A pairs game with 10 pairs = 20 face-down cards. Each pair is one
    sum ("7 x 3") and its answer ("21"). All 10 answers are different,
    so every sum has exactly one partner.
  - The original lays the cards out in a 4x5 grid: the two LEFT columns
    hold the 10 sum cards, the two RIGHT columns hold the 10 answer
    cards. Inside each block the positions are random. We keep that.
  - A turn = flip two cards (a flipped card cannot be flipped again).
    The turn counter goes up by one. Both cards stay visible for 1.5 s
    and further clicks are ignored meanwhile. A sum + its own answer
    is a match and both cards disappear; anything else (two sums, two
    answers, a sum + a wrong answer) turns both cards back over.
  - The game ends when all 10 pairs are found. The score is the number
    of TURNS (fewer is better, the minimum is 10). No timer, no lives.
  - Sums are shown as "other x table" ("7 x 3" for table 3), and
    divisions as "product : table" ("21 : 3").

WHAT IS DIFFERENT HERE (deliberately)
  - The card back is a plain "?".
  - HIDDEN TIMER: the game measures how long the match took, but never
    draws it. It is only stored on the leaderboard, where it breaks ties
    between players with the same number of turns. Turns always come
    first: 10 turns in 5 minutes beats 12 turns in 2 minutes.
    It starts at the FIRST card flip (so reading/setup time does not
    count) and stops at the moment the LAST pair is flipped (the
    1.5 s hold after the final match is not the player's time).
  - CO-OP 2-PLAYER: both players share ONE board and ONE result. They
    shoot in turn; only the active player's gun counts. An indicator at
    the top highlights whose turn it is. See MATCH_KEEPS_TURN below.
  - The "goed" sound plays the moment a matching pair is flipped (the
    original waited for the 1.5 s hold to end). A miss stays silent, as
    in the original.

All pacing numbers are named constants below, and ALL animation is
time-based (dt in milliseconds), never frame-based.
"""

import random
import pygame
from theme import best_text_color, player_color, SIGNAL_GREEN
from exercises import TableSet
from i18n import t

# =====================================================================
# TUNING - everything you might want to adjust while testing with kids.
# =====================================================================
NUM_PAIRS = 10              # original: 10 pairs (20 cards)
REVEAL_HOLD_MS = 1500       # both cards stay visible this long (original: 1500)
FLIP_ANIM_MS = 180          # time for a card to turn over
VANISH_ANIM_MS = 250        # time for a matched pair to shrink away

# Co-op: does a player who finds a pair get to go again?
#   False = players alternate every turn, match or not (default)
#   True  = classic memory rule: a match keeps the turn
MATCH_KEEPS_TURN = False

# Show the running turn count in the top bar. (The timer is NEVER shown.)
SHOW_TURN_COUNT = True
# =====================================================================

# After the hold, cards take this long to turn back / shrink away; input
# is blocked until then so nobody clicks a half-turned card.
SETTLE_MS = max(FLIP_ANIM_MS, VANISH_ANIM_MS)

PHASE_PICK = "pick"          # waiting for the active player to flip a card
PHASE_HOLD = "hold"          # two cards face up, nobody may click
PHASE_SETTLE = "settle"      # cards turning back / vanishing

RESULT_MATCH = "match"
RESULT_MISS = "miss"

# Layout (1280x720). The board is 4 columns: [sums][sums] gap [answers][answers]
BAR_H = 100
BOARD_TOP = 124
BOARD_BOTTOM_MARGIN = 24
SIDE_MARGIN = 60
COL_GAP = 20                 # between the two columns of one block
BLOCK_GAP = 100              # between the sum block and the answer block
ROW_GAP = 16
MAX_CARD_H = 110

# Fixed (dark_pair, light_pair) per themed slot - see theme.py. Each pair
# is (background, text). Back and face are deliberately very different
# so a flipped card is obvious from across the room.
_BACKGROUND = ((25, 30, 45), (255, 255, 255)), ((235, 238, 245), (20, 20, 30))
_TOPBAR = ((15, 15, 25), (255, 255, 255)), ((210, 212, 225), (20, 20, 30))
_BACK = ((70, 70, 125), (255, 255, 255)), ((45, 115, 165), (255, 255, 255))
_FACE = ((240, 240, 245), (20, 20, 30)), ((255, 255, 255), (20, 20, 30))
_FACE_OUTLINE = (90, 90, 120)
_MISS_OUTLINE = (200, 60, 60)     # fixed signal red for "not a pair"


def make_pairs(tables, som_type, count=NUM_PAIRS, problems=None):
    """Builds the pairs for one round: a list of
    {"question": str, "answer": int} dicts, all answers DIFFERENT.

    `problems` is the shared problem set (exercises.py): the multiplication
    tables by default (written "other x table", Memory's style), or the
    plus/min exercises chosen on the selection screen. When the selection
    simply has fewer different answers than `count` (some plus/min types), the
    round gets fewer pairs - the board adapts.

    Note: with "Gedeeld door" the answer is the quotient, so the answer
    cards are always exactly 1..10 (as in the original, where quotients
    also had to be unique across the 10 cards).
    """
    problems = problems or TableSet(tables, som_type, other_first=True)
    return [{"question": p.question, "answer": p.answer}
            for p in problems.unique_problems(count)]


class Card:
    """One card on the board. face_up is where it is HEADING; flip is the
    animated progress (0 = fully face down, 1 = fully face up)."""

    def __init__(self, kind, pair, text, rect):
        self.kind = kind            # "sum" or "answer"
        self.pair = pair            # index of the pair this card belongs to
        self.text = text
        self.rect = rect
        self.face_up = False
        self.flip = 0.0
        self.result = None          # None / RESULT_MATCH / RESULT_MISS
        self.vanishing = False
        self.vanish = 0.0           # 0 = full size, 1 = gone
        self.gone = False


class MemoryGame:
    def __init__(self, screen_w, screen_h, tables, som_type, num_players=1,
                 sound_bank=None, theme=None, problems=None):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.tables = tables
        self.som_type = som_type
        self.num_players = num_players
        self.sound_bank = sound_bank
        self.theme = theme

        # What the exercises are (tables in Memory's "other x table" style, or
        # plus/min): kept like in the other games, see exercises.py.
        self.problems = problems or TableSet(tables, som_type, other_first=True)
        self.pairs = make_pairs(tables, som_type, problems=self.problems)
        self.num_pairs = len(self.pairs)
        self.cards = self._build_cards()

        self.turns = 0
        self.pairs_found = 0
        self.finished = False

        # Hidden timer (never drawn - see module docstring).
        self.elapsed_ms = 0
        self._timer_running = False

        self.active_player = 1       # co-op: whose turn it is (always 1 in 1P)
        self.phase = PHASE_PICK
        self.phase_ms = 0
        self._picked = []            # the (up to two) cards flipped this turn
        self._turn_was_match = False

        self.font_card = pygame.font.SysFont("arial", 44, bold=True)
        self.font_back = pygame.font.SysFont("arial", 60, bold=True)
        self.font_bar = pygame.font.SysFont("arial", 30, bold=True)
        self.font_player = pygame.font.SysFont("arial", 28, bold=True)

    # ---------------------------------------------------------- setup
    def _block_cells(self, first_col):
        """The grid cells (col, row) of one 2-column block."""
        rows = (self.num_pairs + 1) // 2
        return [(first_col + c, r) for r in range(rows) for c in range(2)]

    def _cell_rect(self, col, row, rows):
        usable_w = self.screen_w - SIDE_MARGIN * 2
        card_w = (usable_w - 2 * COL_GAP - BLOCK_GAP) // 4
        usable_h = self.screen_h - BOARD_TOP - BOARD_BOTTOM_MARGIN
        card_h = min(MAX_CARD_H, (usable_h - (rows - 1) * ROW_GAP) // rows)
        board_h = rows * card_h + (rows - 1) * ROW_GAP
        top = BOARD_TOP + (usable_h - board_h) // 2
        # x of each of the 4 columns: two close together, a wide gap, two more.
        col_x = [SIDE_MARGIN,
                 SIDE_MARGIN + card_w + COL_GAP,
                 SIDE_MARGIN + 2 * card_w + COL_GAP + BLOCK_GAP,
                 SIDE_MARGIN + 3 * card_w + 2 * COL_GAP + BLOCK_GAP]
        return pygame.Rect(col_x[col], top + row * (card_h + ROW_GAP), card_w, card_h)

    def _build_cards(self):
        rows = (self.num_pairs + 1) // 2
        sum_cells = self._block_cells(0)
        answer_cells = self._block_cells(2)
        # Random positions inside each block; the block itself is fixed
        # (sums left, answers right) exactly like the original.
        random.shuffle(sum_cells)
        random.shuffle(answer_cells)
        cards = []
        for i, pair in enumerate(self.pairs):
            cards.append(Card("sum", i, pair["question"],
                              self._cell_rect(*sum_cells[i], rows)))
            cards.append(Card("answer", i, str(pair["answer"]),
                              self._cell_rect(*answer_cells[i], rows)))
        return cards

    # ---------------------------------------------------------- turns
    def _click_sound(self):
        if self.sound_bank:
            self.sound_bank.play_click()

    def _handle_click(self, cursor):
        # Only the player whose turn it is can flip cards; the other
        # gun is simply ignored until the turn passes.
        if cursor.player_id != self.active_player:
            return
        for card in self.cards:
            if card.gone or card.face_up:
                continue
            if card.rect.collidepoint((cursor.x, cursor.y)):
                self._flip(card)
                return

    def _flip(self, card):
        if not self._timer_running and self.turns == 0 and not self._picked:
            self._timer_running = True          # first flip of the match
        card.face_up = True
        self._picked.append(card)
        self._click_sound()
        if len(self._picked) == 2:
            self._finish_pick()

    def _finish_pick(self):
        first, second = self._picked
        self.turns += 1
        self._turn_was_match = first.pair == second.pair
        result = RESULT_MATCH if self._turn_was_match else RESULT_MISS
        first.result = second.result = result
        if self._turn_was_match:
            self.pairs_found += 1
            if self.sound_bank:
                self.sound_bank.play_correct()
            if self.pairs_found == self.num_pairs:
                self._timer_running = False     # the player's time ends HERE
        self.phase = PHASE_HOLD
        self.phase_ms = 0

    def _end_hold(self):
        """The 1.5 s are over: matched cards shrink away, others turn back."""
        for card in self._picked:
            if self._turn_was_match:
                card.vanishing = True
            else:
                card.face_up = False
        self.phase = PHASE_SETTLE
        self.phase_ms = 0

    def _end_turn(self):
        for card in self._picked:
            card.result = None
            if self._turn_was_match:
                card.gone = True
        self._picked = []
        if self.pairs_found == self.num_pairs:
            self.finished = True
            return
        if self.num_players == 2 and not (self._turn_was_match and MATCH_KEEPS_TURN):
            self.active_player = 2 if self.active_player == 1 else 1
        self.phase = PHASE_PICK
        self.phase_ms = 0

    # ---------------------------------------------------------- update
    def _animate(self, dt_ms):
        flip_step = dt_ms / FLIP_ANIM_MS
        vanish_step = dt_ms / VANISH_ANIM_MS
        for card in self.cards:
            target = 1.0 if card.face_up else 0.0
            if card.flip < target:
                card.flip = min(target, card.flip + flip_step)
            elif card.flip > target:
                card.flip = max(target, card.flip - flip_step)
            if card.vanishing and card.vanish < 1.0:
                card.vanish = min(1.0, card.vanish + vanish_step)

    def update(self, dt_ms, cursors):
        if self.finished:
            return
        if self._timer_running:
            self.elapsed_ms += dt_ms
        self._animate(dt_ms)

        if self.phase == PHASE_PICK:
            for cursor in cursors:
                if cursor.fired:
                    self._handle_click(cursor)
                    if self.phase != PHASE_PICK:
                        break           # that click completed a turn
        elif self.phase == PHASE_HOLD:
            self.phase_ms += dt_ms
            if self.phase_ms >= REVEAL_HOLD_MS:
                self._end_hold()
        elif self.phase == PHASE_SETTLE:
            self.phase_ms += dt_ms
            if self.phase_ms >= SETTLE_MS:
                self._end_turn()

    # ---------------------------------------------------------- drawing
    def _themed(self, slot, dark_pair, light_pair):
        if self.theme:
            return self.theme.get(slot, dark_pair, light_pair)
        return dark_pair

    def _draw_card(self, screen, card):
        if card.gone:
            return
        # Turning over: the card squeezes to a line, then widens again as
        # the other side. vanish shrinks the whole card.
        if card.flip < 0.5:
            showing_face, squeeze = False, 1 - 2 * card.flip
        else:
            showing_face, squeeze = True, 2 * card.flip - 1
        scale = 1 - card.vanish
        w, h = int(card.rect.w * squeeze * scale), int(card.rect.h * scale)
        if w < 2 or h < 2:
            return
        rect = pygame.Rect(0, 0, w, h)
        rect.center = card.rect.center
        radius = max(1, min(14, h // 4))

        if showing_face:
            if card.result == RESULT_MATCH:
                color, text_color = SIGNAL_GREEN, (255, 255, 255)
            else:
                color, text_color = self._themed("memory_face", *_FACE)
            pygame.draw.rect(screen, color, rect, border_radius=radius)
            if card.result == RESULT_MISS:
                pygame.draw.rect(screen, _MISS_OUTLINE, rect, 6, border_radius=radius)
            else:
                pygame.draw.rect(screen, _FACE_OUTLINE, rect, 3, border_radius=radius)
            label = self.font_card.render(card.text, True, text_color)
        else:
            color, text_color = self._themed("memory_back", *_BACK)
            pygame.draw.rect(screen, color, rect, border_radius=radius)
            darker = tuple(int(c * 0.6) for c in color[:3])
            pygame.draw.rect(screen, darker, rect, 3, border_radius=radius)
            label = self.font_back.render("?", True, text_color)

        # Squeeze the text together with the card so it never sticks out.
        full = squeeze * scale
        if full < 0.999:
            lw = max(1, int(label.get_width() * full))
            lh = max(1, int(label.get_height() * scale))
            label = pygame.transform.smoothscale(label, (lw, lh))
        screen.blit(label, label.get_rect(center=rect.center))

    def _draw_turn_indicator(self, screen, bar_color, bar_text):
        """Co-op: two boxes at the top; the active player's is filled with
        their identity color (red / blue), the other is just outlined."""
        box_w, box_h, gap = 200, 52, 24
        left = self.screen_w // 2 - box_w - gap // 2
        for pid, x in ((1, left), (2, left + box_w + gap)):
            rect = pygame.Rect(x, (BAR_H - box_h) // 2, box_w, box_h)
            ident = player_color(pid, bar_color)
            if pid == self.active_player:
                fill, text = ident, best_text_color(ident)
                pygame.draw.rect(screen, fill, rect, border_radius=12)
                pygame.draw.rect(screen, bar_text, rect, 3, border_radius=12)
            else:
                text = bar_text
                pygame.draw.rect(screen, ident, rect, 3, border_radius=12)
            label = self.font_player.render(t("hud.player", n=pid), True, text)
            screen.blit(label, label.get_rect(center=rect.center))

    def draw(self, screen):
        bg_color, _ = self._themed("background", *_BACKGROUND)
        screen.fill(bg_color)

        bar_color, bar_text = self._themed("memory_topbar", *_TOPBAR)
        pygame.draw.rect(screen, bar_color, (0, 0, self.screen_w, BAR_H))

        if SHOW_TURN_COUNT:
            turns = self.font_bar.render(t("hud.turns", n=self.turns), True, bar_text)
            screen.blit(turns, turns.get_rect(midleft=(30, BAR_H // 2)))
        found = self.font_bar.render(
            t("hud.pairs", n=self.pairs_found, total=self.num_pairs), True, bar_text)
        screen.blit(found, found.get_rect(midright=(self.screen_w - 30, BAR_H // 2)))

        if self.num_players == 2:
            self._draw_turn_indicator(screen, bar_color, bar_text)

        for card in self.cards:
            self._draw_card(screen, card)

    # ---------------------------------------------------------- result
    def results(self):
        """scores: the turn count for every player (co-op: they share it).
        main.py records ONE leaderboard row for Memory - see COOP_GAMES."""
        return {
            "scores": {pid: self.turns for pid in range(1, self.num_players + 1)},
            "turns": self.turns,
            "time_ms": int(self.elapsed_ms),
        }

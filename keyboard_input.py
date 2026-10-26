"""
keyboard_input.py

An on-screen QWERTY keyboard, clickable with a Sinden gun (or mouse) -
no physical keyboard needed. Used for entering a name onto the
leaderboard, the same way arcade/lightgun games handle high-score entry.

OnScreenKeyboard handles ONE name entry. MultiNameEntry chains one or
two of them together (for 1-player or 2-player matches) so main.py can
just drive one object regardless of mode.
"""

import pygame
import icons
from i18n import t
from leaderboard import format_time
from theme import SIGNAL_GREEN

ROWS = [
    list("1234567890"),
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    list("ZXCVBNM"),
]

MAX_NAME_LENGTH = 12

# Fixed (dark_pair, light_pair) per themed slot - see theme.py. Space/
# Backspace/Klaar keep fixed colors (they're distinct actions a kid
# needs to recognize at a glance, not plain letters) - only the
# background and ordinary letter/digit keys are themed, each key its
# own slot for the same per-element chaos as Klok's cards.
_BACKGROUND = ((25, 30, 45), (255, 255, 255)), ((235, 238, 245), (20, 20, 30))
_KEY = ((90, 90, 140), (255, 255, 255)), ((225, 225, 235), (20, 20, 30))


class OnScreenKeyboard:
    def __init__(self, screen_w, screen_h, prompt, theme=None,
                 scores=None, active_player=None, score_word="Score",
                 times=None, score_labels=None):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.prompt = prompt
        self.theme = theme
        # scores: {player_id: final_score} for the match just finished,
        # shown above the keyboard so a kid can see what they got before
        # typing their name - otherwise, with only each name's single
        # best score shown on the leaderboard, there'd be no way to tell
        # what THIS run scored if it wasn't a new best. active_player:
        # which player_id is being entered right now - that one gets a
        # visible highlight so a two-player entry makes it obvious whose
        # score is whose ("highlight first score, enter first name;
        # highlight second score, enter second name").
        self.scores = scores or {}
        self.active_player = active_player
        # Word shown in a lone score box ("Score", "Beurten", ...) so it
        # matches that game's own HUD.
        self.score_word = score_word
        # times: {player_id: hidden-timer ms}. Shown next to the score with a
        # small stopwatch, for the games that have a hidden timer.
        # score_labels: {player_id: "8/11"} to show instead of the bare number.
        self.times = times or {}
        self.score_labels = score_labels or {}
        self.text = ""
        self.done = False

        self.font_prompt = pygame.font.SysFont("arial", 36, bold=True)
        self.font_text = pygame.font.SysFont("arial", 48, bold=True)
        self.font_key = pygame.font.SysFont("arial", 30, bold=True)
        self.font_special = pygame.font.SysFont("arial", 24, bold=True)
        self.font_score = pygame.font.SysFont("arial", 30, bold=True)

        self.key_rects = []  # list of (rect, char_or_action)
        self._layout()

    def _layout(self):
        key_w, key_h = 84, 74
        gap = 8
        top = 300

        for row_i, row in enumerate(ROWS):
            row_width = len(row) * (key_w + gap) - gap
            start_x = (self.screen_w - row_width) // 2
            for col_i, ch in enumerate(row):
                x = start_x + col_i * (key_w + gap)
                y = top + row_i * (key_h + gap)
                rect = pygame.Rect(x, y, key_w, key_h)
                self.key_rects.append((rect, ch))

        # Bottom row: Spatie (space), Backspace, Klaar (done)
        bottom_y = top + len(ROWS) * (key_h + gap) + 10
        space_rect = pygame.Rect(self.screen_w // 2 - 220, bottom_y, 280, key_h)
        back_rect = pygame.Rect(self.screen_w // 2 + 70, bottom_y, 180, key_h)
        done_rect = pygame.Rect(self.screen_w // 2 + 270, bottom_y, 180, key_h)
        self.key_rects.append((space_rect, "SPACE"))
        self.key_rects.append((back_rect, "BACK"))
        self.key_rects.append((done_rect, "DONE"))
        self._space_rect = space_rect
        self._back_rect = back_rect
        self._done_rect = done_rect

        # Score display, top of screen - one box per player with a
        # score, the active one highlighted. Single box, centered, for
        # one player; two side by side (left=P1, right=P2) for two.
        # The boxes are as wide as their widest content (score + stopwatch +
        # time), so nothing can ever stick out of a box.
        self.score_rects = {}
        box_w = max(220, max((self._score_group_width(pid) for pid in self.scores),
                             default=0) + 48)
        if len(self.scores) <= 1:
            pid = next(iter(self.scores), 1)
            self.score_rects[pid] = pygame.Rect(self.screen_w // 2 - box_w // 2, 16, box_w, 50)
        else:
            self.score_rects[1] = pygame.Rect(self.screen_w // 2 - 10 - box_w, 16, box_w, 50)
            self.score_rects[2] = pygame.Rect(self.screen_w // 2 + 10, 16, box_w, 50)

    def _score_text(self, player_id):
        """"Speler 1: 8/11" (two boxes) or "Score: 8/11" (a lone box)."""
        value = self.score_labels.get(player_id, str(self.scores.get(player_id, 0)))
        prefix = t("hud.player", n=player_id) if len(self.scores) > 1 else self.score_word
        return f"{prefix}: {value}"

    _TIME_ICON_SIZE = 30
    _TIME_GAP = 22          # between the score text and the stopwatch
    _ICON_GAP = 8           # between the stopwatch and the time

    def _score_group_width(self, player_id):
        """Width of the content of one score box: the text and, if this
        player has a hidden time, a stopwatch plus the time."""
        width = self.font_score.size(self._score_text(player_id))[0]
        if player_id in self.times:
            time_text = format_time(self.times[player_id])
            width += (self._TIME_GAP + self._TIME_ICON_SIZE + self._ICON_GAP
                      + self.font_score.size(time_text)[0])
        return width

    def _handle_click(self, pos):
        for rect, action in self.key_rects:
            if rect.collidepoint(pos):
                if action == "SPACE":
                    if len(self.text) < MAX_NAME_LENGTH:
                        self.text += " "
                elif action == "BACK":
                    self.text = self.text[:-1]
                elif action == "DONE":
                    self.done = True
                else:
                    if len(self.text) < MAX_NAME_LENGTH:
                        self.text += action
                return

    def update(self, cursors):
        for cursor in cursors:
            if cursor.fired:
                self._handle_click((cursor.x, cursor.y))

    def result(self):
        return self.text.strip() or t("name.default")

    def draw(self, screen):
        bg_color, bg_text = self.theme.get("background", *_BACKGROUND) \
            if self.theme else _BACKGROUND[0]
        screen.fill(bg_color)

        for player_id, rect in self.score_rects.items():
            # A lone score box is shared by whoever is typing (1 player, or
            # co-op Memory where both players typed for ONE result), so it
            # is always highlighted. With two boxes, only the active one.
            is_active = (self.active_player is None) or (player_id == self.active_player) \
                or len(self.scores) <= 1
            if is_active:
                color, text_color = SIGNAL_GREEN, (255, 255, 255)
            else:
                # Inactive box: visibly dimmer than the green active one, but
                # its text still clears 4.5:1 (the old (140,140,150) was 3.5:1).
                color, text_color = (55, 55, 70), (190, 190, 200)
            pygame.draw.rect(screen, color, rect, border_radius=10)
            if is_active and self.active_player is not None and len(self.scores) > 1:
                pygame.draw.rect(screen, (255, 255, 255), rect, 3, border_radius=10)
            # Score text, then (when this player has a hidden time) a small
            # stopwatch and the time, all centered in the box as ONE group.
            label = self.font_score.render(self._score_text(player_id), True, text_color)
            group_w = self._score_group_width(player_id)
            x = rect.centerx - group_w // 2
            screen.blit(label, label.get_rect(midleft=(x, rect.centery)))
            if player_id in self.times:
                x += label.get_width() + self._TIME_GAP
                icon = icons.stopwatch((self._TIME_ICON_SIZE, self._TIME_ICON_SIZE),
                                       text_color, 1.0)
                screen.blit(icon, icon.get_rect(midleft=(x, rect.centery)))
                x += self._TIME_ICON_SIZE + self._ICON_GAP
                time_label = self.font_score.render(
                    format_time(self.times[player_id]), True, text_color)
                screen.blit(time_label, time_label.get_rect(midleft=(x, rect.centery)))

        prompt_label = self.font_prompt.render(self.prompt, True, bg_text)
        screen.blit(prompt_label, prompt_label.get_rect(
            centerx=self.screen_w // 2, y=100))

        box_rect = pygame.Rect(self.screen_w // 2 - 260, 165, 520, 70)
        pygame.draw.rect(screen, (50, 50, 70), box_rect, border_radius=10)
        display_text = self.text if self.text else "_"
        text_label = self.font_text.render(display_text, True, (255, 230, 130))
        screen.blit(text_label, text_label.get_rect(center=box_rect.center))

        for rect, action in self.key_rects:
            if action == "SPACE":
                color, text_color = (90, 90, 130), (255, 255, 255)
                label = self.font_special.render(t("name.key.space"), True, text_color)
            elif action == "BACK":
                color, text_color = (150, 90, 60), (255, 255, 255)
                label = self.font_special.render(t("name.key.backspace"), True, text_color)
            elif action == "DONE":
                color, text_color = SIGNAL_GREEN, (255, 255, 255)
                label = self.font_special.render(t("common.done"), True, text_color)
            else:
                color, text_color = self.theme.get(f"key_{action}", *_KEY) \
                    if self.theme else _KEY[0]
                label = self.font_key.render(action, True, text_color)
            pygame.draw.rect(screen, color, rect, border_radius=10)
            screen.blit(label, label.get_rect(center=rect.center))


class MultiNameEntry:
    """Chains one OnScreenKeyboard per player, in order. main.py just
    calls update()/draw() until .done is True, then reads .names.

    scores: {player_id: final_score} for the match just finished - shown
    above every keyboard screen so a kid can see what they got (the
    leaderboard itself only shows each name's single best score, so this
    is the only place "what did I get just now" is visible). In 2-player
    mode, whichever player is currently typing their name has their
    score box highlighted, making the entry order unambiguous.

    times: {player_id: hidden-timer ms} - shown next to the score for the
    games that have one (Memory, Hoeden). score_labels: {player_id: "8/11"}
    - shown instead of the bare score number (Hoeden)."""

    def __init__(self, screen_w, screen_h, num_players, theme=None, scores=None,
                 score_word="Score", times=None, score_labels=None):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.num_players = num_players
        self.theme = theme
        self.scores = scores or {}
        self.score_word = score_word
        self.times = times
        self.score_labels = score_labels
        self._current_player = 1
        self.names = {}
        self.done = False
        self._keyboard = OnScreenKeyboard(
            screen_w, screen_h, self._prompt_for(1), theme=theme,
            scores=self.scores, active_player=1, score_word=score_word,
            times=times, score_labels=score_labels)

    def _prompt_for(self, player_id):
        if self.num_players == 1:
            return t("name.prompt.single")
        return t("name.prompt.player", n=player_id)

    def update(self, cursors):
        self._keyboard.update(cursors)
        if self._keyboard.done:
            self.names[self._current_player] = self._keyboard.result()
            if self._current_player >= self.num_players:
                self.done = True
            else:
                self._current_player += 1
                self._keyboard = OnScreenKeyboard(
                    self.screen_w, self.screen_h,
                    self._prompt_for(self._current_player), theme=self.theme,
                    scores=self.scores, active_player=self._current_player,
                    score_word=self.score_word, times=self.times,
                    score_labels=self.score_labels)

    def draw(self, screen):
        self._keyboard.draw(screen)

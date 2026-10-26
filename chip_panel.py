"""
chip_panel.py

The plus-and-min exercise chips, drawn and hit-tested in ONE place, so the
selection screen (keuzescherm.py) and the leaderboard's filter overlay
(leaderboard_screen.py) are guaranteed to look and behave the same.

Layout: three groups (Tot 10 / Tot 20 / Tot 100), each with a heading, then a
row of chips for "+" and a row for "-" (up to 7 chips per row; the counts
come from exercises.py). A chip is two lines - "TE + E" over "MB" - and
toggles between "ticked" (blue, with a check mark in the corner, so it is not
colour-only) and "unticked" (a themed neutral color, its own random color in
regenboog).

Everything about a ChipPanel is decided once in __init__: where each chip
is, so tests and click handling use exactly the rectangles that get drawn.
"""

import pygame

from exercises import EXERCISE_BY_KEY, GROUPS, types_in
from i18n import t, exercise_lines
from theme import TILE_BLUE, best_text_color, contrast_ratio

CHIPS_PER_ROW = 7
CHIP_H, CHIP_GAP, CHIP_ROW_GAP = 44, 5, 5
CHIP_GUTTER = 30             # left of each row: the + / - sign
GROUP_HEAD_H, GROUP_GAP = 22, 8

# A button whose fill is practically the same color as the page (contrast
# below this) gets an outline in the page's text color, so its SHAPE is
# always findable - e.g. the green Start button on a random green regenboog
# page. Every button's LABEL already clears 4.5:1 on the button itself, so
# this is only about not losing the button's edges; 1.25 leaves the normal
# dark and light looks (neutral buttons are 1.7:1 / 1.27:1 from the page)
# exactly as they are.
BUTTON_EDGE_CONTRAST = 1.25

# (dark pair, light pair) of (background, text) for an unticked chip.
NEUTRAL_CHIP = ((70, 70, 90), (255, 255, 255)), ((210, 212, 225), (20, 20, 30))
CHIP_OUTLINE = (90, 90, 120)


def fill_button(screen, color, rect, radius, page_bg, page_text, base_outline=None):
    """Draw a button/tile body (with its usual decorative outline, if any); if
    it would blend into the page (contrast below BUTTON_EDGE_CONTRAST) also
    outline it in the page's text color, drawn LAST so it stays on top."""
    pygame.draw.rect(screen, color, rect, border_radius=radius)
    if base_outline is not None:
        pygame.draw.rect(screen, base_outline, rect, 3, border_radius=radius)
    if contrast_ratio(color, page_bg) < BUTTON_EDGE_CONTRAST:
        pygame.draw.rect(screen, page_text, rect, 3, border_radius=radius)


class ChipPanel:
    """x0..x1: the horizontal space available; top: where the first group
    heading sits. After construction: chip_rects[key], group_heads[group],
    row_signs[(group, sign)] and bottom (the y just below the last row)."""

    def __init__(self, x0, x1, top):
        self.x0, self.x1, self.top = x0, x1, top
        self.chip_rects = {}                   # exercise key -> pygame.Rect
        self.group_heads = {}                  # group number -> (x, y) of its heading
        self.row_signs = {}                    # (group, "+"/"-") -> centre of the sign
        chip_w = (x1 - x0 - CHIP_GUTTER - (CHIPS_PER_ROW - 1) * CHIP_GAP) // CHIPS_PER_ROW
        y = top
        for group, _heading in GROUPS:
            self.group_heads[group] = (x0, y)
            y += GROUP_HEAD_H
            for sign in ("+", "-"):
                self.row_signs[(group, sign)] = (x0 + CHIP_GUTTER // 2 - 2, y + CHIP_H // 2)
                for i, etype in enumerate(types_in(group, sign)):
                    self.chip_rects[etype.key] = pygame.Rect(
                        x0 + CHIP_GUTTER + i * (chip_w + CHIP_GAP), y, chip_w, CHIP_H)
                y += CHIP_H + CHIP_ROW_GAP
            y += GROUP_GAP
        self.bottom = y

        self.font_chip = pygame.font.SysFont("arial", 18, bold=True)
        self.font_chip_small = pygame.font.SysFont("arial", 13, bold=True)
        self.font_group = pygame.font.SysFont("arial", 19, bold=True)
        self._fit_fonts = {}                   # size -> font, for labels that need to shrink

    # ------------------------------------------------------------ interaction
    def key_at(self, pos):
        """The exercise key of the chip under `pos`, or None."""
        for key, rect in self.chip_rects.items():
            if rect.collidepoint(pos):
                return key
        return None

    # ------------------------------------------------------------ drawing
    def label_fonts(self, etype, rect):
        """(font for line 1, font for line 2): the biggest size at which line 1
        (in the current language) fits inside the chip with a margin."""
        line1 = exercise_lines(etype)[0]
        for size in (18, 16, 15, 14, 13):
            if size == 18:
                font = self.font_chip
            else:
                font = self._fit_fonts.setdefault(size, pygame.font.SysFont("arial", size, bold=True))
            if font.size(line1)[0] <= rect.w - 14:
                break
        return font, self.font_chip_small

    def draw(self, screen, selected, theme, page_bg, page_text):
        """selected: the set of ticked exercise keys."""
        for group, _heading in GROUPS:
            x, y = self.group_heads[group]
            # The heading comes from the language file ("Tot 20" / "Up to 20");
            # GROUPS only supplies the number.
            screen.blit(self.font_group.render(t("exercise.group", n=group), True, page_text),
                        (x, y))
            for sign in ("+", "-"):
                self._draw_row_sign(screen, self.row_signs[(group, sign)], sign, page_text)
        for key, rect in self.chip_rects.items():
            self._draw_chip(screen, EXERCISE_BY_KEY[key], rect, key in selected,
                            theme, page_bg, page_text)

    @staticmethod
    def _draw_row_sign(screen, center, sign, color):
        """A + or - drawn with lines (not a font glyph, which not every font has)."""
        cx, cy = center
        pygame.draw.line(screen, color, (cx - 9, cy), (cx + 9, cy), 5)
        if sign == "+":
            pygame.draw.line(screen, color, (cx, cy - 9), (cx, cy + 9), 5)

    def _draw_chip(self, screen, etype, rect, selected, theme, page_bg, page_text):
        if selected:
            fill, label_color = TILE_BLUE, (255, 255, 255)
            fill_button(screen, fill, rect, 10, page_bg, page_text)
            pygame.draw.rect(screen, page_text, rect, 2, border_radius=10)
        else:
            fill, label_color = theme.get(f"chip_off_{etype.key}", *NEUTRAL_CHIP) \
                if theme else NEUTRAL_CHIP[0]
            fill_button(screen, fill, rect, 10, page_bg, page_text, base_outline=CHIP_OUTLINE)
        font1, font2 = self.label_fonts(etype, rect)
        text1, text2 = exercise_lines(etype)
        line1 = font1.render(text1, True, label_color)
        if text2:
            line2 = font2.render(text2, True, label_color)
            # Two lines with a 1 px gap: 21 + 15 + 1 = 37 px fits the 44 px chip.
            gap = 1
            block = line1.get_height() + line2.get_height() + gap
            top = rect.centery - block // 2
            screen.blit(line1, line1.get_rect(midtop=(rect.centerx, top)))
            screen.blit(line2, line2.get_rect(midtop=(rect.centerx, top + line1.get_height() + gap)))
        else:
            screen.blit(line1, line1.get_rect(center=rect.center))
        if selected:
            # Check-mark badge on the top-right corner (a second, non-color cue),
            # pushed out to the corner so it stays off the label.
            badge_color = best_text_color(fill)
            center = (rect.right - 3, rect.top + 3)
            pygame.draw.circle(screen, badge_color, center, 9)
            pygame.draw.lines(screen, fill, False, [
                (center[0] - 4, center[1]), (center[0] - 1, center[1] + 3),
                (center[0] + 4, center[1] - 3)], 2)

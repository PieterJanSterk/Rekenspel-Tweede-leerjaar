"""
leaderboard_screen.py

The leaderboard display: separate boards for 1-player and 2-player,
each filterable by time period (today / this week / this month / this
year / all time), shown as a 5-column table (rank, name, score,
pogingen, date).

Exercise-type + table filtering, top-left: two rows of ten checkboxes,
one row per table for "x" (multiplication), one for ":" (division).
Checking a table in only one row shows that pure board; checking the
SAME table in both rows shows its "Gemengd" (mixed) board - that's the
only way a kid's actual Gemengd practice (which mixes both operations
across the same tables) maps onto this grid. Defaults to reconstructing
whatever combination was just played, so finishing an exercise
immediately shows its own board; the player can explore others with a
few clicks, and the next match replaces this with its own combination
again (this screen is rebuilt fresh each time, so nothing "sticks").

A small gear icon in the corner - deliberately small and off to the
side so it doesn't get hit by accident during normal play - opens a
settings overlay where a single entry can be deleted (for the
occasional cheated score) or the whole board wiped. Both actions
require a separate confirmation click before anything actually happens.
"""

import pygame
from theme import SIGNAL_GREEN, TAB_BLUE
import leaderboard
from i18n import t, exercise_lines, exercise_label
from keuzescherm import (GAMES, game_label, DEFAULT_EXERCISES, MODE_TAFELS, MODE_PLUSMIN,
                         mode_title)
from chip_panel import ChipPanel
from exercises import EXERCISE_BY_KEY, EXERCISE_TYPES, valid_keys
from leaderboard import format_time   # shared with the name-entry screen

# Period tabs: (id, language-file key). The ids are internal; the text is looked up
# when drawn, so it follows the language.
PERIODS = [("day", "board.period.day"), ("week", "board.period.week"),
           ("month", "board.period.month"), ("year", "board.period.year"),
           ("all", "board.period.all")]

# What the score column is called per game (language-file keys).
SCORE_COLUMN_KEYS = {"klok": "board.col.points", "ballon": "board.col.points",
                     "hoeden": "board.col.score", "memory": "board.col.turns"}


def score_column_label(game):
    return t(SCORE_COLUMN_KEYS.get(game, "board.col.points"))

# Games whose rows also show the hidden timer (see memory.py and hoeden.py).
TIME_COLUMN_GAMES = {"memory", "hoeden"}

# Unit word after the score in the admin overlay's one-line rows (language-file keys).
SCORE_UNIT_KEYS = {"memory": "board.unit.turns"}


def fit_text(font, text, max_width):
    """text unchanged if it fits max_width pixels, else cut with "..." -
    co-op Memory names ("Jan & Sam") can be up to 27 characters."""
    if font.size(text)[0] <= max_width:
        return text
    while text and font.size(text + "...")[0] > max_width:
        text = text[:-1]
    return text.rstrip() + "..."

# Fixed (dark_pair, light_pair) per themed slot - see theme.py. Active-
# tab highlights, the filter checkboxes, the gear icon, and the settings
# overlay are deliberately left out of theming for the same reasons as
# keuzescherm.py and klok.py: they're either semantic "this is selected"
# signals or an admin screen that doesn't need to be colorful.
_BACKGROUND = ((25, 30, 45), (255, 255, 255)), ((235, 238, 245), (20, 20, 30))
_INACTIVE_TAB = ((70, 70, 90), (255, 255, 255)), ((210, 212, 225), (20, 20, 30))


class LeaderboardScreen:
    def __init__(self, screen_w, screen_h, initial_mode="1", sound_bank=None,
                 leaderboard_path=None, initial_tables=None, initial_som_type=None,
                 theme=None, game="klok", initial_content=MODE_TAFELS,
                 initial_exercises=None):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.sound_bank = sound_bank
        self.theme = theme
        self._page_text = (255, 255, 255)   # replaced on every draw() with the page's real text color
        # Which minigame's board this is - Klok's and Ballon's scores
        # aren't comparable (different scoring models entirely), so this
        # screen only ever shows the one just played. No in-UI way to
        # switch games here yet; that'd be a reasonable future addition
        # if wanted, but out of scope for now.
        self.game = game
        self.mode = initial_mode          # "1" or "2"
        self.period = "all"
        self.done = False                 # set True when "Verder" is clicked
        # Explicit path makes this testable in isolation; production code
        # just leaves this as None and gets the real leaderboard.json.
        self.leaderboard_path = leaderboard_path or leaderboard.DEFAULT_PATH

        # Two independent sets of checked tables, one per operation row.
        # Initialized to reconstruct exactly what was just played: pure
        # Keer -> only the x-row checked; pure Gedeeld door -> only the
        # div-row; Gemengd -> the SAME tables checked in both rows (since
        # that's the convention this grid uses to mean "mixed").
        initial_tables = set(initial_tables) if initial_tables else set()
        if initial_som_type == "Gedeeld door (:)":
            self.filter_x_tables = set()
            self.filter_div_tables = set(initial_tables)
        elif initial_som_type == "Gemengd":
            self.filter_x_tables = set(initial_tables)
            self.filter_div_tables = set(initial_tables)
        elif initial_som_type == "Keer (x)":
            self.filter_x_tables = set(initial_tables)
            self.filter_div_tables = set()
        else:
            # No match context (e.g. constructed standalone) - a
            # reasonable fallback rather than showing nothing.
            self.filter_x_tables = set(range(1, 11))
            self.filter_div_tables = set()

        # Tafels or Plus en min: which kind of board this is. Tafels boards are
        # picked with the checkbox grid above; Plus en min boards with the
        # "Oefeningen" overlay (the same chips as the selection screen).
        self.content = initial_content if initial_content in (MODE_TAFELS, MODE_PLUSMIN) \
            else MODE_TAFELS
        self.filter_exercises = set(valid_keys(initial_exercises)) if initial_exercises \
            else set(DEFAULT_EXERCISES)
        self.filter_open = False          # the exercise-chip overlay

        self.settings_open = False
        self.confirm_delete_id = None     # entry id pending delete confirmation
        self.confirm_reset = False        # reset pending confirmation

        self.font_title = pygame.font.SysFont("arial", 40, bold=True)
        self.font_tab = pygame.font.SysFont("arial", 24, bold=True)
        self.font_row = pygame.font.SysFont("arial", 22)
        self.font_header = pygame.font.SysFont("arial", 22, bold=True)
        self.font_small = pygame.font.SysFont("arial", 18)
        self.font_filter = pygame.font.SysFont("arial", 16, bold=True)
        self.font_filter_label = pygame.font.SysFont("arial", 14)
        self.font_overlay_title = pygame.font.SysFont("arial", 30, bold=True)
        self.font_content_tab = pygame.font.SysFont("arial", 18, bold=True)
        self.font_exercise_button = pygame.font.SysFont("arial", 20, bold=True)

        self._layout()

    def _layout(self):
        # Game tabs - top row, since which game's board you're looking
        # at is the broadest choice, with mode and period narrowing
        # further underneath it. Built from GAMES (shared with
        # Keuzescherm) so a new game is one entry in one place, and sized
        # to span the same 440px as the mode tabs below it.
        gap = 10
        tab_w = (440 - gap * (len(GAMES) - 1)) // len(GAMES)
        # ... unless a game's name (in this language) needs more room than that.
        tab_w = max(tab_w, max(self.font_tab.size(game_label(g))[0] for g in GAMES) + 24)
        total_w = tab_w * len(GAMES) + gap * (len(GAMES) - 1)
        game_start_x = self.screen_w // 2 - total_w // 2
        self.game_rects = {
            game_key: pygame.Rect(game_start_x + i * (tab_w + gap), 66, tab_w, 40)
            for i, game_key in enumerate(GAMES)
        }

        # Mode tabs (1 speler / 2 spelers)
        self.mode_rects = {
            "1": pygame.Rect(self.screen_w // 2 - 220, 116, 210, 44),
            "2": pygame.Rect(self.screen_w // 2 + 10, 116, 210, 44),
        }

        # Period tabs
        period_w = 150
        total_w = period_w * len(PERIODS) + 10 * (len(PERIODS) - 1)
        start_x = (self.screen_w - total_w) // 2
        self.period_rects = {}
        for i, (key, _) in enumerate(PERIODS):
            x = start_x + i * (period_w + 10)
            self.period_rects[key] = pygame.Rect(x, 174, period_w, 40)

        # Table area
        self.table_top = 228
        self.row_height = 34

        # Gear icon - small, top-right corner, away from everything else
        self.gear_rect = pygame.Rect(self.screen_w - 56, 16, 40, 40)

        # Exercise-type + table filter grid, top-LEFT corner (mirrors the
        # gear icon on the right): one row of ten checkboxes for "x",
        # one row for ":" - small since this is a secondary control, not
        # the main setup screen.
        self.filter_x_rects = {}
        self.filter_div_rects = {}
        box_size, gap = 26, 4
        label_w = 20
        start_x = 16 + label_w + gap
        for i in range(10):
            table_num = i + 1
            x = start_x + i * (box_size + gap)
            self.filter_x_rects[table_num] = pygame.Rect(x, 16, box_size, box_size)
            self.filter_div_rects[table_num] = pygame.Rect(
                x, 16 + box_size + gap, box_size, box_size)

        # Tafels | Plus en min switch, top-right, left of the gear.
        seg_h, seg_gap = 44, 4
        widths = {key: max(96, self.font_content_tab.size(mode_title(key))[0] + 28)
                  for key in (MODE_TAFELS, MODE_PLUSMIN)}
        right = self.gear_rect.left - 14
        self.content_rects = {}
        for key in (MODE_PLUSMIN, MODE_TAFELS):
            self.content_rects[key] = pygame.Rect(right - widths[key], 16, widths[key], seg_h)
            right -= widths[key] + seg_gap

        # Plus en min: ONE button top-left instead of the 2x10 grid (which could
        # never hold 23 labelled boxes), plus a caption naming what is ticked.
        button_text_w = self.font_exercise_button.size(
            t("board.exercises.button", n=len(EXERCISE_TYPES)))[0]
        self.exercise_button_rect = pygame.Rect(16, 16, max(300, button_text_w + 14 + 44), 44)

        # The overlay with the chips: a panel in the middle, "Klaar" at its foot.
        panel_w = 800
        panel_left = (self.screen_w - panel_w) // 2
        panel_top = 56
        self.overlay_chips = ChipPanel(panel_left + 28, panel_left + panel_w - 28, panel_top + 62)
        panel_h = self.overlay_chips.bottom - panel_top + 14 + 52 + 16
        self.overlay_rect = pygame.Rect(panel_left, panel_top, panel_w, panel_h)
        self.overlay_done_rect = pygame.Rect(0, 0, 200, 52)
        self.overlay_done_rect.midbottom = (self.overlay_rect.centerx, self.overlay_rect.bottom - 16)

        # "Verder" (continue) button
        self.continue_rect = pygame.Rect(
            self.screen_w // 2 - 100, self.screen_h - 70, 200, 50)

    def _effective_filter(self):
        """Turns the two checked-table sets into the single (tables,
        som_type) pair the stored data actually uses - see the module
        docstring for the both-rows-checked-means-Gemengd convention."""
        x_set, d_set = self.filter_x_tables, self.filter_div_tables
        if x_set and d_set:
            return sorted(x_set | d_set), "Gemengd"
        if x_set:
            return sorted(x_set), "Keer (x)"
        if d_set:
            return sorted(d_set), "Gedeeld door (:)"
        return [], None  # nothing checked - shows nothing, not "everything"

    def _columns(self):
        """[(header, x, max_text_width or None)] for the current game.
        Games with a hidden timer (Memory, Hoeden) get a Tijd column and a
        wider Naam column (joined co-op names); the others keep their
        original layout. The x positions are the usual ones, pushed to the
        right where a header in this language is too long for its slot."""
        cx = self.screen_w // 2
        if self.game in TIME_COLUMN_GAMES:
            columns = [("#", cx - 440, None),
                       (t("board.col.name"), cx - 390, 330),
                       (score_column_label(self.game), cx - 40, None),
                       (t("board.col.time"), cx + 80, None),
                       (t("board.col.attempts"), cx + 170, None),
                       (t("board.col.date"), cx + 300, None)]
        else:
            columns = [("#", cx - 420, None),
                       (t("board.col.name"), cx - 340, None),
                       (score_column_label(self.game), cx - 100, None),
                       (t("board.col.attempts"), cx + 20, None),
                       (t("board.col.date"), cx + 260, None)]
        # The number and the name stay put (the name column is the wide one);
        # every column after them keeps at least 24 px behind the previous header.
        spread = columns[:2]
        for header, x, max_w in columns[2:]:
            prev_header, prev_x, _ = spread[-1]
            x = max(x, prev_x + self.font_header.size(prev_header)[0] + 24)
            spread.append((header, x, max_w))
        return spread

    def _row_values(self, index, entry):
        values = [str(index + 1), entry["name"], str(entry["score"])]
        if self.game in TIME_COLUMN_GAMES:
            values.append(format_time(entry.get("time_ms")))
        values.append(str(entry.get("attempts", 1)))
        values.append(entry["date"].split("T")[0])
        return values

    def _entries(self):
        # unique_names=True: a kid who plays the same combination ten
        # times shows up once, with their best score - the settings
        # overlay's own lookups (below) deliberately skip this, so every
        # individual attempt stays visible there for deleting a
        # specific cheated run.
        if self.content == MODE_PLUSMIN:
            if not self.filter_exercises:
                return []                 # nothing ticked shows nothing, not everything
            return leaderboard.top(10, mode=self.mode, game=self.game, period=self.period,
                                   exercises=sorted(self.filter_exercises),
                                   unique_names=True, path=self.leaderboard_path)
        tables, som_type = self._effective_filter()
        return leaderboard.top(10, mode=self.mode, game=self.game, period=self.period,
                                tables=tables, som_type=som_type,
                                unique_names=True, path=self.leaderboard_path)

    def _exercise_caption(self, max_width):
        """What is ticked, as text under the Oefeningen button, cut to fit."""
        labels = [exercise_label(et) for et in EXERCISE_TYPES if et.key in self.filter_exercises]
        if not labels:
            return t("board.exercises.none")
        return fit_text(self.font_filter_label, ", ".join(labels), max_width)

    def _click_sound(self):
        if self.sound_bank:
            self.sound_bank.play_click()

    def _handle_filter_click(self, pos):
        """The chip overlay is open: chips toggle, Klaar closes. Everything
        else is ignored (the overlay is modal, like the admin one)."""
        key = self.overlay_chips.key_at(pos)
        if key is not None:
            if key in self.filter_exercises:
                self.filter_exercises.remove(key)
            else:
                self.filter_exercises.add(key)
            self._click_sound()
        elif self.overlay_done_rect.collidepoint(pos):
            self.filter_open = False
            self._click_sound()

    def _handle_click(self, pos):
        if self.settings_open:
            self._handle_settings_click(pos)
            return
        if self.filter_open:
            self._handle_filter_click(pos)
            return

        for content_key, rect in self.content_rects.items():
            if rect.collidepoint(pos):
                self.content = content_key
                self._click_sound()
                return

        if self.content == MODE_PLUSMIN:
            if self.exercise_button_rect.collidepoint(pos):
                self.filter_open = True
                self._click_sound()
                return
        else:
            for table_num, rect in self.filter_x_rects.items():
                if rect.collidepoint(pos):
                    if table_num in self.filter_x_tables:
                        self.filter_x_tables.remove(table_num)
                    else:
                        self.filter_x_tables.add(table_num)
                    self._click_sound()
                    return

            for table_num, rect in self.filter_div_rects.items():
                if rect.collidepoint(pos):
                    if table_num in self.filter_div_tables:
                        self.filter_div_tables.remove(table_num)
                    else:
                        self.filter_div_tables.add(table_num)
                    self._click_sound()
                    return

        for game_key, rect in self.game_rects.items():
            if rect.collidepoint(pos):
                self.game = game_key
                self._click_sound()
                return

        for mode_key, rect in self.mode_rects.items():
            if rect.collidepoint(pos):
                self.mode = mode_key
                self._click_sound()
                return

        for period_key, rect in self.period_rects.items():
            if rect.collidepoint(pos):
                self.period = period_key
                self._click_sound()
                return

        if self.gear_rect.collidepoint(pos):
            self.settings_open = True
            self._click_sound()
            return

        if self.continue_rect.collidepoint(pos):
            self._click_sound()
            self.done = True
            return

    def _handle_settings_click(self, pos):
        close_rect = pygame.Rect(self.screen_w // 2 - 90, self.screen_h - 80, 180, 50)
        reset_rect = pygame.Rect(self.screen_w // 2 - 140, self.screen_h - 150, 280, 50)

        if self.confirm_delete_id is not None:
            yes_rect, no_rect = self._confirm_button_rects()
            if yes_rect.collidepoint(pos):
                leaderboard.delete_entry(self.confirm_delete_id, path=self.leaderboard_path)
                self.confirm_delete_id = None
                self._click_sound()
            elif no_rect.collidepoint(pos):
                self.confirm_delete_id = None
                self._click_sound()
            return

        if self.confirm_reset:
            yes_rect, no_rect = self._confirm_button_rects()
            if yes_rect.collidepoint(pos):
                leaderboard.reset_all(mode=self.mode, game=self.game, path=self.leaderboard_path)
                self.confirm_reset = False
                self._click_sound()
            elif no_rect.collidepoint(pos):
                self.confirm_reset = False
                self._click_sound()
            return

        # Per-entry delete buttons
        entries = leaderboard.top(20, mode=self.mode, game=self.game, period="all", path=self.leaderboard_path)
        for i, entry in enumerate(entries):
            row_y = 230 + i * 30
            del_rect = pygame.Rect(self.screen_w - 120, row_y, 90, 26)
            if del_rect.collidepoint(pos):
                self.confirm_delete_id = entry["id"]
                self._click_sound()
                return

        if reset_rect.collidepoint(pos):
            self.confirm_reset = True
            self._click_sound()
            return

        if close_rect.collidepoint(pos):
            self.settings_open = False
            self._click_sound()
            return

    def _admin_row_text(self, entry):
        """One line per stored attempt in the admin overlay."""
        date = entry["date"].split("T")[0]
        unit = t(SCORE_UNIT_KEYS.get(self.game, "board.unit.points"))
        if self.game in TIME_COLUMN_GAMES:
            return t("board.admin.row_time", name=entry["name"], score=entry["score"],
                     unit=unit, time=format_time(entry.get("time_ms")), date=date)
        return t("board.admin.row", name=entry["name"], score=entry["score"],
                 unit=unit, date=date)

    def _confirm_button_rects(self):
        yes_rect = pygame.Rect(self.screen_w // 2 - 130, self.screen_h // 2 + 30, 120, 50)
        no_rect = pygame.Rect(self.screen_w // 2 + 10, self.screen_h // 2 + 30, 120, 50)
        return yes_rect, no_rect

    def update(self, cursors):
        for cursor in cursors:
            if cursor.fired:
                self._handle_click((cursor.x, cursor.y))

    def _draw_filter_row(self, screen, rects, selected_set, row_label):
        """One operation row of the filter grid - same green-selected /
        grey-with-cross convention as Keuzescherm, just smaller since
        this is a secondary control here."""
        for table_num, rect in rects.items():
            selected = table_num in selected_set
            color = SIGNAL_GREEN if selected else (70, 70, 90)
            pygame.draw.rect(screen, color, rect, border_radius=5)
            # (Unselected cells are dark (70,70,90): their numbers need >= 4.5:1,
            # which (190,190,200) gives.)
            label = self.font_filter.render(str(table_num), True,
                                             (255, 255, 255) if selected else (190, 190, 200))
            screen.blit(label, label.get_rect(center=rect.center))
            if not selected:
                pygame.draw.line(screen, (200, 60, 60), rect.topleft, rect.bottomright, 2)
                pygame.draw.line(screen, (200, 60, 60), rect.topright, rect.bottomleft, 2)

        # Row label ("x" / ":") to the left of its row of boxes.
        any_rect = next(iter(rects.values()))
        # The "x" / ":" sit directly on the PAGE, so they use the page's text
        # color (a fixed light grey vanished on the light theme).
        label_surf = self.font_filter.render(row_label, True, self._page_text)
        screen.blit(label_surf, label_surf.get_rect(
            center=(16 + 8, any_rect.centery)))

    def _draw_content_switch(self, screen, inactive):
        """Tafels | Plus en min, top-right: which kind of board this is."""
        inactive_color, inactive_text = inactive
        for key, rect in self.content_rects.items():
            active = key == self.content
            color, text_color = (TAB_BLUE, (255, 255, 255)) if active \
                else (inactive_color, inactive_text)
            pygame.draw.rect(screen, color, rect, border_radius=8)
            label = self.font_content_tab.render(mode_title(key), True, text_color)
            screen.blit(label, label.get_rect(center=rect.center))

    def _draw_exercise_button(self, screen, inactive):
        """Plus en min's filter: one button ("Oefeningen: 4 gekozen" + a small
        triangle, drawn - not a glyph) and a caption of what is ticked."""
        color, text_color = inactive
        rect = self.exercise_button_rect
        pygame.draw.rect(screen, color, rect, border_radius=10)
        pygame.draw.rect(screen, (90, 90, 120), rect, 2, border_radius=10)
        text = t("board.exercises.button", n=len(self.filter_exercises))
        label = self.font_exercise_button.render(text, True, text_color)
        screen.blit(label, label.get_rect(midleft=(rect.left + 14, rect.centery)))
        tx, ty = rect.right - 22, rect.centery
        pygame.draw.polygon(screen, text_color, [(tx - 7, ty - 4), (tx + 7, ty - 4), (tx, ty + 6)])
        caption = self.font_filter_label.render(
            self._exercise_caption(rect.w + 30), True, self._page_text)
        screen.blit(caption, (rect.left + 2, rect.bottom + 6))

    def _draw_filter_overlay(self, screen, page_bg, page_text):
        """The modal chip overlay: same chips as the selection screen."""
        dim = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 170))
        screen.blit(dim, (0, 0))
        pygame.draw.rect(screen, page_bg, self.overlay_rect, border_radius=16)
        pygame.draw.rect(screen, (90, 90, 120), self.overlay_rect, 3, border_radius=16)
        title = self.font_overlay_title.render(t("board.exercises.title"), True, page_text)
        screen.blit(title, title.get_rect(midtop=(self.overlay_rect.centerx, self.overlay_rect.top + 14)))
        self.overlay_chips.draw(screen, self.filter_exercises, self.theme, page_bg, page_text)
        pygame.draw.rect(screen, SIGNAL_GREEN, self.overlay_done_rect, border_radius=12)
        done = self.font_tab.render(t("common.done"), True, (255, 255, 255))
        screen.blit(done, done.get_rect(center=self.overlay_done_rect.center))

    def _draw_filter_panel(self, screen):
        if self.content == MODE_PLUSMIN:
            inactive = self.theme.get("lb_inactive_tab", *_INACTIVE_TAB) \
                if self.theme else _INACTIVE_TAB[0]
            self._draw_exercise_button(screen, inactive)
            return
        # The two rows are labelled with the language's multiplication and
        # division signs (Dutch "x" / ":", English "×" / "÷").
        self._draw_filter_row(screen, self.filter_x_rects, self.filter_x_tables,
                              t("symbol.times"))
        self._draw_filter_row(screen, self.filter_div_rects, self.filter_div_tables,
                              t("symbol.divide"))

        caption_y = max(r.bottom for r in self.filter_div_rects.values()) + 4
        caption = self.font_filter_label.render(
            t("board.filter.hint"), True, self._page_text)
        screen.blit(caption, (16, caption_y))

    def _draw_gear_icon(self, screen, center, radius):
        import math
        cx, cy = center
        # Background disc
        pygame.draw.circle(screen, (80, 80, 100), center, radius + 6)
        pygame.draw.circle(screen, (150, 150, 170), center, radius + 6, 2)
        # Teeth: small rectangles pointing outward at regular angles
        tooth_count = 8
        for i in range(tooth_count):
            angle = (2 * math.pi / tooth_count) * i
            tx = cx + math.cos(angle) * radius
            ty = cy + math.sin(angle) * radius
            tooth_rect = pygame.Rect(0, 0, 6, 6)
            tooth_rect.center = (tx, ty)
            pygame.draw.rect(screen, (220, 220, 230), tooth_rect)
        # Body + center hole
        pygame.draw.circle(screen, (220, 220, 230), center, radius - 4)
        pygame.draw.circle(screen, (80, 80, 100), center, radius - 10)

    def draw(self, screen):
        bg_color, bg_text = self.theme.get("background", *_BACKGROUND) \
            if self.theme else _BACKGROUND[0]
        screen.fill(bg_color)
        # Remembered so the helper that draws the filter labels (which sit
        # straight on the page) can use the page's text color.
        self._page_text = bg_text

        title = self.font_title.render(t("board.title"), True, bg_text)
        screen.blit(title, title.get_rect(centerx=self.screen_w // 2, y=16))

        inactive_color, inactive_text = self.theme.get("lb_inactive_tab", *_INACTIVE_TAB) \
            if self.theme else _INACTIVE_TAB[0]

        for game_key, rect in self.game_rects.items():
            active = game_key == self.game
            color, text_color = (SIGNAL_GREEN, (255, 255, 255)) if active \
                else (inactive_color, inactive_text)
            pygame.draw.rect(screen, color, rect, border_radius=8)
            label = self.font_tab.render(
                game_label(game_key), True, text_color)
            screen.blit(label, label.get_rect(center=rect.center))

        for mode_key, rect in self.mode_rects.items():
            active = mode_key == self.mode
            # Active = fixed green signal color; inactive = themed neutral.
            color, text_color = (SIGNAL_GREEN, (255, 255, 255)) if active \
                else (inactive_color, inactive_text)
            pygame.draw.rect(screen, color, rect, border_radius=8)
            label = self.font_tab.render(
                t("choice.players.one") if mode_key == "1" else t("choice.players.two"),
                True, text_color)
            screen.blit(label, label.get_rect(center=rect.center))

        for period_key, rect in self.period_rects.items():
            active = period_key == self.period
            color, text_color = (TAB_BLUE, (255, 255, 255)) if active \
                else (inactive_color, inactive_text)
            pygame.draw.rect(screen, color, rect, border_radius=8)
            label_text = t(next(lbl for key, lbl in PERIODS if key == period_key))
            label = self.font_small.render(label_text, True, text_color)
            screen.blit(label, label.get_rect(center=rect.center))

        self._draw_filter_panel(screen)
        self._draw_content_switch(screen, (inactive_color, inactive_text))

        # Table header
        columns = self._columns()
        for header, x, _max_w in columns:
            label = self.font_header.render(header, True, bg_text)
            screen.blit(label, (x, self.table_top))

        entries = self._entries()
        for i, entry in enumerate(entries):
            y = self.table_top + 34 + i * self.row_height
            values = self._row_values(i, entry)
            for (_header, x, max_w), v in zip(columns, values):
                if max_w is not None:
                    v = fit_text(self.font_row, v, max_w)
                label = self.font_row.render(v, True, bg_text)
                screen.blit(label, (x, y))

        if not entries:
            empty = self.font_row.render(t("board.empty"), True, bg_text)
            screen.blit(empty, empty.get_rect(centerx=self.screen_w // 2,
                                               y=self.table_top + 60))

        # Gear icon (settings) - drawn as actual shapes rather than a
        # Unicode glyph, since not every font/platform has a gear
        # character and a missing glyph renders as an ugly box.
        self._draw_gear_icon(screen, self.gear_rect.center, 16)

        pygame.draw.rect(screen, SIGNAL_GREEN, self.continue_rect, border_radius=10)
        continue_label = self.font_tab.render(t("board.continue"), True, (255, 255, 255))
        screen.blit(continue_label, continue_label.get_rect(center=self.continue_rect.center))

        if self.filter_open:
            self._draw_filter_overlay(screen, bg_color, bg_text)

        if self.settings_open:
            self._draw_settings(screen)

    def _draw_settings(self, screen):
        overlay = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        overlay.fill((10, 10, 18, 240))
        screen.blit(overlay, (0, 0))

        players = t("choice.players.one") if self.mode == "1" else t("choice.players.two")
        title = self.font_title.render(
            t("board.admin.title", game=game_label(self.game), players=players),
            True, (255, 255, 255))
        screen.blit(title, title.get_rect(centerx=self.screen_w // 2, y=20))

        entries = leaderboard.top(20, mode=self.mode, game=self.game, period="all", path=self.leaderboard_path)
        for i, entry in enumerate(entries):
            row_y = 230 + i * 30
            row_text = self._admin_row_text(entry)
            label = self.font_small.render(row_text, True, (220, 220, 230))
            screen.blit(label, (self.screen_w // 2 - 380, row_y))

            del_rect = pygame.Rect(self.screen_w - 120, row_y, 90, 26)
            pygame.draw.rect(screen, (170, 60, 60), del_rect, border_radius=6)
            del_label = self.font_small.render(t("board.admin.delete"), True, (255, 255, 255))
            screen.blit(del_label, del_label.get_rect(center=del_rect.center))

        reset_rect = pygame.Rect(self.screen_w // 2 - 140, self.screen_h - 150, 280, 50)
        pygame.draw.rect(screen, (170, 60, 60), reset_rect, border_radius=10)
        reset_label = self.font_tab.render(t("board.admin.reset"), True, (255, 255, 255))
        screen.blit(reset_label, reset_label.get_rect(center=reset_rect.center))

        close_rect = pygame.Rect(self.screen_w // 2 - 90, self.screen_h - 80, 180, 50)
        pygame.draw.rect(screen, (70, 70, 90), close_rect, border_radius=10)
        close_label = self.font_tab.render(t("board.admin.close"), True, (255, 255, 255))
        screen.blit(close_label, close_label.get_rect(center=close_rect.center))

        if self.confirm_delete_id is not None or self.confirm_reset:
            self._draw_confirm(screen)

    def _draw_confirm(self, screen):
        box = pygame.Rect(self.screen_w // 2 - 220, self.screen_h // 2 - 80, 440, 220)
        pygame.draw.rect(screen, (40, 40, 60), box, border_radius=12)
        pygame.draw.rect(screen, (200, 200, 220), box, 2, border_radius=12)

        if self.confirm_reset:
            msg = t("board.confirm.reset")
        else:
            msg = t("board.confirm.delete")
        label = self.font_tab.render(msg, True, (255, 255, 255))
        screen.blit(label, label.get_rect(centerx=self.screen_w // 2, y=box.y + 30))
        warn = self.font_small.render(t("board.confirm.warning"),
                                       True, (220, 160, 160))
        screen.blit(warn, warn.get_rect(centerx=self.screen_w // 2, y=box.y + 70))

        yes_rect, no_rect = self._confirm_button_rects()
        pygame.draw.rect(screen, (170, 60, 60), yes_rect, border_radius=8)
        pygame.draw.rect(screen, (70, 70, 90), no_rect, border_radius=8)
        yes_label = self.font_tab.render(t("board.confirm.yes"), True, (255, 255, 255))
        no_label = self.font_tab.render(t("board.confirm.no"), True, (255, 255, 255))
        screen.blit(yes_label, yes_label.get_rect(center=yes_rect.center))
        screen.blit(no_label, no_label.get_rect(center=no_rect.center))

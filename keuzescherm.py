"""
keuzescherm.py

The exercise-selection screen, rebuilt from the original SWF's logic
(the "Keuzescherm" frame). This is deliberately its own module with no
knowledge of Klok/Ballon/etc - every minigame is handed the result
(which tables, which exercise type, sound on/off) and takes it from there.
That's what makes "add Keuzescherm to every game" easy: build a game once,
point it at THIS screen first, done.

Faithful to the original:
  - 10 toggle buttons, one per table (1 t/m 10). Any combination can be
    selected. An unselected table shows a cross (matches the original
    "Kruis" cross-mark + dimmed button behaviour).
  - A "sum type" selector you cycle through with a click (matches
    "SomType" / "OmschrijvingSomType" in the original).
  - A sound on/off toggle with a drawn speaker icon (see icons.py) that
    shows a cross when muted, so on/off is visible from the picture alone.
  - The start button is only enabled once at least one table is selected
    (matches "LaatsteTafel" gating "Cirkelstartknop" in the original).
  - Table tiles and the speaker are drawn in code rather than loaded from
    pictures extracted from the Flash movie, which looked dated.

Under the title ("Tafels") a small hint says tiles can be clicked to switch;
under Start a small line reminds that F11 is full screen. Bottom-left: the
theme button with, directly under it, a Scorebord button that opens the
leaderboard without having to play first (main.py watches
`leaderboard_requested`).

GAME CHOICE: four large tiles, two on the left and two on the right of the
table grid, each with a picture drawn in code (stopwatch = Klok, balloon =
Ballon, top hat = Hoeden, question-mark card = Memory) and the game's name
underneath. One click selects a game; the selected tile turns the same
blue as a selected table, gets a thick outline and a check mark (so it is
not "color only"). Picture and name colors are checked for WCAG contrast
against the tile they sit on.

Theme button, bottom-left corner (see theme.py): cycles dark -> light ->
regenboog -> dark. Selected/cross colors (blue/red) and the green "on"
and "go" buttons stay fixed in every mode since they carry meaning a kid
relies on - only the background, plain neutral buttons (sum type,
players) and the UNSELECTED table tiles change color. Every signal color
is dark enough for white text to clear WCAG AA contrast (see theme.py).

Either player's cursor can interact with this screen - it's a shared
setup step before the two-player game begins, same as the original was
a shared setup step before single-player play.
"""

import os
import paths
import i18n
from i18n import t
import json
import pygame
import icons
from theme import (MODE_LABEL_KEYS, mode_label, SIGNAL_GREEN, TILE_BLUE, contrast_ratio,
                   best_text_color)
from exercises import EXERCISE_BY_KEY, GROUPS, valid_keys
from chip_panel import (ChipPanel, fill_button, BUTTON_EDGE_CONTRAST, CHIPS_PER_ROW,  # noqa: F401
                        CHIP_H, CHIP_GAP, CHIP_ROW_GAP, CHIP_GUTTER, GROUP_HEAD_H, GROUP_GAP)

# Internal ids of the exercise kinds: these exact strings are what is SAVED in
# settings.json and on the leaderboard, so they never change. What the player
# sees comes from the language file (som_label).
SOM_TYPES = ["Keer (x)", "Gedeeld door (:)", "Gemengd"]
SOM_LABEL_KEYS = {"Keer (x)": "som.keer", "Gedeeld door (:)": "som.gedeeld",
                  "Gemengd": "som.gemengd"}


def som_label(som_type):
    return t(SOM_LABEL_KEYS[som_type]) if som_type in SOM_LABEL_KEYS else som_type

# Order the game button cycles through, and its label for each. Adding
# a future game is just one more entry here.
GAMES = ["klok", "ballon", "hoeden", "memory"]
# Keys into the language files (lang/*.json) for each game's name; use
# game_label(game) to get the text in the current language.
GAME_LABEL_KEYS = {"klok": "game.klok", "ballon": "game.ballon", "hoeden": "game.hoeden",
                   "memory": "game.memory"}


def game_label(game):
    """A game's name in the current language ("Klok" / "Clock")."""
    return t(GAME_LABEL_KEYS[game]) if game in GAME_LABEL_KEYS else game

# (BUTTON_EDGE_CONTRAST - when a button gets a page-colored outline - lives in chip_panel.py.)

# The two things the games can practise. The title at the top is a button
# that switches between them; the settings remember the last one used.
MODE_TAFELS, MODE_PLUSMIN = "tafels", "plusmin"
MODES = (MODE_TAFELS, MODE_PLUSMIN)
MODE_TITLE_KEYS = {MODE_TAFELS: "choice.title.tafels", MODE_PLUSMIN: "choice.title.plusmin"}


def mode_title(mode):
    """The title button's text for a mode, in the current language."""
    return t(MODE_TITLE_KEYS[mode])
# What is stored as "som_type" for plus/min results (the tables modes store
# "Keer (x)" etc.) - see leaderboard.py.
PLUSMIN_SOM_TYPE = "Plus en min"
# Ticked the first time ever you open Plus en min: the two easiest types.
DEFAULT_EXERCISES = ["e_plus_e_to10_zb", "e_minus_e_to10_zb"]


# --- game tiles (left/right of the table grid) ---
# Narrower than before so the strip between the two tile columns is wide
# enough for the exercise chips of Plus en min; the same in both modes so
# nothing jumps when you switch.
GAME_TILE_W, GAME_TILE_H = 220, 240
GAME_TILE_GAP = 24           # vertical gap between the two tiles in a column
GAME_TILE_TOP = 130
GAME_TILE_SIDE_MARGIN = 65   # distance from the screen edge
CONTENT_PAD = 12             # between a tile column and the content strip

# --- the content strip between the tile columns ---
TITLE_TOP = 28               # the title button
TITLE_ARROW_SPACE = 64       # room for the < > arrows left and right of the title
PANEL_TOP = 122              # where the tables grid / exercise chips start
TABLE_BTN_SIZE, TABLE_BTN_GAP, TABLE_GRID_TOP = 88, 16, 160
SOM_TYPE_Y = 408             # Keer / Gedeeld door / Gemengd button (Tafels mode)
PLAYERS_ROW_Y = 524          # players + sound, side by side (both modes)
START_Y = 590                # Start (both modes); the F11 line sits right under it

# (The Plus en min chip geometry - CHIP_H, CHIP_GAP, ... - lives in chip_panel.py.)

# Each game's picture: (icons function, size, extra arguments). Sizes are
# the picture's own aspect ratio; every picture is centered in its tile.
_GAME_ICONS = {
    "klok": (icons.stopwatch, (130, 130), {"fraction": 0.7}),
    "ballon": (icons.balloon, (96, 128), {}),
    "hoeden": (icons.hat, (150, 118), {}),
    "memory": (icons.memory_cards, (150, 128), {}),
}
# Colorful picture colors to TRY on an unselected tile, in order: a bright
# one (for dark tiles) and a deep one (for light tiles). The first with
# contrast >= 4.5:1 against the tile wins; if neither passes (e.g. the blue
# selected tile, or a random regenboog color) the picture uses the tile's
# own text color, which is guaranteed readable.
_ICON_ACCENTS = {
    "klok": [(255, 200, 70), (120, 70, 0)],
    "ballon": [(255, 165, 165), (170, 25, 25)],
    "hoeden": [(215, 190, 255), (90, 40, 160)],
    "memory": [(110, 220, 140), (0, 95, 40)],
}
ICON_MIN_CONTRAST = 4.5
# In regenboog the selected tile is the fixed blue, where only near-white
# reaches 4.5:1 - so there a picture may settle for the 3:1 WCAG asks of
# large graphics, which keeps it changing color instead of always white.
# 3.3 rather than 3.0 leaves a margin for the tiny color shifts of the scaled
# picture. Only the SELECTED tile gets this; every other picture stays at 4.5
# (on the rare random tile color where no vivid color can reach 4.5, the
# picture simply uses the tile's black/white text color).
ICON_RELAXED_CONTRAST = 3.3


def game_icon_color(game, tile_bg, tile_text):
    """Picture color for `game` on a tile of color tile_bg, WITHOUT a theme:
    a colorful accent when one is readable on it, else the tile's text color.
    (The screen itself goes through Keuzescherm.icon_color, which asks the
    theme - so in regenboog the pictures change color with every click.)"""
    for accent in _ICON_ACCENTS.get(game, []):
        if contrast_ratio(accent, tile_bg) >= ICON_MIN_CONTRAST:
            return accent
    return tile_text


# Written by the game and must survive restarts: see paths.py (matters once packaged).
SETTINGS_PATH = paths.data_path("settings.json")


def _load_settings():
    """Returns a dict of previously-saved choices, or {} if there's no
    settings file yet (first ever run) or it's unreadable for any reason -
    callers fall back to hardcoded defaults in that case."""
    if not os.path.exists(SETTINGS_PATH):
        return {}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_settings(data):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError as e:
        print(f"[keuzescherm] could not save settings: {e}")


# Fixed (dark_pair, light_pair) color pairs per themed slot. Each pair is
# (background_color, text_color) - see theme.py for how regenboog mode
# generates its own readable pairs for these same slot names.
_BACKGROUND = ((25, 30, 45), (255, 255, 255)), ((235, 238, 245), (20, 20, 30))
# Unselected table tiles: (tile, number) - light tiles, dark numbers.
_TILE_OFF = ((240, 240, 245), (30, 30, 50)), ((255, 255, 255), (30, 30, 50))
_NEUTRAL_BTN = ((70, 70, 90), (255, 255, 255)), ((210, 212, 225), (20, 20, 30))


class Keuzescherm:
    def __init__(self, screen_w, screen_h, sound_bank=None, theme=None):
        self.screen_w = screen_w
        self.screen_h = screen_h
        # Optional SoundBank (see sounds.py) - plays the real extracted
        # "klik" SFX on every button press. None is fine (silent).
        self.sound_bank = sound_bank
        # Shared Theme instance (see theme.py) - optional only so this
        # class stays testable standalone; main.py always provides one.
        self.theme = theme

        # Hardcoded defaults, used only on the very first run ever (no
        # settings.json yet) - after that, whatever was last chosen wins.
        saved = _load_settings()
        # The language is chosen here and applied for the whole app (every
        # other screen just asks i18n.t()); an unknown/missing one falls back.
        self.language = saved.get("language", i18n.DEFAULT_LANGUAGE)
        if not i18n.set_language(self.language):
            self.language = i18n.DEFAULT_LANGUAGE
            i18n.set_language(self.language)
        self.game = saved.get("game", "klok")  # one of GAMES
        if self.game not in GAMES:             # stale/hand-edited settings.json
            self.game = "klok"
        self.mode = saved.get("mode", MODE_TAFELS)
        if self.mode not in MODES:
            self.mode = MODE_TAFELS
        self.selected_tables = set(saved.get("selected_tables", list(range(1, 11))))
        # Plus en min: the ticked exercise types (keys of exercises.EXERCISE_TYPES).
        # Unknown keys (hand-edited / old settings.json) are dropped.
        self.selected_exercises = set(valid_keys(
            saved.get("selected_exercises", DEFAULT_EXERCISES)))
        self.som_type_index = saved.get("som_type_index", 0)
        self.num_players = saved.get("num_players", 1)
        self.sound_on = saved.get("sound_on", True)
        self.done = False                      # set True once Start is pressed
        # Set True when the Scorebord button is clicked; main.py reads it,
        # opens the leaderboard, and a fresh Keuzescherm replaces this one
        # afterwards (settings.json already holds the current choices).
        self.leaderboard_requested = False

        # --- shared geometry: the strip between the two tile columns ---
        self.content_x0 = GAME_TILE_SIDE_MARGIN + GAME_TILE_W + CONTENT_PAD
        self.content_x1 = screen_w - GAME_TILE_SIDE_MARGIN - GAME_TILE_W - CONTENT_PAD
        content_w = self.content_x1 - self.content_x0

        # --- Tafels mode: 10 table buttons in two rows of five ---
        self.table_buttons = {}                # table number -> pygame.Rect
        row_width = 5 * TABLE_BTN_SIZE + 4 * TABLE_BTN_GAP
        start_x = (screen_w - row_width) // 2
        for i in range(10):
            table_num = i + 1
            col, row = i % 5, i // 5
            self.table_buttons[table_num] = pygame.Rect(
                start_x + col * (TABLE_BTN_SIZE + TABLE_BTN_GAP),
                TABLE_GRID_TOP + row * (TABLE_BTN_SIZE + TABLE_BTN_GAP),
                TABLE_BTN_SIZE, TABLE_BTN_SIZE)
        self.som_type_rect = pygame.Rect(screen_w // 2 - 160, SOM_TYPE_Y, 320, 56)

        # --- Plus en min mode: the exercise chips (shared with the leaderboard) ---
        self.chip_panel = ChipPanel(self.content_x0, self.content_x1, PANEL_TOP)
        self.chip_rects = self.chip_panel.chip_rects
        self.group_heads = self.chip_panel.group_heads
        self.row_signs = self.chip_panel.row_signs
        self.panel_bottom = self.chip_panel.bottom

        # Game tiles: the first half of GAMES stacked on the left, the rest
        # on the right (with 4 games: 2 left, 2 right).
        self.game_tiles = {}                   # game key -> pygame.Rect
        per_column = (len(GAMES) + 1) // 2
        for i, game in enumerate(GAMES):
            column, row = divmod(i, per_column)
            x = (GAME_TILE_SIDE_MARGIN if column == 0
                 else screen_w - GAME_TILE_SIDE_MARGIN - GAME_TILE_W)
            y = GAME_TILE_TOP + row * (GAME_TILE_H + GAME_TILE_GAP)
            self.game_tiles[game] = pygame.Rect(x, y, GAME_TILE_W, GAME_TILE_H)

        # --- bottom block, identical in both modes: players + sound side by
        # side, then Start (the F11 line goes right under it, see below) ---
        half_w = (content_w - 12) // 2
        self.players_rect = pygame.Rect(self.content_x0, PLAYERS_ROW_Y, half_w, 52)
        self.sound_rect = pygame.Rect(self.content_x0 + half_w + 12, PLAYERS_ROW_Y, half_w, 52)
        self.start_rect = pygame.Rect(screen_w // 2 - 100, START_Y, 200, 60)

        self.font_title = pygame.font.SysFont("arial", 40, bold=True)
        self.font_btn = pygame.font.SysFont("arial", 30, bold=True)
        self.font_small = pygame.font.SysFont("arial", 22)
        self.font_theme = pygame.font.SysFont("arial", 18, bold=True)
        self.font_tile = pygame.font.SysFont("arial", 38, bold=True)

        self._layout_texts()

    def _layout_texts(self):
        """Everything whose SIZE depends on the words shown: the title button,
        the hint, the F11 line, and the three small buttons. Called at start
        and again whenever the language changes (the words, so the sizes, are
        different then). Their rects are decided here - not while drawing - so
        the layout is one place and can be checked for overlaps."""
        screen_w, screen_h = self.screen_w, self.screen_h
        # The title is a BUTTON (it switches Tafels <-> Plus en min), sized for
        # the longest title so it never changes size or position between modes.
        longest_title = max((mode_title(m) for m in MODES),
                            key=lambda text: self.font_title.size(text)[0])
        self.title_rect = pygame.Rect(
            0, 0, self.font_title.size(longest_title)[0] + 2 * TITLE_ARROW_SPACE,
            self.font_title.get_height() + 10)
        self.title_rect.midtop = (screen_w // 2, TITLE_TOP)
        self.hint_rect = pygame.Rect((0, 0), self.font_small.size(t("choice.hint")))
        self.hint_rect.midtop = (screen_w // 2, self.title_rect.bottom + 4)
        self.f11_rect = pygame.Rect((0, 0), self.font_small.size(t("choice.fullscreen")))
        self.f11_rect.midtop = (screen_w // 2, self.start_rect.bottom + 10)

        # The two corner buttons (theme bottom-left, Scorebord bottom-right):
        # one shared size that fits the LONGEST of their possible labels,
        # measured rather than guessed, so nothing can overflow whichever mode
        # or language is active - and nothing resizes while you cycle modes.
        corner_labels = [t("choice.theme", mode=mode_label(m)) for m in MODE_LABEL_KEYS] \
            + [t("choice.scoreboard")]
        corner_w = max(self.font_theme.size(text)[0] for text in corner_labels) + 32
        corner_h = 36
        corner_y = screen_h - 14 - corner_h
        self.theme_rect = pygame.Rect(16, corner_y, corner_w, corner_h)
        self.leaderboard_rect = pygame.Rect(screen_w - 16 - corner_w, corner_y, corner_w, corner_h)

        # The language button, top-right: a small globe and the language's own
        # name (always in that language, so anyone can find theirs). Sized for
        # the longest of the available names.
        names = [name for _code, name in i18n.available_languages()] or [""]
        language_w = max(self.font_theme.size(name)[0] for name in names) + 28 + 26
        self.language_rect = pygame.Rect(screen_w - 16 - language_w, 14, language_w, 36)

    def _persist(self):
        _save_settings({
            "game": self.game,
            "language": self.language,
            "mode": self.mode,
            "selected_exercises": sorted(self.selected_exercises),
            "selected_tables": sorted(self.selected_tables),
            "som_type_index": self.som_type_index,
            "num_players": self.num_players,
            "sound_on": self.sound_on,
        })

    def _handle_click(self, pos):
        for game, rect in self.game_tiles.items():
            if rect.collidepoint(pos):
                if self.sound_bank:
                    self.sound_bank.play_click()
                if game != self.game:
                    self.game = game
                    self._persist()
                return

        # The title is a button: it switches between Tafels and Plus en min.
        if self.title_rect.collidepoint(pos):
            self.mode = MODE_PLUSMIN if self.mode == MODE_TAFELS else MODE_TAFELS
            if self.sound_bank:
                self.sound_bank.play_click()
            self._persist()
            return

        # Only the controls of the CURRENT mode react (the other mode's
        # controls are not on screen).
        if self.mode == MODE_TAFELS:
            for table_num, rect in self.table_buttons.items():
                if rect.collidepoint(pos):
                    if table_num in self.selected_tables:
                        self.selected_tables.remove(table_num)
                    else:
                        self.selected_tables.add(table_num)
                    if self.sound_bank:
                        self.sound_bank.play_click()
                    self._persist()
                    return

            if self.som_type_rect.collidepoint(pos):
                self.som_type_index = (self.som_type_index + 1) % len(SOM_TYPES)
                if self.sound_bank:
                    self.sound_bank.play_click()
                self._persist()
                return
        else:
            key = self.chip_panel.key_at(pos)
            if key is not None:
                if key in self.selected_exercises:
                    self.selected_exercises.remove(key)
                else:
                    self.selected_exercises.add(key)
                if self.sound_bank:
                    self.sound_bank.play_click()
                self._persist()
                return

        if self.players_rect.collidepoint(pos):
            self.num_players = 1 if self.num_players == 2 else 2
            if self.sound_bank:
                self.sound_bank.play_click()
            self._persist()
            return

        if self.sound_rect.collidepoint(pos):
            self.sound_on = not self.sound_on
            if self.sound_bank:
                # play it regardless of the new state, so toggling OFF
                # still gives audible confirmation of the click itself
                self.sound_bank.play_click()
            self._persist()
            return

        if self.theme_rect.collidepoint(pos):
            if self.theme:
                self.theme.cycle()
            if self.sound_bank:
                self.sound_bank.play_click()
            return

        if self.leaderboard_rect.collidepoint(pos):
            if self.sound_bank:
                self.sound_bank.play_click()
            self.leaderboard_requested = True
            return

        if self.language_rect.collidepoint(pos):
            self._switch_language()
            return

        if self.start_rect.collidepoint(pos) and self._has_selection():
            if self.sound_bank:
                self.sound_bank.play_click()
            self.done = True

    def _switch_language(self):
        """Go to the next available language (nl -> en -> ... -> nl), remember it,
        and re-measure everything whose size depends on the words."""
        self.language = i18n.next_language(self.language)
        i18n.set_language(self.language)
        self._layout_texts()
        if self.sound_bank:
            self.sound_bank.play_click()
        self._persist()

    def _has_selection(self):
        """Something is ticked in the current mode, so Start may be pressed."""
        if self.mode == MODE_PLUSMIN:
            return bool(self.selected_exercises)
        return bool(self.selected_tables)

    def update(self, cursors):
        """cursors: iterable of Cursor objects (player1, player2)."""
        for cursor in cursors:
            if cursor.fired:
                self._handle_click((cursor.x, cursor.y))

    def result(self):
        """Call once .done is True to get what the player(s) picked."""
        plusmin = self.mode == MODE_PLUSMIN
        return {
            "game": self.game,
            "mode": self.mode,
            # In Plus en min there are no tables: "tables" is empty and
            # "som_type" says "Plus en min", while "exercises" lists the ticked
            # types. (Everything downstream that handles tables/som_type keeps
            # working; only the code that builds exercises looks at "exercises".)
            "tables": [] if plusmin else sorted(self.selected_tables),
            "som_type": PLUSMIN_SOM_TYPE if plusmin else SOM_TYPES[self.som_type_index],
            "exercises": sorted(self.selected_exercises) if plusmin else [],
            "num_players": self.num_players,
            "sound_on": self.sound_on,
        }

    def tile_colors(self, game):
        """(tile background, text color) for a game tile. The selected tile is
        always the same blue as a selected table; the others follow the theme
        (each its own color in regenboog)."""
        if game == self.game:
            return TILE_BLUE, (255, 255, 255)
        if self.theme:
            return self.theme.get(f"game_tile_{game}", *_NEUTRAL_BTN)
        return _NEUTRAL_BTN[0]

    def _fill_button(self, screen, color, rect, radius, page_bg, page_text,
                     base_outline=None):
        """A button/tile body that never blends into the page: see chip_panel.fill_button."""
        fill_button(screen, color, rect, radius, page_bg, page_text, base_outline)

    def icon_color(self, game, tile_bg, tile_text):
        """Color of a game's picture on a tile. Goes through the theme: dark
        and light use the readable accent (or the tile's text color), and
        regenboog picks a fresh random readable color on every click - so the
        pictures re-color along with everything else."""
        if not self.theme:
            return game_icon_color(game, tile_bg, tile_text)
        return self.theme.color_on(f"game_icon_{game}", tile_bg,
                                   _ICON_ACCENTS.get(game, []), fallback=tile_text,
                                   min_contrast=ICON_MIN_CONTRAST,
                                   relaxed_contrast=(ICON_RELAXED_CONTRAST
                                                     if game == self.game else None))

    def _draw_game_tile(self, screen, game, rect, outline_color, page_bg):
        """outline_color: the PAGE's text color - guaranteed to contrast with
        the page background (white on dark, near-black on light, readable in
        every regenboog), so the selected outline is visible in every theme."""
        selected = game == self.game
        tile_bg, tile_text = self.tile_colors(game)
        self._fill_button(screen, tile_bg, rect, 18, page_bg, outline_color,
                          base_outline=None if selected else (90, 90, 120))
        if selected:
            # Thick outline: the selection is visible from its SHAPE too, not
            # just from the blue.
            pygame.draw.rect(screen, outline_color, rect, 6, border_radius=18)

        icon_fn, icon_size, icon_kwargs = _GAME_ICONS[game]
        icon_color = self.icon_color(game, tile_bg, tile_text)
        icon = icon_fn(icon_size, icon_color, **icon_kwargs)
        icon_box = pygame.Rect(0, 0, 150, 130)
        icon_box.midtop = (rect.centerx, rect.top + 22)
        screen.blit(icon, icon.get_rect(center=icon_box.center))

        title = self.font_tile.render(game_label(game), True, tile_text)
        screen.blit(title, title.get_rect(midbottom=(rect.centerx, rect.bottom - 22)))

        if selected:
            # Check-mark badge, top-right: a second, non-color cue.
            badge_color = best_text_color(tile_bg)
            center = (rect.right - 34, rect.top + 34)
            pygame.draw.circle(screen, badge_color, center, 20)
            pygame.draw.lines(screen, tile_bg, False, [
                (center[0] - 9, center[1] + 1), (center[0] - 2, center[1] + 8),
                (center[0] + 10, center[1] - 8)], 5)

    @staticmethod
    def _draw_globe(screen, center, radius, color):
        """A tiny globe (circle, meridian, equator) drawn from shapes - a
        Unicode globe emoji would show as a box in many fonts."""
        cx, cy = center
        pygame.draw.circle(screen, color, center, radius, 2)
        pygame.draw.ellipse(screen, color, (cx - radius // 2, cy - radius, radius, 2 * radius), 2)
        pygame.draw.line(screen, color, (cx - radius, cy), (cx + radius, cy), 2)

    def _draw_language_button(self, screen, page_bg, page_text):
        """Top-right: a globe and the current language's own name; clicking it
        goes to the next language."""
        bg, text_color = self.theme.get("btn_language", *_NEUTRAL_BTN) \
            if self.theme else _NEUTRAL_BTN[0]
        rect = self.language_rect
        self._fill_button(screen, bg, rect, 8, page_bg, page_text, base_outline=(90, 90, 120))
        self._draw_globe(screen, (rect.left + 18, rect.centery), 8, text_color)
        label = self.font_theme.render(i18n.language_name(self.language), True, text_color)
        screen.blit(label, label.get_rect(midleft=(rect.left + 34, rect.centery)))

    def _draw_title_button(self, screen, page_bg, page_text):
        """The title as a button: a pill with the current mode's name and a
        small arrow on each side, to say "click me to switch"."""
        pill_bg, pill_text = self.theme.get("btn_title", *_NEUTRAL_BTN) \
            if self.theme else _NEUTRAL_BTN[0]
        self._fill_button(screen, pill_bg, self.title_rect, 16, page_bg, page_text,
                          base_outline=(90, 90, 120))
        label = self.font_title.render(mode_title(self.mode), True, pill_text)
        screen.blit(label, label.get_rect(center=self.title_rect.center))
        cy = self.title_rect.centery
        for edge_x, direction in ((self.title_rect.left + 30, -1), (self.title_rect.right - 30, 1)):
            pygame.draw.polygon(screen, pill_text, [
                (edge_x + direction * 9, cy), (edge_x - direction * 6, cy - 11),
                (edge_x - direction * 6, cy + 11)])

    def _draw_tables_panel(self, screen, bg_color, text_color):
        """Tafels mode: the 10 table buttons and the Keer/Gedeeld/Gemengd button."""
        for table_num, rect in self.table_buttons.items():
            selected = table_num in self.selected_tables
            if selected:
                tile_color, label_color = TILE_BLUE, (255, 255, 255)
                self._fill_button(screen, tile_color, rect, 12, bg_color, text_color)
            else:
                # Unselected: a themed tile (its own color each in
                # regenboog), outlined so it reads on any background.
                tile_color, label_color = self.theme.get(
                    f"table_off_{table_num}", *_TILE_OFF) if self.theme else _TILE_OFF[0]
                self._fill_button(screen, tile_color, rect, 12, bg_color, text_color,
                                  base_outline=(90, 90, 120))
                # The "Kruis" from the original - a fixed red signal, with a
                # white underlay so it stays visible even on a reddish
                # regenboog tile. Drawn BEFORE the number so the number
                # stays readable on top of it.
                for cross_color, width in (((255, 255, 255), 9), ((200, 60, 60), 5)):
                    pygame.draw.line(screen, cross_color, (rect.left + 9, rect.top + 9),
                                     (rect.right - 9, rect.bottom - 9), width)
                    pygame.draw.line(screen, cross_color, (rect.right - 9, rect.top + 9),
                                     (rect.left + 9, rect.bottom - 9), width)
            label = self.font_btn.render(str(table_num), True, label_color)
            screen.blit(label, label.get_rect(center=rect.center))


        neutral_bg, neutral_text = self.theme.get("btn_somtype", *_NEUTRAL_BTN) \
            if self.theme else _NEUTRAL_BTN[0]
        self._fill_button(screen, neutral_bg, self.som_type_rect, 10, bg_color, text_color)
        som_surface = self.font_btn.render(
            som_label(SOM_TYPES[self.som_type_index]), True, neutral_text)
        screen.blit(som_surface, som_surface.get_rect(center=self.som_type_rect.center))


    def _chip_label_fonts(self, etype, rect):
        """(line-1 font, line-2 font) of a chip - see ChipPanel.label_fonts."""
        return self.chip_panel.label_fonts(etype, rect)

    def _draw_exercises_panel(self, screen, bg_color, text_color):
        """Plus en min mode: three groups (Tot 10 / 20 / 100), each a row of
        chips for + and one for -. A chip is ticked = blue with a check mark."""
        self.chip_panel.draw(screen, self.selected_exercises, self.theme, bg_color, text_color)

    def draw(self, screen):
        bg_color, text_color = self.theme.get("background", *_BACKGROUND) \
            if self.theme else _BACKGROUND[0]
        screen.fill(bg_color)

        self._draw_title_button(screen, bg_color, text_color)
        self._draw_language_button(screen, bg_color, text_color)
        # The hint sits directly on the PAGE, so it uses the page's text
        # color (a button's text color is only guaranteed readable on that
        # button - on a random regenboog page it could vanish).
        hint = self.font_small.render(t("choice.hint"), True, text_color)
        screen.blit(hint, hint.get_rect(midtop=self.hint_rect.midtop))

        if self.mode == MODE_TAFELS:
            self._draw_tables_panel(screen, bg_color, text_color)
        else:
            self._draw_exercises_panel(screen, bg_color, text_color)

        for game, rect in self.game_tiles.items():
            self._draw_game_tile(screen, game, rect, text_color, bg_color)

        players_bg, players_text = self.theme.get("btn_players", *_NEUTRAL_BTN) \
            if self.theme else _NEUTRAL_BTN[0]
        self._fill_button(screen, players_bg, self.players_rect, 10, bg_color, text_color)
        players_label = self.font_btn.render(
            t("choice.players.one") if self.num_players == 1 else t("choice.players.two"),
            True, players_text)
        screen.blit(players_label, players_label.get_rect(center=self.players_rect.center))

        # Sound button: green=on stays a fixed signal color; the "off"
        # state uses the neutral theme color since it carries no meaning
        # beyond "not currently active".
        if self.sound_on:
            sound_color, sound_text = SIGNAL_GREEN, (255, 255, 255)
        else:
            sound_color, sound_text = self.theme.get("btn_sound_off", *_NEUTRAL_BTN) \
                if self.theme else _NEUTRAL_BTN[0]
        self._fill_button(screen, sound_color, self.sound_rect, 10, bg_color, text_color)
        sound_label = self.font_btn.render(
            t("choice.sound.on") if self.sound_on else t("choice.sound.off"), True, sound_text)
        # Icon + text are centered as ONE group within the button, rather
        # than the icon anchored to the left edge and the text anchored
        # off of that - otherwise any leftover space all piles up on one
        # side instead of balancing around both.
        icon_gap = 8
        # The speaker is drawn in the button's own text color (so it has
        # the same guaranteed contrast), and shows a cross when muted.
        icon = icons.speaker((40, 40), sound_text, muted=not self.sound_on)
        content_w = icon.get_width() + icon_gap + sound_label.get_width()
        start_x = self.sound_rect.centerx - content_w // 2
        icon_rect = icon.get_rect(midleft=(start_x, self.sound_rect.centery))
        screen.blit(icon, icon_rect)
        screen.blit(sound_label, sound_label.get_rect(
            midleft=(icon_rect.right + icon_gap, self.sound_rect.centery)))

        can_start = self._has_selection()
        if can_start:
            start_color, start_text = SIGNAL_GREEN, (255, 255, 255)
        else:
            # Disabled: clearly grey, but the word stays readable (5:1).
            start_color, start_text = (55, 55, 65), (175, 175, 185)
        self._fill_button(screen, start_color, self.start_rect, 12, bg_color, text_color)
        start_label = self.font_btn.render(t("choice.start"), True, start_text)
        screen.blit(start_label, start_label.get_rect(center=self.start_rect.center))

        # Full-screen reminder, small, under Start - on the page, so page text color.
        f11 = self.font_small.render(t("choice.fullscreen"), True, text_color)
        screen.blit(f11, f11.get_rect(midtop=self.f11_rect.midtop))

        # Scorebord button (bottom-left, under the theme button).
        lb_bg, lb_text = self.theme.get("btn_leaderboard", *_NEUTRAL_BTN) \
            if self.theme else _NEUTRAL_BTN[0]
        self._fill_button(screen, lb_bg, self.leaderboard_rect, 8, bg_color, text_color)
        lb_label = self.font_theme.render(t("choice.scoreboard"), True, lb_text)
        screen.blit(lb_label, lb_label.get_rect(center=self.leaderboard_rect.center))

        # Theme toggle button, bottom-left - small and out of the way.
        if self.theme:
            theme_bg, theme_text = self.theme.get("btn_theme_toggle", *_NEUTRAL_BTN)
            self._fill_button(screen, theme_bg, self.theme_rect, 8, bg_color, text_color)
            label_text = t("choice.theme", mode=mode_label(self.theme.mode))
            theme_label = self.font_theme.render(label_text, True, theme_text)
            screen.blit(theme_label, theme_label.get_rect(center=self.theme_rect.center))

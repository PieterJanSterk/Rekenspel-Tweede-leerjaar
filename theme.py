"""
theme.py

Three UI color modes, selectable from a small button on Keuzescherm:

  - "dark" (the default on every fresh launch): the existing dark palette.
  - "light": a light equivalent of the same layout.
  - "regenboog" (rainbow): every click randomizes colors across the whole
    app, all at once - background and every "neutral" button get fresh
    random colors each time any cursor fires. It's meant to feel a bit
    chaotic for the kids, but text must stay readable regardless of what
    random color it lands on.

The readability guarantee uses the same math browsers use to judge
accessible contrast: WCAG's relative luminance formula. For any random
background color, we compute its luminance and then just pick whichever
of pure black or pure white text contrasts better against it. To make
that choice reliably strong (not a borderline 4.6:1), random backgrounds
are generated with lightness deliberately kept OUT of the "muddy middle"
range where neither black nor white text would read well - so we always
land solidly on one side or the other.

Semantic colors - green for "selected/correct/on", red for "wrong/off",
the red/blue player identity colors - are deliberately NOT randomized in
any mode, dark/light/regenboog included. Those colors carry meaning a
kid relies on at a glance; scrambling them would hurt the exact
readability this module exists to protect. Only backgrounds and plain
neutral buttons (which carry no on/off meaning) are themed.

Not saved to settings.json on purpose: the chosen theme carries over
between rounds within one running session (this object is created once
in main.py and shared by every screen), but a fresh launch of the game
always starts back in dark mode, as requested.
"""

import random
import colorsys

MODES = ["dark", "light", "regenboog"]
# Language-file keys of the three theme names (the displayed text comes from
# lang/*.json; "regenboog" stays the internal mode id).
MODE_LABEL_KEYS = {"dark": "theme.dark", "light": "theme.light", "regenboog": "theme.rainbow"}


def mode_label(mode):
    """The theme's name in the current language ("Donker" / "Dark")."""
    from i18n import t
    return t(MODE_LABEL_KEYS[mode])


# Dutch names, kept for old callers/tests that read the dictionary directly.
MODE_LABELS = {"dark": "Donker", "light": "Licht", "regenboog": "Regenboog"}

# Signal colors - the ones that carry meaning (green = selected / on / go).
# All three are dark enough that WHITE text on them clears WCAG AA (4.5:1);
# the original brighter shades measured 2.7:1 / 3.8:1 / 3.0:1 with white
# text, which is not readable. Defined once here so every screen agrees.
SIGNAL_GREEN = (25, 130, 60)
TAB_BLUE = (45, 115, 165)
TILE_BLUE = (0, 112, 220)


def _relative_luminance(rgb):
    """WCAG relative luminance, 0 (black) to 1 (white)."""
    def channel(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(rgb1, rgb2):
    """WCAG contrast ratio: 1 (no contrast) to 21 (black vs white).
    4.5 is the WCAG AA threshold for normal-sized text."""
    l1 = _relative_luminance(rgb1)
    l2 = _relative_luminance(rgb2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def best_text_color(bg_rgb):
    """Whichever of pure black / pure white reads better against this
    background."""
    white_contrast = contrast_ratio(bg_rgb, (255, 255, 255))
    black_contrast = contrast_ratio(bg_rgb, (0, 0, 0))
    return (255, 255, 255) if white_contrast > black_contrast else (0, 0, 0)


def _random_vivid_color():
    """A random hue at high saturation, with lightness kept clearly dark
    or clearly light - never the mid-grey band where neither black nor
    white text contrasts strongly."""
    hue = random.random()
    saturation = random.uniform(0.55, 0.9)
    lightness = random.choice([
        random.uniform(0.16, 0.30),   # clearly dark
        random.uniform(0.78, 0.92),   # clearly light
    ])
    r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
    return (int(r * 255), int(g * 255), int(b * 255))


def _carries_text(color, min_contrast=4.5):
    """True when black or white text on `color` clears min_contrast."""
    return contrast_ratio(color, best_text_color(color)) >= min_contrast


def random_color_on(bg, min_contrast=4.5, fallback=None, with_text=False,
                    relaxed_contrast=None):
    """A random vivid color that is readable ON `bg` (contrast >= min_contrast).
    Used for pictures, which sit on a tile or the page rather than behind
    text. with_text=True additionally requires that black/white text drawn ON
    the color is readable (>= 4.5:1) - for things that carry a label, like a
    balloon with its number. relaxed_contrast: if no color reaches
    min_contrast (a mid-tone bg like the selected-tile blue only allows
    near-white), settle for this lower bar rather than always returning the
    same fallback - WCAG asks only 3:1 of large graphics. If everything
    fails, returns `fallback`, or black/white - whichever reads better on bg."""
    bars = [min_contrast] + ([relaxed_contrast] if relaxed_contrast is not None else [])
    for bar in bars:
        for _ in range(60):
            color = _random_vivid_color()
            if contrast_ratio(color, bg) >= bar and (not with_text or _carries_text(color)):
                return color
    return fallback if fallback is not None else best_text_color(bg)


def random_readable_pair(min_contrast=4.5):
    """(background, text) with guaranteed strong contrast. The lightness
    constraint above makes this pass on the first try almost always; the
    retry loop is just a safety net, never a real bottleneck."""
    for _ in range(10):
        bg = _random_vivid_color()
        text = best_text_color(bg)
        if contrast_ratio(bg, text) >= min_contrast:
            return bg, text
    return bg, text  # practically unreachable, but never raises


# Player identity colors: (variant for dark backgrounds, variant for
# light backgrounds). A single fixed pastel can't be readable on both -
# the pale pink/blue that looks great on a dark bar measured 1.5:1 on the
# light-mode bar, effectively invisible.
PLAYER_COLORS = {
    1: ((255, 140, 140), (170, 30, 30)),
    2: ((140, 180, 255), (20, 70, 180)),
}


def player_color(player_id, bg_rgb, min_contrast=4.5):
    """The player's red/blue, in whichever variant reads better against
    the actual background it's drawn on. If neither variant clears
    min_contrast (possible on a random regenboog bar), fall back to the
    guaranteed black/white text color - readability beats identity
    color, and the left/right position plus the "Speler N" label still
    say whose score it is."""
    best = max(PLAYER_COLORS[player_id], key=lambda c: contrast_ratio(c, bg_rgb))
    if contrast_ratio(best, bg_rgb) >= min_contrast:
        return best
    return best_text_color(bg_rgb)


class Theme:
    def __init__(self, mode="dark"):
        self.mode = mode
        self._regenboog_cache = {}

    def cycle(self):
        idx = MODES.index(self.mode)
        self.mode = MODES[(idx + 1) % len(MODES)]
        self._regenboog_cache = {}

    def randomize(self):
        """Call once per click while in regenboog mode - clears the
        cache so every themed slot picks a fresh color on next draw."""
        if self.mode == "regenboog":
            self._regenboog_cache = {}

    def color_on(self, slot, bg, dark_candidates, light_candidates=None,
                 fallback=None, min_contrast=4.5, with_text=False,
                 relaxed_contrast=None):
        """A DECORATIVE color - a picture, a balloon - that is readable on
        `bg`, and that follows the theme like everything else does.

        dark / light: the first color of that mode's candidate list whose
        contrast against bg is >= min_contrast (light_candidates defaults to
        the dark list); if none qualifies, `fallback` (typically the text
        color of whatever the picture sits on, which is guaranteed readable).
        regenboog: a fresh random color that is readable on bg, kept until
        the next click, so pictures re-color along with the rest of the app.
        relaxed_contrast (regenboog only): the lower bar to settle for when
        nothing reaches min_contrast, so the color still varies.
        with_text=True: the color must also carry black/white text readably
        (for a balloon and its number). (The cache is keyed on bg too, so a
        picture whose tile changes color - e.g. because it just got selected -
        never keeps a stale color.)"""
        bg = tuple(bg[:3])
        if self.mode == "regenboog":
            key = (slot, bg)
            if key not in self._regenboog_cache:
                self._regenboog_cache[key] = random_color_on(
                    bg, min_contrast, fallback, with_text, relaxed_contrast)
            return self._regenboog_cache[key]
        candidates = (light_candidates if self.mode == "light" and light_candidates is not None
                      else dark_candidates)
        for color in candidates:
            if contrast_ratio(color, bg) >= min_contrast and (not with_text or _carries_text(color)):
                return tuple(color)
        return tuple(fallback) if fallback is not None else best_text_color(bg)

    def get(self, slot, dark_pair, light_pair):
        """slot: a stable string key naming one UI element (e.g.
        'background', 'klok_card_3'). dark_pair/light_pair: (bg, text)
        tuples used verbatim in those modes. Returns (bg, text)."""
        if self.mode == "dark":
            return dark_pair
        if self.mode == "light":
            return light_pair
        if slot not in self._regenboog_cache:
            self._regenboog_cache[slot] = random_readable_pair()
        return self._regenboog_cache[slot]

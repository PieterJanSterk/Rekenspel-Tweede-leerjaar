"""
test_theme_audit.py - dev-only. Proves, from real rendered pixels, that every
screen and game follows the theme and stays readable in dark, light and
regenboog (many random re-rolls).

  - every text label: contrast against the pixels actually behind it >= 4.5:1
  - every picture:    dominant color against the pixels behind it   >= 3.0:1
  - every screen's background follows the theme (changes in regenboog)
  - balloon colors, which used to ignore the background

Uses theme_audit.py (the measuring harness).   Run:  python test_theme_audit.py
"""
import os
import random
import sys
import tempfile
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((1280, 720))

import ballon
import exercises
import hoeden
import keuzescherm
import keyboard_input
import klok
import leaderboard
import leaderboard_screen
import memory
from theme import Theme, best_text_color, contrast_ratio
from theme_audit import Audit

keuzescherm.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "settings.json")   # never the real one

PASSED, FAILED = [], []
REGENBOOG_ROUNDS = 20
TABLES, SOM = [2, 3, 7], "Gemengd"


def test(fn):
    try:
        fn()
        PASSED.append(fn.__name__)
    except Exception:
        FAILED.append(fn.__name__)
        print(f"FAIL {fn.__name__}")
        traceback.print_exc()
    return fn


from audit_screens import C, SCREENS, TABLES, SOM  # noqa: E402


def audit_screen(name, mode, rounds):
    """Measure a screen in a theme mode; returns (findings, number of measurements)."""
    theme = Theme(mode)
    findings, count = [], 0
    for _ in range(rounds):
        with Audit() as audit:
            for state, draw in SCREENS[name](theme):
                draw(audit.screen(f"{name}/{state}"))
        findings += audit.findings(min_text=4.5, min_graphic=3.0)
        count += len(audit.log)
        theme.randomize()
    return findings, count


# ------------------------------------------------------------------ the tests
@test
def the_harness_itself_catches_bad_contrast_and_sees_plenty():
    with Audit() as audit:
        font = pygame.font.SysFont("arial", 30)
        screen = audit.screen("selftest")
        screen.fill((60, 60, 60))
        screen.blit(font.render("hard to read", True, (75, 75, 75)), (100, 100))
        screen.blit(font.render("easy to read", True, (255, 255, 255)), (100, 200))
    bad = audit.findings()
    assert len(bad) == 1 and bad[0][2] == "hard to read", bad
    # And it really measures: a screen yields lots of labels, not zero.
    findings, count = audit_screen("keuzescherm", "dark", 1)
    assert count >= 25, count


@test
def every_screen_is_readable_in_dark_light_and_regenboog():
    total = 0
    for name in SCREENS:
        for mode, rounds in (("dark", 1), ("light", 1), ("regenboog", REGENBOOG_ROUNDS)):
            findings, count = audit_screen(name, mode, rounds)
            total += count
            assert not findings, (name, mode, findings[:4])
    print(f"   {total} text/picture measurements, all readable")


@test
def every_screens_background_follows_the_theme():
    def page_pixel(draw):
        surf = pygame.Surface((1280, 720))
        draw(surf)
        return tuple(surf.get_at((3, 400)))[:3]

    for name, builder in SCREENS.items():
        seen = {}
        for mode in ("dark", "light", "regenboog"):
            theme = Theme(mode)
            colors = set()
            for _ in range(10):
                colors.add(page_pixel(builder(theme)[0][1]))
                theme.randomize()
            seen[mode] = colors
        assert len(seen["dark"]) == 1 and len(seen["light"]) == 1, (name, seen)
        assert seen["dark"] != seen["light"], name
        assert len(seen["regenboog"]) >= 8, (name, "background barely changes in regenboog")


@test
def balloon_palettes_carry_their_number_and_stand_out_from_their_background():
    dark_bg, light_bg = (25, 30, 45), (235, 238, 245)
    for color in ballon.BALLOON_COLORS + ballon.BALLOON_COLORS_LIGHT:
        assert contrast_ratio(color, best_text_color(color)) >= 4.5, color
    for color in ballon.BALLOON_COLORS:
        assert contrast_ratio(color, dark_bg) >= ballon.BALLOON_MIN_CONTRAST, ("dark", color)
    for color in ballon.BALLOON_COLORS_LIGHT:
        assert contrast_ratio(color, light_bg) >= ballon.BALLOON_MIN_CONTRAST, ("light", color)


@test
def balloons_use_the_right_palette_and_neighbours_differ():
    for mode, palette, bg in (("dark", ballon.BALLOON_COLORS, (25, 30, 45)),
                              ("light", ballon.BALLOON_COLORS_LIGHT, (235, 238, 245))):
        g = ballon.BallonGame(1280, 720, TABLES, SOM, 1, None, Theme(mode))
        colors = [g._balloon_color(i, bg) for i in range(6)]
        assert colors == palette, (mode, colors)
        assert len(set(colors)) == 6


@test
def balloons_get_new_colors_on_every_regenboog_click_and_stay_visible():
    theme = Theme("regenboog")
    g = ballon.BallonGame(1280, 720, TABLES, SOM, 1, None, theme)
    bg = theme.get("background", (25, 30, 45), (235, 238, 245))[0]
    seen = set()
    for _ in range(25):
        color = g._balloon_color(0, bg)
        assert contrast_ratio(color, bg) >= ballon.BALLOON_MIN_CONTRAST
        assert contrast_ratio(color, best_text_color(color)) >= 4.5
        seen.add(color)
        theme.randomize()
        bg = theme.get("background", (25, 30, 45), (235, 238, 245))[0]
    assert len(seen) >= 10


if __name__ == "__main__":
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", ", ".join(FAILED))
        sys.exit(1)

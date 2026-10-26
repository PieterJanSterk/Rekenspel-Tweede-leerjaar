"""
test_keuzescherm.py - dev-only tests for the game-choice tiles on the
selection screen.   Run:  python test_keuzescherm.py

Checks behaviour (what a click selects/saves, what is drawn, what is
readable), not just that something changed. settings.json is redirected to
a temp file, so your real settings are never touched.
"""
import json
import os
import sys
import tempfile
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((1280, 720))

import keuzescherm
from keuzescherm import Keuzescherm, GAMES, game_label
from theme import Theme, contrast_ratio, TILE_BLUE
from theme_audit import Audit
import icons
import leaderboard_screen
import main as main_module

PASSED, FAILED = [], []
_TEMP_SETTINGS = os.path.join(tempfile.mkdtemp(), "settings.json")
keuzescherm.SETTINGS_PATH = _TEMP_SETTINGS          # never touch the real file


def test(fn):
    try:
        fn()
        PASSED.append(fn.__name__)
    except Exception:
        FAILED.append(fn.__name__)
        print(f"FAIL {fn.__name__}")
        traceback.print_exc()
    return fn


class FakeCursor:
    def __init__(self, x, y, fired=True, player_id=1):
        self.x, self.y, self.fired, self.player_id = x, y, fired, player_id


def fresh(theme_mode="dark", saved=None):
    if os.path.exists(_TEMP_SETTINGS):
        os.remove(_TEMP_SETTINGS)
    if saved is not None:
        with open(_TEMP_SETTINGS, "w") as f:
            json.dump(saved, f)
    return Keuzescherm(1280, 720, theme=Theme(theme_mode))


def click_at(k, pos):
    k.update([FakeCursor(*pos)])


def snapshot(k):
    return (sorted(k.selected_tables), k.som_type_index, k.num_players, k.sound_on, k.done)


# ---------------------------------------------------------------- layout
@test
def four_tiles_two_left_and_two_right_of_the_content_strip():
    k = fresh()
    assert set(k.game_tiles) == set(GAMES) and len(GAMES) == 4
    left = [g for g, r in k.game_tiles.items() if r.right <= k.content_x0]
    right = [g for g, r in k.game_tiles.items() if r.left >= k.content_x1]
    assert len(left) == 2 and len(right) == 2, (left, right)
    # Two stacked per side, same column x.
    for side in (left, right):
        a, b = (k.game_tiles[g] for g in side)
        assert a.left == b.left and a.bottom < b.top
    # Tiles are still big (much larger than the old 320x56 button) ...
    assert all(r.w >= 200 and r.h >= 200 for r in k.game_tiles.values())
    # ... and everything in the strip between them sits inside it.
    strip = pygame.Rect(k.content_x0, 0, k.content_x1 - k.content_x0, 720)
    for r in list(k.table_buttons.values()) + list(k.chip_rects.values()) + [
            k.players_rect, k.sound_rect, k.start_rect, k.som_type_rect, k.title_rect]:
        assert strip.contains(r), r


@test
def nothing_on_the_screen_overlaps_and_everything_fits():
    screen = pygame.Rect(0, 0, 1280, 720)
    for mode in (keuzescherm.MODE_TAFELS, keuzescherm.MODE_PLUSMIN):
        k = fresh()
        k.mode = mode
        rects = {f"tile_{g}": r for g, r in k.game_tiles.items()}
        if mode == keuzescherm.MODE_TAFELS:
            rects.update({f"table_{n}": r for n, r in k.table_buttons.items()})
            rects["som"] = k.som_type_rect
        else:
            rects.update({f"chip_{key}": r for key, r in k.chip_rects.items()})
        rects.update(players=k.players_rect, sound=k.sound_rect, start=k.start_rect,
                     theme=k.theme_rect, scorebord=k.leaderboard_rect,
                     title=k.title_rect, hint=k.hint_rect, f11=k.f11_rect)
        names = list(rects)
        for i, a in enumerate(names):
            assert screen.contains(rects[a]), (mode, a)
            for b in names[i + 1:]:
                assert not rects[a].colliderect(rects[b]), (mode, a, b)
        # Everything above the content (title + hint) ends before it starts.
        first_row = (min(r.top for r in k.table_buttons.values()) if mode == keuzescherm.MODE_TAFELS
                     else min(r.top for r in k.chip_rects.values()))
        assert k.hint_rect.bottom < first_row, mode
    # The chip panel ends clear of the players/sound row.
    assert k.panel_bottom < k.players_rect.top - 8


@test
def the_old_game_button_is_gone():
    k = fresh()
    assert not hasattr(k, "game_rect")
    start_game = k.game
    # Click all around the empty gap between the Keer button and the players
    # row, where nothing lives any more (and where "Spel:" never was).
    before = snapshot(k)
    gap_y = (k.som_type_rect.bottom + k.players_rect.top) // 2
    for pos in ((640, gap_y), (500, gap_y), (790, gap_y)):
        click_at(k, pos)
    assert k.game == start_game and snapshot(k) == before


# ---------------------------------------------------------------- behaviour
@test
def clicking_a_tile_selects_that_game_and_nothing_else():
    for game in GAMES:
        k = fresh()
        before = snapshot(k)
        click_at(k, k.game_tiles[game].center)
        assert k.game == game and k.result()["game"] == game
        assert snapshot(k) == before, "a tile click must not change tables/type/players/sound or start"


@test
def tile_choice_is_saved_and_restored_next_launch():
    k = fresh()
    click_at(k, k.game_tiles["hoeden"].center)
    assert json.load(open(_TEMP_SETTINGS))["game"] == "hoeden"
    k2 = Keuzescherm(1280, 720, theme=Theme("dark"))
    assert k2.game == "hoeden"
    click_at(k2, k2.game_tiles["memory"].center)
    assert Keuzescherm(1280, 720, theme=Theme("dark")).game == "memory"


@test
def clicking_the_already_selected_tile_keeps_it_selected():
    k = fresh(saved={"game": "ballon"})
    click_at(k, k.game_tiles["ballon"].center)
    assert k.game == "ballon"


@test
def stale_saved_game_falls_back_to_klok_so_a_tile_is_always_selected():
    k = fresh(saved={"game": "does_not_exist"})
    assert k.game == "klok"


@test
def tile_corners_and_edges_count_as_the_tile():
    k = fresh()
    r = k.game_tiles["ballon"]
    for pos in (r.topleft, (r.right - 1, r.bottom - 1), (r.centerx, r.top), (r.left, r.centery)):
        k.game = "klok"
        click_at(k, pos)
        assert k.game == "ballon", pos
    k.game = "klok"
    click_at(k, (r.left - 3, r.centery))          # just outside
    assert k.game == "klok"


@test
def start_still_needs_a_table_and_other_controls_still_work():
    k = fresh()
    k.selected_tables.clear()
    click_at(k, k.start_rect.center)
    assert not k.done
    click_at(k, k.table_buttons[3].center)
    assert k.selected_tables == {3}
    click_at(k, k.som_type_rect.center)
    assert k.som_type_index == 1
    click_at(k, k.players_rect.center)
    assert k.num_players == 2
    click_at(k, k.sound_rect.center)
    assert k.sound_on is False
    click_at(k, k.game_tiles["memory"].center)
    click_at(k, k.start_rect.center)
    assert k.done and k.result()["game"] == "memory" and k.result()["tables"] == [3]


# ---------------------------------------------------------------- drawing
def outline_pixel(surf, rect):
    return tuple(surf.get_at((rect.left + 2, rect.centery)))[:3]


@test
def exactly_the_selected_tile_is_highlighted_and_it_follows_the_click():
    for mode in ("dark", "light"):
        k = fresh(mode)
        surf = pygame.Surface((1280, 720))
        _, page_text = k.theme.get("background", *keuzescherm._BACKGROUND)
        for game in GAMES:
            click_at(k, k.game_tiles[game].center)
            k.draw(surf)
            for other, rect in k.game_tiles.items():
                px = outline_pixel(surf, rect)
                if other == game:
                    assert px == tuple(page_text[:3]), (mode, other, px)
                    # the tile body itself is the "selected" blue
                    assert tuple(surf.get_at((rect.left + 30, rect.centery)))[:3] == TILE_BLUE
                else:
                    assert px != tuple(page_text[:3]), (mode, game, other)
            # a check mark badge only on the selected tile
            sel = k.game_tiles[game]
            badge = (sel.right - 34, sel.top + 34)
            assert tuple(surf.get_at(badge))[:3] == (255, 255, 255)
            for other, rect in k.game_tiles.items():
                if other != game:
                    assert tuple(surf.get_at((rect.right - 34, rect.top + 34)))[:3] != (255, 255, 255)


@test
def tile_text_and_pictures_meet_wcag_aa_in_every_theme_and_selection():
    worst = {"title": 99.0, "icon": 99.0, "outline": 99.0}
    for mode, rounds in (("dark", 1), ("light", 1), ("regenboog", 150)):
        theme = Theme(mode)
        k = Keuzescherm(1280, 720, theme=theme)
        for _ in range(rounds):
            page_bg, page_text = theme.get("background", *keuzescherm._BACKGROUND)
            for selected_game in GAMES:
                k.game = selected_game
                for game in GAMES:
                    bg, text = k.tile_colors(game)
                    icon = k.icon_color(game, bg, text)       # what the screen really uses
                    worst["title"] = min(worst["title"], contrast_ratio(bg, text))
                    # Pictures: 4.5:1 normally; in regenboog the selected (blue) tile's
                    # picture may settle for the 3:1 WCAG asks of large graphics.
                    ratio = contrast_ratio(bg, icon)
                    if mode == "regenboog" and game == selected_game:
                        assert ratio >= keuzescherm.ICON_RELAXED_CONTRAST, (mode, game, ratio)
                    else:
                        worst["icon"] = min(worst["icon"], ratio)
                worst["outline"] = min(worst["outline"], contrast_ratio(page_bg, page_text))
            if mode == "regenboog":
                theme.randomize()
    print("   worst contrast:", {k_: round(v, 2) for k_, v in worst.items()})
    assert all(v >= 4.5 for v in worst.values()), worst


@test
def colorful_pictures_are_used_where_readable_and_fall_back_where_not():
    k = fresh("dark")
    k.game = "ballon"
    # Unselected dark tile: a bright accent is picked, not the white text color.
    bg, text = k.tile_colors("klok")
    assert keuzescherm.game_icon_color("klok", bg, text) in keuzescherm._ICON_ACCENTS["klok"]
    # Selected blue tile: no accent clears 4.5:1, so the picture is the white text color.
    bg, text = k.tile_colors("ballon")
    assert bg == TILE_BLUE
    assert keuzescherm.game_icon_color("ballon", bg, text) == text
    # Light theme: the deep accent is chosen on a light tile.
    k2 = fresh("light")
    bg, text = k2.tile_colors("hoeden")
    assert keuzescherm.game_icon_color("hoeden", bg, text) == keuzescherm._ICON_ACCENTS["hoeden"][1]


@test
def in_dark_and_light_every_unselected_picture_is_colorful_not_a_plain_fallback():
    for mode in ("dark", "light"):
        k = fresh(mode)
        k.game = "klok"
        for game in GAMES:
            if game == k.game:
                continue
            bg, text = k.tile_colors(game)
            color = k.icon_color(game, bg, text)
            assert color in keuzescherm._ICON_ACCENTS[game], (mode, game, color)
            assert contrast_ratio(color, bg) >= 4.7, (mode, game, "needs a margin above 4.5")


@test
def every_game_has_a_picture_a_title_and_a_color_entry():
    assert set(GAMES) == set(keuzescherm._GAME_ICONS) == set(keuzescherm._ICON_ACCENTS) == set(keuzescherm.GAME_LABEL_KEYS)
    assert [game_label(g) for g in GAMES] == ["Klok", "Ballon", "Hoeden", "Memory"]


@test
def all_four_pictures_render_solid_centered_and_inside_their_box():
    for game in GAMES:
        fn, size, kwargs = keuzescherm._GAME_ICONS[game]
        surf = fn(size, (255, 255, 255), **kwargs)
        assert surf.get_size() == size
        mask = pygame.mask.from_surface(surf, 128)
        bbox = mask.get_bounding_rects()
        assert bbox, f"{game}: nothing drawn"
        box = bbox[0].unionall(bbox[1:])
        fill = mask.count() / (size[0] * size[1])
        assert 0.12 < fill < 0.9, (game, fill)
        # Content must reach most of the picture's width and height (not a tiny speck)...
        assert box.w > 0.6 * size[0] and box.h > 0.6 * size[1], (game, box, size)
        # ...and be roughly centered, so the tile looks balanced.
        assert abs(box.centerx - size[0] / 2) < 0.12 * size[0], (game, box.centerx)
    # The hat is two shades of the base color: base + a visible band. Not a flat blob.
    hat = icons.hat((150, 118), (255, 200, 70))
    colors = {tuple(hat.get_at((x, y)))[:3] for x in range(0, 150, 3) for y in range(0, 118, 3)
              if hat.get_at((x, y))[3] > 250}
    assert len(colors) >= 3


@test
def the_question_mark_is_a_real_hole_you_can_see_the_tile_through():
    size = (150, 128)
    surf = icons.memory_cards(size, (255, 255, 255))
    # Front card spans x 4%-68%, y 16%-98%; its "?" is centered in it.
    cx, cy = int(size[0] * 0.36), int(size[1] * 0.57)
    column = [surf.get_at((cx, cy + dy))[3] for dy in range(-30, 31)]
    assert min(column) < 30, "no see-through pixels where the ? is"
    assert max(column) > 250, "the card around the ? must stay solid"
    # The solid parts must keep the picture's color. (A past bug blacked out
    # the whole rectangle around the "?": the hole was there, but the card
    # around it turned into a dark box.) With a white picture, no solid
    # pixel may be dark.
    dark_solid = [(x, y) for x in range(size[0]) for y in range(size[1])
                  if surf.get_at((x, y))[3] > 250 and max(surf.get_at((x, y))[:3]) < 100]
    assert not dark_solid, f"{len(dark_solid)} dark solid pixels - black box around the ?"
    # Drawn on two different tiles, the hole shows each tile's own color.
    for tile in ((25, 30, 45), (200, 60, 60)):
        canvas = pygame.Surface(size)
        canvas.fill(tile)
        canvas.blit(surf, (0, 0))
        seen = {tuple(canvas.get_at((cx, cy + dy)))[:3] for dy in range(-30, 31)}
        assert tile in seen, tile


# ---------------------------------------------------------------- texts + corner buttons
def drawn(theme_mode="dark", mode=None, **setup):
    """Draw the screen once through the audit harness; returns (screen obj, audit)."""
    with Audit() as audit:
        k = fresh(theme_mode)
        if mode:
            k.mode = mode
        for key, value in setup.items():
            setattr(k, key, value)
        k.draw(audit.screen("keuzescherm"))
    return k, audit


@test
def title_is_a_button_and_the_hint_sits_directly_under_it():
    for mode, title_text in ((keuzescherm.MODE_TAFELS, "Tafels"), (keuzescherm.MODE_PLUSMIN, "Plus en min")):
        k, audit = drawn(mode=mode)
        texts = [what for kind, _w, what, *_ in audit.log if kind == "text"]
        assert title_text in texts and "Kies je tafels" not in texts
        assert texts.count("(klik om te wisselen)") == 1
        title, hint = audit.rect_of(title_text), audit.rect_of("(klik om te wisselen)")
        assert k.title_rect.contains(title), "the title text sits inside its button"
        assert title.centerx == hint.centerx == 640
        assert k.title_rect.bottom < hint.top <= k.title_rect.bottom + 8, "hint right under the button"
        assert hint.bottom < k.som_type_rect.top - 100, "no longer under the Keer button"


@test
def f11_reminder_sits_centered_under_start_in_the_small_font():
    k, audit = drawn()
    f11 = audit.rect_of("Volledig scherm = F11")
    assert f11 is not None
    assert f11.top >= k.start_rect.bottom and f11.top - k.start_rect.bottom <= 16
    assert abs(f11.centerx - k.start_rect.centerx) <= 1
    assert f11.bottom < 720 - 8, "must fit on screen with a margin"
    start = audit.rect_of("Start")
    assert f11.height < start.height, "small font: smaller than the button label"


@test
def theme_button_is_bottom_left_and_scorebord_bottom_right():
    k, audit = drawn()
    t, b = k.theme_rect, k.leaderboard_rect
    assert t.size == b.size and t.top == b.top, "same size, same height"
    assert t.left == 16 and b.right == 1280 - 16, "in the two bottom corners"
    assert t.bottom <= 720 - 10 and b.bottom <= 720 - 10
    for tile in k.game_tiles.values():
        assert not tile.colliderect(t) and not tile.colliderect(b)
    assert not k.f11_rect.colliderect(t) and not k.f11_rect.colliderect(b)
    assert b.contains(audit.rect_of("Scorebord")) and t.contains(audit.rect_of("Thema: Donker"))


@test
def clicking_scorebord_asks_for_the_leaderboard_and_changes_nothing_else():
    k = fresh()
    click_at(k, k.game_tiles["hoeden"].center)
    click_at(k, k.table_buttons[4].center)
    before, game = snapshot(k), k.game
    assert k.leaderboard_requested is False
    click_at(k, k.leaderboard_rect.center)
    assert k.leaderboard_requested is True
    assert snapshot(k) == before and k.game == game and not k.done
    # The theme button right above it still only cycles the theme.
    k2 = fresh()
    mode_before = k2.theme.mode
    click_at(k2, k2.theme_rect.center)
    assert k2.theme.mode != mode_before and k2.leaderboard_requested is False


@test
def the_leaderboard_opens_on_what_is_currently_picked():
    k = fresh()
    click_at(k, k.game_tiles["memory"].center)
    k.selected_tables = {3, 4}
    click_at(k, k.som_type_rect.center)               # -> "Gedeeld door (:)"
    click_at(k, k.players_rect.center)                # -> 2 players
    screen = main_module._leaderboard_for_choice(k, None, Theme("dark"))
    assert isinstance(screen, leaderboard_screen.LeaderboardScreen)
    tables, som_type = screen._effective_filter()
    assert screen.game == "memory" and screen.mode == "2"
    assert sorted(tables) == [3, 4] and som_type == keuzescherm.SOM_TYPES[k.som_type_index]
    assert not screen.done


@test
def with_no_table_selected_the_leaderboard_shows_every_table():
    k = fresh()
    k.selected_tables.clear()
    screen = main_module._leaderboard_for_choice(k, None, Theme("dark"))
    tables, _ = screen._effective_filter()
    assert sorted(tables) == list(range(1, 11))


@test
def choices_survive_the_round_trip_through_the_leaderboard():
    k = fresh()
    click_at(k, k.game_tiles["ballon"].center)
    click_at(k, k.table_buttons[7].center)
    click_at(k, k.players_rect.center)
    chosen = (k.game, sorted(k.selected_tables), k.num_players)
    click_at(k, k.leaderboard_rect.center)
    assert k.leaderboard_requested
    # After "Verder" main.py builds a fresh Keuzescherm: it must come back identical.
    k2 = Keuzescherm(1280, 720, theme=Theme("dark"))
    assert (k2.game, sorted(k2.selected_tables), k2.num_players) == chosen
    assert k2.leaderboard_requested is False


# ---------------------------------------------------------------- the pictures follow the theme
def icon_colors_over_clicks(mode, rounds, selected="klok"):
    """{icon size: set of colors} for the 4 tile pictures over `rounds` clicks."""
    seen = {}
    theme = Theme(mode)
    k = fresh(mode)
    k.theme = theme
    k.game = selected
    for _ in range(rounds):
        with Audit() as audit:
            k.draw(audit.screen())
        for kind, _w, what, fg, bg, _r in audit.log:
            if kind == "graphic":
                seen.setdefault(what, set()).add(fg)
        theme.randomize()
    return seen


@test
def pictures_change_color_in_regenboog_but_stay_put_in_dark_and_light():
    for mode in ("dark", "light"):
        seen = icon_colors_over_clicks(mode, 15)
        assert seen and all(len(colors) == 1 for colors in seen.values()), (mode, seen)
    seen = icon_colors_over_clicks("regenboog", 25)
    tile_icons = {what: colors for what, colors in seen.items()
                  if what in ("icon (130, 130)", "icon (96, 128)", "icon (150, 118)", "icon (150, 128)")}
    assert len(tile_icons) == 4, tile_icons.keys()
    for what, colors in tile_icons.items():
        assert len(colors) >= 8, f"{what} barely changes in regenboog: {len(colors)} colors"


@test
def the_selected_tiles_picture_also_changes_in_regenboog():
    for game, size in (("klok", "icon (130, 130)"), ("ballon", "icon (96, 128)")):
        seen = icon_colors_over_clicks("regenboog", 25, selected=game)
        assert len(seen[size]) >= 8, (game, len(seen[size]))


@test
def every_picture_is_readable_on_its_tile_in_every_theme_as_actually_drawn():
    for mode, rounds in (("dark", 1), ("light", 1), ("regenboog", 30)):
        theme = Theme(mode)
        k = fresh(mode)
        k.theme = theme
        for _ in range(rounds):
            for game in GAMES:
                k.game = game
                with Audit() as audit:
                    k.draw(audit.screen())
                bad = audit.findings(min_text=4.5, min_graphic=3.0)
                assert not bad, (mode, game, bad[:3])
            theme.randomize()


@test
def theme_color_on_follows_each_mode():
    bg = (70, 70, 90)
    dark = Theme("dark").color_on("s", bg, [(255, 200, 70), (120, 70, 0)], fallback=(255, 255, 255))
    assert dark == (255, 200, 70)
    light_bg = (210, 212, 225)
    light = Theme("light").color_on("s", light_bg, [(255, 200, 70), (120, 70, 0)], fallback=(20, 20, 30))
    assert light == (120, 70, 0), "first candidate that is readable on the light tile"
    nothing = Theme("dark").color_on("s", bg, [(80, 80, 100)], fallback=(1, 2, 3))
    assert nothing == (1, 2, 3), "no candidate readable -> the fallback"
    t = Theme("regenboog")
    a = t.color_on("s", bg, [(255, 200, 70)], fallback=(255, 255, 255))
    assert t.color_on("s", bg, [(255, 200, 70)], fallback=(255, 255, 255)) == a, "stable until a click"
    seen = set()
    for _ in range(30):
        t.randomize()
        c = t.color_on("s", bg, [(255, 200, 70)], fallback=(255, 255, 255))
        assert contrast_ratio(c, bg) >= 4.5
        seen.add(c)
    assert len(seen) >= 10
    # A different background (the tile got selected) never reuses a stale color.
    c2 = t.color_on("s", TILE_BLUE, [(255, 200, 70)], fallback=(255, 255, 255))
    assert contrast_ratio(c2, TILE_BLUE) >= 4.5


@test
def disabled_start_button_is_dimmed_but_readable():
    with Audit() as audit:
        k = fresh()
        k.selected_tables.clear()
        k.draw(audit.screen())
    start = [(fg, bg) for kind, _w, what, fg, bg, _r in audit.log if what == "Start"][0]
    assert contrast_ratio(*start) >= 4.5, start
    assert start[1] == (55, 55, 65), "still clearly the grey 'disabled' look"


def _all_buttons(k):
    rects = {f"tile_{g}": r for g, r in k.game_tiles.items()}
    if k.mode == keuzescherm.MODE_TAFELS:
        rects.update({f"table_{n}": r for n, r in k.table_buttons.items()})
        rects["som"] = k.som_type_rect
    else:
        rects.update({f"chip_{key}": r for key, r in k.chip_rects.items()})
    rects.update(players=k.players_rect, sound=k.sound_rect, start=k.start_rect,
                 theme=k.theme_rect, scorebord=k.leaderboard_rect, title=k.title_rect)
    return rects


@test
def no_button_ever_blends_into_the_page_in_any_theme():
    """Whatever the (random) page color, every button and tile must be
    findable by its shape: its fill OR its outline stands out from the page."""
    worst = 99.0
    for mode, rounds in (("dark", 1), ("light", 1), ("regenboog", 80)):
        theme = Theme(mode)
        k = fresh(mode)
        k.theme = theme
        surf = pygame.Surface((1280, 720))
        for _ in range(rounds):
            for game, mode in zip(GAMES, (keuzescherm.MODE_TAFELS, keuzescherm.MODE_PLUSMIN) * 2):
                k.game, k.mode = game, mode
                k.selected_exercises = {"e_plus_e_to10_zb", "te_minus_te_to100_mb", "e_plus_e_to20_mb"}
                k.draw(surf)
                for name, r in _all_buttons(k).items():
                    # (2 px left of the button: inside even the 5 px gap between chips)
                    page = tuple(surf.get_at((r.left - 2, r.centery)))[:3]
                    inside = tuple(surf.get_at((r.left + 14, r.centery)))[:3]
                    edge = tuple(surf.get_at((r.left + 1, r.centery)))[:3]
                    visible = max(contrast_ratio(inside, page), contrast_ratio(edge, page))
                    worst = min(worst, visible)
                    assert visible >= keuzescherm.BUTTON_EDGE_CONTRAST, (mode, game, name, page, inside, edge)
            theme.randomize()
    print(f"   least visible button edge/fill: {worst:.2f}:1")


# ---------------------------------------------------------------- Plus en min
PLUSMIN = keuzescherm.MODE_PLUSMIN
TAFELS = keuzescherm.MODE_TAFELS


def settings_on_disk():
    with open(keuzescherm.SETTINGS_PATH) as f:
        return json.load(f)


@test
def clicking_the_title_switches_between_tafels_and_plus_en_min_and_remembers_it():
    k = fresh()
    assert k.mode == TAFELS, "first ever launch is Tafels"
    click_at(k, k.title_rect.center)
    assert k.mode == PLUSMIN and settings_on_disk()["mode"] == "plusmin"
    click_at(k, k.title_rect.center)
    assert k.mode == TAFELS and settings_on_disk()["mode"] == "tafels"
    click_at(k, k.title_rect.center)
    k2 = Keuzescherm(1280, 720, theme=Theme("dark"))
    assert k2.mode == PLUSMIN, "the next launch starts in the mode you left"
    assert not k2.done and not k2.leaderboard_requested


@test
def the_title_button_does_not_move_or_resize_between_modes():
    k = fresh()
    rect = tuple(k.title_rect)
    k.mode = PLUSMIN
    assert tuple(k.title_rect) == rect
    for mode, text in ((TAFELS, "Tafels"), (PLUSMIN, "Plus en min")):
        _, audit = drawn(mode=mode)
        assert k.title_rect.contains(audit.rect_of(text))


@test
def only_the_current_modes_controls_react():
    # In Tafels mode the chips are not there ...
    k = fresh()
    before = (set(k.selected_exercises), sorted(k.selected_tables))
    clicked = 0
    for key, rect in k.chip_rects.items():
        # only chips whose centre is NOT on a real Tafels control (they overlap in
        # the picture; there the Tafels control rightly wins)
        if not any(t.collidepoint(rect.center) for t in k.table_buttons.values()) \
                and not k.som_type_rect.collidepoint(rect.center):
            click_at(k, rect.center)
            clicked += 1
    assert clicked >= 10, "the test must really click a good number of chips"
    assert (set(k.selected_exercises), sorted(k.selected_tables)) == before
    # ... and in Plus en min mode the tables and the Keer button are not.
    k = fresh()
    k.mode = PLUSMIN
    tables_before, som_before = sorted(k.selected_tables), k.som_type_index
    for rect in k.table_buttons.values():
        click_at(k, rect.center)
    click_at(k, k.som_type_rect.center)
    assert sorted(k.selected_tables) == tables_before and k.som_type_index == som_before


@test
def chips_toggle_and_are_saved():
    k = fresh()
    k.mode = PLUSMIN
    k.selected_exercises = set()
    key = "te_plus_e_to100_mb"
    click_at(k, k.chip_rects[key].center)
    assert k.selected_exercises == {key}
    assert settings_on_disk()["selected_exercises"] == [key]
    click_at(k, k.chip_rects["e_minus_e_to10_zb"].center)
    assert k.selected_exercises == {key, "e_minus_e_to10_zb"}
    click_at(k, k.chip_rects[key].center)
    assert k.selected_exercises == {"e_minus_e_to10_zb"}
    # one click toggles exactly one chip: no neighbour is touched
    assert snapshot(k)[1:4] == (0, 1, True)


@test
def start_needs_a_chip_in_plus_en_min_and_a_table_in_tafels():
    k = fresh()
    k.mode = PLUSMIN
    k.selected_exercises = set()
    click_at(k, k.start_rect.center)
    assert not k.done
    click_at(k, k.chip_rects["e_plus_e_to10_zb"].center)
    click_at(k, k.start_rect.center)
    assert k.done
    # Tafels mode: ticked chips must not let Start through when no table is ticked.
    k = fresh()
    k.selected_exercises = {"e_plus_e_to10_zb"}
    k.selected_tables.clear()
    click_at(k, k.start_rect.center)
    assert not k.done


@test
def the_result_describes_the_chosen_mode():
    k = fresh()
    k.selected_tables = {2, 5}
    k.selected_exercises = {"e_plus_e_to10_zb", "te_minus_e_to100_mb"}
    r = k.result()
    assert r["mode"] == TAFELS and r["tables"] == [2, 5] and r["som_type"] == "Keer (x)"
    assert r["exercises"] == [], "no exercises in Tafels mode"
    k.mode = PLUSMIN
    r = k.result()
    assert r["mode"] == PLUSMIN and r["tables"] == [] and r["som_type"] == "Plus en min"
    assert r["exercises"] == ["e_plus_e_to10_zb", "te_minus_e_to100_mb"]
    assert {"game", "num_players", "sound_on"} <= set(r)


@test
def mode_and_exercise_choices_survive_a_restart_and_bad_settings_are_repaired():
    k = fresh()
    k.mode = PLUSMIN
    k.selected_exercises = {"e_plus_e_to20_mb", "t_plus_t_to100_zb"}
    k._persist()
    k2 = Keuzescherm(1280, 720, theme=Theme("dark"))
    assert k2.mode == PLUSMIN and k2.selected_exercises == {"e_plus_e_to20_mb", "t_plus_t_to100_zb"}
    # hand-edited / old files
    k3 = fresh(saved={"mode": "nonsense", "selected_exercises": ["e_plus_e_to10_zb", "gone_type"]})
    assert k3.mode == TAFELS and k3.selected_exercises == {"e_plus_e_to10_zb"}
    # first ever launch in Plus en min starts with the two easiest types ticked
    k4 = fresh()
    assert sorted(k4.selected_exercises) == sorted(keuzescherm.DEFAULT_EXERCISES)
    # an old settings.json (from before Plus en min existed) just works
    k5 = fresh(saved={"game": "memory", "selected_tables": [3], "som_type_index": 1,
                      "num_players": 2, "sound_on": False})
    assert k5.mode == TAFELS and k5.game == "memory" and k5.selected_tables == {3}


@test
def the_exercise_panel_has_23_chips_in_3_groups_with_a_plus_row_above_a_minus_row():
    k = fresh()
    assert len(k.chip_rects) == 23 == len(keuzescherm.EXERCISE_BY_KEY)
    rows = {}
    for key, rect in k.chip_rects.items():
        etype = keuzescherm.EXERCISE_BY_KEY[key]
        rows.setdefault((etype.group, etype.sign), []).append(rect)
    assert len(rows) == 6
    for (group, sign), rects in rows.items():
        assert len(rects) <= 7
        assert len({r.top for r in rects}) == 1, "one row = one height"
        xs = [r.left for r in rects]
        assert xs == sorted(xs) and rects[0].left == k.content_x0 + keuzescherm.CHIP_GUTTER
        assert all(a.right < b.left for a, b in zip(rects, rects[1:])), "no overlap in a row"
    for group, _ in keuzescherm.GROUPS:
        assert rows[(group, "+")][0].bottom < rows[(group, "-")][0].top
    tops = [rows[(g, s)][0].top for g, _ in keuzescherm.GROUPS for s in ("+", "-")]
    assert tops == sorted(tops), "10 above 20 above 100"
    assert all(r.w >= 80 and r.h >= 40 for rs in rows.values() for r in rs), "chips big enough to hit and read"


@test
def every_chip_label_fits_inside_its_chip_and_the_ticked_look_is_right():
    k, audit = drawn(mode=PLUSMIN, selected_exercises={"e_plus_e_to10_zb", "te_minus_te_to100_mb"})
    for key, rect in k.chip_rects.items():
        etype = keuzescherm.EXERCISE_BY_KEY[key]
        font1, font2 = k._chip_label_fonts(etype, rect)
        assert font1.size(etype.line1)[0] <= rect.w - 14, (key, etype.line1)
        assert font1.get_height() + font2.get_height() + 1 <= rect.h if etype.line2 else True
        inside = [r for kind, _w, what, _fg, _bg, r in audit.log
                  if kind == "text" and what == etype.line1 and rect.contains(r)]
        assert inside, f"label {etype.line1!r} is not drawn inside its chip"
    surf = pygame.Surface((1280, 720))
    k.draw(surf)
    on, off = k.chip_rects["e_plus_e_to10_zb"], k.chip_rects["e_minus_e_to10_zb"]
    assert tuple(surf.get_at((on.left + 8, on.centery)))[:3] == TILE_BLUE
    assert tuple(surf.get_at((off.left + 8, off.centery)))[:3] != TILE_BLUE
    assert min(surf.get_at((on.right - 3, on.top + 3))[:3]) > 230, "check badge on ticked chips"
    assert min(surf.get_at((off.right - 3, off.top + 3))[:3]) < 200, "no badge on unticked chips"


@test
def the_bottom_block_and_tiles_are_identical_in_both_modes():
    seen = {}
    for mode in (TAFELS, PLUSMIN):
        k, audit = drawn(mode=mode)
        seen[mode] = {text: audit.rect_of(text) for text in
                      ("Start", "1 speler", "Geluid: Aan", "Volledig scherm = F11", "Scorebord",
                       "Klok", "Ballon", "Hoeden", "Memory")}
    assert seen[TAFELS] == seen[PLUSMIN], "nothing may jump when the mode changes"


@test
def disabled_start_is_readable_in_plus_en_min_too():
    with Audit() as audit:
        k = fresh()
        k.mode = PLUSMIN
        k.selected_exercises = set()
        k.draw(audit.screen())
    start = [(fg, bg) for kind, _w, what, fg, bg, _r in audit.log if what == "Start"][0]
    assert contrast_ratio(*start) >= 4.5 and start[1] == (55, 55, 65)


@test
def main_hands_the_games_the_right_kind_of_problems():
    import exercises
    for game in ("klok", "ballon", "hoeden", "memory"):
        g = main_module._make_game(game, [], "Plus en min", 1, None, Theme("dark"),
                                   exercises=["e_plus_e_to10_zb"])
        assert g.problems.kind == "plusmin", game
        g = main_module._make_game(game, [2, 3], "Keer (x)", 1, None, Theme("dark"), exercises=[])
        assert g.problems.kind == "tafels", game
        g = main_module._make_game(game, [2, 3], "Keer (x)", 1, None, Theme("dark"))
        assert g.problems.kind == "tafels", game


if __name__ == "__main__":
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", ", ".join(FAILED))
        sys.exit(1)

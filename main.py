"""
main.py

Run this to play. State machine:

    KEUZESCHERM --start--> PLAYING --finished--> NAME_ENTRY --done--> LEADERBOARD
         ^                 (Klok,                                         |
         |                  Ballon or                                     |
         |                  Hoeden or                                     |
         |                  Memory,                                       |
         |                  chosen on                                     |
         |                  Keuzescherm)                                  |
         '-------------------------- "Verder" clicked ----------------------'

All games share a compatible interface (update/draw/finished/
num_players/results), so PLAYING is one state regardless of which was
chosen - no need to duplicate the state machine per minigame.

Both player cursors are always drawn as colored crosshairs (red = P1,
blue = P2) so it's obvious which gun is which, on every screen.

Press F11 anytime to toggle fullscreen - useful on Windows where the
window's own maximize button doesn't give a true fullscreen pygame
window. This rebuilds the display surface manually with pygame.SCALED
rather than using pygame.display.toggle_fullscreen(), which is known to
be unreliable specifically on Windows (it often silently does nothing,
or leaves the window in a broken state). SCALED makes pygame stretch
our fixed 1280x720 game to whatever the monitor's actual resolution is,
with letterboxing if the aspect ratio doesn't match exactly - so this
works correctly regardless of what resolution your screen actually is.

Test on a normal PC first (mouse = P1, arrow keys + Enter = P2) before
moving to the Batocera box with real guns - see input_devices.py for how
that switch happens automatically.
"""

import sys
import pygame

from input_devices import InputManager
from keuzescherm import Keuzescherm
from klok import KlokGame
from ballon import BallonGame
from hoeden import HoedenGame
from memory import MemoryGame
from exercises import ExerciseSet
from keyboard_input import MultiNameEntry
from leaderboard_screen import LeaderboardScreen
from sounds import SoundBank
import i18n
from i18n import t
from theme import Theme
import leaderboard

SCREEN_W, SCREEN_H = 1280, 720

STATE_KEUZESCHERM = "keuzescherm"
STATE_PLAYING = "playing"
STATE_NAME_ENTRY = "name_entry"
STATE_LEADERBOARD = "leaderboard"


def draw_cursor(screen, cursor):
    x, y = int(cursor.x), int(cursor.y)
    size = 14
    pygame.draw.line(screen, cursor.color, (x - size, y), (x + size, y), 3)
    pygame.draw.line(screen, cursor.color, (x, y - size), (x, y + size), 3)
    pygame.draw.circle(screen, cursor.color, (x, y), size, 2)


def _score_for_player(game_name, results, player_id, num_players):
    """The two games score differently: Klok's 1-player score is the
    points-remaining in its draining bank (not a per-player tally),
    while Ballon's score (both modes) and Klok's 2-player score are
    already a direct per-player number."""
    if game_name == "klok" and num_players == 1:
        return results["bank_remaining"]
    return results["scores"].get(player_id, 0)


# Co-op games: both players play ONE shared match, so the result is ONE
# leaderboard row with both names joined ("Jan & Sam"), not one row each.
# (The list lives in leaderboard.py, which also needs it to treat
# "Jan & Sam" and "Sam & Jan" as the same pair.)
COOP_GAMES = leaderboard.COOP_GAMES


def _final_scores(game_name, results, num_players):
    """{player_id: score} shown on the name-entry screen. For a co-op game
    that is a single shared score (player 1's key), so the screen shows one
    box ("Beurten: 12") instead of one per player."""
    if game_name in COOP_GAMES:
        return {1: results["turns"]}
    return {
        pid: _score_for_player(game_name, results, pid, num_players)
        for pid in range(1, num_players + 1)
    }


def _make_leaderboard(keuzescherm, sound_bank, theme, game, content_mode, num_players):
    """The leaderboard screen for a game, opened on the right kind of board:
    `content_mode` is Tafels or Plus en min (what was just played / is picked).
    Both selections are handed over - the tables with their exercise type, and
    the ticked exercises - so switching Tafels <-> Plus en min on the
    leaderboard itself already starts from what is picked on the choice screen.
    With no table ticked it falls back to every table (an empty filter would
    only ever show an empty board)."""
    from keuzescherm import SOM_TYPES
    return LeaderboardScreen(
        SCREEN_W, SCREEN_H,
        initial_mode=str(num_players),
        sound_bank=sound_bank,
        initial_tables=sorted(keuzescherm.selected_tables) or list(range(1, 11)),
        initial_som_type=SOM_TYPES[keuzescherm.som_type_index],
        theme=theme,
        game=game,
        initial_content=content_mode,
        initial_exercises=sorted(keuzescherm.selected_exercises))


def _leaderboard_for_choice(keuzescherm, sound_bank, theme):
    """The leaderboard opened straight from the choice screen (Scorebord
    button): the board for what is currently picked there - the selected
    game, number of players, and Tafels or Plus en min with its selection -
    exactly like the one shown after a match."""
    return _make_leaderboard(keuzescherm, sound_bank, theme, game=keuzescherm.game,
                             content_mode=keuzescherm.mode,
                             num_players=keuzescherm.num_players)


def _record_match(choice, final_scores, names, results, path=None):
    """Store a finished match on the leaderboard. `choice` is what
    Keuzescherm.result() said when the match was started: in Plus en min its
    "tables" is empty, its "som_type" is "Plus en min" and "exercises" lists
    the ticked types - so what is stored is always what was PLAYED, never
    whatever happens to be picked on the choice screen now."""
    _record_scores(choice["game"], final_scores, names, choice["tables"],
                   choice["som_type"], results=results, path=path,
                   exercises=choice["exercises"])


def _name_entry_extras(game_name, final_scores, results):
    """(score_labels, times) for the name-entry screen.
    times: the hidden timer(s), shown next to the score - Memory has ONE
    shared time (key 1, like its single shared score box), Hoeden one per
    player. score_labels: "8/11" instead of a bare 8, for Hoeden. Games
    without a hidden timer get (None, None) and look exactly as before."""
    times, labels = None, None
    if game_name in COOP_GAMES:
        if results.get("time_ms") is not None:
            times = {1: results["time_ms"]}
    elif results.get("times_ms"):
        times = dict(results["times_ms"])
    if results.get("rounds_total"):
        labels = {pid: f"{score}/{results['rounds_total']}"
                  for pid, score in final_scores.items()}
    return labels, times


def _record_scores(game_name, final_scores, names, tables, som_type,
                   results=None, path=None, exercises=None):
    """Normal games: one leaderboard row per player, so both individual
    bests rank against everyone else's in that mode's board. final_scores
    is the same {player_id: score} dict already shown on the name-entry
    screen - computed once when the round ended, reused here.
    Co-op games (Memory): ONE row for the pair, named "Jan & Sam", with the
    shared turn count and the hidden play time from `results`.
    exercises: the ticked Plus en min exercise keys (then tables is [] and
    som_type "Plus en min"), stored with every row so boards stay separate.
    path: only for tests, so they never touch the real leaderboard.json."""
    mode = str(len(names))
    extra = {"path": path} if path else {}
    if exercises:
        extra["exercises"] = exercises
    if game_name in COOP_GAMES:
        joined = " & ".join(names[pid] for pid in sorted(names))
        leaderboard.add_score(joined, results["turns"], mode, tables, som_type,
                               game=game_name, time_ms=results.get("time_ms"),
                               **extra)
        return
    # Games with a per-player hidden timer (Hoeden) store each player's own.
    times = (results or {}).get("times_ms", {})
    for player_id, name in names.items():
        leaderboard.add_score(name, final_scores.get(player_id, 0), mode,
                               tables, som_type, game=game_name,
                               time_ms=times.get(player_id), **extra)


def _set_display_mode(fullscreen):
    """(Re)creates the display surface. SCALED lets pygame stretch our
    fixed 1280x720 surface to fill whatever resolution the monitor
    actually is in fullscreen, rather than requiring an exact
    resolution match (which can fail or letterbox oddly otherwise) -
    but SCALED needs a hardware-accelerated renderer, which not every
    machine (older hardware, some Batocera setups) has. Fall back to
    plain FULLSCREEN - still a real fullscreen window, just without the
    automatic stretching - if SCALED isn't available."""
    try:
        flags = (pygame.FULLSCREEN | pygame.SCALED) if fullscreen else pygame.SCALED
        return pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
    except pygame.error:
        flags = pygame.FULLSCREEN if fullscreen else 0
        return pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)


# Word shown for a single player's score on the name-entry screen,
# matching each game's own HUD (Hoeden counts flowers, not points).
# The word shown with a score on the name-entry screen, per game (language-file keys).
SCORE_WORD_KEYS = {"klok": "hud.score_word.default", "ballon": "hud.score_word.default",
                   "hoeden": "hud.score_word.default", "memory": "hud.score_word.memory"}


def score_word(game_name):
    """"Score" (or "Beurten" for Memory) in the current language."""
    return t(SCORE_WORD_KEYS.get(game_name, "hud.score_word.default"))

GAME_CLASSES = {
    "klok": KlokGame,
    "ballon": BallonGame,
    "hoeden": HoedenGame,
    "memory": MemoryGame,
}


def _make_game(game_name, tables, som_type, num_players, sound_bank, theme,
               exercises=None):
    """exercises: the ticked plus/min exercise keys (Plus en min mode), or
    empty/None for the multiplication tables. In plus/min mode the game gets
    an ExerciseSet; otherwise it builds its own TableSet from tables/som_type."""
    cls = GAME_CLASSES[game_name]
    problems = ExerciseSet(exercises) if exercises else None
    return cls(SCREEN_W, SCREEN_H, tables, som_type,
               num_players=num_players, sound_bank=sound_bank, theme=theme,
               problems=problems)


def main():
    # `Tafels --selftest`: a headless health check (used by the build workflow
    # on every packaged executable) instead of starting the game.
    if "--selftest" in sys.argv[1:]:
        from selftest import run as run_selftest
        sys.exit(run_selftest())
    pygame.init()
    fullscreen = False
    screen = _set_display_mode(fullscreen)
    clock = pygame.time.Clock()

    inputs = InputManager()
    sound_bank = SoundBank()  # loads goed.wav / fout.wav / klik.wav, or fails silently
    # One Theme instance for the whole run - shared by every screen so a
    # mode change (or a regenboog randomize) applies everywhere at once.
    # Always starts in dark mode; never saved to settings.json, so a
    # fresh launch is always dark again even if last session ended on
    # light or regenboog.
    theme = Theme("dark")

    state = STATE_KEUZESCHERM
    keuzescherm = Keuzescherm(SCREEN_W, SCREEN_H, sound_bank=sound_bank, theme=theme)
    active_game = None
    name_entry = None
    leaderboard_screen = None
    last_final_scores = None
    last_results = None
    last_choice = None

    caption_language = None            # the window title follows the language
    running = True
    while running:
        dt_ms = clock.tick(60)
        if i18n.language() != caption_language:
            # (Keuzescherm applies the saved language when it is created, and the
            # language button changes it - either way it shows up here.)
            caption_language = i18n.language()
            pygame.display.set_caption(t("app.caption"))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                fullscreen = not fullscreen
                screen = _set_display_mode(fullscreen)

        inputs.update(SCREEN_W, SCREEN_H)

        # Regenboog mode: every click, anywhere, re-randomizes every
        # themed color in the app at once - this is the single
        # integration point rather than each screen handling it itself.
        if theme.mode == "regenboog" and (inputs.player1.fired or inputs.player2.fired):
            theme.randomize()

        if state == STATE_KEUZESCHERM:
            keuzescherm.update([inputs.player1, inputs.player2])
            keuzescherm.draw(screen)
            if keuzescherm.done:
                last_choice = keuzescherm.result()
                sound_bank.enabled = last_choice["sound_on"]
                active_game = _make_game(
                    last_choice["game"], last_choice["tables"], last_choice["som_type"],
                    last_choice["num_players"], sound_bank, theme,
                    exercises=last_choice["exercises"])
                state = STATE_PLAYING
            elif keuzescherm.leaderboard_requested:
                leaderboard_screen = _leaderboard_for_choice(keuzescherm, sound_bank, theme)
                state = STATE_LEADERBOARD

        elif state == STATE_PLAYING:
            active_cursors = [inputs.player1] if active_game.num_players == 1 \
                else [inputs.player1, inputs.player2]
            active_game.update(dt_ms, active_cursors)
            active_game.draw(screen)
            if active_game.finished:
                results = active_game.results()
                last_results = results
                last_final_scores = _final_scores(
                    last_choice["game"], results, active_game.num_players)
                score_labels, times = _name_entry_extras(
                    last_choice["game"], last_final_scores, results)
                name_entry = MultiNameEntry(SCREEN_W, SCREEN_H,
                                             num_players=active_game.num_players,
                                             theme=theme, scores=last_final_scores,
                                             score_word=score_word(last_choice["game"]),
                                             times=times, score_labels=score_labels)
                state = STATE_NAME_ENTRY

        elif state == STATE_NAME_ENTRY:
            active_cursors = [inputs.player1] if active_game.num_players == 1 \
                else [inputs.player1, inputs.player2]
            name_entry.update(active_cursors)
            name_entry.draw(screen)
            if name_entry.done:
                # (what was played comes from last_choice - in Plus en min its
                # "tables" is empty and "exercises" lists the ticked types)
                _record_match(last_choice, last_final_scores, name_entry.names, last_results)
                leaderboard_screen = _make_leaderboard(
                    keuzescherm, sound_bank, theme, game=last_choice["game"],
                    content_mode=last_choice["mode"],
                    num_players=active_game.num_players)
                state = STATE_LEADERBOARD

        elif state == STATE_LEADERBOARD:
            active_cursors = [inputs.player1, inputs.player2]
            leaderboard_screen.update(active_cursors)
            leaderboard_screen.draw(screen)
            if leaderboard_screen.done:
                keuzescherm = Keuzescherm(SCREEN_W, SCREEN_H, sound_bank=sound_bank,
                                           theme=theme)
                state = STATE_KEUZESCHERM

        draw_cursor(screen, inputs.player1)
        draw_cursor(screen, inputs.player2)

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

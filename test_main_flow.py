"""
test_main_flow.py - dev-only. Drives the REAL main() loop (headless) with
scripted mouse clicks and checks the screen-to-screen flow of the new
features:

   choice screen -> click the title -> Plus en min
   -> click Scorebord -> leaderboard opens on a Plus en min board
   -> click Verder -> back on the choice screen, still in Plus en min
   -> tick a chip, press Start -> a game starts on plus/min exercises
   -> ESC ... (the run is then ended)

The mouse is simulated by replacing pygame.mouse.get_pos / get_pressed (the
fallback input reads them); settings.json is redirected to a temp file, and
nothing is written to leaderboard.json (no match is finished).
Run:  python test_main_flow.py   (takes about 10 seconds)
"""
import os
import re
import sys
import tempfile
import threading
import time
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

pygame.init()

import i18n
import keuzescherm
import klok
import leaderboard_screen
import main as main_module
from theme import Theme

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_LEADERBOARD = os.path.join(HERE, "leaderboard.json")
real_before = open(REAL_LEADERBOARD, "rb").read() if os.path.exists(REAL_LEADERBOARD) else None

keuzescherm.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "settings.json")

# ---- what is on screen right now (updated by wrapping the draw methods)
seen = {"screen": None, "info": {}}
mouse = {"pos": (0, 0), "down": False}


def wrap(cls, name, describe):
    original = cls.draw

    def draw(self, screen, *args, **kwargs):
        seen["screen"], seen["info"] = name, describe(self)
        return original(self, screen, *args, **kwargs)
    cls.draw = draw


wrap(keuzescherm.Keuzescherm, "choice",
     lambda s: {"mode": s.mode, "game": s.game, "language": i18n.language()})
wrap(leaderboard_screen.LeaderboardScreen, "leaderboard",
     lambda s: {"content": s.content, "game": s.game, "exercises": sorted(s.filter_exercises),
                "language": i18n.language()})

# the window title (set by main() from the language file)
captions = []
_real_set_caption = pygame.display.set_caption
pygame.display.set_caption = lambda text, *a: (captions.append(text), _real_set_caption(text, *a))
wrap(klok.KlokGame, "klok", lambda s: {"kind": s.problems.kind,
                                       "questions": [c["question"] for c in s.slots]})

pygame.mouse.get_pos = lambda: mouse["pos"]
pygame.mouse.get_pressed = lambda *a, **k: (mouse["down"], False, False)

problems = []


def check(condition, message):
    if not condition:
        problems.append(message)
        print("  FAIL:", message)


def wait_for(condition, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.05)
    return False


def click(pos):
    mouse["pos"] = pos
    time.sleep(0.12)
    mouse["down"] = True
    time.sleep(0.15)
    mouse["down"] = False
    time.sleep(0.25)


def script():
    try:
        k = keuzescherm.Keuzescherm(1280, 720, theme=Theme("dark"))   # for the geometry only
        os.remove(keuzescherm.SETTINGS_PATH) if os.path.exists(keuzescherm.SETTINGS_PATH) else None
        check(wait_for(lambda: seen["screen"] == "choice"), "the choice screen shows first")
        check(seen["info"].get("mode") == "tafels", "starts in Tafels mode")
        check(seen["info"].get("language") == "nl", "starts in Dutch")
        check(captions and captions[-1] == "Tafels oefenen - 2 spelers", f"Dutch window title ({captions})")

        click(k.language_rect.center)
        check(wait_for(lambda: seen["info"].get("language") == "en"), "the language button switches to English")
        check(captions[-1] == "Practise tables - 2 players", f"the window title follows ({captions})")
        k = keuzescherm.Keuzescherm(1280, 720, theme=Theme("dark"))   # geometry in English now

        click(k.title_rect.center)
        check(wait_for(lambda: seen["info"].get("mode") == "plusmin"), "clicking the title switches to Plus en min")

        click(k.leaderboard_rect.center)
        check(wait_for(lambda: seen["screen"] == "leaderboard"), "the Scorebord button opens the leaderboard")
        check(seen["info"].get("content") == "plusmin", "...on a Plus en min board (the mode picked)")
        check(seen["info"].get("language") == "en", "...in the language that was picked")

        board = leaderboard_screen.LeaderboardScreen(1280, 720, theme=Theme("dark"))
        click(board.continue_rect.center)
        check(wait_for(lambda: seen["screen"] == "choice"), "Verder returns to the choice screen")
        check(seen["info"].get("mode") == "plusmin", "...which is still in Plus en min mode")
        check(seen["info"].get("language") == "en", "...and still in English")

        # untick the default chips, tick one chip, then Start
        for key in ("e_plus_e_to10_zb", "e_minus_e_to10_zb"):
            click(k.chip_rects[key].center)
        click(k.start_rect.center)
        time.sleep(0.5)
        check(seen["screen"] == "choice", "Start does nothing while no exercise is ticked")
        click(k.chip_rects["e_plus_e_to20_mb"].center)
        click(k.game_tiles["klok"].center)
        click(k.start_rect.center)
        check(wait_for(lambda: seen["screen"] == "klok"), "Start launches the game")
        info = seen["info"]
        check(info.get("kind") == "plusmin", "the game plays plus/min exercises")
        qs = info.get("questions", [])
        check(len(qs) == 8 and all(re.fullmatch(r"\d+ \+ \d+", q) for q in qs),
              f"E + E MB gives 8 cards of sums (got {qs})")
    except Exception:
        problems.append("exception in the script: " + traceback.format_exc())
    finally:
        pygame.event.post(pygame.event.Event(pygame.QUIT))


threading.Thread(target=script, daemon=True).start()
try:
    main_module.main()
except SystemExit:
    pass
except Exception:
    # a crash inside the real loop is the worst failure of all: report it as one
    problems.append("main() crashed: " + traceback.format_exc().strip().splitlines()[-1])
    print("  FAIL: main() crashed")
    traceback.print_exc()

after = open(REAL_LEADERBOARD, "rb").read() if os.path.exists(REAL_LEADERBOARD) else None
check(after == real_before, "the real leaderboard.json was not modified")
print(f"\n{'FAILED' if problems else 'main flow OK'}: {len(problems)} problem(s)")
sys.exit(1 if problems else 0)

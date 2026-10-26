"""
selftest.py - a quick, headless health check of the game:

    python main.py --selftest          (from source)
    Tafels --selftest                  (a packaged build; Tafels.exe on Windows)

It opens no window and plays no sound. It checks that everything a PACKAGED
build can easily lose is really there and working: the language files, the
sound files, a data folder the game can write to, and that every screen and
every game can be created and drawn - in both Dutch and English. The build
workflow (.github/workflows/build.yml) runs this on each freshly built
executable on Windows, macOS and Linux, so a broken package is caught before
anyone downloads it.

Exit code 0 = all fine, 1 = something failed (each line says what). With the
environment variable TAFELS_SELFTEST_REPORT set to a file path, the same report
is also written to that file (useful where there is no console).
"""
import os
import sys
import tempfile


def run():
    # No window, no audio device needed (set before pygame starts up).
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    results = []

    def check(name, function):
        try:
            detail = function() or ""
            results.append((True, name, detail))
        except Exception as error:                 # a failed check must never stop the others
            results.append((False, name, f"{type(error).__name__}: {error}"))

    import pygame
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    surface = pygame.Surface((1280, 720))

    import i18n
    import paths

    def versions():
        frozen = "packaged build" if paths.is_frozen() else "running from source"
        return f"Python {sys.version.split()[0]}, pygame {pygame.version.ver}, {frozen}"

    def languages():
        codes = dict(i18n.available_languages())
        for needed in ("nl", "en"):
            assert needed in codes, f"language file {needed}.json is missing"
            problems = i18n.validate(needed)
            assert not any(problems.values()), f"{needed}.json has problems: {problems}"
        return "available: " + ", ".join(f"{c} ({n})" for c, n in sorted(codes.items()))

    def sounds():
        folder = paths.resource_path("assets", "sounds")
        for name in ("goed.wav", "fout.wav", "klik.wav"):
            path = os.path.join(folder, name)
            assert os.path.isfile(path) and os.path.getsize(path) > 100, f"{name} is missing or empty"
        return folder

    def data_folder():
        folder = paths.data_dir()
        probe = os.path.join(folder, ".selftest")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return f"writable: {folder}"

    def screens_and_games():
        import exercises
        import keuzescherm
        import keyboard_input
        import leaderboard_screen
        from klok import KlokGame
        from ballon import BallonGame
        from hoeden import HoedenGame
        from memory import MemoryGame
        from theme import Theme

        theme = Theme("dark")
        drawn = 0
        for code in ("nl", "en"):
            assert i18n.set_language(code)
            for mode in (keuzescherm.MODE_TAFELS, keuzescherm.MODE_PLUSMIN):
                chooser = keuzescherm.Keuzescherm(1280, 720, theme=theme)
                chooser.mode = mode
                chooser.draw(surface)
                drawn += 1
            tables = dict(tables=[2, 3], som_type="Gemengd")
            problem_sets = [None, exercises.ExerciseSet(["te_plus_e_to20_zb", "te_minus_e_to100_mb"])]
            for game_class in (KlokGame, BallonGame, HoedenGame, MemoryGame):
                for problems in problem_sets:
                    for players in (1, 2):
                        game = game_class(1280, 720, tables["tables"], tables["som_type"],
                                          num_players=players, theme=theme, problems=problems)
                        for _ in range(5):
                            game.update(16, [])
                        game.draw(surface)
                        game.results()
                        drawn += 1
            board = leaderboard_screen.LeaderboardScreen(
                1280, 720, initial_mode="1", theme=theme,
                leaderboard_path=os.path.join(tempfile.mkdtemp(), "leaderboard.json"))
            board.draw(surface)
            entry = keyboard_input.MultiNameEntry(1280, 720, 2, theme=theme, scores={1: 5, 2: 3})
            entry.draw(surface)
            drawn += 2
        i18n.set_language(i18n.DEFAULT_LANGUAGE)
        return f"{drawn} screens drawn (Dutch and English)"

    check("versions", versions)
    check("language files", languages)
    check("sound files", sounds)
    check("data folder", data_folder)
    check("screens and games", screens_and_games)

    failed = 0
    lines = []
    for ok, name, detail in results:
        lines.append(f"[{'ok' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
        failed += 0 if ok else 1
    lines.append("SELFTEST " + ("OK" if not failed else f"FAILED ({failed} problem(s))"))
    print("\n".join(lines))
    # A packaged Windows game has no console window, so the report can ALSO be
    # written to a file: set TAFELS_SELFTEST_REPORT=<path> (the build workflow does).
    report_path = os.environ.get("TAFELS_SELFTEST_REPORT")
    if report_path:
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError as error:
            print(f"(could not write the report to {report_path}: {error})")
    del screen
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())

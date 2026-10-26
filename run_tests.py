#!/usr/bin/env python3
"""
run_tests.py - run every test file and print one line each.

    python run_tests.py            all tests
    python run_tests.py --fast     skip the slowest ones (the real-game-loop test)

No window or sound device is needed (the tests use SDL's dummy drivers).
Exit code 0 only when every test file passes. The build workflow runs this
before it builds anything.
"""
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SLOW = {"test_main_flow.py"}


def main(argv):
    fast = "--fast" in argv
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    failures = []
    for path in sorted(glob.glob(os.path.join(HERE, "test_*.py"))):
        name = os.path.basename(path)
        if fast and name in SLOW:
            print(f"{name:26s} skipped (--fast)")
            continue
        for attempt in (1, 2):
            result = subprocess.run([sys.executable, path], cwd=HERE, env=env,
                                    capture_output=True, text=True, timeout=600)
            summary = re.findall(r"(\d+ passed, \d+ failed|main flow OK.*)", result.stdout)
            ok = result.returncode == 0
            # The real-game-loop test uses timing; give it one more try before failing.
            if ok or name not in SLOW:
                break
        print(f"{name:26s} {'ok  ' if ok else 'FAIL'} {summary[-1] if summary else ''}")
        if not ok:
            failures.append(name)
            print((result.stdout + result.stderr)[-1500:])
    print()
    print("ALL TESTS PASSED" if not failures else f"FAILED: {', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

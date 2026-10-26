#!/usr/bin/env python3
"""
package_release.py - zip what PyInstaller built (dist/) into release/Tafels-<platform>.zip.

    python package_release.py <platform-name>      e.g.  windows | linux | macos

The zip holds the app plus a short README for the person who downloads it.
Used by the build workflow; also fine to run by hand after `pyinstaller tafels.spec`.
"""
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
README = """Tafels - practise tables and plus/minus

Start the game by opening the program in this folder.
Your settings and the scoreboard are saved next to it (settings.json,
leaderboard.json), so keep it in a folder you can write to.

More languages: put a language file (see docs/TRANSLATING.md in the project)
in a folder named "lang" next to the program.
Full screen: F11.   Quit: Esc.
"""


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    platform = argv[0]
    items = [n for n in os.listdir(DIST) if n.startswith("Tafels")]
    if not items:
        print(f"nothing named Tafels* in {DIST} - run pyinstaller first")
        return 1
    os.makedirs(os.path.join(HERE, "release"), exist_ok=True)
    target = os.path.join(HERE, "release", f"Tafels-{platform}.zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        readme = zipfile.ZipInfo("Tafels/README.txt")
        readme.external_attr = 0o644 << 16          # readable by everyone
        readme.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(readme, README)
        for item in items:
            path = os.path.join(DIST, item)
            if os.path.isdir(path):
                for folder, _dirs, files in os.walk(path):
                    for filename in files:
                        full = os.path.join(folder, filename)
                        zf.write(full, os.path.join("Tafels", os.path.relpath(full, DIST)))
            else:
                info = zipfile.ZipInfo.from_file(path, os.path.join("Tafels", item))
                with open(path, "rb") as f:
                    zf.writestr(info, f.read(), zipfile.ZIP_DEFLATED)   # keeps the executable bit
    print(f"wrote {target} ({os.path.getsize(target) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

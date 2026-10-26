# -*- mode: python ; coding: utf-8 -*-
"""
tafels.spec - PyInstaller recipe for ONE app per operating system.

    pip install -r requirements.txt -r requirements-build.txt
    pyinstaller --noconfirm tafels.spec

Result (in dist/):
  Windows   Tafels.exe        one file, no console window
  Linux     Tafels            one file
  macOS     Tafels.app        an app bundle (PyInstaller no longer supports a
                              single-file windowed app on macOS)

What gets packed inside besides the code: the language files (lang/) and the
sounds (assets/sounds/). The game finds them again at run time through
paths.py. Settings and scores are NOT packed: they are written next to the
program (see paths.py) so they survive restarts.
"""
import importlib.util
import sys

hidden = []
if importlib.util.find_spec("evdev"):          # Linux only: Sinden light guns
    hidden.append("evdev")

a = Analysis(
    ["main.py"],
    pathex=[],
    datas=[("lang", "lang"), ("assets/sounds", "assets/sounds")],
    hiddenimports=hidden,
    excludes=["tkinter", "unittest", "test"],
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Tafels", console=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="Tafels")
    app = BUNDLE(coll, name="Tafels.app", bundle_identifier="org.example.tafels",
                 info_plist={"NSHighResolutionCapable": True})
else:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="Tafels",
        console=(sys.platform != "win32"),     # no black console window on Windows
        upx=False,
    )

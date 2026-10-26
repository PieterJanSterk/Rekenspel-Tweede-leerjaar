"""
paths.py

WHERE THE APP FINDS ITS FILES. Two different kinds of files, which must not be
mixed up once the game is packaged into a single executable (PyInstaller):

  resource_dir()  READ-ONLY files that ship with the game: the language files
                  (lang/) and the sounds (assets/sounds/).
                  - normal run:   the folder this script lives in
                  - packaged run: the folder PyInstaller unpacks them into
                                  (sys._MEIPASS - a TEMPORARY folder that is
                                  deleted when the game quits!)

  data_dir()      files the game WRITES and that must SURVIVE: settings.json
                  and leaderboard.json (the students' scores).
                  - normal run:   the folder this script lives in (as always)
                  - packaged run: next to the executable, so the whole game
                                  stays portable (copy the folder, keep the
                                  scores) - EXCEPT inside a macOS .app bundle,
                                  or when that folder is not writable
                                  (e.g. C:\\Program Files): then a per-user
                                  data folder is used instead
                  - always: the environment variable TAFELS_DATA_DIR wins, if
                            set (handy for a USB stick, a shared school drive,
                            or tests)

Writing to resource_dir() when packaged would silently lose every score and
setting at the next launch - that is the whole reason this module exists.
"""

import os
import sys

APP_NAME = "Tafels"


def _script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def is_frozen():
    """True inside a PyInstaller-built executable."""
    return bool(getattr(sys, "frozen", False))


def resource_dir():
    """Folder holding the read-only files that ship with the game."""
    if is_frozen():
        return getattr(sys, "_MEIPASS", _script_dir())
    return _script_dir()


def resource_path(*parts):
    return os.path.join(resource_dir(), *parts)


def _user_data_dir():
    """The conventional per-user folder for app data on this operating system."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, APP_NAME)


def _is_writable_dir(path):
    return os.path.isdir(path) and os.access(path, os.W_OK)


def data_dir():
    """Folder where settings.json and leaderboard.json live (created if needed)."""
    override = os.environ.get("TAFELS_DATA_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    if not is_frozen():
        return _script_dir()
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    inside_mac_bundle = ".app/Contents/" in exe_dir.replace("\\", "/") + "/"
    if not inside_mac_bundle and _is_writable_dir(exe_dir):
        return exe_dir
    folder = _user_data_dir()
    os.makedirs(folder, exist_ok=True)
    return folder


def data_path(filename):
    return os.path.join(data_dir(), filename)

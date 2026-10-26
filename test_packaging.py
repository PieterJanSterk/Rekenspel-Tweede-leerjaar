"""
test_packaging.py - dev-only tests for everything that matters once the game is
packaged: where files are read from and written to (paths.py), the --selftest
health check, and the build files (PyInstaller spec, GitHub workflow).
Run:  python test_packaging.py
"""
import contextlib
import importlib
import io
import os
import subprocess
import sys
import tempfile
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((1280, 720))

import paths
import selftest

HERE = os.path.dirname(os.path.abspath(__file__))
PASSED, FAILED = [], []


def test(fn):
    try:
        fn()
        PASSED.append(fn.__name__)
    except Exception:
        FAILED.append(fn.__name__)
        print(f"FAIL {fn.__name__}")
        traceback.print_exc()
    return fn


@contextlib.contextmanager
def packaged(exe_path, meipass=None, platform=None, env=None, writable=None):
    """Pretend to be a PyInstaller build running from exe_path."""
    saved = (getattr(sys, "frozen", None), sys.executable, getattr(sys, "_MEIPASS", None),
             sys.platform, dict(os.environ), paths._is_writable_dir)
    had_frozen = hasattr(sys, "frozen")
    had_meipass = hasattr(sys, "_MEIPASS")
    sys.frozen = True
    sys.executable = exe_path
    if meipass:
        sys._MEIPASS = meipass
    if platform:
        sys.platform = platform
    os.environ.pop("TAFELS_DATA_DIR", None)
    os.environ.update(env or {})
    if writable is not None:
        paths._is_writable_dir = lambda folder: writable
    try:
        yield
    finally:
        if had_frozen:
            sys.frozen = saved[0]
        else:
            del sys.frozen
        sys.executable = saved[1]
        if had_meipass:
            sys._MEIPASS = saved[2]
        elif hasattr(sys, "_MEIPASS"):
            del sys._MEIPASS
        sys.platform = saved[3]
        os.environ.clear()
        os.environ.update(saved[4])
        paths._is_writable_dir = saved[5]


# ------------------------------------------------------------------ paths
@test
def running_from_source_everything_lives_next_to_the_scripts_as_always():
    os.environ.pop("TAFELS_DATA_DIR", None)
    assert not paths.is_frozen()
    assert paths.data_dir() == HERE and paths.resource_dir() == HERE
    assert paths.data_path("leaderboard.json") == os.path.join(HERE, "leaderboard.json")


@test
def the_environment_variable_moves_the_data_but_not_the_bundled_files():
    folder = os.path.join(tempfile.mkdtemp(), "scores")
    old = os.environ.get("TAFELS_DATA_DIR")
    os.environ["TAFELS_DATA_DIR"] = folder
    try:
        assert paths.data_dir() == folder and os.path.isdir(folder), "created if needed"
        assert paths.resource_dir() == HERE
    finally:
        if old is None:
            del os.environ["TAFELS_DATA_DIR"]
        else:
            os.environ["TAFELS_DATA_DIR"] = old


@test
def a_packaged_game_reads_bundled_files_from_its_unpack_folder_and_writes_next_to_the_exe():
    root = tempfile.mkdtemp()
    exe_dir, unpack = os.path.join(root, "game"), os.path.join(root, "_MEI123")
    os.makedirs(exe_dir)
    os.makedirs(unpack)
    with packaged(os.path.join(exe_dir, "Tafels"), meipass=unpack):
        assert paths.is_frozen()
        assert paths.resource_dir() == unpack and paths.resource_path("lang") == os.path.join(unpack, "lang")
        assert paths.data_dir() == exe_dir, "scores must NOT go to the temporary unpack folder"
        assert paths.data_dir() != paths.resource_dir()


@test
def a_packaged_game_in_a_read_only_folder_falls_back_to_the_users_data_folder():
    root = tempfile.mkdtemp()
    exe_dir, home = os.path.join(root, "Program Files", "Tafels"), os.path.join(root, "home")
    os.makedirs(exe_dir)
    os.makedirs(home)
    cases = (("win32", {"APPDATA": os.path.join(home, "AppData")}, os.path.join(home, "AppData", "Tafels")),
             ("linux", {"XDG_DATA_HOME": os.path.join(home, "share")}, os.path.join(home, "share", "Tafels")))
    for platform, env, expected in cases:
        with packaged(os.path.join(exe_dir, "Tafels"), platform=platform, env=env, writable=False):
            assert paths.data_dir() == expected and os.path.isdir(expected), platform


@test
def inside_a_mac_app_bundle_the_data_goes_to_application_support():
    root = tempfile.mkdtemp()
    exe_dir = os.path.join(root, "Tafels.app", "Contents", "MacOS")
    home = os.path.join(root, "home")
    os.makedirs(exe_dir)
    os.makedirs(home)
    with packaged(os.path.join(exe_dir, "Tafels"), platform="darwin", env={"HOME": home}, writable=True):
        expected = os.path.join(home, "Library", "Application Support", "Tafels")
        assert paths.data_dir() == expected, "never write inside the .app bundle"


@test
def the_games_files_really_use_paths_and_a_packaged_run_would_keep_its_scores():
    import keuzescherm
    import leaderboard
    import sounds
    root = tempfile.mkdtemp()
    exe_dir, unpack = os.path.join(root, "game"), os.path.join(root, "_MEI9")
    os.makedirs(exe_dir)
    os.makedirs(unpack)
    try:
        with packaged(os.path.join(exe_dir, "Tafels"), meipass=unpack):
            for module in (keuzescherm, leaderboard, sounds):
                importlib.reload(module)
            assert keuzescherm.SETTINGS_PATH == os.path.join(exe_dir, "settings.json")
            assert leaderboard.DEFAULT_PATH == os.path.join(exe_dir, "leaderboard.json")
            assert sounds.ASSET_DIR == os.path.join(unpack, "assets", "sounds")
            leaderboard.add_score("Emma", 5, "1", [2], "Keer (x)", game="klok")
            assert os.path.isfile(os.path.join(exe_dir, "leaderboard.json"))
            assert not os.path.exists(os.path.join(unpack, "leaderboard.json"))
    finally:
        for module in (keuzescherm, leaderboard, sounds):
            importlib.reload(module)
    assert leaderboard.DEFAULT_PATH == os.path.join(HERE, "leaderboard.json"), "back to normal"


# ------------------------------------------------------------------ the self-check
def run_selftest():
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = selftest.run()
    return code, out.getvalue()


@test
def the_selftest_passes_and_reports_every_check():
    code, text = run_selftest()
    assert code == 0, text
    for name in ("versions", "language files", "sound files", "data folder", "screens and games"):
        assert f"[ok] {name}" in text, text
    assert text.strip().endswith("SELFTEST OK")
    assert "40 screens drawn" in text


@test
def the_selftest_notices_a_missing_sound_file_or_language_file_or_unwritable_folder():
    real_resource_path, real_data_dir = paths.resource_path, paths.data_dir
    try:
        empty = tempfile.mkdtemp()
        paths.resource_path = lambda *parts: os.path.join(empty, *parts)
        code, text = run_selftest()
        assert code == 1 and "[FAIL] sound files" in text and text.strip().endswith("FAILED (1 problem(s))"), text
        paths.resource_path = real_resource_path
        paths.data_dir = lambda: os.path.join(empty, "does", "not", "exist")
        code, text = run_selftest()
        assert code == 1 and "[FAIL] data folder" in text, text
    finally:
        paths.resource_path, paths.data_dir = real_resource_path, real_data_dir


@test
def the_selftest_can_also_write_its_report_to_a_file_for_consoleless_windows_builds():
    report = os.path.join(tempfile.mkdtemp(), "report.txt")
    os.environ["TAFELS_SELFTEST_REPORT"] = report
    try:
        code, text = run_selftest()
    finally:
        del os.environ["TAFELS_SELFTEST_REPORT"]
    with open(report, encoding="utf-8") as f:
        assert f.read() == text and text.strip().endswith("SELFTEST OK")


@test
def the_command_line_flag_runs_the_selftest_without_a_window_and_returns_its_exit_code():
    env = dict(os.environ, TAFELS_DATA_DIR=tempfile.mkdtemp())
    result = subprocess.run([sys.executable, os.path.join(HERE, "main.py"), "--selftest"],
                            capture_output=True, text=True, env=env, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().endswith("SELFTEST OK"), result.stdout


# ------------------------------------------------------------------ the build files
def read(*parts):
    with open(os.path.join(HERE, *parts), encoding="utf-8") as f:
        return f.read()


try:
    import yaml
except ImportError:                      # PyYAML is only needed for these tests
    yaml = None


@test
def every_third_party_import_is_in_the_requirements_files():
    import ast
    import re
    stdlib = set(sys.stdlib_module_names)
    local = {f[:-3] for f in os.listdir(HERE) if f.endswith(".py")}
    wanted = set()
    for name in os.listdir(HERE):
        if name.endswith(".py") and not name.startswith("test_") and name not in (
                "theme_audit.py", "audit_screens.py"):
            for node in ast.walk(ast.parse(read(name))):     # real imports only, not prose
                modules = ([a.name for a in node.names] if isinstance(node, ast.Import)
                           else [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0
                           else [])
                for module in modules:
                    top = module.split(".")[0]
                    if top not in stdlib and top not in local:
                        wanted.add(top)
    listed = set()
    for requirements in ("requirements.txt", "requirements-linux.txt"):
        listed |= set(re.findall(r"^([A-Za-z0-9_.-]+)", read(requirements), re.M))
    assert wanted <= listed, f"imported but not in a requirements file: {sorted(wanted - listed)}"
    assert "pygame" in listed


@test
def the_spec_packs_the_language_files_and_sounds_and_the_entry_point_exists():
    spec = read("tafels.spec")
    assert '"main.py"' in spec and os.path.isfile(os.path.join(HERE, "main.py"))
    for folder in ("lang", "assets/sounds"):
        assert f'("{folder}", "{folder}")' in spec, folder
        assert os.path.isdir(os.path.join(HERE, folder)), folder
    assert os.listdir(os.path.join(HERE, "assets", "sounds")), "the sounds must exist to be packed"
    assert any(f.endswith(".json") for f in os.listdir(os.path.join(HERE, "lang")))
    assert "BUNDLE" in spec and 'sys.platform == "darwin"' in spec, "macOS gets an app bundle"
    assert 'console=(sys.platform != "win32")' in spec, "no console window on Windows"


@test
def the_gitignore_keeps_the_childrens_data_and_old_leftovers_out_of_the_repository():
    import fnmatch
    patterns = [line.strip() for line in read(".gitignore").splitlines()
                if line.strip() and not line.startswith("#")]

    def matches(path, pattern):
        """The part of .gitignore matching that this project uses."""
        parts = path.split("/")
        if pattern.endswith("/"):                       # a folder
            folder = pattern.rstrip("/")
            if "/" in folder:                           # anchored: assets/images/
                return path.startswith(folder + "/")
            return folder in parts[:-1]                 # anywhere: build/, __pycache__/
        return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(parts[-1], pattern)

    def ignored(path):
        return any(matches(path, p) for p in patterns)

    for private in ("leaderboard.json", "settings.json", "selftest-report.txt"):
        assert ignored(private), f"{private} must never be committed (real students' data)"
    for leftover in ("assets/images/anything.png", "sound_test.py", "old/klik.mp3", "dist/Tafels",
                     "__pycache__/x.pyc", "release/Tafels-linux.zip", "Tafels_oefenen.swf"):
        assert ignored(leftover), leftover
    for needed in ("main.py", "lang/nl.json", "lang/en.json", "assets/sounds/goed.wav",
                   "docs/TRANSLATING.md", "tafels.spec", ".github/workflows/build.yml",
                   "requirements.txt"):
        assert not ignored(needed), f"{needed} must be committed"


@test
def the_workflow_tests_then_builds_all_three_systems_and_selftests_each_before_zipping():
    if yaml is None:
        print("   (PyYAML not installed - workflow structure test skipped: pip install pyyaml)")
        return
    workflow = yaml.safe_load(read(".github", "workflows", "build.yml"))
    jobs = workflow["jobs"]
    assert set(jobs) == {"test", "build", "release"}
    triggers = workflow.get("on", workflow.get(True))
    assert {"push", "pull_request", "workflow_dispatch"} <= set(triggers)
    assert "v*" in triggers["push"]["tags"]
    matrix = jobs["build"]["strategy"]["matrix"]["include"]
    assert {m["os"] for m in matrix} == {"ubuntu-latest", "windows-latest", "macos-latest"}
    assert {m["name"] for m in matrix} == {"linux", "windows", "macos"}
    assert jobs["build"]["needs"] == "test" and jobs["release"]["needs"] == "build"
    assert jobs["build"]["strategy"]["fail-fast"] is False, "one failing OS must not hide the others"
    steps = jobs["build"]["steps"]
    commands = [step.get("run", "") for step in steps]
    order = [i for i, c in enumerate(commands) if "PyInstaller" in c]
    selftests = [i for i, c in enumerate(commands) if "--selftest" in c]
    zips = [i for i, c in enumerate(commands) if "package_release.py" in c]
    assert len(order) == 1 and len(selftests) == 2 and len(zips) == 1
    assert order[0] < min(selftests) and max(selftests) < zips[0], "build -> selftest -> zip"
    windows_step = next(st for st in steps if "--selftest" in st.get("run", "") and "Tafels.exe" in st["run"])
    assert windows_step["if"] == "runner.os == 'Windows'"
    other_step = next(st for st in steps if "--selftest" in st.get("run", "") and "Tafels.exe" not in st["run"])
    assert other_step["if"] == "runner.os != 'Windows'" and "Tafels.app/Contents/MacOS/Tafels" in other_step["run"]
    assert any("upload-artifact" in st.get("uses", "") for st in steps)


@test
def the_workflow_only_publishes_for_version_tags_and_only_that_job_may_write():
    if yaml is None:
        return
    workflow = yaml.safe_load(read(".github", "workflows", "build.yml"))
    assert workflow["permissions"] == {"contents": "read"}, "least privilege by default"
    release = workflow["jobs"]["release"]
    assert release["if"] == "startsWith(github.ref, 'refs/tags/v')"
    assert release["permissions"] == {"contents": "write"}
    for name in ("test", "build"):
        assert "permissions" not in workflow["jobs"][name]


@test
def everything_the_workflow_runs_or_installs_exists_in_the_repository():
    import re
    text = read(".github", "workflows", "build.yml")
    for script in set(re.findall(r"python (?:-m \w+ )?(?:--[\w-]+ )?([\w./-]+\.(?:py|spec))", text)):
        assert os.path.isfile(os.path.join(HERE, script)), f"the workflow runs {script}, which is missing"
    for requirements in set(re.findall(r"-r ([\w.-]+\.txt)", text)):
        assert os.path.isfile(os.path.join(HERE, requirements)), requirements
    for action in re.findall(r"uses: ([\w./-]+)@(\S+)", text):
        assert re.fullmatch(r"v\d+", action[1]), f"pin {action[0]} to a major version, got {action[1]}"
    assert "TAFELS_SELFTEST_REPORT" in text and "pyyaml" in text


@test
def the_docs_point_at_things_that_exist_and_explain_the_language_workflow():
    import re
    for doc in ("README.md", os.path.join("docs", "TRANSLATING.md")):
        text = read(doc)
        base = os.path.dirname(os.path.join(HERE, doc))
        for link in re.findall(r"\]\((?!http)([^)#]+)\)", text):
            assert os.path.exists(os.path.join(base, link)), f"{doc}: broken link {link}"
    guide = " ".join(read("docs", "TRANSLATING.md").split())     # (line breaks don't matter)
    for needed in ("check_translation.py --init", "{placeholders}", "exercise.token", "symbol.times",
                   "next to the program", "30%"):
        assert needed in guide, needed
    # the keys the guide names really exist
    import i18n
    keys = i18n.table("en")
    for key in ("choice.start", "hud.round", "board.empty", "exercise.group", "symbol.times"):
        assert key in keys, key


@test
def run_tests_py_finds_every_test_file():
    import glob
    sys.path.insert(0, HERE)
    import run_tests
    found = {os.path.basename(p) for p in glob.glob(os.path.join(HERE, "test_*.py"))}
    assert {"test_i18n.py", "test_packaging.py", "test_exercises.py", "test_keuzescherm.py",
            "test_plusmin_board.py", "test_main_flow.py", "test_theme_audit.py"} <= found
    assert run_tests.SLOW <= found




if __name__ == "__main__":
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", ", ".join(FAILED))
        sys.exit(1)

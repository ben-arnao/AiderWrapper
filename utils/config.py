"""Configuration and build helpers.

Centralizing configuration logic in this module keeps code organized and
reduces the likelihood of merge conflicts in unrelated areas of the
project.
"""
import glob
import os
import configparser  # Read/write simple configuration values
from pathlib import Path  # Locate config file relative to this module
from typing import Optional
import shutil  # Locate executables on the PATH
import subprocess  # Run external commands like git or Unity

# Path to the shared config file sitting next to this module
CONFIG_PATH = Path(__file__).with_name("config.ini")

# File where we remember the last working directory selected by the user.
# Keeping it separate from the main config avoids storing file paths in
# config.ini as per project guidelines.
WORKING_DIR_CACHE_PATH = Path(__file__).with_name("last_working_dir.txt")


def _read_log_tail(log_file: Path, lines: int = 80) -> str:
    """Return the last ``lines`` from ``log_file`` or ``""`` if unavailable.

    Reading the log tail helps surface Unity build errors without dumping the
    entire file into the UI. Any exception while reading is ignored so that
    failures to access the log do not mask the original problem.
    """

    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as fh:
            return "".join(fh.readlines()[-lines:])
    except Exception:
        return ""


def load_default_model(config_path: Path = CONFIG_PATH) -> str:
    """Return the model to use on startup."""
    # Model selection is no longer persisted between sessions, so we always start
    # with the medium quality model (`gpt-5-mini`).
    return "gpt-5-mini"


def save_default_model(model: str, config_path: Path = CONFIG_PATH) -> None:
    """Remember the selected model for the current run only."""
    # The application intentionally forgets the model when it exits, so this
    # function is effectively a no-op. It exists to keep the call sites simple
    # and to make the intent explicit.
    return None


def load_working_dir(cache_path: Path = WORKING_DIR_CACHE_PATH) -> Optional[str]:
    """Return the cached working directory or None if it is missing or empty."""
    if cache_path.exists():
        text = cache_path.read_text().strip()
        # An empty file means no cached path was saved.
        return text or None
    return None


def save_working_dir(path: str, cache_path: Path = WORKING_DIR_CACHE_PATH) -> None:
    """Persist the selected working directory so it can be reloaded later."""
    with open(cache_path, "w") as fh:
        fh.write(path)


def load_usage_days(config_path: Path = CONFIG_PATH) -> int:
    """Return how many days of API usage history to request."""
    config = configparser.ConfigParser()
    if config_path.exists():
        config.read(config_path)
    return config.getint("api", "usage_days", fallback=30)


def _find_unity_exe(config_path: Path = CONFIG_PATH) -> str:
    """Locate the Unity Editor executable using config, env var, or auto-search."""
    cfg = configparser.ConfigParser()
    build_cmd = None

    # 1) Read build_cmd from the optional [build] section of config.ini
    if config_path.exists():
        cfg.read(config_path)
        build_cmd = cfg.get("build", "build_cmd", fallback="").strip() or None

    # 2) Fall back to UNITY_PATH environment variable
    build_cmd = build_cmd or os.environ.get("UNITY_PATH")

    # 3) Auto-discover Unity installations if nothing was specified
    if not build_cmd:
        candidates = glob.glob(r"C:\\Program Files\\Unity\\Hub\\Editor\\*\\Editor\\Unity.exe")
        if candidates:
            # Choose the highest version by sorting the folder names
            build_cmd = sorted(candidates)[-1]

    # 4) Validate that the resulting path points to a file
    if build_cmd and Path(build_cmd).is_file():
        return build_cmd

    raise FileNotFoundError(
        "Unity Editor executable not found.\n"
        "Set config build_cmd to the full path to Unity.exe or define UNITY_PATH.\n"
        "Example: C:\\Program Files\\Unity\\Hub\\Editor\\2022.3.20f1\\Editor\\Unity.exe"
    )


def build_and_launch_game(
    build_cmd=None,
    run_cmd=None,
    project_path=None,
    unity_exe=None,
    method="RogueLike2D.Editor.BuildScript.PerformBuild",
):
    """Build the Unity project then start the resulting executable.

    Parameters
    ----------
    method:
        Fully-qualified Unity method used to trigger the build. The default
        targets ``RogueLike2D.Editor.BuildScript.PerformBuild`` which wraps the
        project's Windows build logic. The command list avoids shell quoting so
        paths with spaces remain intact.
    """
    if build_cmd is None:
        # Resolve ``Unity.exe`` and construct the batch build command.
        unity_exe = unity_exe or _find_unity_exe()
        project_path = project_path or str(
            Path(__file__).resolve().parents[2] / "NoLightUnityProject"
        )
        log_file = Path(project_path) / "Editor.log.batchbuild.txt"
        build_cmd = [
            unity_exe,
            "-batchmode",
            "-nographics",
            "-quit",
            "-projectPath",
            project_path,
            "-executeMethod",
            method,
            "-logFile",
            str(log_file),
        ]
    else:
        log_file = None  # No Unity log when using a custom build command

    if run_cmd is None:
        # Default to launching the Windows build produced by ``BuildScript``.
        run_cmd = [
            str(Path(project_path or ".") / "Builds" / "Windows" / "NoLight.exe")
        ]

    exe_path = build_cmd[0]
    # Ensure the build tool exists either on PATH or as an absolute file.
    if not (shutil.which(exe_path) or Path(exe_path).is_file()):
        raise FileNotFoundError(
            f"Build tool '{exe_path}' not found. Install Unity or provide the full path via build_cmd."
        )

    # Run the build without ``check=True`` so we can surface log output on failure.
    proc = subprocess.run(build_cmd, capture_output=True, text=True)
    stderr_text = proc.stderr.strip()

    if proc.returncode != 0:
        # Non-zero exit means Unity reported a failure; include stderr and log tail
        # so the user can see what went wrong.
        tail = _read_log_tail(log_file) if log_file else ""
        log_display = str(log_file) if log_file else "(no log file)"
        msg = (
            f"Unity batch build failed (exit {proc.returncode}).\n"
            f"Command: {' '.join(build_cmd)}\n\n"
            f"STDERR:\n{stderr_text or '(empty)'}\n\n"
            f"--- Log tail ({log_display}) ---\n{tail or '(log missing)'}"
        )
        raise RuntimeError(msg)

    # Confirm the game binary was produced; if not, surface stderr/log tail for context.
    game_path = Path(run_cmd[0])
    if not game_path.exists():
        tail = _read_log_tail(log_file) if log_file else ""
        log_display = str(log_file) if log_file else "(no log file)"
        msg = (
            f"Game binary '{run_cmd[0]}' not found. Verify the build output path.\n"
            f"STDERR:\n{stderr_text or '(empty)'}\n\n"
            f"--- Log tail ({log_display}) ---\n{tail or '(log missing)'}"
        )
        raise FileNotFoundError(msg)

    # Start the game without waiting for it to exit.
    return subprocess.Popen(run_cmd)

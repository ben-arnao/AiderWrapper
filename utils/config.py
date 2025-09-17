"""Configuration and build helpers.

Centralizing configuration logic in this module keeps code organized and
reduces the likelihood of merge conflicts in unrelated areas of the
project.
"""
import glob
import os
import re  # Inspect Unity scripts for API patterns that need upgrades
import configparser  # Read/write simple configuration values
from pathlib import Path  # Locate config file relative to this module
from typing import Optional
import shutil  # Locate executables on the PATH
import subprocess  # Run external commands like git or Unity

# Path to the shared config file stored at the repository root. Using
# resolve() lets us hop up to the project directory even if utils is
# imported via a symlinked location.
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.ini"

# File where we remember the last working directory selected by the user.
# Keeping it separate from the main config avoids storing file paths in
# config.ini as per project guidelines.
WORKING_DIR_CACHE_PATH = Path(__file__).with_name("last_working_dir.txt")

# Snippet injected into legacy Unity scripts so they work with Unity 6.
# The helper calls the new AssignDefaultActions() API and mirrors the old
# LoadDefaultActions() behavior by returning the module's action asset.
_ASSIGN_HELPER_SNIPPET = (
    "\n"
    "        // Unity 6 removed InputSystemUIInputModule.LoadDefaultActions.\n"
    "        // This helper invokes AssignDefaultActions so the existing\n"
    "        // bootstrap script keeps working without manual edits.\n"
    "        private static UnityEngine.InputSystem.InputActionAsset AssignDefaultUIActions(\n"
    "            UnityEngine.InputSystem.UI.InputSystemUIInputModule module)\n"
    "        {\n"
    "            if (module == null)\n"
    "            {\n"
    "                throw new System.ArgumentNullException(nameof(module));\n"
    "            }\n"
    "\n"
    "            module.AssignDefaultActions();\n"
    "\n"
    "            // The legacy script expects each action to be enabled after setup.\n"
    "            EnableAction(module.move);\n"
    "            EnableAction(module.submit);\n"
    "            EnableAction(module.cancel);\n"
    "            EnableAction(module.point);\n"
    "            EnableAction(module.leftClick);\n"
    "            EnableAction(module.rightClick);\n"
    "            EnableAction(module.middleClick);\n"
    "            EnableAction(module.scrollWheel);\n"
    "            EnableAction(module.trackedDeviceOrientation);\n"
    "            EnableAction(module.trackedDevicePosition);\n"
    "\n"
    "            return module.actionsAsset;\n"
    "        }\n"
    "\n"
    "        // EnableAction safely turns on an InputActionReference if it exists.\n"
    "        private static void EnableAction(UnityEngine.InputSystem.InputActionReference reference)\n"
    "        {\n"
    "            var action = reference?.action;\n"
    "            if (action != null && !action.enabled)\n"
    "            {\n"
    "                action.Enable();\n"
    "            }\n"
    "        }\n"
)


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


def resolve_game_executable(project_path: str, preferred_name: str = "NoLight.exe") -> Path:
    """Return the path to the built Windows game executable.

    Parameters
    ----------
    project_path:
        Root of the Unity project that contains the ``Builds/Windows`` folder.
    preferred_name:
        The expected ``.exe`` name. If it's missing, the first executable in the
        directory is returned instead. A ``FileNotFoundError`` is raised when no
        executables are present.
    """

    out_dir = Path(project_path) / "Builds" / "Windows"
    preferred = out_dir / preferred_name
    if preferred.exists():
        return preferred
    candidates = sorted(out_dir.glob("*.exe"))
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"No .exe found in {out_dir}")


def _find_input_module_variable(text: str) -> Optional[str]:
    """Return the variable name used for ``InputSystemUIInputModule`` instances."""

    # Match declarations like ``InputSystemUIInputModule module = ...`` first.
    explicit = re.search(r"InputSystemUIInputModule\s+(?P<name>\w+)\s*=", text)
    if explicit:
        return explicit.group("name")

    # Fall back to ``var module = ... InputSystemUIInputModule ...`` declarations.
    implicit = re.search(
        r"var\s+(?P<name>\w+)\s*=\s*[^;\n]*InputSystemUIInputModule(?!\s*\.)",
        text,
    )
    if implicit:
        return implicit.group("name")

    # Lastly, try to catch assignments such as ``module = ... InputSystemUIInputModule ...``.
    assignment = re.search(
        r"(?P<name>\w+)\s*=\s*[^;\n]*InputSystemUIInputModule(?!\s*\.)",
        text,
    )
    if assignment:
        return assignment.group("name")
    return None


def _insert_assign_helper(text: str) -> str:
    """Insert the compatibility helper before the class' closing braces."""

    # Look for the final closing braces of the class/namespace pair.
    match = re.search(r"\n\s*\}\s*\n\s*\}\s*$", text)
    if not match:
        # If the expected structure is missing, append the helper at the end.
        return text + _ASSIGN_HELPER_SNIPPET
    idx = match.start()
    return text[:idx] + _ASSIGN_HELPER_SNIPPET + text[idx:]


def _upgrade_input_module_bootstrap(project_root: Path) -> bool:
    """Rewrite legacy Input System API usage when Unity 6 is detected."""

    target = (
        project_root
        / "Assets"
        / "Scripts"
        / "UI"
        / "InputModuleBootstrap.cs"
    )
    if not target.exists():
        # Projects without the script simply continue unmodified.
        return False

    text = target.read_text()
    if "LoadDefaultActions" not in text:
        # Nothing to do when the project already uses the new API.
        return False
    if "AssignDefaultUIActions" in text:
        # The helper was injected previously, so avoid duplicating it.
        return False

    module_var = _find_input_module_variable(text)
    if not module_var:
        # Without a variable to target, we cannot safely rewrite the file.
        return False

    # Replace the deprecated static call with the helper that wraps AssignDefaultActions().
    new_text, replacements = re.subn(
        r"InputSystemUIInputModule\.LoadDefaultActions\s*\(\s*\)",
        f"AssignDefaultUIActions({module_var})",
        text,
    )
    if replacements == 0:
        return False

    # Append the compatibility helper so the rewritten call compiles.
    new_text = _insert_assign_helper(new_text)
    target.write_text(new_text)
    return True


def build_and_launch_game(
    build_cmd=None,
    run_cmd=None,
    project_path=None,
    unity_exe=None,
    method="RogueLike2D.Editor.BuildScript.PerformWindowsBuild",
):
    """Build the Unity project then start the resulting executable.

    Parameters
    ----------
    method:
        Fully-qualified Unity method used to trigger the build. The default
        targets ``RogueLike2D.Editor.BuildScript.PerformWindowsBuild`` which wraps the
        project's Windows build logic. The command list avoids shell quoting so
        paths with spaces remain intact.
    """

    # Determine the Unity project path if none was provided.
    if project_path is None:
        project_root = Path(__file__).resolve().parents[2] / "NoLightUnityProject"
    else:
        project_root = Path(project_path)
    # Upgrade Unity scripts before invoking the build so compilation succeeds.
    _upgrade_input_module_bootstrap(project_root)
    project_path = str(project_root)

    if run_cmd is None:
        # Preferred name for the built game; Unity may produce a different one.
        run_cmd = [
            str(Path(project_path) / "Builds" / "Windows" / "NoLight.exe")
        ]

    if build_cmd is None:
        # Resolve ``Unity.exe`` and construct the batch build command.
        unity_exe = unity_exe or _find_unity_exe()
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
            "-customBuildPath",
            run_cmd[0],
            "-logFile",
            str(log_file),
        ]
    else:
        log_file = None  # No Unity log when using a custom build command

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

    # Confirm the game binary was produced; fall back to any .exe if the
    # preferred name is missing so a successful build still launches.
    game_path = Path(run_cmd[0])
    if not game_path.exists():
        try:
            game_path = resolve_game_executable(project_path, game_path.name)
        except FileNotFoundError:
            tail = _read_log_tail(log_file) if log_file else ""
            log_display = str(log_file) if log_file else "(no log file)"
            msg = (
                f"Game binary '{run_cmd[0]}' not found. Verify the build output path.\n"
                f"STDERR:\n{stderr_text or '(empty)'}\n\n"
                f"--- Log tail ({log_display}) ---\n{tail or '(log missing)'}"
            )
            raise FileNotFoundError(msg)

    # Start the game without waiting for it to exit.
    run_cmd = [str(game_path)]
    return subprocess.Popen(run_cmd)

import os
import re
import configparser  # Read/write simple configuration values
from pathlib import Path  # Locate config file relative to this module
from typing import Callable, Optional

import subprocess  # Run git commands to gather commit statistics
import requests

# Patterns to filter noisy warnings when no TTY is attached
NO_TTY_PATTERNS = [
    r"^Can't initialize prompt toolkit: No Windows console found",
    r"^Terminal does not support pretty output",
]

# Compile regexes once at module import for efficiency
NO_TTY_REGEXES = [re.compile(pat) for pat in NO_TTY_PATTERNS]

# Regexes used to detect when aider is asking for additional input from the user.
# We look for lines that begin with "Please" and end with a question mark as a
# simple heuristic for interactive prompts.
USER_INPUT_PATTERNS = [r"^Please .+\?$"]
USER_INPUT_REGEXES = [re.compile(pat, re.IGNORECASE) for pat in USER_INPUT_PATTERNS]

# Path to the shared config file sitting next to this module
CONFIG_PATH = Path(__file__).with_name("config.ini")

# File where we remember the last working directory selected by the user.
# Keeping it separate from the main config avoids storing file paths in
# config.ini as per project guidelines.
WORKING_DIR_CACHE_PATH = Path(__file__).with_name("last_working_dir.txt")

# Regex used to detect commit hashes in aider output
COMMIT_RE = re.compile(r"(?:Committed|commit) ([0-9a-f]{7,40})", re.IGNORECASE)


def sanitize(text: str) -> str:
    """Remove newlines and quotes, and collapse whitespace to single spaces."""
    text = text.replace("\n", " ").replace("\r", " ")
    text = text.replace('"', '').replace("'", "")
    # Collapse any run of whitespace into a single space and trim
    text = re.sub(r"\s+", " ", text).strip()
    return text


def should_suppress(line: str) -> bool:
    """Return True if the line matches known warnings to suppress."""
    return any(rx.search(line) for rx in NO_TTY_REGEXES)


def verify_api_key(api_key: str, request_fn: Callable = requests.get) -> bool:
    """Call OpenAI API to ensure the provided key is valid.

    Raises
    ------
    ValueError
        If the key is missing or the API responds with an error. The error
        message includes the status code and response text for easier
        debugging.
    """
    if not api_key:
        raise ValueError("API key not provided")

    resp = request_fn(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if resp.status_code == 200:
        return True
    # Surface details so the caller can display them to the user
    raise ValueError(
        f"API key validation failed: {resp.status_code} {getattr(resp, 'text', '')}"
    )


def load_timeout(config_path: Path = CONFIG_PATH) -> int:
    """Return timeout (minutes) from config or default to 5.

    The config file uses a [ui] section; if it or the key is missing,
    a default of 5 minutes is returned.
    """
    config = configparser.ConfigParser()
    if config_path.exists():
        config.read(config_path)
    return config.getint("ui", "timeout_minutes", fallback=5)


def save_timeout(value: int, config_path: Path = CONFIG_PATH) -> None:
    """Persist the timeout value back to the config file.

    Any existing configuration values (e.g. the default model) are preserved so
    that updates feel "real-time" and no settings are lost when another one is
    changed.
    """
    config = configparser.ConfigParser()
    if config_path.exists():
        config.read(config_path)
    # Ensure required sections exist before assigning values
    if "ui" not in config:
        config["ui"] = {}
    config["ui"]["timeout_minutes"] = str(value)
    with open(config_path, "w") as fh:
        config.write(fh)


def load_default_model(config_path: Path = CONFIG_PATH) -> str:
    """Return the model to use on startup.

    Model selection is no longer persisted between sessions, so we always start
    with the medium quality model (`gpt-5-mini`).
    """

    # Always use the medium model regardless of any existing config file.
    return "gpt-5-mini"


def save_default_model(model: str, config_path: Path = CONFIG_PATH) -> None:
    """Remember the selected model for the current run only.

    The application intentionally forgets the model when it exits, so this
    function is effectively a no-op. It exists to keep the call sites simple
    and to make the intent explicit.
    """

    # Do nothing so no config file is written.
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


def extract_commit_id(text: str) -> Optional[str]:
    """Return the first commit hash found in the text or None."""
    match = COMMIT_RE.search(text)
    return match.group(1) if match else None


def needs_user_input(line: str) -> bool:
    """Return True if the line indicates aider expects more information.

    The check is intentionally lightweight. If the line starts with the word
    "Please" and ends with a question mark, we assume aider is prompting the
    user for additional input and the UI should stop waiting for a commit id.
    """

    stripped = line.strip()
    return any(rx.match(stripped) for rx in USER_INPUT_REGEXES)


def get_commit_stats(commit_id: str, repo_path: str) -> dict:
    """Return line and file change counts for a given commit.

    Parameters
    ----------
    commit_id:
        The hash of the commit to inspect.
    repo_path:
        Path to the git repository containing the commit.

    Returns
    -------
    dict
        Mapping with line counts (added/removed/changed), file counts
        (added/removed/changed), and a short description of the commit.

    Raises
    ------
    RuntimeError
        If any git command fails. Callers are expected to handle this so the
        UI can surface a helpful message rather than silently continuing.
    """

    # Gather insertion/deletion counts for the commit using --shortstat.
    shortstat_cmd = ["git", "show", "--shortstat", commit_id]
    shortstat = subprocess.run(
        shortstat_cmd, cwd=repo_path, capture_output=True, text=True, check=True
    ).stdout

    # Initialize counters for lines and files.
    lines_added = lines_removed = 0
    files_changed = files_added = files_removed = 0

    # The shortstat output ends with a summary line like:
    # "1 file changed, 2 insertions(+), 1 deletion(-)"
    for line in shortstat.splitlines():
        if "file" in line and "changed" in line:
            m = re.search(r"(\d+) insertions?", line)
            lines_added = int(m.group(1)) if m else 0
            m = re.search(r"(\d+) deletions?", line)
            lines_removed = int(m.group(1)) if m else 0

    # Determine how many files were added, deleted, or modified.
    diff_cmd = [
        "git",
        "diff-tree",
        "--no-commit-id",
        "--name-status",
        "--root",  # Include changes from the initial commit
        "-r",
        commit_id,
    ]
    diff_out = subprocess.run(
        diff_cmd, cwd=repo_path, capture_output=True, text=True, check=True
    ).stdout

    for line in diff_out.splitlines():
        status, _path = line.split("\t", 1)
        if status == "A":
            files_added += 1
        elif status == "D":
            files_removed += 1
        else:  # Treat anything else (M/R/C) as a modified file
            files_changed += 1

    # The commit title serves as a short description for the history table.
    msg_cmd = ["git", "log", "-1", "--format=%s", commit_id]
    description = subprocess.run(
        msg_cmd, cwd=repo_path, capture_output=True, text=True, check=True
    ).stdout.strip()

    return {
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "lines_changed": lines_added + lines_removed,
        "files_added": files_added,
        "files_removed": files_removed,
        "files_changed": files_changed,
        "description": description,
    }

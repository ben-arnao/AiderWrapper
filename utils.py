import os
import re
import configparser  # Read/write simple configuration values
from pathlib import Path  # Locate config file relative to this module
from typing import Callable

import requests

# Patterns to filter noisy warnings when no TTY is attached
NO_TTY_PATTERNS = [
    r"^Can't initialize prompt toolkit: No Windows console found",
    r"^Terminal does not support pretty output",
]

# Compile regexes once at module import for efficiency
NO_TTY_REGEXES = [re.compile(pat) for pat in NO_TTY_PATTERNS]

# Path to the shared config file sitting next to this module
CONFIG_PATH = Path(__file__).with_name("config.ini")

# File where we remember the last Unity project directory selected by the user.
# Keeping it separate from the main config avoids storing file paths in
# config.ini as per project guidelines.
PROJECT_CACHE_PATH = Path(__file__).with_name("last_project_dir.txt")

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


def verify_unity_project(path: os.PathLike) -> bool:
    """Basic Unity project check: ensure Assets folder and ProjectSettings/ProjectVersion.txt exist."""
    path = os.fspath(path)
    assets = os.path.join(path, "Assets")
    proj_version = os.path.join(path, "ProjectSettings", "ProjectVersion.txt")
    return os.path.isdir(assets) and os.path.isfile(proj_version)


def verify_api_key(api_key: str, request_fn: Callable = requests.get) -> bool:
    """Call OpenAI API to ensure the provided key is valid. Raises ValueError on failure."""
    if not api_key:
        raise ValueError("API key not provided")

    resp = request_fn(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if resp.status_code == 200:
        return True
    raise ValueError("API key validation failed")


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
    """Persist the timeout value back to the config file."""
    config = configparser.ConfigParser()
    config["ui"] = {"timeout_minutes": str(value)}
    with open(config_path, "w") as fh:
        config.write(fh)


def load_project_dir(cache_path: Path = PROJECT_CACHE_PATH) -> str | None:
    """Return the cached Unity project path or None if it is missing or empty."""
    if cache_path.exists():
        text = cache_path.read_text().strip()
        # An empty file means no cached path was saved.
        return text or None
    return None


def save_project_dir(path: str, cache_path: Path = PROJECT_CACHE_PATH) -> None:
    """Persist the selected Unity project path so it can be reloaded later."""
    with open(cache_path, "w") as fh:
        fh.write(path)


def extract_commit_id(text: str) -> str | None:
    """Return the first commit hash found in the text or None."""
    match = COMMIT_RE.search(text)
    return match.group(1) if match else None

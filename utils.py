import os
import re
import configparser  # Read/write simple configuration values
from pathlib import Path  # Locate config file relative to this module
from typing import Callable, Optional

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
    """Return the default model choice stored in config or a sensible fallback."""
    config = configparser.ConfigParser()
    if config_path.exists():
        config.read(config_path)
    return config.get("aider", "default_model", fallback="gpt-5-mini")


def save_default_model(model: str, config_path: Path = CONFIG_PATH) -> None:
    """Persist the selected model so it can be restored on next launch."""
    config = configparser.ConfigParser()
    if config_path.exists():
        config.read(config_path)
    if "aider" not in config:
        config["aider"] = {}
    config["aider"]["default_model"] = model
    # Make sure we don't lose other sections such as [ui]
    with open(config_path, "w") as fh:
        config.write(fh)


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

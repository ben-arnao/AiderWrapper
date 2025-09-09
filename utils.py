import os
import re
from typing import Callable

import requests

# Patterns to filter noisy warnings when no TTY is attached
NO_TTY_PATTERNS = [
    r"^Can't initialize prompt toolkit: No Windows console found",
    r"^Terminal does not support pretty output",
]

# Compile regexes once at module import for efficiency
NO_TTY_REGEXES = [re.compile(pat) for pat in NO_TTY_PATTERNS]


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

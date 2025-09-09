"""Text and prompt related helper functions.

These functions operate on raw strings to sanitize content and detect
user prompts in aider's output. Keeping them separate from other
utilities helps avoid merge conflicts in unrelated areas of the
codebase.
"""
import re
from typing import Optional

# Patterns to filter noisy warnings when no TTY is attached
NO_TTY_PATTERNS = [
    r"^Can't initialize prompt toolkit: No Windows console found",
    r"^Terminal does not support pretty output",
]

# Compile regexes once at module import for efficiency
NO_TTY_REGEXES = [re.compile(pat) for pat in NO_TTY_PATTERNS]

# Regexes used to detect when aider is asking for additional input from the user.
# Besides direct questions beginning with "Please ...?", aider often prints
# conversational hints such as "I will stop here so you can add them to the chat"
# or "Reply with answers".  We keep the patterns broad so new phrasing still
# triggers a prompt for the user.
USER_INPUT_PATTERNS = [
    r"^Please .+\?$",              # Explicit question
    r"add (?:them|the files) to the chat",  # Requests to attach files
    r"stop here so you can",        # Aider pauses for more info
    r"reply with answers",          # Explicit instruction to respond
]
# Compile regexes with IGNORECASE so minor variations are still matched.
USER_INPUT_REGEXES = [re.compile(pat, re.IGNORECASE) for pat in USER_INPUT_PATTERNS]

# Regex used to extract dollar amounts from aider output
COST_RE = re.compile(r"\$([0-9]+(?:\.[0-9]+)?)")


def sanitize(text: str) -> str:
    """Remove newlines and quotes, and collapse whitespace to single spaces."""
    # Replace newlines with spaces so everything fits on one line
    text = text.replace("\n", " ").replace("\r", " ")
    # Strip out all quote characters which might break shell commands
    text = text.replace('"', '').replace("'", "")
    # Collapse any run of whitespace into a single space and trim
    text = re.sub(r"\s+", " ", text).strip()
    return text


def should_suppress(line: str) -> bool:
    """Return True if the line matches known warnings to suppress."""
    # Check each compiled regex to see if the line is a noisy warning
    return any(rx.search(line) for rx in NO_TTY_REGEXES)


def extract_cost(text: str) -> Optional[float]:
    """Return the first dollar amount found in the text or ``None``."""
    # Search for a dollar sign followed by a number and optional cents
    match = COST_RE.search(text)
    return float(match.group(1)) if match else None


def needs_user_input(line: str) -> bool:
    """Return True if the line indicates aider expects more information."""
    # Trim whitespace so prefix/suffix spaces don't defeat detection
    stripped = line.strip()
    # Use ``search`` instead of ``match`` so patterns can appear anywhere in
    # the line.  This lets us catch phrases like "I will stop here so you can"
    # that do not begin the line.
    return any(rx.search(stripped) for rx in USER_INPUT_REGEXES)

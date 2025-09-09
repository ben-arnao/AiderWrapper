"""Git-related helpers for working with commit information.

Functions here parse commit identifiers from text, query git for
statistics, and format data for the history table in the UI. By keeping
all git logic in one module we reduce the likelihood of merge
conflicts elsewhere in the project.
"""
import re
import subprocess
from typing import Optional

# Regex used to detect commit hashes in aider output
COMMIT_RE = re.compile(r"(?:Committed|commit) ([0-9a-f]{7,40})", re.IGNORECASE)

# Default column widths for the history table. ID and count columns stay
# compact while textual fields get extra room for readability.
HISTORY_COL_WIDTHS = {
    "request_id": 80,
    "commit_id": 80,
    "lines": 60,
    "files": 60,
    "failure_reason": 200,
    "description": 300,
}


def extract_commit_id(text: str) -> Optional[str]:
    """Return the first commit hash found in the text or None."""
    # Look for the commit pattern anywhere in the given text
    match = COMMIT_RE.search(text)
    return match.group(1) if match else None


def get_commit_stats(commit_id: str, repo_path: str) -> dict:
    """Return line and file change counts for a given commit."""
    # Gather insertion/deletion counts for the commit using --shortstat
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


def abbreviate(value: Optional[str], length: int = 8) -> str:
    """Return the first ``length`` characters of ``value`` for compact display."""
    # Empty values result in an empty string
    if not value:
        return ""
    return value[:length]


def format_history_row(rec: dict) -> tuple:
    """Return display-friendly values for a history record."""
    # Abbreviate IDs so the history table stays compact
    return (
        abbreviate(rec.get("request_id")),
        abbreviate(rec.get("commit_id")),
        rec.get("lines", 0),
        rec.get("files", 0),
        rec.get("failure_reason", ""),
        rec.get("description", ""),
    )

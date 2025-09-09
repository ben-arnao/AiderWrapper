"""Convenience re-exports for utility helpers.

The package is split into multiple modules to minimize merge conflicts,
but common functions are re-exported here for backwards compatibility.
"""
from .text import sanitize, should_suppress, extract_cost, needs_user_input
from .git import (
    extract_commit_id,
    get_commit_stats,
    format_history_row,
    HISTORY_COL_WIDTHS,
)
from .config import (
    load_default_model,
    save_default_model,
    load_working_dir,
    save_working_dir,
    load_usage_days,
    build_and_launch_game,
)
from .api import verify_api_key, fetch_usage_data

__all__ = [
    "sanitize",
    "should_suppress",
    "extract_cost",
    "needs_user_input",
    "extract_commit_id",
    "get_commit_stats",
    "format_history_row",
    "HISTORY_COL_WIDTHS",
    "load_default_model",
    "save_default_model",
    "load_working_dir",
    "save_working_dir",
    "load_usage_days",
    "build_and_launch_game",
    "verify_api_key",
    "fetch_usage_data",
]

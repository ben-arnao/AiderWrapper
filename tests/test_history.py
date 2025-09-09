import sys
from pathlib import Path

# Ensure project root is on path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import utils


def test_format_history_row_truncates_ids():
    """IDs should be abbreviated to keep history rows compact."""
    rec = {
        "request_id": "1234567890abcdef",  # Longer than display length
        "commit_id": "fedcba0987654321",  # Longer than display length
        "lines": 12,
        "files": 3,
        "failure_reason": "oops",
        "description": "something happened",
    }
    row = utils.format_history_row(rec)
    # Only the first 8 characters should remain for the IDs
    assert row[0] == "12345678"
    assert row[1] == "fedcba09"
    # The rest of the fields should pass through unchanged
    assert row[2:] == (12, 3, "oops", "something happened")


def test_history_column_width_defaults():
    """History table should allocate more space for text fields."""
    expected = {
        "request_id": 80,
        "commit_id": 80,
        "lines": 60,
        "files": 60,
        "failure_reason": 200,
        "description": 300,
    }
    assert utils.HISTORY_COL_WIDTHS == expected

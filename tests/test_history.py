import sys
from pathlib import Path

# Ensure project root is on path
sys.path.append(str(Path(__file__).resolve().parents[1]))

# Import git-related helpers directly from the utils package
from utils.git import (
    format_history_row,
    format_history_row_full,
    history_records_to_tsv,
    HISTORY_COL_WIDTHS,
)


def test_format_history_row_truncates_ids():
    """IDs should be abbreviated to keep history rows compact."""
    rec = {
        "request_id": "1234567890abcdef",  # Longer than display length
        "commit_id": "fedcba0987654321",  # Longer than display length
        "lines": 12,
        "files": 3,
        "cost": 1.23,
        "failure_reason": "oops",
        "description": "something happened",
    }
    row = format_history_row(rec)
    # Only the first 8 characters should remain for the IDs
    assert row[0] == "12345678"
    assert row[1] == "fedcba09"
    # The rest of the fields should pass through unchanged
    assert row[2:] == (12, 3, 1.23, "oops", "something happened")


def test_history_column_width_defaults():
    """History table should allocate more space for text fields."""
    expected = {
        "request_id": 80,
        "commit_id": 80,
        "lines": 60,
        "files": 60,
        "cost": 80,
        "failure_reason": 200,
        "description": 300,
    }
    assert HISTORY_COL_WIDTHS == expected


def test_format_history_row_full_preserves_ids():
    """Full rows should return entire IDs without abbreviation."""
    rec = {
        "request_id": "1234567890abcdef",
        "commit_id": "fedcba0987654321",
        "lines": 12,
        "files": 3,
        "cost": 1.23,
        "failure_reason": "oops",
        "description": "something happened",
    }
    row = format_history_row_full(rec)
    # IDs should not be truncated when using the full formatter
    assert row[0] == "1234567890abcdef"
    assert row[1] == "fedcba0987654321"
    assert row[2:] == (12, 3, 1.23, "oops", "something happened")


def test_history_records_to_tsv_uses_full_values():
    """Clipboard export should include full values for each record."""
    recs = [
        {
            "request_id": "1234567890abcdef",
            "commit_id": "fedcba0987654321",
            "lines": 1,
            "files": 2,
            "cost": 0.1,
            "failure_reason": "",
            "description": "first",
        },
        {
            "request_id": "abcdef1234567890",
            "commit_id": "0123456789abcdef",
            "lines": 3,
            "files": 4,
            "cost": 0.2,
            "failure_reason": "fail",
            "description": "second",
        },
    ]
    tsv = history_records_to_tsv(recs)
    lines = tsv.splitlines()
    # First row should start with the full request and commit IDs
    assert lines[0].startswith("1234567890abcdef\tfedcba0987654321")
    # Second row should contain the second set of IDs
    assert lines[1].startswith("abcdef1234567890\t0123456789abcdef")

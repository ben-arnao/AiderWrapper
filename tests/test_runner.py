import sys
from pathlib import Path

# Ensure project root is on path so we can import the package
sys.path.append(str(Path(__file__).resolve().parents[1]))

from nolight import runner


def test_record_request_success():
    """Stats should populate line and file totals."""
    runner.request_history.clear()
    stats = {
        "lines_changed": 5,
        "files_changed": 1,
        "files_added": 0,
        "files_removed": 0,
        "description": "demo",
    }
    runner.record_request("id1", "abc123", stats)
    rec = runner.request_history[0]
    assert rec["commit_id"] == "abc123"
    assert rec["lines"] == 5
    assert rec["files"] == 1
    assert rec["failure_reason"] is None
    assert rec["description"] == "demo"


def test_record_request_failure():
    """Failures should record the reason and zero counts."""
    runner.request_history.clear()
    runner.record_request("id2", None, failure_reason="timeout")
    rec = runner.request_history[0]
    assert rec["commit_id"] is None
    assert rec["lines"] == 0
    assert rec["files"] == 0
    assert rec["failure_reason"] == "timeout"

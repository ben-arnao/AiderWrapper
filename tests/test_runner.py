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


class DummyWidget:
    """Minimal stand-in for a Tk text widget used in tests."""

    def __init__(self):
        self.content = "hello"
        self.state = "normal"

    def configure(self, state: str) -> None:
        # Store the state but ignore it otherwise.
        self.state = state

    def delete(self, start: str, end: str) -> None:
        # Simulate clearing all text from the widget.
        self.content = ""


def test_maybe_clear_output_resets_when_flag_set():
    """Output should be cleared and flag reset when marked for reset."""
    widget = DummyWidget()
    runner.reset_on_new_request = True
    runner.request_active = False
    runner.maybe_clear_output(widget)
    assert widget.content == ""
    assert runner.reset_on_new_request is False


def test_maybe_clear_output_no_reset_when_flag_unset():
    """Widget remains unchanged if reset flag is not set."""
    widget = DummyWidget()
    widget.content = "stay"
    runner.reset_on_new_request = False
    runner.request_active = False
    runner.maybe_clear_output(widget)
    assert widget.content == "stay"

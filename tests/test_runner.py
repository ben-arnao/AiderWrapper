import sys
from pathlib import Path
import io
import pytest

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
    assert rec["cost"] == 0.0
    assert rec["failure_reason"] is None
    assert rec["description"] == "demo"


def test_record_request_failure():
    """Failures should record the reason and zero counts."""
    runner.request_history.clear()
    runner.record_request("id2", None, failure_reason="error")
    rec = runner.request_history[0]
    assert rec["commit_id"] is None
    assert rec["lines"] == 0
    assert rec["files"] == 0
    assert rec["cost"] == 0.0
    assert rec["failure_reason"] == "error"


def test_run_aider_records_exit_reason(monkeypatch):
    """run_aider should store exit code and last line on failure."""
    runner.request_history.clear()

    # Simple stand-ins for the Tk widgets so run_aider can interact with them
    class DummyText:
        def __init__(self):
            self.text = ""

        def insert(self, _idx, txt):
            self.text += txt  # Append text to mimic a Tk widget

        def see(self, _idx):
            pass

        def configure(self, **kwargs):
            pass

        def config(self, **kwargs):
            pass

        def focus_set(self):
            pass

    class DummyVar:
        def __init__(self):
            self.value = ""

        def set(self, _val):
            # Remember the last status message set by the runner
            self.value = _val

    class DummyLabel:
        def config(self, **kwargs):
            pass

        def unbind(self, *_args, **_kwargs):
            pass

    # Mock Popen to simulate aider exiting with an error
    class MockPopen:
        def __init__(self, *args, **kwargs):
            # Provide two lines of output, the last being an error
            self.stdout = io.StringIO("ok\nboom\n")
            self.returncode = 2

        def wait(self):
            return self.returncode

        def kill(self):
            pass

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: MockPopen())

    output = DummyText()
    txt_input = DummyText()
    status_var = DummyVar()
    status_label = DummyLabel()

    runner.run_aider(
        msg="hi",
        output_widget=output,
        txt_input=txt_input,
        work_dir=".",
        model="gpt-5",
        status_var=status_var,
        status_label=status_label,
        request_id="req1",
    )

    rec = runner.request_history[0]
    assert rec["failure_reason"] == "aider exited with code 2: boom"
    assert rec["cost"] == 0.0
    # The status message should mention the request id and failure reason
    assert status_var.value == "Request req1: failed - aider exited with code 2: boom"


def test_run_aider_reports_empty_output(monkeypatch):
    """If aider exits silently, a placeholder reason should be recorded."""

    runner.request_history.clear()

    class DummyText:
        def __init__(self):
            self.text = ""

        def insert(self, _idx, txt):
            # Append any text that runner writes to mimic a Tk widget.
            self.text += txt

        def see(self, _idx):
            pass

        def configure(self, **kwargs):
            pass

        def config(self, **kwargs):
            pass

        def focus_set(self):
            pass

    class DummyVar:
        def __init__(self):
            self.value = ""

        def set(self, _val):
            # Remember the last status message for assertions.
            self.value = _val

    class DummyLabel:
        def config(self, **kwargs):
            pass

        def unbind(self, *_args, **_kwargs):
            pass

    class MockPopen:
        def __init__(self, *args, **kwargs):
            # Simulate aider producing no output before exiting with an error.
            self.stdout = io.StringIO("")
            self.returncode = 1

        def wait(self):
            return self.returncode

        def kill(self):
            pass

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: MockPopen())

    output = DummyText()
    txt_input = DummyText()
    status_var = DummyVar()
    status_label = DummyLabel()

    runner.run_aider(
        msg="hi",
        output_widget=output,
        txt_input=txt_input,
        work_dir=".",
        model="gpt-5",
        status_var=status_var,
        status_label=status_label,
        request_id="req1",
    )

    rec = runner.request_history[0]
    # The failure reason should include our placeholder message.
    assert rec["failure_reason"] == "aider exited with code 1: no output captured"
    assert status_var.value == "Request req1: failed - aider exited with code 1: no output captured"


def test_run_aider_records_cost(monkeypatch):
    """run_aider should parse cost lines and track session totals."""
    runner.request_history.clear()
    runner.session_total_cost = 0.0

    class DummyText:
        def __init__(self):
            self.text = ""

        def insert(self, _idx, txt):
            self.text += txt

        def see(self, _idx):
            pass

        def configure(self, **kwargs):
            pass

        def config(self, **kwargs):
            pass

        def focus_set(self):
            pass

    class DummyVar:
        def __init__(self):
            self.value = ""

        def set(self, _val):
            self.value = _val

    class DummyLabel:
        def config(self, **kwargs):
            pass

        def unbind(self, *_args, **_kwargs):
            pass

    class MockPopen:
        def __init__(self, *args, **kwargs):
            # Include cost line so the runner can parse it
            self.stdout = io.StringIO(
                "Committed abcdef1\nTokens: cost line\nCost: $0.50 message, $0.50 session.\n"
            )
            self.returncode = 0

        def wait(self):
            return self.returncode

        def kill(self):
            pass

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: MockPopen())
    monkeypatch.setattr(
        runner, "get_commit_stats", lambda commit, repo: {"lines_changed": 0, "files_changed": 0, "files_added": 0, "files_removed": 0, "description": "d"}
    )

    output = DummyText()
    txt_input = DummyText()
    status_var = DummyVar()
    status_label = DummyLabel()

    runner.run_aider(
        msg="hi",
        output_widget=output,
        txt_input=txt_input,
        work_dir=".",
        model="gpt-5",
        status_var=status_var,
        status_label=status_label,
        request_id="req1",
    )

    rec = runner.request_history[0]
    assert rec["cost"] == pytest.approx(0.50)
    assert runner.session_total_cost == pytest.approx(0.50)


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


def test_update_status_sets_message_and_color():
    """update_status should set both the text and the color."""

    class DummyVar:
        def __init__(self):
            self.value = ""

        def set(self, value):
            # Store the last message assigned to the variable
            self.value = value

    class DummyLabel:
        def __init__(self):
            self.fg = ""

        def config(self, **kwargs):
            # Capture the requested foreground color
            self.fg = kwargs.get("foreground", self.fg)

    var = DummyVar()
    lbl = DummyLabel()
    runner.update_status(var, lbl, "hello", "green")
    assert var.value == "hello"
    assert lbl.fg == "green"

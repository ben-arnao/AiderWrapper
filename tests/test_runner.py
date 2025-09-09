import sys
from pathlib import Path
import types

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
    assert rec["failure_reason"] == "error"


def test_run_aider_records_commit(monkeypatch, tmp_path):
    """A commit hash in aider's output should record the request and end the run."""

    class DummyText:
        """Simplified stand-in for Tk's Text widget."""

        def __init__(self):
            self.state = "normal"

        def configure(self, **_):
            pass

        def insert(self, _idx, _text):
            pass

        def see(self, _idx):
            pass

        def config(self, **kwargs):  # for txt_input
            self.state = kwargs.get("state", self.state)

        def focus_set(self):
            pass

    class DummyVar:
        def __init__(self):
            self.value = ""

        def set(self, value):
            self.value = value

    class DummyLabel:
        def config(self, **_):
            pass

        def unbind(self, _):
            pass

    # Simulate aider emitting a commit line
    lines = iter(["Committed abcdef1 add feature\n"])

    class FakeProc:
        def __init__(self):
            self.stdout = lines
            self.returncode = 0

        def kill(self):
            pass

        def wait(self):
            pass

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: FakeProc())
    monkeypatch.setattr(
        runner,
        "get_commit_stats",
        lambda cid, wd: {"lines_changed": 1, "files_changed": 0, "files_added": 0, "files_removed": 0, "description": "msg"},
    )

    out = DummyText()
    inp = DummyText()
    var = DummyVar()
    lbl = DummyLabel()

    runner.request_history.clear()
    runner.request_active = True
    runner.run_aider("msg", out, inp, str(tmp_path), "model", var, lbl, "req1")

    assert runner.request_history[0]["commit_id"] == "abcdef1"
    assert not runner.request_active  # run ended after commit
    assert "Successfully" in var.value


def test_run_aider_waits_on_user(monkeypatch, tmp_path):
    """When aider requests input, the run should stop without recording a commit."""

    class DummyText:
        def __init__(self):
            self.state = "normal"

        def configure(self, **_):
            pass

        def insert(self, _idx, _text):
            pass

        def see(self, _idx):
            pass

        def config(self, **kwargs):
            self.state = kwargs.get("state", self.state)

        def focus_set(self):
            pass

    class DummyVar:
        def __init__(self):
            self.value = ""

        def set(self, value):
            self.value = value

    class DummyLabel:
        def config(self, **_):
            pass

        def unbind(self, _):
            pass

    # Line mimics aider asking for more details
    lines = iter([
        "Please add README.md to the chat so I can generate the exact SEARCH/REPLACE blocks?\n"
    ])

    class FakeProc:
        def __init__(self):
            self.stdout = lines
            self.returncode = 0
            self.killed = False

        def kill(self):
            self.killed = True

        def wait(self):
            pass

    fake = FakeProc()
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: fake)

    out = DummyText()
    inp = DummyText()
    var = DummyVar()
    lbl = DummyLabel()

    runner.request_history.clear()
    runner.request_active = True
    runner.run_aider("msg", out, inp, str(tmp_path), "model", var, lbl, "req2")

    assert runner.request_history == []  # no commit recorded
    assert runner.request_active  # still waiting for follow-up input
    assert "waiting" in var.value.lower()
    assert fake.killed  # process should be terminated

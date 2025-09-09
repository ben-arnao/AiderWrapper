"""Tests for the top-level build-and-run button logic."""

import sys
from pathlib import Path

# Ensure project root is on path so the UI module can be imported
sys.path.append(str(Path(__file__).resolve().parents[1]))

import nolight.app as app


def test_launch_game_invokes_builder(monkeypatch):
    """Successful builds should call the builder and show no error."""

    calls = []

    def fake_build():
        """Pretend to build the game successfully."""
        calls.append("build")

    # Replace the real build function with our fake to capture invocation.
    monkeypatch.setattr(app, "build_and_launch_game", fake_build)
    # Stub out the error dialog to ensure it is not triggered on success.
    monkeypatch.setattr(app.messagebox, "showerror", lambda *_: calls.append("error"))

    app.launch_game()

    # Only the build function should have been called.
    assert calls == ["build"]


def test_launch_game_shows_error_on_failure(monkeypatch):
    """Failures should surface to the user via a dialog."""

    errors = []

    def fake_build():
        """Simulate the build step raising an error."""
        raise FileNotFoundError("missing unity")

    monkeypatch.setattr(app, "build_and_launch_game", fake_build)
    monkeypatch.setattr(app.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    app.launch_game()

    # The error dialog should report the reason for the failure.
    assert errors == [("Build failed", "missing unity")]


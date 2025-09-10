"""Tests for the top-level build-and-run button logic."""

import sys
from pathlib import Path

# Bring in Tkinter for widget construction and pytest for skipping when unavailable.
import tkinter as tk
import pytest

# Ensure project root is on path so the UI module can be imported
sys.path.append(str(Path(__file__).resolve().parents[1]))

import nolight.app as app


def test_launch_game_invokes_builder(monkeypatch):
    """Successful builds should call the builder with the selected path."""

    calls = []

    def fake_build(*, project_path):
        """Pretend to build the game successfully."""
        # Record the project path to ensure it was forwarded correctly.
        calls.append(project_path)

    # Replace the real build function with our fake to capture invocation.
    monkeypatch.setattr(app, "build_and_launch_game", fake_build)
    # Stub out the error dialog to ensure it is not triggered on success.
    monkeypatch.setattr(app, "show_build_error", lambda *_: calls.append("error"))

    app.launch_game("/tmp/project")

    # Only the build function should have been called with the given path.
    assert calls == ["/tmp/project"]


def test_launch_game_shows_error_on_failure(monkeypatch):
    """Failures should surface to the user via a dialog."""

    errors = []

    def fake_build(*, project_path):
        """Simulate the build step raising an error."""
        raise FileNotFoundError("missing unity")

    monkeypatch.setattr(app, "build_and_launch_game", fake_build)
    # Capture the message passed to the custom error window instead of popping a real GUI.
    monkeypatch.setattr(app, "show_build_error", lambda msg: errors.append(msg))

    app.launch_game("/tmp/project")

    # The error window should include the original message so users can copy it.
    assert "missing unity" in errors[0]


def test_show_build_error_creates_scrollable_text(monkeypatch):
    """Error dialog should provide scrollable, selectable text."""

    wins = []
    texts = []
    scrolls = []

    class DummyWin:
        """Minimal stand-in for ``tk.Toplevel`` used in tests."""

        def __init__(self):
            self.children = []

        def title(self, text):
            # Record the window title for assertions.
            self.title_text = text

        def rowconfigure(self, *_args, **_kwargs):
            pass

        def columnconfigure(self, *_args, **_kwargs):
            pass

    class DummyText:
        """Fake ``tk.Text`` widget capturing inserted content and config."""

        def __init__(self, parent, **kwargs):
            parent.children.append(self)
            self.kwargs = kwargs
            self.content = ""

        def configure(self, **kwargs):
            self.kwargs.update(kwargs)

        config = configure  # ``Text`` aliases ``config`` to ``configure``

        def insert(self, _idx, text):
            self.content = text

        def grid(self, *_args, **_kwargs):
            pass

        def yview(self, *_args, **_kwargs):
            pass

    class DummyScrollbar:
        """Fake vertical scrollbar that records its command callback."""

        def __init__(self, parent, **kwargs):
            parent.children.append(self)
            self.orient = kwargs.get("orient")
            self.command = kwargs.get("command")
            self.set = lambda *_args, **_kwargs: None

        def grid(self, *_args, **_kwargs):
            pass

    def fake_toplevel():
        win = DummyWin()
        wins.append(win)
        return win

    def fake_text(parent, **kwargs):
        txt = DummyText(parent, **kwargs)
        texts.append(txt)
        return txt

    def fake_scrollbar(parent, **kwargs):
        sc = DummyScrollbar(parent, **kwargs)
        scrolls.append(sc)
        return sc

    # Replace real widgets with our fakes to avoid needing a GUI environment.
    monkeypatch.setattr(app.tk, "Toplevel", fake_toplevel)
    monkeypatch.setattr(app.tk, "Text", fake_text)
    monkeypatch.setattr(app.ttk, "Scrollbar", fake_scrollbar)

    app.show_build_error("traceback info")

    win = wins[0]
    txt = texts[0]
    sc = scrolls[0]

    # The window should be titled and contain our message.
    assert win.title_text == "Build failed"
    assert txt.content == "traceback info"
    # The text widget should be wired to the scrollbar for vertical scrolling.
    assert txt.kwargs["yscrollcommand"] == sc.set
    assert sc.orient == "vertical"
    # Text should be read-only so users can't accidentally modify it.
    assert txt.kwargs["state"] == "disabled"


def test_input_cleared_after_send(monkeypatch):
    """Submitting a prompt should wipe the input box for the next message."""

    try:
        root = tk.Tk()
        root.withdraw()  # Hide main window if display is available
    except tk.TclError:
        pytest.skip("Tkinter display not available")

    widgets, _ = app.build_ui(root)
    txt_input = widgets["txt_input"]
    work_var = widgets["work_dir_var"]
    work_var.set("/tmp")  # Pretend the user selected a working directory

    def fake_run_aider(msg, output, txt, *_args, **_kwargs):
        """Short-circuit the runner so the test doesn't spawn aider."""
        app.runner.request_active = False
        txt.config(state="normal")

    # Replace the real runner with our instant-return fake
    monkeypatch.setattr(app.runner, "run_aider", fake_run_aider)

    txt_input.insert("1.0", "hello")
    txt_input.event_generate("<Return>")  # Trigger the send handler
    root.update()  # Process pending events so the handler runs

    # After sending, the input area should be empty and ready for new text
    assert txt_input.get("1.0", "end-1c") == ""
    root.destroy()


import sys
import types
from pathlib import Path
import subprocess

import pytest

# Ensure the project root is on the Python path so we can import utils
sys.path.append(str(Path(__file__).resolve().parents[1]))
import utils


def test_sanitize_removes_noise():
    """Quotes and newlines should be stripped out."""
    raw = "Hello\n'Quote'  Test"
    assert utils.sanitize(raw) == "Hello Quote Test"


def test_should_suppress_matches_known_warning():
    line = "Can't initialize prompt toolkit: No Windows console found"
    assert utils.should_suppress(line)


def test_verify_api_key_success():
    """A 200 response should validate the key."""

    def fake_request(url, headers):
        resp = types.SimpleNamespace()
        resp.status_code = 200
        return resp

    assert utils.verify_api_key("key", request_fn=fake_request)


def test_verify_api_key_failure():
    """Non-200 responses should raise ValueError with details."""

    def bad_request(url, headers):
        resp = types.SimpleNamespace()
        resp.status_code = 401
        resp.text = "unauthorized"
        return resp

    with pytest.raises(ValueError) as exc:
        utils.verify_api_key("key", request_fn=bad_request)
    assert "401" in str(exc.value)
    assert "unauthorized" in str(exc.value)


def test_verify_api_key_missing():
    """Empty keys should raise an explicit error."""

    with pytest.raises(ValueError):
        utils.verify_api_key("")


def test_extract_commit_id_found():
    """A commit hash embedded in the text should be returned."""
    text = "Some output\nCommitted abcdef1 add feature\n"
    assert utils.extract_commit_id(text) == "abcdef1"


def test_extract_commit_id_missing():
    """If no commit hash is present, None should be returned."""
    text = "Aider did nothing useful"
    assert utils.extract_commit_id(text) is None


def test_needs_user_input_detects_prompt():
    """Lines that start with 'Please' and end with '?' require user action."""
    line = "Please add README.md to the chat so I can generate the exact SEARCH/REPLACE blocks?"
    assert utils.needs_user_input(line)


def test_needs_user_input_ignores_regular_output():
    """Normal output lines should not be flagged as requiring input."""
    line = "Aider v0.86.1"
    assert not utils.needs_user_input(line)


def test_load_and_save_timeout(tmp_path: Path):
    """Saving then loading should persist the timeout value."""
    cfg = tmp_path / "config.ini"
    # When file is missing, default should be 5
    assert utils.load_timeout(cfg) == 5
    # After saving a new value, it should round-trip
    utils.save_timeout(10, cfg)
    assert utils.load_timeout(cfg) == 10


def test_load_and_save_working_dir(tmp_path: Path):
    """The last selected working directory should persist between runs."""
    cache = tmp_path / "dir.txt"
    # Without a cache file we expect None
    assert utils.load_working_dir(cache) is None
    # After saving a path it should load back the same value
    utils.save_working_dir("/path/to/dir", cache)
    assert utils.load_working_dir(cache) == "/path/to/dir"


def test_model_selection_is_not_persisted(tmp_path: Path):
    """Saving the model should have no effect on subsequent loads."""
    cfg = tmp_path / "config.ini"
    # Loading should always return the medium model regardless of config file.
    assert utils.load_default_model(cfg) == "gpt-5-mini"
    # Attempting to save a different model should not create or modify the file.
    utils.save_default_model("gpt-5", cfg)
    assert utils.load_default_model(cfg) == "gpt-5-mini"
    # Config file should not exist because nothing was persisted.
    assert not cfg.exists()


def test_get_commit_stats(tmp_path: Path):
    """Commit stats should report line and file counts accurately."""

    repo = tmp_path
    # Initialize an empty git repository to run our test commits.
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    file_path = repo / "demo.txt"
    # First commit adds a file with two lines.
    file_path.write_text("a\nb\n")
    subprocess.run(["git", "add", file_path.name], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "add file"], cwd=repo, check=True)
    commit1 = (
        subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()
    )

    # Second commit modifies one line.
    file_path.write_text("a\nc\n")
    subprocess.run(["git", "add", file_path.name], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "modify file"], cwd=repo, check=True)
    commit2 = (
        subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()
    )

    # Third commit removes the file entirely.
    subprocess.run(["git", "rm", file_path.name], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "remove file"], cwd=repo, check=True)
    commit3 = (
        subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()
    )

    stats1 = utils.get_commit_stats(commit1, repo)
    assert stats1["lines_added"] == 2
    assert stats1["files_added"] == 1

    stats2 = utils.get_commit_stats(commit2, repo)
    assert stats2["lines_added"] == 1
    assert stats2["lines_removed"] == 1
    assert stats2["files_changed"] == 1
    assert stats2["description"] == "modify file"

    stats3 = utils.get_commit_stats(commit3, repo)
    assert stats3["files_removed"] == 1
    assert stats3["lines_removed"] == 2


def test_load_usage_days(tmp_path: Path):
    """Loading should return 30 by default and respect config value."""
    cfg = tmp_path / "config.ini"
    # Without a config file we expect the default window of 30 days.
    assert utils.load_usage_days(cfg) == 30
    # After writing a custom value it should be returned.
    cfg.write_text("[usage]\nbilling_days = 10\n")
    assert utils.load_usage_days(cfg) == 10


def test_fetch_usage_data_parses_responses():
    """Spending and credit info should be computed from API responses."""

    def fake_request(url, headers=None, params=None):
        resp = types.SimpleNamespace()
        resp.status_code = 200
        # Return usage cost in cents for the billing/usage endpoint.
        if "billing/usage" in url:
            resp.json = lambda: {"total_usage": 1234}
        else:  # credit_grants endpoint
            resp.json = lambda: {
                "total_granted": 20,
                "total_used": 5,
                "total_available": 15,
            }
        return resp

    stats = utils.fetch_usage_data("key", days=30, request_fn=fake_request)
    assert stats["total_spent"] == pytest.approx(12.34)
    assert stats["credits_total"] == 20
    assert stats["credits_remaining"] == 15
    assert stats["pct_credits_used"] == pytest.approx(25.0)


def test_fetch_usage_data_error():
    """Non-200 responses should raise ValueError."""

    def bad_request(url, headers=None, params=None):
        resp = types.SimpleNamespace()
        resp.status_code = 500
        resp.text = "boom"
        return resp

    with pytest.raises(ValueError):
        utils.fetch_usage_data("key", request_fn=bad_request)

def test_build_and_launch_game_runs(monkeypatch, tmp_path):
    """Building then launching should invoke subprocess.run and subprocess.Popen."""
    calls = []  # record the order and arguments of subprocess calls

    def fake_run(cmd, check):
        # capture the build command
        calls.append(("run", cmd, check))

    def fake_popen(cmd):
        # capture the launch command and return a dummy process object
        calls.append(("popen", cmd))
        return types.SimpleNamespace()

    # Patch which() so the build tool appears to exist on the system
    monkeypatch.setattr(utils.shutil, "which", lambda _cmd: "/usr/bin/build")
    # Replace subprocess functions with our fakes so no real commands run
    monkeypatch.setattr(utils.subprocess, "run", fake_run)
    monkeypatch.setattr(utils.subprocess, "Popen", fake_popen)

    # Create a dummy game file to satisfy the existence check
    game = tmp_path / "game.exe"
    game.touch()

    proc = utils.build_and_launch_game(["build"], [str(game)])

    assert calls == [("run", ["build"], True), ("popen", [str(game)])]
    assert isinstance(proc, types.SimpleNamespace)


def test_build_and_launch_game_propagates_build_error(monkeypatch):
    """If the build step fails, the exception should bubble up."""

    def fail_run(cmd, check):
        raise subprocess.CalledProcessError(1, cmd)

    # Pretend the build tool exists so we reach the failing run()
    monkeypatch.setattr(utils.shutil, "which", lambda _cmd: "/usr/bin/build")
    monkeypatch.setattr(utils.subprocess, "run", fail_run)

    with pytest.raises(subprocess.CalledProcessError):
        utils.build_and_launch_game(["build"], ["run"])


def test_build_and_launch_game_missing_build_tool():
    """A missing build executable should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        utils.build_and_launch_game(["missing_tool"], ["run"])


def test_build_and_launch_game_missing_game_binary(monkeypatch, tmp_path):
    """If the built game is absent, an explicit error should be raised."""

    # Pretend the build tool exists and the build command succeeds
    monkeypatch.setattr(utils.shutil, "which", lambda _cmd: "/usr/bin/build")
    monkeypatch.setattr(utils.subprocess, "run", lambda cmd, check: None)

    # Path to a game binary that was not created by the build step
    missing_game = tmp_path / "no_game.exe"

    with pytest.raises(FileNotFoundError):
        utils.build_and_launch_game(["build"], [str(missing_game)])

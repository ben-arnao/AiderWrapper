import sys
import types
import sys
import types
from pathlib import Path
import subprocess

import pytest

# Ensure the project root is on the Python path so we can import the utils package
sys.path.append(str(Path(__file__).resolve().parents[1]))

# Pull in individual util modules to make dependencies explicit
import utils.text as text_utils
import utils.api as api_utils
import utils.config as config_utils
import utils.git as git_utils


def test_sanitize_removes_noise():
    """Quotes and newlines should be stripped out."""
    raw = "Hello\n'Quote'  Test"
    assert text_utils.sanitize(raw) == "Hello Quote Test"


def test_should_suppress_matches_known_warning():
    line = "Can't initialize prompt toolkit: No Windows console found"
    assert text_utils.should_suppress(line)


def test_verify_api_key_success():
    """A 200 response should validate the key."""

    def fake_request(url, headers):
        resp = types.SimpleNamespace()
        resp.status_code = 200
        return resp

    assert api_utils.verify_api_key("key", request_fn=fake_request)


def test_verify_api_key_failure():
    """Non-200 responses should raise ValueError with details."""

    def bad_request(url, headers):
        resp = types.SimpleNamespace()
        resp.status_code = 401
        resp.text = "unauthorized"
        return resp

    with pytest.raises(ValueError) as exc:
        api_utils.verify_api_key("key", request_fn=bad_request)
    assert "401" in str(exc.value)
    assert "unauthorized" in str(exc.value)


def test_verify_api_key_missing():
    """Empty keys should raise an explicit error."""

    with pytest.raises(ValueError):
        api_utils.verify_api_key("")


def test_extract_commit_id_found():
    """A commit hash embedded in the text should be returned."""
    text = "Some output\nCommitted abcdef1 add feature\n"
    assert git_utils.extract_commit_id(text) == "abcdef1"


def test_extract_commit_id_missing():
    """If no commit hash is present, None should be returned."""
    text = "Aider did nothing useful"
    assert git_utils.extract_commit_id(text) is None


def test_extract_cost_found():
    """Dollar amounts should be parsed as floats."""
    line = "Total cost: $1.23"
    assert text_utils.extract_cost(line) == 1.23


def test_extract_cost_missing():
    """Lines without dollar amounts should return None."""
    line = "No money mentioned here"
    assert text_utils.extract_cost(line) is None


def test_strip_ansi_removes_escape_sequences():
    """ANSI color codes should be stripped out leaving plain text."""
    colored = "\x1b[31merror\x1b[0m"  # Red text followed by reset
    assert text_utils.strip_ansi(colored) == "error"


def test_needs_user_input_detects_prompt():
    """Lines that start with 'Please' and end with '?' require user action."""
    line = "Please add README.md to the chat so I can generate the exact SEARCH/REPLACE blocks?"
    assert text_utils.needs_user_input(line)


def test_needs_user_input_detects_file_request():
    """Phrases telling the user to add files should also trigger a prompt."""
    # This line mirrors aider's message when it pauses for file attachments
    line = (
        "These are the files we might edit. I will stop here so you can add them to the chat (or confirm you want me to create them):"
    )
    assert text_utils.needs_user_input(line)


def test_needs_user_input_ignores_regular_output():
    """Normal output lines should not be flagged as requiring input."""
    line = "Aider v0.86.1"
    assert not text_utils.needs_user_input(line)


def test_load_and_save_working_dir(tmp_path: Path):
    """The last selected working directory should persist between runs."""
    cache = tmp_path / "dir.txt"
    # Without a cache file we expect None
    assert config_utils.load_working_dir(cache) is None
    # After saving a path it should load back the same value
    config_utils.save_working_dir("/path/to/dir", cache)
    assert config_utils.load_working_dir(cache) == "/path/to/dir"


def test_model_selection_is_not_persisted(tmp_path: Path):
    """Saving the model should have no effect on subsequent loads."""
    cfg = tmp_path / "config.ini"
    # Loading should always return the medium model regardless of config file.
    assert config_utils.load_default_model(cfg) == "gpt-5-mini"
    # Attempting to save a different model should not create or modify the file.
    config_utils.save_default_model("gpt-5", cfg)
    assert config_utils.load_default_model(cfg) == "gpt-5-mini"
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

    stats1 = git_utils.get_commit_stats(commit1, repo)
    assert stats1["lines_added"] == 2
    assert stats1["files_added"] == 1

    stats2 = git_utils.get_commit_stats(commit2, repo)
    assert stats2["lines_added"] == 1
    assert stats2["lines_removed"] == 1
    assert stats2["files_changed"] == 1
    assert stats2["description"] == "modify file"

    stats3 = git_utils.get_commit_stats(commit3, repo)
    assert stats3["files_removed"] == 1
    assert stats3["lines_removed"] == 2


def test_fetch_usage_data_parses_responses():
    """fetch_usage_data should combine usage and credit info correctly."""

    def fake_request(url, headers=None, params=None):
        # Simulate different API endpoints based on the URL requested
        resp = types.SimpleNamespace()
        resp.status_code = 200
        if url.endswith("/usage"):
            # Usage endpoint returns total_usage in cents
            resp.json = lambda: {"total_usage": 1234}
        else:
            # Credit grants endpoint reports totals and remaining credits
            resp.json = lambda: {
                "total_granted": 20,
                "total_used": 5,
                "total_available": 15,
            }
        return resp

    stats = api_utils.fetch_usage_data("key", days=30, request_fn=fake_request)
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
        api_utils.fetch_usage_data("key", request_fn=bad_request)


def test_build_and_launch_game_runs(monkeypatch, tmp_path):
    """Building then launching should invoke subprocess.run and subprocess.Popen."""
    calls = []  # record the order and arguments of subprocess calls

    def fake_run(cmd, capture_output, text):
        # capture the build command and pretend it succeeded
        calls.append(("run", cmd))
        return types.SimpleNamespace(returncode=0, stderr="")

    def fake_popen(cmd):
        # capture the launch command and return a dummy process object
        calls.append(("popen", cmd))
        return types.SimpleNamespace()

    # Patch which() so the build tool appears to exist on the system
    monkeypatch.setattr(config_utils.shutil, "which", lambda _cmd: "/usr/bin/build")
    # Replace subprocess functions with our fakes so no real commands run
    monkeypatch.setattr(config_utils.subprocess, "run", fake_run)
    monkeypatch.setattr(config_utils.subprocess, "Popen", fake_popen)

    # Create a dummy game file to satisfy the existence check
    game = tmp_path / "game.exe"
    game.touch()

    proc = config_utils.build_and_launch_game(["build"], [str(game)])

    assert calls == [("run", ["build"]), ("popen", [str(game)])]
    assert isinstance(proc, types.SimpleNamespace)


def test_build_and_launch_game_propagates_build_error(monkeypatch):
    """If the build step fails, the exception should bubble up."""

    def fail_run(cmd, capture_output, text):
        # Simulate Unity returning a failure exit code
        return types.SimpleNamespace(returncode=1, stderr="boom")

    # Pretend the build tool exists so we reach the failing run()
    monkeypatch.setattr(config_utils.shutil, "which", lambda _cmd: "/usr/bin/build")
    monkeypatch.setattr(config_utils.subprocess, "run", fail_run)

    with pytest.raises(RuntimeError):
        config_utils.build_and_launch_game(["build"], ["run"])


def test_build_and_launch_game_missing_build_tool():
    """A missing build executable should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        config_utils.build_and_launch_game(["missing_tool"], ["run"])


def test_build_and_launch_game_missing_game_binary(monkeypatch, tmp_path):
    """If the built game is absent, an explicit error should be raised."""

    # Pretend the build tool exists and the build command succeeds
    monkeypatch.setattr(config_utils.shutil, "which", lambda _cmd: "/usr/bin/build")
    monkeypatch.setattr(
        config_utils.subprocess,
        "run",
        lambda cmd, capture_output, text: types.SimpleNamespace(returncode=0, stderr=""),
    )

    # Path to a game binary that was not created by the build step
    missing_game = tmp_path / "no_game.exe"

    with pytest.raises(FileNotFoundError):
        config_utils.build_and_launch_game(["build"], [str(missing_game)])


def test_find_unity_exe_from_config(tmp_path):
    """Path from config.ini should be returned when present."""
    unity = tmp_path / "Unity.exe"
    unity.touch()  # create dummy executable
    cfg = tmp_path / "config.ini"
    cfg.write_text(f"[build]\nbuild_cmd = {unity}\n")
    assert config_utils._find_unity_exe(cfg) == str(unity)


def test_find_unity_exe_from_env(monkeypatch, tmp_path):
    """UNITY_PATH env var should be used when config is missing."""
    unity = tmp_path / "Unity.exe"
    unity.touch()
    monkeypatch.setenv("UNITY_PATH", str(unity))
    assert config_utils._find_unity_exe(tmp_path / "missing.ini") == str(unity)


def test_find_unity_exe_autodiscover(monkeypatch, tmp_path):
    """Auto-discovery should pick the highest-version Unity install."""
    # Create two fake Unity paths so we can choose the "latest" one
    older = tmp_path / "a" / "Unity.exe"
    older.parent.mkdir()
    older.touch()
    newer = tmp_path / "b" / "Unity.exe"
    newer.parent.mkdir()
    newer.touch()
    monkeypatch.delenv("UNITY_PATH", raising=False)
    # Patch glob.glob to return our fake candidates
    monkeypatch.setattr(config_utils.glob, "glob", lambda pattern: [str(older), str(newer)])
    assert config_utils._find_unity_exe(tmp_path / "missing.ini") == str(newer)


def test_find_unity_exe_missing(monkeypatch, tmp_path):
    """An explicit error should be raised when Unity.exe cannot be found."""
    monkeypatch.delenv("UNITY_PATH", raising=False)
    monkeypatch.setattr(config_utils.glob, "glob", lambda pattern: [])
    with pytest.raises(FileNotFoundError) as exc:
        config_utils._find_unity_exe(tmp_path / "missing.ini")
    assert "Unity Editor executable not found" in str(exc.value)


def test_build_and_launch_game_uses_finder(monkeypatch, tmp_path):
    """When no build_cmd is supplied, _find_unity_exe should provide the path."""
    calls = []  # record subprocess usage

    # Pretend Unity.exe lives here
    unity = tmp_path / "Unity.exe"
    unity.touch()
    game = tmp_path / "game.exe"
    game.touch()

    # Provide a fake finder so we know the path used
    # Replace the internal finder with one that returns our fake path
    monkeypatch.setattr(
        config_utils, "_find_unity_exe", lambda cfg=config_utils.CONFIG_PATH: str(unity)
    )

    # Patch subprocess.run and Popen so nothing real executes
    def fake_run(cmd, capture_output, text):
        calls.append(("run", cmd))
        return types.SimpleNamespace(returncode=0, stderr="")

    def fake_popen(cmd):
        calls.append(("popen", cmd))
        return types.SimpleNamespace()

    monkeypatch.setattr(config_utils.subprocess, "run", fake_run)
    monkeypatch.setattr(config_utils.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(config_utils.shutil, "which", lambda p: p)

    proc = config_utils.build_and_launch_game(run_cmd=[str(game)])

    cmd = calls[0][1]
    assert cmd[0] == str(unity)
    # Ensure the fully-qualified build method is included in the command.
    idx = cmd.index("-executeMethod")
    assert (
        cmd[idx + 1] == "RogueLike2D.Editor.BuildScript.PerformBuild"
    )
    assert isinstance(proc, types.SimpleNamespace)


def test_build_and_launch_game_includes_log_tail(monkeypatch, tmp_path):
    """Failures should include Unity's log tail for easier debugging."""

    # Create fake Unity executable and game binary paths
    unity = tmp_path / "Unity.exe"
    unity.touch()
    game = tmp_path / "game.exe"

    # Write a log file with a distinctive last line
    log_file = tmp_path / "Editor.log.batchbuild.txt"
    log_file.write_text("line1\nline2\nlast line\n")

    def fail_run(cmd, capture_output, text):
        # Return failure while leaving stderr populated
        return types.SimpleNamespace(returncode=1, stderr="boom")

    # Patch helpers so the function uses our fake paths and log file
    monkeypatch.setattr(config_utils, "_find_unity_exe", lambda cfg=config_utils.CONFIG_PATH: str(unity))
    monkeypatch.setattr(config_utils.shutil, "which", lambda p: p)
    monkeypatch.setattr(config_utils.subprocess, "run", fail_run)

    with pytest.raises(RuntimeError) as exc:
        config_utils.build_and_launch_game(run_cmd=[str(game)], project_path=str(tmp_path))

    # Both stderr and the last log line should be present in the error message
    msg = str(exc.value)
    assert "boom" in msg
    assert "last line" in msg

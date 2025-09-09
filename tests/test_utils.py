import sys
import types
from pathlib import Path
import os

import pytest

# Ensure the project root is on the Python path so we can import utils
sys.path.append(str(Path(__file__).resolve().parents[1]))
import utils

def test_sanitize_removes_noise():
    raw = 'Hello\n\'Quote\'  Test'
    assert utils.sanitize(raw) == 'Hello Quote Test'

def test_should_suppress_matches_known_warning():
    line = "Can't initialize prompt toolkit: No Windows console found"
    assert utils.should_suppress(line)

def test_verify_unity_project(tmp_path: Path):
    (tmp_path / 'Assets').mkdir()
    project_settings = tmp_path / 'ProjectSettings'
    project_settings.mkdir()
    (project_settings / 'ProjectVersion.txt').write_text('dummy')
    assert utils.verify_unity_project(tmp_path)
    for child in project_settings.iterdir():
        child.unlink()
    project_settings.rmdir()
    assert not utils.verify_unity_project(tmp_path)

def test_verify_api_key(monkeypatch):
    def fake_request(url, headers):
        resp = types.SimpleNamespace()
        resp.status_code = 200
        return resp
    assert utils.verify_api_key('key', request_fn=fake_request)
    def bad_request(url, headers):
        resp = types.SimpleNamespace()
        resp.status_code = 401
        return resp
    with pytest.raises(ValueError):
        utils.verify_api_key('key', request_fn=bad_request)


def test_extract_commit_id_found():
    """A commit hash embedded in the text should be returned."""
    text = "Some output\nCommitted abcdef1 add feature\n"
    assert utils.extract_commit_id(text) == "abcdef1"


def test_extract_commit_id_missing():
    """If no commit hash is present, None should be returned."""
    text = "Aider did nothing useful"
    assert utils.extract_commit_id(text) is None


def test_load_and_save_timeout(tmp_path: Path):
    """Saving then loading should persist the timeout value."""
    cfg = tmp_path / "config.ini"
    # When file is missing, default should be 5
    assert utils.load_timeout(cfg) == 5
    # After saving a new value, it should round-trip
    utils.save_timeout(10, cfg)
    assert utils.load_timeout(cfg) == 10


def test_load_and_save_project_dir(tmp_path: Path):
    """The last selected project directory should persist between runs."""
    cache = tmp_path / "proj.txt"
    # Without a cache file we expect None
    assert utils.load_project_dir(cache) is None
    # After saving a path it should load back the same value
    utils.save_project_dir("/path/to/project", cache)
    assert utils.load_project_dir(cache) == "/path/to/project"


@pytest.mark.skipif(os.name == "nt", reason="PTY not supported on Windows")
def test_spawn_pty_process_captures_output():
    """Running a simple command through the pseudo-terminal should yield its output."""
    proc, fd = utils.spawn_pty_process(["python", "-c", "print('hi')"])
    with fd:
        output = ""
        try:
            # Read lines until the child process closes the pseudo-terminal
            for line in fd:
                output += line
        except OSError:
            # Some platforms raise EIO when the slave end is closed; that's fine
            pass
    proc.wait()
    assert "hi" in output

import sys
import types
from pathlib import Path

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

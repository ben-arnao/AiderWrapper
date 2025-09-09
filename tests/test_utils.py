import tempfile
from pathlib import Path
import sys

# Ensure the project root is on the Python path so we can import NoLight
sys.path.append(str(Path(__file__).resolve().parents[1]))
from NoLight import extract_commit_id, load_timeout, save_timeout


def test_extract_commit_id_found():
    """A commit hash embedded in the text should be returned."""
    text = "Some output\nCommitted abcdef1 add feature\n"
    assert extract_commit_id(text) == "abcdef1"


def test_extract_commit_id_missing():
    """No commit hash should return None."""
    text = "Aider did nothing useful"
    assert extract_commit_id(text) is None


def test_load_and_save_timeout(tmp_path: Path):
    """Saving then loading should persist the timeout value."""
    cfg = tmp_path / "config.ini"
    # When file is missing, default should be 5
    assert load_timeout(cfg) == 5
    # After saving a new value, it should round-trip
    save_timeout(10, cfg)
    assert load_timeout(cfg) == 10

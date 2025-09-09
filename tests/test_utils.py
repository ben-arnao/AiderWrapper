import sys
import types
from pathlib import Path

import pytest

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

import pytest

from photosorter.config import Paths
from photosorter.core.labelers import find_jev_key


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv("JEV_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


def test_no_key_anywhere_is_none(tmp_path):
    assert find_jev_key(Paths(root=tmp_path)) is None


def test_environment_wins_over_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("JEV_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("TYPESAFE_API_KEY", "from-env")
    assert find_jev_key(Paths(root=tmp_path)) == "from-env"


def test_dotenv_is_read_and_quotes_are_stripped(tmp_path):
    (tmp_path / ".env").write_text("OTHER=1\nJEV_KEY=\"abc\"\n", encoding="utf-8")
    assert find_jev_key(Paths(root=tmp_path)) == "abc"


def test_an_empty_value_is_no_key(tmp_path):
    (tmp_path / ".env").write_text("JEV_KEY=\n", encoding="utf-8")
    assert find_jev_key(Paths(root=tmp_path)) is None


def test_a_notepad_bom_does_not_hide_the_key(tmp_path):
    (tmp_path / ".env").write_bytes(b"\xef\xbb\xbfJEV_KEY=abc\r\n")
    assert find_jev_key(Paths(root=tmp_path)) == "abc"


def test_an_export_prefix_is_accepted(tmp_path):
    (tmp_path / ".env").write_text("export JEV_KEY=abc\n", encoding="utf-8")
    assert find_jev_key(Paths(root=tmp_path)) == "abc"


def test_a_non_utf8_env_file_means_no_key_not_a_crash(tmp_path):
    (tmp_path / ".env").write_bytes(b"JEV_KEY=caf\xe9\xff\xfe")
    assert find_jev_key(Paths(root=tmp_path)) is None

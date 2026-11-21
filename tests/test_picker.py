import subprocess
import sys
from pathlib import Path

from photosorter import picker
from photosorter.picker import choose_folder, picker_available


def _stub_child(monkeypatch, stdout: str, returncode: int = 0, calls: list | None = None):
    def fake_run(args, **kwargs):
        if calls is not None:
            calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(picker.subprocess, "run", fake_run)


def test_choose_folder_returns_path_printed_by_child(monkeypatch):
    calls = []
    _stub_child(monkeypatch, r"D:\pics" + "\n", calls=calls)

    assert choose_folder("Choose your photos") == Path("D:/pics")
    args, kwargs = calls[0]
    assert args == [sys.executable, "-m", "photosorter.picker", "Choose your photos"]
    assert kwargs["timeout"] == 300


def test_choose_folder_returns_none_when_child_prints_nothing(monkeypatch):
    _stub_child(monkeypatch, "")

    assert choose_folder("Choose your photos") is None


def test_picker_available_reports_plain_words_when_tkinter_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "tkinter", None)

    ok, reason = picker_available()

    assert ok is False
    assert "folder" in reason
    assert "directory" not in reason


def test_child_process_crash_returns_none_not_exception(monkeypatch):
    _stub_child(monkeypatch, r"D:\pics" + "\n", returncode=1)

    assert choose_folder("x") is None

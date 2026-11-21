import shutil
import subprocess
import sys
from pathlib import Path, PureWindowsPath

import pytest

from photosorter.platform import (
    copy_file,
    file_manager_name,
    find_claude,
    free_space_bytes,
    long_path,
    open_folder,
    reveal_in_file_manager,
)

BS = chr(92)


@pytest.fixture
def calls(monkeypatch):
    """Record argv lists passed to subprocess.run; returncode is settable via calls.rc."""
    class Calls(list):
        rc = 0

    recorded = Calls()

    def fake_run(argv, *args, **kwargs):
        recorded.append(list(argv))
        return subprocess.CompletedProcess(argv, recorded.rc)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return recorded


def test_reveal_uses_explorer_select_with_backslashes_on_windows(monkeypatch, calls):
    monkeypatch.setattr(sys, "platform", "win32")
    reveal_in_file_manager(Path("D:/pics/a.jpg"))
    assert calls[0] == ["explorer", r"/select,D:\pics\a.jpg"]


def test_reveal_uses_open_dash_r_on_macos(monkeypatch, calls):
    monkeypatch.setattr(sys, "platform", "darwin")
    reveal_in_file_manager(Path("/pics/a.jpg"))
    assert calls[0] == ["open", "-R", "/pics/a.jpg"]


def test_reveal_opens_parent_folder_on_linux(monkeypatch, calls):
    monkeypatch.setattr(sys, "platform", "linux")
    reveal_in_file_manager(Path("/pics/a.jpg"))
    assert calls[0] == ["xdg-open", "/pics"]


def test_open_folder_per_platform(monkeypatch, calls):
    for plat, expected in [
        ("win32", ["explorer", r"D:\pics"]),
        ("darwin", ["open", "D:/pics"]),
        ("linux", ["xdg-open", "D:/pics"]),
    ]:
        monkeypatch.setattr(sys, "platform", plat)
        open_folder(Path("D:/pics"))
        assert calls[-1] == expected


def test_file_manager_name_per_platform(monkeypatch):
    for plat, name in [("win32", "File Explorer"), ("darwin", "Finder"), ("linux", "file manager")]:
        monkeypatch.setattr(sys, "platform", plat)
        assert file_manager_name() == name


def test_copy_falls_back_to_copy2_when_clone_fails(monkeypatch, calls, tmp_path):
    src, dst = tmp_path / "s.bin", tmp_path / "d.bin"
    src.write_bytes(b"hello")
    calls.rc = 1  # clone command fails
    for plat in ("darwin", "linux"):
        monkeypatch.setattr(sys, "platform", plat)
        dst.unlink(missing_ok=True)
        copy_file(src, dst)
        assert dst.read_bytes() == b"hello"
    assert calls[0][:3] == ["cp", "-c", "-p"]
    assert calls[1][:2] == ["cp", "--reflink=auto"]


def test_copy_falls_back_when_clone_command_missing(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise FileNotFoundError("cp")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(sys, "platform", "linux")
    src, dst = tmp_path / "s.bin", tmp_path / "d.bin"
    src.write_bytes(b"hello")
    copy_file(src, dst)
    assert dst.read_bytes() == b"hello"


def test_copy_on_windows_skips_subprocess_and_preserves_mtime(monkeypatch, calls, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    src, dst = tmp_path / "s.bin", tmp_path / "d.bin"
    src.write_bytes(b"hello")
    copy_file(src, dst)
    assert calls == []
    assert dst.read_bytes() == b"hello"
    assert dst.stat().st_mtime == src.stat().st_mtime


def test_find_claude_finds_cmd_shim_on_windows(monkeypatch):
    monkeypatch.setattr(
        shutil, "which", lambda n: r"C:\npm\claude.cmd" if n == "claude.cmd" else None
    )
    assert find_claude().endswith("claude.cmd")


def test_find_claude_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: None)
    assert find_claude() is None


def test_long_path_prefixes_only_long_windows_paths(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    root = Path(Path.cwd().anchor)  # absolute on whichever host runs the suite
    prefix = BS * 2 + "?" + BS
    assert str(long_path(root / ("a" * 300))).startswith(prefix)
    assert not str(long_path(root / "short.jpg")).startswith(prefix)


def test_long_path_uses_unc_form_for_long_unc_paths(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    tail = BS.join(["server", "share", "a" * 300])
    unc = PureWindowsPath(BS * 2 + tail)
    assert str(long_path(unc)) == BS * 2 + "?" + BS + "UNC" + BS + tail


def test_long_path_is_identity_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    p = Path("D:/" + "a" * 300)
    assert long_path(p) == p


def test_free_space_bytes_is_positive(tmp_path):
    assert free_space_bytes(tmp_path) > 0


@pytest.mark.parametrize("plat,head", [("darwin", ["cp", "-c", "-p"]), ("linux", ["cp", "--reflink=auto", "-p"])])
def test_successful_clone_skips_copy2_and_passes_src_dst_last(monkeypatch, calls, tmp_path, plat, head):
    monkeypatch.setattr(sys, "platform", plat)
    monkeypatch.setattr(shutil, "copy2", lambda *a, **k: pytest.fail("copy2 must not run"))
    src, dst = tmp_path / "s.bin", tmp_path / "d.bin"
    copy_file(src, dst)
    assert calls[0] == head + [src.as_posix(), dst.as_posix()]


def test_find_claude_tries_candidates_in_order(monkeypatch):
    tried = []
    monkeypatch.setattr(shutil, "which", lambda n: tried.append(n))
    find_claude()
    assert tried == ["claude", "claude.cmd", "claude.exe", "claude.ps1"]

"""The only module allowed to read sys.platform; every OS difference funnels through here."""
import shutil
import subprocess
import sys
from pathlib import Path


def _win() -> bool:
    return sys.platform == "win32"


def copy_file(src: Path, dst: Path) -> None:
    """Clone where the OS supports it; any clone failure falls back to copy2 (never loses a file)."""
    if sys.platform == "darwin":
        cmd = ["cp", "-c", "-p", src.as_posix(), dst.as_posix()]
    elif sys.platform.startswith("linux"):
        cmd = ["cp", "--reflink=auto", "-p", src.as_posix(), dst.as_posix()]
    else:
        cmd = None
    if cmd:
        try:
            if subprocess.run(cmd, capture_output=True).returncode == 0:
                return
        except OSError:
            pass
    shutil.copy2(src, dst)


def reveal_in_file_manager(path: Path) -> None:
    if _win():
        cmd = ["explorer", "/select," + str(path).replace("/", "\\")]
    elif sys.platform == "darwin":
        cmd = ["open", "-R", path.as_posix()]
    else:  # xdg-open cannot select a file, so open its folder
        cmd = ["xdg-open", path.parent.as_posix()]
    subprocess.run(cmd, check=False)  # explorer exits non-zero even on success


def open_folder(path: Path) -> None:
    if _win():
        cmd = ["explorer", str(path).replace("/", "\\")]
    elif sys.platform == "darwin":
        cmd = ["open", path.as_posix()]
    else:
        cmd = ["xdg-open", path.as_posix()]
    subprocess.run(cmd, check=False)


def file_manager_name() -> str:
    if _win():
        return "File Explorer"
    return "Finder" if sys.platform == "darwin" else "file manager"


def find_claude() -> str | None:
    # On Windows the CLI is a shim (.cmd/.exe/.ps1), so try each name.
    for name in ("claude", "claude.cmd", "claude.exe", "claude.ps1"):
        found = shutil.which(name)
        if found:
            return found
    return None


def free_space_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def long_path(path: Path) -> Path:
    """Windows caps paths near 260 chars; prefix absolute paths over 250 with the extended-length marker."""
    if _win() and path.is_absolute() and len(str(path)) > 250:
        return Path("\\\\?\\" + str(path))
    return path

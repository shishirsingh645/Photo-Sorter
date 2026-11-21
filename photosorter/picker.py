"""Native folder picker. Runs the dialog in a child process so tkinter gets its own main thread."""

import subprocess
import sys
from pathlib import Path

TIMEOUT_SECONDS = 300


def choose_folder(prompt: str) -> Path | None:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "photosorter.picker", prompt],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError, UnicodeDecodeError):
        # Undecodable output means the path is unknown, so report no choice rather than a mangled path.
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip())


def picker_available() -> tuple[bool, str]:
    try:
        import tkinter  # noqa: F401
    except ImportError:
        return False, (
            "This Python install cannot show a folder window. "
            "Type or paste the folder path instead."
        )
    return True, ""


if __name__ == "__main__":
    import tkinter
    from tkinter import filedialog

    sys.stdout.reconfigure(encoding="utf-8")
    root = tkinter.Tk()
    root.withdraw()
    root.lift()
    chosen = filedialog.askdirectory(title=sys.argv[1])
    root.destroy()
    if chosen:
        print(chosen)

# Platform support status

This document lists every platform seam from spec §8.4 and the Windows checks from the Task 9 brief, with the status of each.

**Status of this build: nothing has been verified on real hardware.** Every row below is marked *written, not yet verified*, Windows included. The rows describe what the code is written to do. They do not say that the behaviour works. Each row also says whether its only evidence is a unit test that uses fakes. A fake is not the platform: a test that replaces `subprocess.run` or `sys.platform` proves the argument list and the branch selection, not that Explorer, Finder, `xdg-open` or `cp` do the right thing.

This file is also the checklist for the later verification pass. Each row says what to do and what the expected result is. When a row is exercised on real hardware, change its status and record the date and the machine.

## Status key

- **Written, not yet verified**: code exists, no run on the target OS.
- **Verified (date, machine)**: exercised by hand on the target OS. No row is verified yet.

## Seam table

Spec references are to `docs/superpowers/specs/2026-11-21-photo-sorter-modernized-replica-design.md`. Code references are to `photosorter/platform.py` unless stated.

| # | Seam | Source | Windows | macOS | Linux | Unit tests (fakes) |
|---|------|--------|---------|-------|-------|--------------------|
| 1 | Folder picker | §8.4, §8.4 item 3 and 4 | Written, not yet verified | Written, not yet verified | Written, not yet verified | Yes, fakes only |
| 2 | Copy | §8.4 | Written, not yet verified | Written, not yet verified | Written, not yet verified | Yes, fakes only |
| 3 | Reveal file ("Show in File Explorer") | §8.4 | Written, not yet verified | Written, not yet verified | Written, not yet verified | Yes, fakes only |
| 4 | Open folder ("Open sorted folder") | §8.4 | Written, not yet verified | Written, not yet verified | Written, not yet verified | Yes, fakes only |
| 5 | Text I/O | §8.4, §8.4 item 1 | Written, not yet verified | Written, not yet verified | Written, not yet verified | Partial |
| 6 | Paths | §8.4, §8.4 item 2 | Written, not yet verified | Written, not yet verified | Written, not yet verified | Partial |
| 7 | `claude` lookup | §8.4 | Written, not yet verified | Written, not yet verified | Written, not yet verified | Yes, fakes only |
| 8 | Browser launch | §8.4 | Written, not yet verified | Written, not yet verified | Written, not yet verified | Partial (fake) |
| 9 | Destination on another drive | Brief Step 2 | Written, not yet verified | Not in brief | Not in brief | No |
| 10 | Devanagari and emoji filenames through scan, label and copy | Brief Step 2 | Written, not yet verified | Written, not yet verified | Written, not yet verified | Partial |
| 11 | App runs without `PYTHONUTF8=1` | Brief Step 2, spec §5 and §8.4 item 1 | Written, not yet verified | Written, not yet verified | Written, not yet verified | No |

Row 9 is a Windows check from the brief. The macOS and Linux cells are marked "Not in brief" because the brief does not ask for them. They are not claimed as working.

## Row details

Each row gives the code's behaviour as read from the source, the unit-test evidence, and the manual check.

### 1. Folder picker

- **Code:** `photosorter/picker.py`. `choose_folder` runs `python -m photosorter.picker <prompt>` as a child process and reads one path from stdout. The child uses `tkinter.filedialog.askdirectory`. A non-zero exit, empty output, timeout or decode error returns `None`. `picker_available` reports a plain-words message when `tkinter` cannot be imported, which covers the Debian/Ubuntu `python3-tk` case.
- **Unit-test evidence (fakes only):** `tests/test_picker.py` stubs `subprocess.run` and checks path return, cancel, child crash, timeout, and the missing-`tkinter` message. `tests/api/test_folders_routes.py` covers the `/api/pick` route with `choose_folder` monkeypatched. **The real `tkinter` dialog has never run under test.**
- **To verify:** on Windows, click the folder-choose control in the setup card. Expected: the native folder dialog opens; choosing a folder fills the path field with that folder's full path; cancelling leaves the field unchanged and shows no error. Also confirm a crash-free return when the dialog is cancelled.
- **Linux check:** on a Python without `python3-tk`, expected: the setup card says in plain words that the folder window is unavailable and offers path entry. It must not show a silent empty result.

### 2. Copy

- **Code:** `copy_file`. macOS runs `cp -c -p src dst`. Linux runs `cp --reflink=auto -p src dst`. Windows runs no command and uses `shutil.copy2`. Any non-zero exit or `OSError` from the command falls back to `shutil.copy2`.
- **Unit-test evidence (fakes only):** `tests/test_platform.py` replaces `subprocess.run` with a recorder and sets `sys.platform` by monkeypatch. It checks argument order and the fallback to `copy2`. The Windows test uses real files on whatever OS runs the test, but it does not prove the copy on a real NTFS volume. **The `cp -c` and `cp --reflink=auto` commands have never been executed.**
- **To verify:** run a sort into a destination on the same drive. Expected: every file in `<dest>/<folder>/` exists with the same byte count and SHA-256 as its source; the source folder is byte-identical before and after (compare a hash list taken before the run). On macOS, check that the copy command is used (APFS clone); on Linux, check `cp --reflink=auto` succeeds or falls back.

### 3. Reveal file ("Show in File Explorer")

- **Code:** `reveal_in_file_manager`. Windows runs `explorer /select,<path with backslashes>`. macOS runs `open -R <path>`. Linux runs `xdg-open <parent folder>`, which does **not** select the file. The return code is ignored because Explorer exits non-zero even on success.
- **Unit-test evidence (fakes only):** `tests/test_platform.py` checks the argv built for each platform. The subprocess is faked. **Nothing has opened Explorer, Finder or a Linux file manager.** The route test in `tests/api/test_folders_routes.py` replaces `reveal_in_file_manager` and checks only the id-to-path lookup.
- **To verify (Windows):** open a sorted folder, click a photo in the browse grid, choose "Show in File Explorer". Expected: a new Explorer window opens on the photo's folder with that exact file highlighted (selected). The file name shown in the window matches the photo clicked.
- **Linux limit:** the Linux check is expected to open the parent folder with no file selected. Record that as the expected result, not a failure.

### 4. Open folder ("Open sorted folder")

- **Code:** `open_folder`. Windows runs `explorer <path with backslashes>`. macOS runs `open <path>`. Linux runs `xdg-open <path>`. The route `/api/open` refuses any folder outside the stored destination, and refuses when no destination is stored.
- **Note:** spec §8.4 says Windows uses `os.startfile`. The code uses `explorer`. Both open the folder. The difference is recorded here and is not a defect by itself.
- **Unit-test evidence (fakes only):** `tests/test_platform.py` checks the argv per platform. `tests/api/test_folders_routes.py` checks containment: inside the destination opens, outside is refused, a sibling whose name starts with the destination is refused, and a link pointing outside is refused. The containment tests use real temporary folders on the host. **The actual folder open has not been seen.**
- **To verify (Windows):** after a completed sort, click "Open sorted folder". Expected: Explorer opens the destination folder that the run wrote to, showing the category folders. A folder outside the destination is refused in the app with a plain message.

### 5. Text I/O

- **Code:** `config.py` and the core modules open text files with `encoding="utf-8"`. Examples: `photosorter/config.py` (`read_json`, `write_json`), `photosorter/core/apply.py` (CSV output with `newline=""`), `photosorter/core/categories.py`, `photosorter/core/labelers/claude.py` (subprocess text with `encoding="utf-8"`, `errors="replace"`).
- **Unit-test evidence:** `tests/test_config.py` round-trips an emoji through `write_json` and `read_json` and asserts the file bytes contain it. This test does not clear `PYTHONUTF8` from the environment, so it does not prove the app works without it (see row 11). **No test scans every text-file open for `encoding=`.**
- **To verify:** run the check in row 11 and confirm `categories.json` with emoji loads and saves. Also open a sorted CSV in a text editor and confirm the Devanagari and emoji names are readable.

### 6. Paths

- **Code:** `long_path` in `platform.py` prefixes absolute Windows paths longer than 250 characters with `\\?\` (or `\\?\UNC\` for UNC paths). It is the identity off Windows. `photosorter/api/routes_files.py` and `routes_folders.py` check containment with `Path.is_relative_to` after `.resolve()`. `photosorter/core/apply.py` and `scan.py` pass paths through `long_path`.
- **Unit-test evidence:** `tests/test_platform.py` checks `long_path` by monkeypatching `sys.platform` (for example the UNC form). The containment tests in `tests/api/` use real temporary folders on the host. **No test uses a real path longer than 260 characters, a real UNC share, or a path with a trailing backslash on a real drive.**
- **To verify (Windows):** point the source at a folder whose full path is over 260 characters and run `--limit 200` then a full sort. Expected: the scan finds the files, and the copy completes. Also point the source at a folder with a trailing backslash and check the sort still runs.

### 7. `claude` lookup

- **Code:** `find_claude` tries `claude`, `claude.cmd`, `claude.exe`, `claude.ps1` in that order with `shutil.which`. `photosorter/core/labelers/claude.py` calls it. The code tries all four names on every OS. Spec §8.4 specifies plain `claude` on macOS and Linux, so on those systems the extra names are a difference from the spec.
- **Unit-test evidence (fakes only):** `tests/test_platform.py` replaces `shutil.which` and checks the order and the `None` result. `tests/test_labeler_claude.py` stubs the labeller. **The real Claude CLI has not been run through this lookup.**
- **To verify (Windows):** open a new terminal and confirm `claude` is on `PATH`. Start the app, run a label phase on a small sample (`--limit 200`). Expected: the labeller starts and at least one batch returns labels. A missing CLI shows a plain message, not a crash.

### 8. Browser launch

- **Code:** `photosorter/api/serve.py` starts `webbrowser.open` one second after the server starts. This is not in `platform.py`, and the code is not platform-specific, so the spec's placement is not followed. Recorded here as a deviation.
- **Unit-test evidence (fakes only):** `tests/api/test_serve.py`, `test_browser_timer_is_daemon` (lines 133-145). It replaces `threading.Timer` with a spy, calls `serve(..., open_browser=True)`, asserts `assert made and made[0].daemon`, then cancels the timer. It checks only that the timer is a daemon. It does not check the delay or the URL. The test cancels the timer before its one-second delay elapses, so `webbrowser.open` never runs. Nothing enforces that timing. **The real browser launch has never been seen.**
- **To verify:** run `python -m photosorter serve` on each OS. Expected: the default browser opens `http://127.0.0.1:8765/` (or the `--port` value). Record the browser used.

### 9. Destination on another drive

- **Code:** the copy path uses the same `copy_file` as row 2. On Windows this is `shutil.copy2`, which copies across volumes. On macOS, a cross-volume `cp -c` is expected to fail and fall back to `copy2`. This is expected behaviour to confirm, not a result. On Linux, `cp --reflink=auto` is expected to make an ordinary copy across filesystems without failing, so no fallback is expected. `long_path` applies to the destination too.
- **Unit-test evidence:** none. No test uses two volumes.
- **To verify (Windows):** set the source on one drive (for example `C:`) and the destination on another (for example `D:`). Run `--limit 200`, then a full sort. Expected: both CSVs are written to the destination; folders are created on that drive; the source is unchanged (hash before and after).

### 10. Devanagari and emoji filenames through scan, label and copy

- **Code:** file names are carried as Python `str` throughout. Labels and CSVs are written as UTF-8 (row 5). The copy uses the same `copy_file` as row 2.
- **Unit-test evidence:** `tests/test_apply.py` copies a file named with Devanagari (`नमस्ते.jpg`) into a category folder on a real temporary folder, and checks the `sorted.csv` row. This covers copy and CSV only. **No test runs scan or label on a non-ASCII file name.** The emoji test in `tests/test_config.py` covers JSON only. The label path has no non-ASCII name test.
- **To verify (Windows):** prepare a camera-roll folder with files named with Devanagari and with emoji (for example `नमस्ते.jpg`, `🍜 lunch.jpg`). Run the full sort. Expected: the scan lists every file with its original name; the label step labels them; the copy writes each file under its exact name into the right folder; both CSVs show the names unchanged. Open the dashboard lightbox for one of them; the name shows correctly.

### 11. App runs without `PYTHONUTF8=1`

- **Code:** explicit `encoding="utf-8"` everywhere text is read or written (row 5). `photosorter/picker.py` calls `sys.stdout.reconfigure(encoding="utf-8")` in the child process. `photosorter/picker.py`'s `choose_folder` passes `encoding="utf-8"` to the child.
- **Unit-test evidence:** `tests/test_config.py` documents the intent in its docstring. Its test does not remove `PYTHONUTF8` from the environment, so passing it proves nothing about the variable. **No test runs the app with `PYTHONUTF8` unset in a controlled way.**
- **To verify (Windows):** in a new PowerShell session where `PYTHONUTF8` is not set (`echo $env:PYTHONUTF8` prints nothing), start the app with `python -m photosorter serve`. Expected: it starts without a `UnicodeDecodeError`; the setup card loads; a sort with emoji folder names (from `categories.json`) completes.

## Unit tests and what they do not cover

Unit tests exist for rows 1 to 7 and partially for rows 5, 6, 8 and 10. Every such test replaces an OS call or timer (`subprocess.run`, `shutil.which`, `sys.platform`, `threading.Timer`) or runs on the host filesystem with ordinary paths. None of them has been run as part of this document; the check was reading only.

Rows 8, 9 and 11 have no test that covers the real behaviour. Row 8 has only the fake timer test described in its row.

## Deviations from spec §8.4

1. Row 4: Windows open-folder uses `explorer` in the code, where the spec names `os.startfile`.
2. Row 8: browser launch sits in `photosorter/api/serve.py`, not in `platform.py`.
3. Row 7: `find_claude` tries `claude`, `claude.cmd`, `claude.exe` and `claude.ps1` on every OS, where spec §8.4 specifies plain `claude` on macOS and Linux.

Each of these three deviations needs either a spec amendment or a code change. That decision sits outside this document.

## Verification record

| Date | Machine | OS | Rows exercised | Result |
|------|---------|----|----------------|--------|
| (none yet) | | | | No row has been verified on real hardware in this build. |

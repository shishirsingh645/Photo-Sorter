# Photo Sorter — Plan 1: Core Engine & CLI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A tested, cross-platform Python package that scans a photo folder, finds duplicates at any library size, labels every file with Claude, and copies everything into sorted folders — usable end-to-end from the command line with no server and no browser.

**Architecture:** One package, `photosorter/`, with a pure `core/` of importable functions that take a progress callback and never print or touch HTTP, a single `platform.py` holding every OS branch in the codebase, and a thin `__main__.py` CLI over the top. Duplicate detection uses pigeonhole banding over perceptual hashes so cost stays near-linear at any size.

**Tech Stack:** Python 3.11+, Pillow, pillow-heif, imagehash, pytest, ruff. No web framework in this plan.

**Spec:** `docs/superpowers/specs/2026-11-21-photo-sorter-modernized-replica-design.md`

## Global Constraints

- Python 3.11+. Runtime dependencies are exactly `pillow>=10.0`, `pillow-heif>=0.16`, `imagehash>=4.3`. Nothing else.
- **Every** text file open passes `encoding="utf-8"` explicitly. No exceptions. This is the bug that forces `PYTHONUTF8=1` on the reference.
- **Every** filesystem path is a `pathlib.Path`. No `rstrip("/")`, no string concatenation of paths, no `os.sep` comparisons.
- **No `sys.platform` branch anywhere outside `photosorter/platform.py`.** A reviewer rejects the task if one appears elsewhere.
- **Originals are read-only.** No code path may move, rename, write to, or delete a file under the source folder. Copies only.
- Library size is unbounded. No algorithm may be O(n²) in the number of files.
- User-facing message style: plain words, "folder" not "directory", one question at a time.
- Windows is the verified platform; macOS and Linux branches must be written and unit-tested with fakes, never stubbed out or left to raise.

## Review Focus

Five input classes the spec implies but that no feature task naturally exercises. Each has its test assigned to the task that owns the code.

1. **Non-ASCII and over-long paths.** The reference library used for testing sits under a deeply nested Windows path with Devanagari and emoji filenames; Windows also caps paths near 260 characters. Scanning, thumbnailing and copying must all survive both. → Task 6, Task 11.
2. **A file that vanishes or is locked mid-scan.** OneDrive cloud placeholders, antivirus locks and files deleted while scanning are normal on Windows. One bad file must not abort a 100,000-file scan. → Task 6.
3. **Destination on a different drive, or without room.** `D:` source to `C:` destination must work, and the scan must refuse up front with a clear message when the disk cannot hold the previews. → Task 5, Task 11.
4. **A degenerate perceptual-hash bucket.** Thousands of near-identical dark frames collapse into one band bucket and restore quadratic cost locally. → Task 7.
5. **A library with no videos at all** (the owner's real sort had zero). The video catch-all lookup must not raise `IndexError` when no video file exists. → Task 11.

---

### Task 1: Project scaffold, settings and JSON I/O

**Files:**
- Create: `pyproject.toml`, `photosorter/__init__.py`, `photosorter/config.py`, `.gitignore`, `LICENSE`, `tests/__init__.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `photosorter.config.Paths` — frozen dataclass with `root: Path`, and properties `data`, `thumbs`, `mini`, `work`, `labels`, `sheets`, `peek`, `inventory_file`, `slim_file`, `source_file`, `dupes_file`, `labels_file`, `overrides_file`, `jev_file`, `categories_file`, all `Path`.
  - `photosorter.config.Paths.default() -> Paths` — rooted at the repo root.
  - `photosorter.config.read_json(path: Path, default: Any = None) -> Any`
  - `photosorter.config.write_json(path: Path, obj: Any) -> None` — creates parent folders, `encoding="utf-8"`, `ensure_ascii=False`, `indent=1`.

- [ ] **Step 1: Write the failing test**

```python
def test_write_json_round_trips_emoji_without_locale_env(tmp_path):
    p = tmp_path / "nested" / "cats.json"
    write_json(p, [{"label": "Food & drinks", "emoji": "🍜"}])
    assert read_json(p)[0]["emoji"] == "🍜"
    assert "🍜" in p.read_text(encoding="utf-8")

def test_read_json_returns_default_when_missing(tmp_path):
    assert read_json(tmp_path / "nope.json", default={}) == {}

def test_paths_are_all_under_root(tmp_path):
    paths = Paths(root=tmp_path)
    assert paths.thumbs == tmp_path / "data" / "thumbs"
    assert paths.labels == tmp_path / "work" / "labels"
    assert paths.categories_file == tmp_path / "categories.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'photosorter'`

- [ ] **Step 3: Write `pyproject.toml`**

Project name `photo-sorter`, `requires-python = ">=3.11"`, the three runtime dependencies verbatim from Global Constraints, an optional `dev` extra with `pytest` and `ruff`, a console script `photo-sorter = "photosorter.__main__:main"`, and ruff configured with line-length 120.

- [ ] **Step 4: Implement `Paths`, `read_json` and `write_json` in `photosorter/config.py`**

`Paths` is a frozen dataclass over `root`; every other location is a computed property, so no caller ever joins paths by hand. `write_json` must pass `ensure_ascii=False` — without it the emoji round-trip test still passes but the file is unreadable, which defeats the point.

- [ ] **Step 5: Write `.gitignore`** covering `data/`, `work/`, `.env`, `.venv/`, `__pycache__/`, `web/node_modules/`, and **not** `web/dist/`.

- [ ] **Step 6: Copy `LICENSE` from the reference** at `D:\CODING\REA-Photo Sorter\claude-photo-sorter\LICENSE`, preserving the original MIT copyright line, and add a second line attributing this work as a derivative.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml photosorter/ tests/ .gitignore LICENSE
git commit -m "feat: project scaffold with utf-8 safe json io"
```

---

### Task 2: Data models

**Files:**
- Create: `photosorter/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `FileRecord` dataclass: `id: int`, `path: Path`, `name: str`, `ext: str`, `kind: Literal["photo","video"]`, `bytes: int`, `sha256: str`, `w: int = 0`, `h: int = 0`, `duration: float = 0.0`, `phash: str | None = None`, `taken: int | None = None`, `geo: tuple[float, float] | None = None`, `error: str | None = None`.
  - `FileRecord.to_dict() -> dict` (path as `str`) and `FileRecord.from_dict(d) -> FileRecord`.
  - `FileRecord.slim() -> dict` returning exactly `{"id", "kind", "bytes"}` — the §13.2 slim index record.
  - `DupeGroup` dataclass: `keep: int`, `dupes: list[int]`, `type: Literal["exact","near"]`, `freed: int`, plus `to_dict`/`from_dict`.
  - `Category` dataclass: `key: str`, `kind: Literal["photo","video"]`, `label: str`, `emoji: str`, `rule: str`, plus `to_dict`/`from_dict`.
  - `ProgressFn = Callable[[int, int], None]` type alias.
  - `IMAGE_EXTS` and `VIDEO_EXTS` frozensets, copied verbatim from the reference's `common.py`.

- [ ] **Step 1: Write the failing test**

```python
def test_file_record_round_trips_through_dict():
    r = FileRecord(id=3, path=Path("D:/pics/a.jpg"), name="a.jpg", ext=".jpg",
                   kind="photo", bytes=100, sha256="ab")
    assert FileRecord.from_dict(r.to_dict()) == r

def test_slim_record_carries_only_three_fields():
    r = FileRecord(id=3, path=Path("D:/pics/a.jpg"), name="a.jpg", ext=".jpg",
                   kind="photo", bytes=100, sha256="ab", phash="ffff")
    assert r.slim() == {"id": 3, "kind": "photo", "bytes": 100}

def test_extension_sets_match_reference():
    assert ".heic" in IMAGE_EXTS and ".mov" in VIDEO_EXTS
    assert not (IMAGE_EXTS & VIDEO_EXTS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'FileRecord'`

- [ ] **Step 3: Implement the dataclasses in `photosorter/models.py`**

`to_dict` omits `None`-valued optional fields so the inventory stays compact at 100k records; `from_dict` therefore must tolerate their absence.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add photosorter/models.py tests/test_models.py
git commit -m "feat: file, dupe group and category models"
```

---

### Task 3: The platform layer

**Files:**
- Create: `photosorter/platform.py`
- Test: `tests/test_platform.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `copy_file(src: Path, dst: Path) -> None` — clone where the OS supports it, `shutil.copy2` everywhere else, always preserving metadata.
  - `reveal_in_file_manager(path: Path) -> None`
  - `open_folder(path: Path) -> None`
  - `file_manager_name() -> str` — `"File Explorer"`, `"Finder"` or `"file manager"`.
  - `find_claude() -> str | None` — resolves `claude`, `claude.cmd`, `claude.exe`, `claude.ps1`.
  - `free_space_bytes(path: Path) -> int`
  - `long_path(path: Path) -> Path` — on Windows, prefixes `\\?\` for absolute paths over 250 characters; identity elsewhere.

This is the only module in the codebase permitted to read `sys.platform`.

- [ ] **Step 1: Write the failing test**

Tests monkeypatch `sys.platform` and capture `subprocess.run` calls, so all three branches are exercised on Windows.

```python
def test_reveal_uses_explorer_select_with_backslashes_on_windows(monkeypatch, calls):
    monkeypatch.setattr(sys, "platform", "win32")
    reveal_in_file_manager(Path("D:/pics/a.jpg"))
    assert calls[0] == ["explorer", "/select,D:\\pics\\a.jpg"]

def test_reveal_uses_open_dash_r_on_macos(monkeypatch, calls):
    monkeypatch.setattr(sys, "platform", "darwin")
    reveal_in_file_manager(Path("/pics/a.jpg"))
    assert calls[0] == ["open", "-R", "/pics/a.jpg"]

def test_reveal_opens_parent_folder_on_linux(monkeypatch, calls):
    monkeypatch.setattr(sys, "platform", "linux")
    reveal_in_file_manager(Path("/pics/a.jpg"))
    assert calls[0] == ["xdg-open", "/pics"]

def test_file_manager_name_per_platform(monkeypatch):
    for plat, name in [("win32", "File Explorer"), ("darwin", "Finder"), ("linux", "file manager")]:
        monkeypatch.setattr(sys, "platform", plat)
        assert file_manager_name() == name

def test_copy_falls_back_to_copy2_when_clone_fails(monkeypatch, tmp_path):
    # clone command returns non-zero; bytes must still arrive
    ...
    assert dst.read_bytes() == b"hello"

def test_find_claude_finds_cmd_shim_on_windows(monkeypatch):
    # shutil.which returns None for "claude", a path for "claude.cmd"
    assert find_claude().endswith("claude.cmd")

def test_long_path_prefixes_only_long_windows_paths(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert str(long_path(Path("D:/" + "a" * 300))).startswith("\\\\?\\")
    assert not str(long_path(Path("D:/short.jpg"))).startswith("\\\\?\\")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_platform.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'photosorter.platform'`

- [ ] **Step 3: Implement `photosorter/platform.py`**

Copy strategy per the spec's table: macOS tries `cp -c -p` (APFS clone), Linux tries `cp --reflink=auto`, Windows goes straight to `shutil.copy2`; any clone failure falls through to `shutil.copy2` rather than raising. `free_space_bytes` wraps `shutil.disk_usage`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_platform.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add photosorter/platform.py tests/test_platform.py
git commit -m "feat: platform layer for windows, macos and linux"
```

---

### Task 4: Folder picker as a child process

**Files:**
- Create: `photosorter/picker.py`
- Test: `tests/test_picker.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `choose_folder(prompt: str) -> Path | None` — launches this module as a child process, reads the chosen path from its stdout, returns `None` when cancelled.
  - `picker_available() -> tuple[bool, str]` — `(True, "")`, or `(False, <plain-words reason>)` when tkinter is missing.

Running `python -m photosorter.picker "<prompt>"` opens the dialog and prints the path. This is what makes it work on macOS, where tkinter must own the main thread (spec §8.4).

- [ ] **Step 1: Write the failing test**

```python
def test_choose_folder_returns_path_printed_by_child(monkeypatch):
    # child process stubbed to print "D:\\pics\n"
    assert choose_folder("Choose your photos") == Path("D:/pics")

def test_choose_folder_returns_none_when_child_prints_nothing(monkeypatch):
    assert choose_folder("Choose your photos") is None

def test_picker_available_reports_plain_words_when_tkinter_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "tkinter", None)
    ok, reason = picker_available()
    assert ok is False
    assert "folder" in reason and "directory" not in reason

def test_child_process_crash_returns_none_not_exception(monkeypatch):
    # child exits non-zero
    assert choose_folder("x") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_picker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'photosorter.picker'`

- [ ] **Step 3: Implement `photosorter/picker.py`**

The `__main__` block creates a `tkinter.Tk` root, calls `withdraw()`, lifts it to the front, calls `askdirectory(title=prompt)`, prints the result and exits. The parent uses `subprocess.run([sys.executable, "-m", "photosorter.picker", prompt], capture_output=True, text=True)` with a 300-second timeout, and returns `None` on timeout, non-zero exit, or empty output.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_picker.py -v`
Expected: 4 passed

- [ ] **Step 5: Manually verify the real dialog opens**

Run: `python -m photosorter.picker "Choose your photos"`
Expected: a native folder dialog appears; choosing a folder prints its path; cancelling prints nothing.

- [ ] **Step 6: Commit**

```bash
git add photosorter/picker.py tests/test_picker.py
git commit -m "feat: cross-platform folder picker in a child process"
```

---

### Task 5: Categories and the peek step

**Files:**
- Create: `photosorter/core/__init__.py`, `photosorter/core/categories.py`, `photosorter/core/peek.py`, `categories.json`
- Test: `tests/test_categories.py`, `tests/test_peek.py`

**Interfaces:**
- Consumes: `Paths`, `read_json`, `write_json` (Task 1); `Category`, `IMAGE_EXTS`, `VIDEO_EXTS` (Task 2); `free_space_bytes` (Task 3).
- Produces:
  - `load_categories(paths: Paths) -> list[Category]`
  - `save_categories(paths: Paths, cats: list[Category]) -> None`
  - `validate_categories(cats: list[Category]) -> None` — raises `ValueError` with a plain-words message.
  - `categories_fingerprint(paths: Paths) -> str` — first 12 chars of the SHA-1 of the categories file.
  - `catch_all_for(cats: list[Category], kind: str) -> Category | None` — the **last** category of that kind, or `None` when there is none.
  - `peek_folder(source: Path, paths: Paths, preview_count: int = 60) -> PeekResult` — dataclass with `source`, `photos`, `videos`, `bytes`, `previews: list[str]`, `suggested_dest: Path`, `preview_bytes_needed: int`, `free_bytes: int`.

`categories.json` is copied verbatim from the reference — the same 14 folders, same keys, same rules, same emoji, same order.

- [ ] **Step 1: Write the failing test**

```python
def test_validate_rejects_duplicate_keys():
    with pytest.raises(ValueError, match="twice"):
        validate_categories([cat("food"), cat("food")])

def test_validate_rejects_losing_the_last_video_folder():
    with pytest.raises(ValueError, match="video folder"):
        validate_categories([cat("food", kind="photo")])

def test_catch_all_is_the_last_of_its_kind():
    cats = [cat("selfies"), cat("home"), cat("vtalk", kind="video"), cat("vclips", kind="video")]
    assert catch_all_for(cats, "photo").key == "home"
    assert catch_all_for(cats, "video").key == "vclips"

def test_catch_all_returns_none_when_kind_absent():
    assert catch_all_for([cat("selfies")], "video") is None

def test_shipped_categories_file_is_valid_and_has_fourteen_folders():
    cats = load_categories(Paths.default())
    assert len(cats) == 14
    validate_categories(cats)

def test_peek_skips_dotfolders_and_already_sorted_output(tmp_path):
    # tmp_path/.cache/x.jpg and "tmp_path/pics (sorted)/y.jpg" must not be counted
    assert peek_folder(tmp_path, paths).photos == 1

def test_peek_reports_preview_space_needed(tmp_path):
    r = peek_folder(tmp_path, paths)
    assert r.preview_bytes_needed == r.photos * 18_000 + r.videos * 18_000
    assert r.free_bytes > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_categories.py tests/test_peek.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'photosorter.core'`

- [ ] **Step 3: Copy `categories.json`** verbatim from `D:\CODING\REA-Photo Sorter\claude-photo-sorter\categories.json`.

- [ ] **Step 4: Implement `categories.py` and `peek.py`**

`peek_folder` walks once, counting photos and videos and summing bytes, pruning directories whose name starts with `.` or ends with `" (sorted)"`, then writes up to `preview_count` 64px previews into `paths.peek` from a `random.Random(3)` sample — the reference's seed, so previews are reproducible. 18,000 bytes per file is the §13.4 preview estimate.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_categories.py tests/test_peek.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add photosorter/core/ categories.json tests/test_categories.py tests/test_peek.py
git commit -m "feat: categories, validation and folder peek"
```

---

### Task 6: Scanning

**Files:**
- Create: `photosorter/core/scan.py`
- Test: `tests/test_scan.py`

**Interfaces:**
- Consumes: `Paths`, `write_json` (Task 1); `FileRecord`, `IMAGE_EXTS`, `VIDEO_EXTS`, `ProgressFn` (Task 2); `free_space_bytes`, `long_path` (Task 3).
- Produces:
  - `find_files(source: Path, limit: int = 0) -> list[Path]` — sorted, extension-filtered, `._*` excluded; `limit` takes a `random.Random(0)` sample, the reference's seed.
  - `find_sidecar(path: Path) -> Path | None` — Google Takeout metadata, including the `IMG_1(1).JPG` → `IMG_1.JPG...(1).json` case.
  - `scan_folder(source: Path, paths: Paths, limit: int = 0, on_progress: ProgressFn | None = None, cancel: threading.Event | None = None) -> list[FileRecord]` — writes `inventory.json`, the slim index, and `source.json`.

- [ ] **Step 1: Write the failing test**

```python
def test_find_sidecar_matches_plain_name(tmp_path):
    (tmp_path / "IMG_1.JPG").touch(); (tmp_path / "IMG_1.JPG.json").touch()
    assert find_sidecar(tmp_path / "IMG_1.JPG").name == "IMG_1.JPG.json"

def test_find_sidecar_matches_truncated_supplemental_metadata(tmp_path):
    (tmp_path / "IMG_1.JPG").touch(); (tmp_path / "IMG_1.JPG.supplemental-met.json").touch()
    assert find_sidecar(tmp_path / "IMG_1.JPG") is not None

def test_find_sidecar_matches_numbered_copy(tmp_path):
    (tmp_path / "IMG_1(1).JPG").touch(); (tmp_path / "IMG_1.JPG.supplemental-metadata(1).json").touch()
    assert find_sidecar(tmp_path / "IMG_1(1).JPG").name.endswith("(1).json")

def test_find_sidecar_does_not_match_a_different_numbered_copy(tmp_path):
    (tmp_path / "IMG_1.JPG").touch(); (tmp_path / "IMG_1.JPG.supplemental-metadata(1).json").touch()
    assert find_sidecar(tmp_path / "IMG_1.JPG") is None

def test_find_files_skips_appledouble_and_unknown_extensions(tmp_path): ...

def test_limit_sample_is_deterministic(tmp_path):
    assert find_files(tmp_path, limit=5) == find_files(tmp_path, limit=5)

# Review Focus 1 — non-ASCII and long names
def test_scan_handles_devanagari_and_emoji_filenames(tmp_path):
    name = "शादी_फोटो_🎉.jpg"
    make_jpeg(tmp_path / name)
    recs = scan_folder(tmp_path, paths)
    assert recs[0].name == name
    assert (paths.thumbs / "0.jpg").exists()

# Review Focus 2 — a file that cannot be read
def test_unreadable_file_is_kept_with_error_and_does_not_abort_scan(tmp_path):
    make_jpeg(tmp_path / "good.jpg")
    (tmp_path / "bad.jpg").write_bytes(b"not an image")
    recs = scan_folder(tmp_path, paths)
    assert len(recs) == 2
    assert any(r.error for r in recs) and any(r.error is None for r in recs)
    assert (paths.thumbs / "1.jpg").exists()   # placeholder preview still written

def test_vanishing_file_is_recorded_as_an_error_not_an_exception(tmp_path): ...

# Review Focus 3 — not enough room for previews
def test_scan_refuses_in_plain_words_when_disk_cannot_hold_previews(tmp_path, monkeypatch):
    monkeypatch.setattr(platform_mod, "free_space_bytes", lambda p: 1000)
    with pytest.raises(ValueError, match="free space"):
        scan_folder(tmp_path, paths)

def test_progress_is_throttled_not_per_file(tmp_path):
    calls = []
    scan_folder(big_tmp_folder, paths, on_progress=lambda d, t: calls.append(d))
    assert len(calls) < 50          # 500 files, throttled per §13.3
    assert calls[-1] == 500          # final event always fires

def test_cancel_event_stops_the_scan_early(tmp_path): ...

def test_slim_index_is_written_alongside_full_inventory(tmp_path):
    scan_folder(tmp_path, paths)
    slim = read_json(paths.slim_file)
    assert set(slim[0]) == {"id", "kind", "bytes"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan.py -v`
Expected: FAIL with `ImportError: cannot import name 'scan_folder'`

- [ ] **Step 3: Implement `find_files` and `find_sidecar`**

The sidecar rules are the reference's, which the tests above pin exactly: a numbered copy matches only a sidecar with the same number, and a plain name must *not* match a numbered sidecar.

- [ ] **Step 4: Implement `scan_folder`**

Clears and recreates `thumbs/` and `mini/`, checks free space against `len(files) * 18_000` before starting, then processes through a `ThreadPoolExecutor(8)`. Per file: size, sha256 (1 MiB chunks), dimensions, a 256×256 centre-cropped preview at quality 80, a 72×72 mini at quality 72, and `imagehash.phash` of the preview. Videos go through `ffprobe`/`ffmpeg` when present (honouring the rotate tag, frame grabbed at 1s or 0s when under 2s) and get a grey 256px placeholder when not. Any per-file exception is caught, stored in `error`, and given a beige placeholder preview — never re-raised. Progress is throttled per §13.3: at most 10 calls/second and at most one per 0.5% of total, with a guaranteed final call.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_scan.py -v`
Expected: 13 passed

- [ ] **Step 6: Commit**

```bash
git add photosorter/core/scan.py tests/test_scan.py
git commit -m "feat: scanning with previews, hashes and takeout sidecars"
```

---

### Task 7: Duplicate detection at any scale

**Files:**
- Create: `photosorter/core/dupes.py`
- Test: `tests/test_dupes.py`

**Interfaces:**
- Consumes: `Paths`, `write_json` (Task 1); `FileRecord`, `DupeGroup`, `ProgressFn` (Task 2).
- Produces:
  - `band_keys(phash_hex: str, bands: int = 5) -> list[tuple[int, int]]` — the §13.1 pigeonhole bands.
  - `hamming(a_hex: str, b_hex: str) -> int`
  - `find_duplicates(records, paths, on_progress=None, max_bucket=10_000) -> DuplicateResult` — writes `dupes.json` and `work/duplicates.jpg`.
  - `DuplicateResult` dataclass: `groups: list[DupeGroup]`, `oversized_buckets: int`, `pairs_compared: int`.
  - `build_dupe_sheet(groups, paths, limit: int = 60) -> Path | None` — the reference's eyeball-check contact sheet.

**This is the task that makes an unbounded library possible.** It must be exact — the same groups the reference's nested loop finds, no more and no fewer.

- [ ] **Step 1: Write the failing test**

```python
def test_bands_cover_all_64_bits_without_overlap():
    keys = band_keys("ffffffffffffffff")
    assert len(keys) == 5 and len({i for i, _ in keys}) == 5

def test_hashes_within_distance_four_always_share_a_band():
    # pigeonhole guarantee — the correctness proof of the whole approach
    base = 0x0123456789abcdef
    for positions in itertools.combinations(range(64), 4):
        other = base
        for p in positions:
            other ^= 1 << p
        assert set(band_keys(f"{base:016x}")) & set(band_keys(f"{other:016x}"))

def test_exact_duplicates_grouped_by_sha256(): ...

def test_near_duplicates_grouped_within_distance_four(): ...

def test_distance_five_is_not_a_duplicate(): ...

def test_photo_and_video_never_group_together(): ...

def test_keeper_is_largest_then_shortest_name():
    g = find_duplicates([rec(0, b=100, name="aaaa.jpg"), rec(1, b=100, name="a.jpg"),
                         rec(2, b=50, name="b.jpg")], paths).groups[0]
    assert g.keep == 1

def test_png_pixel_guard_separates_different_screens_of_the_same_app(): ...
def test_png_pixel_guard_still_groups_resaved_identical_screenshots(): ...

def test_results_match_bruteforce_on_a_random_library():
    # the exactness proof: 400 synthetic records, banded result == nested-loop result
    assert groups_of(find_duplicates(recs, paths).groups) == groups_of(bruteforce(recs))

# Review Focus 4 — degenerate bucket
def test_thousands_of_identical_hashes_stay_fast_and_are_reported():
    recs = [rec(i, phash="0000000000000000") for i in range(5000)]
    t0 = time.monotonic()
    result = find_duplicates(recs, paths, max_bucket=1000)
    assert time.monotonic() - t0 < 10
    assert result.oversized_buckets >= 1

def test_records_with_errors_are_excluded_from_near_matching(): ...

def test_dupe_sheet_shows_the_keeper_first_in_each_row():
    sheet = build_dupe_sheet(groups, paths)
    assert sheet.exists()

def test_dupe_sheet_is_skipped_when_there_are_no_duplicates():
    assert build_dupe_sheet([], paths) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dupes.py -v`
Expected: FAIL with `ImportError: cannot import name 'find_duplicates'`

- [ ] **Step 3: Implement `band_keys` and `hamming`**

Split the 64-bit hash into 5 segments of 13/13/13/13/12 bits. Each key is `(segment_index, segment_value)`. With at most 4 differing bits across 5 segments, at least one segment is identical — that is why the banded search misses nothing.

- [ ] **Step 4: Implement `find_duplicates`**

Union-find over record ids. Pass 1: group identical `sha256`. Pass 2: build `dict[(band, value)] -> list[id]`, then compare only within buckets, skipping buckets larger than `max_bucket` beyond their first `max_bucket` members and counting them in `oversized_buckets`. Each candidate pair is confirmed with the real Hamming distance, the same-`kind` rule, and the PNG pixel guard (both `.png`, different `sha256`, > 0.4% of preview pixels differing by more than 40 → not a duplicate). Keeper per group is largest `bytes`, then shortest `name`.

- [ ] **Step 5: Implement `build_dupe_sheet`**

One row per group with the keeper first, at most 8 columns and `limit` rows, 160px tiles on a 170px pitch, each tagged with its id and the keeper additionally tagged `KEEP`, written to `work/duplicates.jpg` at quality 80. Returns `None` when there are no groups.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_dupes.py -v`
Expected: 15 passed

- [ ] **Step 7: Commit**

```bash
git add photosorter/core/dupes.py tests/test_dupes.py
git commit -m "feat: near-linear duplicate detection via pigeonhole banding"
```

---

### Task 8: Contact sheets

**Files:**
- Create: `photosorter/core/sheets.py`
- Test: `tests/test_sheets.py`

**Interfaces:**
- Consumes: `Paths` (Task 1); `FileRecord` (Task 2).
- Produces:
  - `build_sheets(records, paths, sample: bool = False) -> list[Path]`
  - `ids_in_sheet_range(records, first_sheet: int, last_sheet: int, per_sheet: int = 30) -> list[str]`

- [ ] **Step 1: Write the failing test**

```python
def test_thirty_previews_per_sheet_in_a_six_by_five_grid():
    sheets = build_sheets(records(65), paths)
    assert len(sheets) == 3
    assert Image.open(sheets[0]).size == (6 * 230, 5 * 230)

def test_video_tiles_are_tagged_with_video_and_seconds(): ...
def test_png_tiles_are_tagged_png(): ...
def test_sample_mode_writes_at_most_three_sheets_deterministically():
    assert build_sheets(records(500), paths, sample=True) == build_sheets(records(500), paths, sample=True)

def test_ids_in_sheet_range_covers_exactly_those_sheets():
    assert ids_in_sheet_range(records(100), 0, 2) == [str(i) for i in range(90)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sheets.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_sheets'`

- [ ] **Step 3: Implement `build_sheets`**

230px cells, 222px thumbnails inset 4px, id tag drawn in yellow on a black rectangle, `" VIDEO {duration:.0f}s"` appended for video and `" PNG"` for `.png`. Font resolution tries the platform's own fonts and falls back to `ImageFont.load_default()`. `sample=True` takes 90 records with `random.Random(1)` — the reference's seed — into `paths.work / "sample"`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sheets.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add photosorter/core/sheets.py tests/test_sheets.py
git commit -m "feat: contact sheets for the labeller"
```

---

### Task 9: The Claude labeller

**Files:**
- Create: `photosorter/core/labelers/__init__.py`, `photosorter/core/labelers/base.py`, `photosorter/core/labelers/claude.py`
- Test: `tests/test_labeler_claude.py`

**Interfaces:**
- Consumes: `Paths`, `read_json`, `write_json` (Task 1); `FileRecord`, `Category`, `ProgressFn` (Task 2); `find_claude` (Task 3); `build_sheets`, `ids_in_sheet_range` (Task 8).
- Produces:
  - `base.Labeler` Protocol with `label(self, records, cats, paths, on_progress=None, cancel=None) -> dict[str, str]` and `name: str`.
  - `base.LabelerUnavailable(Exception)` — carries a plain-words message.
  - `claude.ClaudeLabeler(model: str = "sonnet", workers: int = 4, sheets_per_batch: int = 3)`.
  - `claude.build_prompt(cats, sheet_paths) -> str`
  - `claude.parse_label_response(stdout: str, wanted: list[str]) -> dict[str, str]`

- [ ] **Step 1: Write the failing test**

The subprocess is stubbed throughout; **no test may invoke the real `claude` CLI.**

```python
def test_prompt_lists_every_folder_as_key_kind_rule():
    p = build_prompt(cats, [Path("sheet_00.jpg")])
    assert "food (photo): meals, snacks" in p
    assert "sheet_00.jpg" in p

def test_parse_extracts_first_json_object_and_drops_foreign_ids():
    out = '{"result": "Sure! {\\"1\\": \\"food\\", \\"99\\": \\"pets\\"} done"}'
    assert parse_label_response(out, ["1", "2"]) == {"1": "food"}

def test_parse_returns_empty_dict_on_unparseable_output():
    assert parse_label_response("I could not read those images", ["1"]) == {}

def test_batch_accepted_at_ninety_percent_coverage(): ...
def test_batch_below_ninety_percent_triggers_retry(): ...
def test_batch_fails_after_four_attempts_with_reason(): ...

def test_finished_batches_are_cached_and_skipped_on_rerun():
    labeler.label(recs, cats, paths)
    calls_before = stub.call_count
    labeler.label(recs, cats, paths)
    assert stub.call_count == calls_before

def test_missing_claude_cli_raises_labeler_unavailable_in_plain_words():
    with pytest.raises(LabelerUnavailable, match="Claude Code"):
        ClaudeLabeler().label(recs, cats, paths)

def test_cancel_event_stops_dispatching_new_batches(): ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_labeler_claude.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'photosorter.core.labelers'`

- [ ] **Step 3: Implement `base.py` and `claude.py`**

The CLI invocation is fixed by the spec and must be exact:

```python
[claude, "-p", prompt, "--model", model, "--allowedTools", "Read", "--strict-mcp-config",
 "--setting-sources", "project", "--no-session-persistence", "--output-format", "json"]
```

run with `cwd=paths.work` and `timeout=900`. Batches are 3 sheets, dispatched through a `ThreadPoolExecutor(workers)`; each writes `work/labels/claude_NN.json` on success and `work/claude_failed_NN.txt` on a failed attempt. Accept at ≥ 90% of wanted ids; otherwise retry up to 4 attempts with `8 × attempt` seconds of backoff. `CLAUDE_WORKERS` and `CLAUDE_MODEL` override the defaults.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_labeler_claude.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add photosorter/core/labelers/ tests/test_labeler_claude.py
git commit -m "feat: claude labeller with batching, retries and caching"
```

---

### Task 10: The Jev labeller

**Files:**
- Create: `photosorter/core/labelers/jev.py`
- Test: `tests/test_labeler_jev.py`

**Interfaces:**
- Consumes: `base.Labeler`, `LabelerUnavailable` (Task 9).
- Produces:
  - `JevLabeler(model: str = "jev-1.14.0", workers: int = 6)` with `estimate(records) -> JevEstimate` (`files: int`, `tokens: int`), and `label(...) -> dict[str, dict]` returning `{"key", "confidence", "tokens"}` per id.
  - `find_jev_key(paths: Paths) -> str | None` — environment first (`JEV_KEY`, `TYPESAFE_API_KEY`), then `.env`.
  - `TOKENS_PER_FILE = 980`

All HTTP is stubbed in tests. **No test may make a real network call.**

- [ ] **Step 1: Write the failing test**

```python
def test_estimate_counts_only_unlabelled_files():
    assert JevLabeler().estimate(recs, done={"0": {...}}).files == len(recs) - 1

def test_estimate_uses_980_tokens_per_file():
    assert JevLabeler().estimate(recs).tokens == len(recs) * 980

def test_find_key_prefers_environment_over_dotenv(monkeypatch, tmp_path): ...
def test_find_key_strips_quotes_from_dotenv_value(tmp_path): ...

def test_401_aborts_immediately_without_retrying(stub):
    with pytest.raises(LabelerUnavailable, match="key"):
        JevLabeler().label(recs, cats, paths)
    assert stub.call_count == 1

def test_429_is_retried_with_backoff(stub): ...
def test_results_are_saved_incrementally_so_a_run_can_resume(): ...
def test_video_records_are_asked_with_video_criteria_only(): ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_labeler_jev.py -v`
Expected: FAIL with `ImportError: cannot import name 'JevLabeler'`

- [ ] **Step 3: Implement `jev.py`**

`POST https://api.typesafe.ai/v1/systemone` with headers `Authorization: Bearer <key>`, `Content-Type: application/json` and `TypeSafe-Danger-Zone-Images: true`. Body carries a 280px JPEG (quality 85) of the preview, and a `choice` question whose criteria are the `key → rule` map **for that file's kind only**. 401/403 raise `LabelerUnavailable`; 429 and 5xx retry 5 times with exponential backoff; other codes stop. Results are flushed to `work/jev.json` every 50 files so a stopped run resumes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_labeler_jev.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add photosorter/core/labelers/jev.py tests/test_labeler_jev.py
git commit -m "feat: optional jev labeller behind an estimate gate"
```

---

### Task 11: Building the sorted folders

**Files:**
- Create: `photosorter/core/apply.py`
- Test: `tests/test_apply.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `merge_labels(records, claude, jev, overrides, cats) -> MergeResult` — `labels: dict[str, str]`, `missing: int`, `fixed: int`.
  - `folder_name(cat: Category) -> str` — `label` with `&` → `and` and `/` → `-`.
  - `apply_labels(records, dupes, labels, dest: Path, paths, on_progress=None, cancel=None) -> ApplyResult` — `counts: dict[str, int]`, `copied: int`, `dest: Path`.
  - `check_destination(source: Path, dest: Path) -> None` — raises `ValueError` in plain words.

**This task owns the "never touch originals" guarantee.** Every test below is a guard on it.

- [ ] **Step 1: Write the failing test**

```python
def test_jev_wins_above_seventy_percent_confidence():
    assert merge("food", jev=("pets", 0.8)).labels["0"] == "pets"

def test_claude_wins_when_jev_is_unsure():
    assert merge("food", jev=("pets", 0.5)).labels["0"] == "food"

def test_jev_is_used_when_claude_has_no_answer():
    assert merge(None, jev=("pets", 0.1)).labels["0"] == "pets"

def test_overrides_beat_everything():
    assert merge("food", jev=("pets", 0.9), overrides={"0": "travel"}).labels["0"] == "travel"

def test_photo_labelled_with_a_video_folder_falls_to_the_photo_catch_all():
    r = merge("vtalk", kind="photo")
    assert r.labels["0"] == "screenshots" and r.fixed == 1

def test_unknown_folder_key_falls_to_the_catch_all(): ...
def test_unlabelled_file_is_counted_as_missing_and_still_placed(): ...

# Review Focus 5 — a library with no videos at all
def test_library_with_no_videos_does_not_raise():
    result = apply_labels(photo_only_records, [], labels, dest, paths)
    assert result.copied == len(photo_only_records)

def test_folder_name_replaces_ampersand_and_slash():
    assert folder_name(cat(label="Food & drinks")) == "Food and drinks"

def test_duplicates_go_to_review_duplicates(tmp_path):
    apply_labels(recs, dupes, labels, dest, paths)
    assert (dest / "_Review" / "duplicates" / "copy.jpg").exists()

def test_name_collision_gets_the_id_suffix(tmp_path):
    # two files called IMG_1.JPG from different subfolders, same folder
    assert (dest / "Selfies" / "IMG_1__1.JPG").exists()

def test_originals_are_never_modified(tmp_path):
    before = snapshot(source_tree)
    apply_labels(recs, dupes, labels, dest, paths)
    assert snapshot(source_tree) == before

def test_rerun_is_idempotent_and_removes_only_its_own_files(tmp_path):
    apply_labels(recs, dupes, labels, dest, paths)
    (dest / "my notes.txt").write_text("keep me", encoding="utf-8")
    before = snapshot(dest / "Selfies")
    apply_labels(recs, dupes, labels, dest, paths)
    assert snapshot(dest / "Selfies") == before
    assert (dest / "my notes.txt").read_text(encoding="utf-8") == "keep me"

def test_destination_inside_source_is_refused_in_plain_words():
    with pytest.raises(ValueError, match="outside"):
        check_destination(Path("D:/pics"), Path("D:/pics/sorted"))

# Review Focus 3 — cross-drive destination
def test_destination_on_another_drive_is_allowed():
    check_destination(Path("D:/pics"), Path("C:/sorted"))   # must not raise

# Review Focus 1 — long paths
def test_deeply_nested_long_names_copy_on_windows(tmp_path): ...

def test_sorted_and_duplicates_csv_have_the_specified_columns(tmp_path):
    assert header(dest / "sorted.csv") == ["file", "folder", "original_path"]
    assert header(dest / "duplicates.csv") == ["duplicate", "kept_copy", "type",
                                               "duplicate_path", "kept_path"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_apply.py -v`
Expected: FAIL with `ImportError: cannot import name 'apply_labels'`

- [ ] **Step 3: Implement `merge_labels`, `folder_name` and `check_destination`**

Merge order is fixed by spec §7.3 and pinned by the tests: Claude, then Jev at ≥ 0.7 confidence or where Claude is silent, then the kind guard to `catch_all_for(cats, kind)`, then overrides. When `catch_all_for` returns `None` for a kind that has no files, nothing must raise — that is Review Focus 5.

- [ ] **Step 4: Implement `apply_labels`**

Rebuild logic first: if `sorted.csv` exists, read it and delete exactly the files it lists, then prune directories that are now empty, then rebuild — never a blanket `rmtree`. Copy each record with `platform.copy_file` through `long_path`, collide to `<base>__<id><ext>`, and stream both CSVs with `newline=""` and `encoding="utf-8"`. Duplicates are routed to `_Review/duplicates` regardless of label. Progress is throttled per §13.3.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_apply.py -v`
Expected: 17 passed

- [ ] **Step 6: Commit**

```bash
git add photosorter/core/apply.py tests/test_apply.py
git commit -m "feat: build sorted folders, idempotent and read-only on originals"
```

---

### Task 12: Demo library generator

**Files:**
- Create: `photosorter/core/demo.py`
- Test: `tests/test_demo.py`

**Interfaces:**
- Consumes: `Paths`, `write_json` (Task 1); `load_categories` (Task 5).
- Produces: `build_demo(paths: Paths, out: Path | None = None) -> int` — returns the number of files generated; writes `thumbs/`, `mini/`, `inventory.json`, slim index, `labels.json`, `dupes.json`, `categories.json`, `source.json` into `out` (default `paths.data.parent / "demo"`).

- [ ] **Step 1: Write the failing test**

```python
def test_demo_is_deterministic(tmp_path):
    assert build_demo(paths, tmp_path / "a") == build_demo(paths, tmp_path / "b")
    assert (tmp_path / "a" / "thumbs" / "0.jpg").read_bytes() == \
           (tmp_path / "b" / "thumbs" / "0.jpg").read_bytes()

def test_demo_covers_every_category(tmp_path):
    build_demo(paths, tmp_path)
    labels = read_json(tmp_path / "labels.json")
    assert set(labels.values()) == {c.key for c in load_categories(paths)}

def test_demo_uses_no_real_photos(tmp_path):
    inv = read_json(tmp_path / "inventory.json")
    assert all("path" not in r for r in inv)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_demo.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_demo'`

- [ ] **Step 3: Implement `build_demo`**

Port the reference's `demo.py` drawing routines (per-category procedural shapes for screenshots, documents, memes, landscapes, city nights, food, pets and people), its `WEIGHTS` table and its `random.Random(7)` seed, so the generated library is byte-identical run to run. No `path` field is written — these files do not exist on disk.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_demo.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add photosorter/core/demo.py tests/test_demo.py
git commit -m "feat: procedural demo camera roll"
```

---

### Task 13: Command-line interface and full-pipeline smoke test

**Files:**
- Create: `photosorter/__main__.py`
- Test: `tests/test_cli.py`, `tests/test_pipeline_smoke.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `main(argv: list[str] | None = None) -> int` with subcommands `scan`, `dupes`, `sheets`, `label`, `apply`, `demo`, `sort`, each printing human-readable progress and returning a process exit code.

`sort` runs the whole pipeline: scan (skipped when the source and limit are unchanged), dupes, label, apply.

- [ ] **Step 1: Write the failing test**

```python
def test_scan_subcommand_reports_counts(capsys, tmp_path):
    assert main(["scan", str(tmp_path)]) == 0
    assert "files" in capsys.readouterr().out

def test_apply_without_labels_explains_what_to_do_first(capsys):
    assert main(["apply", str(dest)]) == 1
    assert "label" in capsys.readouterr().out.lower()

def test_sort_skips_rescan_when_source_and_limit_unchanged(tmp_path): ...

def test_changing_categories_invalidates_cached_labels(tmp_path):
    # fingerprint differs -> work/labels is cleared
    ...

# the smoke test — full pipeline, stubbed labeller, no claude CLI, no network
def test_full_pipeline_over_the_demo_library_with_a_stub_labeller(tmp_path):
    source = make_synthetic_camera_roll(tmp_path, n=120)
    assert main(["sort", str(source), "--dest", str(tmp_path / "out"),
                 "--labeler", "stub"]) == 0
    assert (tmp_path / "out" / "sorted.csv").exists()
    assert sum(1 for _ in csv_rows(tmp_path / "out" / "sorted.csv")) == 120
    assert snapshot(source) == snapshot_taken_before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py tests/test_pipeline_smoke.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'photosorter.__main__'`

- [ ] **Step 3: Implement `main` with `argparse`**

A `--labeler` choice of `claude` (default), `jev` or `stub`; `stub` assigns each record the first category of its kind and exists so CI never needs the Claude CLI or a paid key. `sort` compares the stored source and limit against the request to decide whether to rescan, and clears `work/labels` when `categories_fingerprint` has changed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ -v`
Expected: all tests pass

- [ ] **Step 5: Run the real thing once, end to end**

Run: `python -m photosorter demo` then `python -m photosorter sort "<a small real folder>" --dest "<a temp folder>" --limit 50`
Expected: exits 0, the sorted folders and both CSVs exist, and the source folder is untouched.

- [ ] **Step 6: Commit**

```bash
git add photosorter/__main__.py tests/
git commit -m "feat: command line interface and full pipeline smoke test"
```

---

## Done when

`python -m photosorter sort "<folder>" --dest "<folder>"` sorts a real camera roll on Windows, every test passes, `ruff check` is clean, and no `sys.platform` appears outside `photosorter/platform.py`.

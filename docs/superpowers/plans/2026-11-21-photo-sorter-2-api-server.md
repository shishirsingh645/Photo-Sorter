# Photo Sorter — Plan 2: API Server & Job Runner

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A loopback-only FastAPI server that drives the core engine from HTTP, streams live progress over Server-Sent Events, serves originals with range support, and exposes a typed OpenAPI schema the frontend generates its client from.

**Architecture:** FastAPI app with four routers over a single in-process job runner. The runner executes one job at a time in a worker thread, calling `core` functions directly with a progress callback — no subprocesses, no stdout scraping. Progress is throttled and fanned out to every connected SSE client; `/api/state` stays as the initial-load and reconnect fallback.

**Tech Stack:** FastAPI, uvicorn, pydantic v2, `httpx` + `pytest-asyncio` for tests. Builds on Plan 1's `photosorter` package.

**Spec:** `docs/superpowers/specs/2026-11-21-photo-sorter-modernized-replica-design.md`

**Depends on:** Plan 1, all tasks complete.

## Global Constraints

- Everything in Plan 1's Global Constraints still applies: utf-8 everywhere, `pathlib` everywhere, no `sys.platform` outside `platform.py`, originals read-only, nothing O(n²).
- The server binds **`127.0.0.1` only**. Never `0.0.0.0`, not even behind a flag.
- Every mutating request is rejected unless its `Origin` header is absent or one of `http://127.0.0.1:<port>` / `http://localhost:<port>`.
- One job at a time. A second start request while a job runs is an error, not a queue.
- Added runtime dependencies: `fastapi`, `uvicorn[standard]`, `pydantic`. Nothing else.
- Default port 8765, overridable with `--port`; the parity sweep runs this on 8766 beside the reference on 8765.

## Review Focus

1. **A browser reloaded mid-sort.** The page must reattach to the running job and keep animating, not restart it or show an empty dashboard. → Task 3.
2. **An SSE connection that drops** (sleep, network blip, closed laptop lid). The UI must recover from `/api/state` without stranding, and the server must not leak the dead subscriber queue. → Task 2.
3. **A job that raises.** An exception inside a phase must end the job with a readable message and `running=False`, never leave `running=True` forever and wedge the app. → Task 2.
4. **A range request for a 4 GB video**, including an open-ended `bytes=1000-` and a client that disconnects mid-stream. → Task 5.
5. **A path traversal attempt** through any endpoint that accepts a path (`/api/open`, `/api/peek`). Nothing outside the chosen source or destination may be opened or revealed. → Task 4.

---

### Task 1: App skeleton, origin guard and `/api/state`

**Files:**
- Create: `photosorter/api/__init__.py`, `photosorter/api/app.py`, `photosorter/api/schemas.py`, `photosorter/api/routes_state.py`
- Test: `tests/api/test_state.py`, `tests/api/test_origin_guard.py`

**Interfaces:**
- Consumes: `Paths`, `read_json` (P1 T1); `load_categories` (P1 T5); `find_claude` (P1 T3); `find_jev_key` (P1 T10).
- Produces:
  - `create_app(paths: Paths, port: int = 8765) -> FastAPI`
  - `schemas.AppState` pydantic model with fields `categories`, `source`, `limit`, `sorted`, `files`, `bytes`, `steps`, `jev_key`, `claude_cli`, `overrides`, `job`, `platform` — the same shape as the reference's `/api/state`.
  - `schemas.JobState`: `step`, `running`, `code`, `phase`, `phases`, `done`, `total`, `started`, `phase_started`, `timings`, `log`.
  - `schemas.StepFlags`: `scan`, `dupes`, `label`, `jev_labels`, `apply`.
  - `build_state(paths, runner) -> AppState`

- [ ] **Step 1: Write the failing test**

```python
def test_state_on_an_empty_install_reports_no_steps_done(client):
    s = client.get("/api/state").json()
    assert s["files"] == 0
    assert s["steps"] == {"scan": False, "dupes": False, "label": False,
                          "jev_labels": False, "apply": False}
    assert len(s["categories"]) == 14

def test_state_reports_claude_and_jev_availability(client, monkeypatch): ...

def test_post_from_a_foreign_origin_is_rejected(client):
    r = client.post("/api/peek", json={"source": "."},
                    headers={"Origin": "http://evil.example"})
    assert r.status_code == 403

def test_post_with_no_origin_header_is_allowed(client): ...
def test_post_from_localhost_origin_is_allowed(client): ...
def test_get_requests_are_not_origin_guarded(client): ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_state.py tests/api/test_origin_guard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'photosorter.api'`

- [ ] **Step 3: Implement `schemas.py`, the origin-guard middleware and `routes_state.py`**

The guard is HTTP middleware, so no route can forget it. It applies to `POST`, `PUT`, `PATCH` and `DELETE` only.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/ -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add photosorter/api/ tests/api/
git commit -m "feat: fastapi app, origin guard and state endpoint"
```

---

### Task 2: The job runner and SSE events

**Files:**
- Create: `photosorter/jobs.py`, `photosorter/api/routes_events.py`
- Test: `tests/test_jobs.py`, `tests/api/test_events.py`

**Interfaces:**
- Consumes: `ProgressFn` (P1 T2).
- Produces:
  - `JobRunner(paths: Paths)` with:
    - `start(step: str, phases: list[str], body: Callable[[JobContext], None]) -> None` — raises `JobBusy` if one is already running.
    - `state() -> JobState`
    - `cancel() -> None`
    - `subscribe() -> AsyncIterator[JobEvent]`
  - `JobContext` passed to the body: `.run_phase(name: str, fn: Callable[[ProgressFn], int])`, `.log(msg: str)`, `.cancel_event: threading.Event`.
  - `JobEvent` discriminated union on `type`: `phase_started`, `progress`, `log`, `job_finished`.
  - `JobBusy(Exception)`.
  - `GET /api/events` — an SSE stream of `JobEvent` JSON.

- [ ] **Step 1: Write the failing test**

```python
def test_second_start_while_running_raises_job_busy(): ...

def test_phases_are_timed_and_recorded_in_order():
    runner.start("sort", ["scan", "dupes"], body); wait(runner)
    assert list(runner.state().timings) == ["scan", "dupes"]

# Review Focus 3 — a phase that raises
def test_exception_inside_a_phase_ends_the_job_with_a_message():
    runner.start("sort", ["scan"], lambda ctx: ctx.run_phase("scan", boom)); wait(runner)
    s = runner.state()
    assert s.running is False and s.code != 0
    assert "boom" in " ".join(s.log)

def test_cancel_sets_the_event_and_finishes_the_job(): ...

def test_progress_is_throttled_to_ten_per_second_with_a_final_event():
    events = collect(runner, lambda ctx: ctx.run_phase("scan", emit_1000_quickly))
    assert len([e for e in events if e.type == "progress"]) < 40
    assert events[-2].done == 1000

def test_every_subscriber_receives_the_same_events(): ...

# Review Focus 2 — a dropped subscriber
def test_a_dropped_subscriber_is_removed_and_does_not_block_others():
    a, b = runner.subscribe(), runner.subscribe()
    drop(b)
    run_a_job()
    assert received(a) and runner.subscriber_count == 1

def test_events_endpoint_streams_text_event_stream(client):
    with client.stream("GET", "/api/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'photosorter.jobs'`

- [ ] **Step 3: Implement `JobRunner`**

The body runs in a `threading.Thread(daemon=True)`. Events cross into the event loop with `asyncio.run_coroutine_threadsafe` onto per-subscriber `asyncio.Queue`s; a queue that is full or whose consumer has gone is dropped from the subscriber set rather than awaited. The body is wrapped so **any** exception sets `running=False`, `code=1` and appends the message to the log — Review Focus 3.

- [ ] **Step 4: Implement `routes_events.py`** as a `StreamingResponse` over `runner.subscribe()`, sending a comment heartbeat every 15 seconds so idle proxies and sleeping laptops do not silently kill the stream.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_jobs.py tests/api/test_events.py -v`
Expected: 9 passed

- [ ] **Step 6: Commit**

```bash
git add photosorter/jobs.py photosorter/api/routes_events.py tests/
git commit -m "feat: in-process job runner with throttled sse progress"
```

---

### Task 3: Sort and single-step endpoints

**Files:**
- Create: `photosorter/api/routes_jobs.py`
- Test: `tests/api/test_jobs_routes.py`

**Interfaces:**
- Consumes: `JobRunner` (T2); `scan_folder`, `find_duplicates`, labellers, `apply_labels`, `categories_fingerprint` (Plan 1).
- Produces:
  - `POST /api/sort` — body `{source, dest, labeler, limit}` → `AppState`.
  - `POST /api/run` — body `{step, ...}` for one phase → `AppState`.
  - `POST /api/cancel` → `AppState`.
  - `GET /api/labels` → `dict[str, str]`, the labels written so far.

- [ ] **Step 1: Write the failing test**

```python
def test_sort_rejects_a_source_folder_that_does_not_exist(client):
    r = client.post("/api/sort", json={"source": "D:/nope", "dest": "D:/out"})
    assert r.status_code == 400 and "folder" in r.json()["error"]

def test_sort_rejects_claude_labeller_when_cli_is_missing(client, monkeypatch): ...
def test_sort_rejects_jev_labeller_without_a_key(client, monkeypatch): ...

def test_sort_skips_the_scan_phase_when_source_and_limit_are_unchanged(client):
    assert client.post("/api/sort", json=same_as_last_time).json()["job"]["phases"] \
        == ["dupes", "label", "apply"]

def test_changing_the_limit_forces_a_rescan(client): ...

def test_label_phase_failure_is_tolerated_above_ninety_five_percent(client):
    # 96% labelled -> job still reaches apply and finishes with code 0
    ...

def test_label_phase_failure_below_ninety_five_percent_fails_the_job(client): ...

def test_changing_categories_clears_cached_label_batches(client): ...

def test_starting_a_second_sort_while_one_runs_returns_an_error(client):
    assert client.post("/api/sort", json=ok).status_code == 400

# Review Focus 1 — reload mid-sort
def test_state_during_a_running_sort_lets_a_fresh_client_reattach(client):
    s = client.get("/api/state").json()
    assert s["job"]["running"] is True and s["job"]["step"] == "sort"
    assert s["job"]["phase"] in ("scan", "dupes", "label", "apply")

def test_live_labels_endpoint_merges_claude_batches_and_confident_jev(client): ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_jobs_routes.py -v`
Expected: FAIL with 404 on `/api/sort`

- [ ] **Step 3: Implement `routes_jobs.py`**

`/api/sort` validates, decides the phase list, then submits a body that calls Plan 1's core functions in order through `ctx.run_phase`. The 95% label tolerance and the categories-fingerprint invalidation are spec §7.2 and are pinned by the tests above. Errors become `400` with `{"error": "<plain words>"}`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/test_jobs_routes.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add photosorter/api/routes_jobs.py tests/api/test_jobs_routes.py
git commit -m "feat: sort and single-step endpoints over the job runner"
```

---

### Task 4: Folder endpoints — peek, categories, move, open, pick

**Files:**
- Create: `photosorter/api/routes_folders.py`
- Test: `tests/api/test_folders_routes.py`

**Interfaces:**
- Consumes: `peek_folder`, `save_categories`, `validate_categories` (P1 T5); `reveal_in_file_manager`, `open_folder`, `file_manager_name` (P1 T3); `choose_folder`, `picker_available` (P1 T4).
- Produces: `POST /api/peek`, `POST /api/categories`, `POST /api/move`, `POST /api/open`, `POST /api/pick`.

- [ ] **Step 1: Write the failing test**

```python
def test_peek_returns_counts_and_a_suggested_destination(client, tmp_path):
    r = client.post("/api/peek", json={"source": str(tmp_path)}).json()
    assert r["suggested_dest"].endswith(" (sorted)")
    assert r["preview_bytes_needed"] > 0

def test_categories_rejects_removing_the_last_video_folder(client):
    assert client.post("/api/categories", json={"categories": photos_only}).status_code == 400

def test_move_records_an_override_and_updates_labels(client):
    client.post("/api/move", json={"id": 3, "key": "food"})
    assert read_json(paths.overrides_file)["3"] == "food"
    assert read_json(paths.labels_file)["3"] == "food"

def test_pick_returns_the_chosen_path(client, monkeypatch): ...

def test_pick_explains_itself_when_tkinter_is_unavailable(client, monkeypatch):
    r = client.post("/api/pick", json={"prompt": "x"}).json()
    assert r["path"] is None and "folder" in r["reason"]

def test_open_reveals_a_file_by_id(client, monkeypatch): ...

def test_open_reports_the_right_file_manager_name_per_platform(client, monkeypatch):
    assert client.get("/api/state").json()["file_manager"] == "File Explorer"

# Review Focus 5 — path traversal
def test_open_refuses_a_folder_outside_the_sorted_destination(client):
    r = client.post("/api/open", json={"folder": "../../../Windows/System32"})
    assert r.status_code == 400

def test_peek_refuses_a_path_that_is_not_a_folder(client): ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_folders_routes.py -v`
Expected: FAIL with 404 on `/api/peek`

- [ ] **Step 3: Implement `routes_folders.py`**

`/api/open` resolves the requested folder against the stored sorted destination and rejects anything that is not `Path.is_relative_to` it — Review Focus 5. `/api/pick` runs the picker in a thread pool so the event loop is never blocked, and returns `{"path": None, "reason": "<plain words>"}` rather than a bare `None` when tkinter is unavailable. `file_manager` is added to `AppState` here; update `schemas.AppState` and Task 1's test accordingly.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/ -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add photosorter/api/routes_folders.py photosorter/api/schemas.py tests/api/
git commit -m "feat: peek, categories, move, open and pick endpoints"
```

---

### Task 5: Serving originals

**Files:**
- Create: `photosorter/api/routes_files.py`
- Test: `tests/api/test_files_routes.py`

**Interfaces:**
- Produces:
  - `GET /api/file/{id}` — the original, with range support and on-the-fly conversion.
  - `GET /api/record/{id}` — the full `FileRecord` for one file, the §13.2 on-demand detail fetch.

- [ ] **Step 1: Write the failing test**

```python
def test_missing_id_returns_404(client): ...
def test_file_deleted_since_the_scan_returns_404_not_500(client): ...

def test_jpeg_is_served_untouched_with_accept_ranges(client):
    r = client.get("/api/file/0")
    assert r.headers["accept-ranges"] == "bytes"
    assert r.content == original_bytes

# Review Focus 4 — ranges
def test_range_request_returns_206_with_content_range(client):
    r = client.get("/api/file/0", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 10-19/{size}"
    assert len(r.content) == 10

def test_open_ended_range_runs_to_the_last_byte(client):
    r = client.get("/api/file/0", headers={"Range": "bytes=10-"})
    assert r.status_code == 206 and len(r.content) == size - 10

def test_range_past_the_end_is_clamped(client): ...
def test_client_disconnect_mid_stream_does_not_raise(client): ...

def test_heic_is_converted_to_jpeg(client):
    assert client.get("/api/file/1").headers["content-type"] == "image/jpeg"

def test_mov_is_served_as_video_mp4(client):
    assert client.get("/api/file/2").headers["content-type"] == "video/mp4"

def test_record_endpoint_returns_the_full_record(client):
    assert set(client.get("/api/record/0").json()) >= {"id", "name", "sha256", "path"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_files_routes.py -v`
Expected: FAIL with 404 on `/api/file/0`

- [ ] **Step 3: Implement `routes_files.py`**

`.heic`, `.heif`, `.tif`, `.tiff` and `.bmp` are decoded, EXIF-transposed, thumbnailed to 2400px and returned as JPEG at quality 88. `.mov` is relabelled `video/mp4`. Everything else streams from disk in 1 MiB chunks, honouring `Range`, with `BrokenPipeError` and `ConnectionResetError` swallowed. The inventory is indexed by id once and cached, not re-read per request — at 100k records a linear scan per request is a real cost.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/test_files_routes.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add photosorter/api/routes_files.py tests/api/test_files_routes.py
git commit -m "feat: serve originals with range support and format conversion"
```

---

### Task 6: Server entrypoint and static hosting

**Files:**
- Modify: `photosorter/__main__.py`
- Create: `photosorter/api/static.py`
- Test: `tests/api/test_serve.py`

**Interfaces:**
- Produces:
  - `photo-sorter serve [--port 8765] [--dev] [--no-browser]`
  - `mount_frontend(app, paths)` — serves `web/dist/` at `/`, `data/` at `/data`, `demo/` at `/demo`, `peek/` at `/peek`, all with `Cache-Control: no-store` on JSON and HTML.

- [ ] **Step 1: Write the failing test**

```python
def test_server_binds_loopback_only():
    assert uvicorn_config(port=8765).host == "127.0.0.1"

def test_json_data_is_served_with_no_store(client):
    assert client.get("/data/labels.json").headers["cache-control"] == "no-store"

def test_missing_frontend_build_serves_a_plain_words_message(client, tmp_path):
    r = client.get("/")
    assert r.status_code == 200 and "npm run build" in r.text

def test_port_in_use_reports_the_port_and_suggests_another(capsys): ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_serve.py -v`
Expected: FAIL — no `serve` subcommand

- [ ] **Step 3: Implement `static.py` and the `serve` subcommand**

`--dev` skips the `web/dist/` mount, on the assumption the Vite dev server is proxying. Without `--no-browser`, open the dashboard after a one-second delay. An `OSError` on bind prints the port and suggests `--port 8766` in plain words.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ -v`
Expected: all pass

- [ ] **Step 5: Verify by hand**

Run: `photo-sorter serve --port 8766 --no-browser`, then `curl http://127.0.0.1:8766/api/state` and `curl http://127.0.0.1:8766/openapi.json`
Expected: both return JSON; the reference on 8765 is unaffected.

- [ ] **Step 6: Commit**

```bash
git add photosorter/api/static.py photosorter/__main__.py tests/api/test_serve.py
git commit -m "feat: loopback server entrypoint with static hosting"
```

---

## Done when

`photo-sorter serve` runs a complete sort end-to-end over HTTP with live SSE progress, `openapi.json` describes every endpoint, all tests pass, and the server refuses to bind anything but `127.0.0.1`.

# Photo Sorter — modernized cross-platform replica

**Date:** 2026-11-21
**Target repo:** `D:\CODING\REA-Photo Sorter\Photo-Sorter` (currently empty)
**Reference system:** `D:\CODING\REA-Photo Sorter\claude-photo-sorter` (kairothq/claude-photo-sorter, MIT), running at http://127.0.0.1:8765/

---

## 1. Intent and why

Rebuild `claude-photo-sorter` as a modernized, genuinely cross-platform application: same product, same visual design, same behaviour, on a current stack with real tests and no platform-specific dead ends.

The original is an excellent product trapped on one platform. It is Mac-first in eight concrete places (native folder picker, APFS clone copies, `open -R`, POSIX path assumptions, implicit text encoding). Off macOS it degrades silently rather than failing: the folder picker returns `None` and the UI quietly falls back to typing a raw path. It also has **zero automated tests** — including for the duplicate-grouping union-find and the label→folder fallback, the two places where a silent bug misfiles a person's photos.

The owner is on Windows, wants the app to run on Windows, Linux and macOS together, and asked for a modernized rebuild following best practices.

## 2. Goals

1. **Behavioural parity.** Every feature of the reference works in the replica: the four-phase pipeline, live animated progress, duplicate review, folder editing, folder browsing, the full-size lightbox with hand re-filing, demo mode, replay mode, URL parameters, theme toggle.
2. **Visual parity.** The dashboard looks like the original. Verified by diffing against the running reference, not by assertion.
3. **Three platforms, together.** Windows, Linux and macOS each get a correct implementation at every platform seam — not a macOS path plus fallbacks.
4. **Modern stack.** FastAPI backend, React + TypeScript frontend, typed API contracts, Server-Sent Events instead of polling.
5. **Tested where it matters.** The pure logic (duplicate grouping, sidecar parsing, label merge precedence, filename collisions, path handling) has real tests.
6. **Privacy preserved.** Loopback-only binding, originals never modified, nothing uploaded except the optional Jev path.

## 3. Non-goals

- No cloud, no multi-user, no auth, no hosted deployment. It stays a local single-user app on 127.0.0.1.
- No new product features. Parity first; anything new is a separate request.
- No mobile or responsive-phone layout beyond what the original has.
- No replacement for the `claude -p` labelling approach with a direct API-key integration. Using the person's existing Claude plan with no API key is a core product property.
- No database. JSON files on disk, as in the original.

## 4. Anti-goals — things that would make this a failure even if it ran

- **A replica that only really works on Windows** with untested mac/Linux branches. That is the original's failure mode with the platforms swapped.
- **A UI that is recognisably not the original** — React-default styling, different motion, different spacing. The hand-written sphere and fly animations are the product's signature; losing their feel loses the thing being replicated.
- **A React rewrite that renders 320 animated tiles through the component tree** and drops frames. The original holds 60fps imperatively; the replica must too.
- **Touching the user's originals.** Any code path that moves, renames or deletes a source file is a critical defect.
- **Ceremony without substance:** layers of abstraction, dependency injection, or microservice-shaped structure in a local single-user app. Modern means typed, tested and cross-platform — not enterprise.

## 5. Constraints

- **Python 3.11+** and **Node 20+** for development. End users must need Python only — so the built frontend is committed.
- Three Python imaging dependencies carry over as-is: `pillow`, `pillow-heif`, `imagehash`. They are correct and cross-platform.
- `ffmpeg`/`ffprobe` stay optional. Without them, videos get grey placeholder previews, as in the original.
- Claude Code CLI (`claude`) must be on `PATH` for the default labeller. On Windows it resolves as `claude.cmd`.
- `tkinter` ships with python.org CPython on Windows and macOS, but on Debian/Ubuntu it needs `python3-tk`. The app must detect this and degrade to path entry with a clear message, never a silent `None`.
- The reference is MIT-licensed. Its licence and attribution must be preserved.
- This is a replica of a working system, so the reference is the specification. Where this document and the reference disagree, the reference wins — except at the eight platform seams, where this document wins.

## 6. Approaches considered

| | Approach | Trades off |
|---|---|---|
| **A** | **Faithful rebuild** — same stdlib `ThreadingHTTPServer`, same vanilla JS, no build step, fix only the platform seams. | Cheapest and lowest-risk; visual parity nearly free. But keeps stdout-scraping `PROGRESS` lines for progress, 900ms polling, and an untyped 733-line JS file. Not modernized. |
| **B** | **Modernized rebuild** — FastAPI + SSE backend, React + TypeScript + Vite frontend, pytest + Vitest, pure-function core package. | **Chosen.** Typed contracts, event-driven progress, real tests, proper CLI. Costs the most work, adds a build step and ~25 dependencies, and makes visual parity something to verify rather than inherit. |
| **C** | **Copy and patch** — copy the repo, fix the Mac-isms found so far. | Fastest to something running. But a copy is not a replica, and it silently inherits every untested platform assumption; you would never learn which parts work on Windows and which simply were never hit. |

**Decision: B**, chosen by the owner after A was recommended and the parity risk was stated. The concern was raised once and overruled; B is the decision.

The parity risk is mitigated, not ignored: `tokens.css` is ported **verbatim** (it is a pure design-token file with no structural coupling), `app.css` and `components.css` are ported value-for-value into CSS Modules, and the animation code stays imperative behind refs rather than being re-expressed as React state.

**REA was not used.** It is for reverse-engineering binaries and opaque bundles; the reference is complete, commented source, and REA's own guidance says to skip it for source-repository analysis. The live app will be driven in Chrome at the end, for visual diffing.

## 7. The reference system, as it actually works

This section is the specification. It was derived by reading all ~1,900 lines of the reference.

### 7.1 Four-phase pipeline

| Phase | Reference script | What it does |
|---|---|---|
| **scan** | `scan.py` | Walks the source folder for known image/video extensions, skipping `._*` AppleDouble files. 8-thread pool. Per file records: `id` (index), `path`, `name`, `ext`, `kind` (photo/video), `bytes`, `sha256`, `w`, `h`, `phash`, plus `duration` for video. Writes a 256×256 centre-cropped preview to `thumbs/<id>.jpg` (quality 80) and a 72×72 copy to `mini/<id>.jpg` (quality 72). Videos: `ffprobe` for dimensions/rotation/duration, `ffmpeg` grabs a frame at 1s (or 0s if under 2s). Unreadable files stay in the inventory with an `error` field and a beige placeholder. Google Takeout `.json` sidecars are matched (including the `IMG_1(1).JPG` → `IMG_1.JPG...(1).json` case) for `taken` timestamp and `geo`. `--limit N` takes a random sample with **seed 0**. Outputs `inventory.json`, `source.json`. |
| **dupes** | `dupes.py` | Union-find over all files. Exact duplicates by identical `sha256`. Near-duplicates by perceptual-hash Hamming distance ≤ 4, **same kind only**. Guard: two different PNGs that are not byte-identical are only grouped if their 256px greyscale previews differ by ≤ 0.4% of pixels (per-pixel delta > 40 counts as changed) — this stops different screens of the same dark-UI app being called copies. Keeper per group: largest `bytes`, then shortest name. Writes `dupes.json` as `{keep, dupes[], type: exact\|near, freed}` and a visual contact sheet of the first 60 groups to `work/duplicates.jpg`. |
| **label** | `label_claude.py` (default) or `label_jev.py` | See 7.2. |
| **apply** | `apply.py` | Merges labels, **copies** (never moves) each file into `<dest>/<Folder Label>/`, duplicates into `<dest>/_Review/duplicates/`. Writes `sorted.csv` (file, folder, original_path) and `duplicates.csv` (duplicate, kept_copy, type, duplicate_path, kept_path). See 7.3. |

Progress in the reference is scraped from subprocess stdout via `PROGRESS <done> <total>` lines. **The replica replaces this with structured events** (§8.2).

### 7.2 Labelling

**Claude path (default, no API key).** `sheets.py` renders contact sheets: 30 previews per sheet in a 6×5 grid of 230px cells, each tile tagged with its id in yellow on black, suffixed `VIDEO <n>s` for video and `PNG` for PNGs. Sheets are grouped **3 per batch** (~90 files), **4 batches concurrently**, model `sonnet` (both overridable by `CLAUDE_WORKERS` / `CLAUDE_MODEL`). Each batch invokes:

```
claude -p <prompt> --model sonnet --allowedTools Read --strict-mcp-config
       --setting-sources project --no-session-persistence --output-format json
```

with `cwd` = the work directory and a 900s timeout. The prompt lists every folder as `key (kind): rule`, tells Claude to Read the named sheet images, and demands a bare JSON object mapping id → folder key. The response is parsed by finding the first `{...}` block; ids outside the batch are discarded. **A batch is accepted when ≥ 90% of its expected ids came back**, otherwise it retries up to 4 times with `8 × attempt` second backoff, saving the raw failed response for debugging. Finished batches are cached to `work/labels/claude_NN.json` and skipped on re-run — this is what makes the whole thing resumable.

**Jev path (optional, paid).** TypeSafe's Jev model via `POST https://api.typesafe.ai/v1/systemone`, one 280px JPEG per file, 6 concurrent, 5 retries with exponential backoff, 980 tokens estimated per file. Requires `JEV_KEY`/`TYPESAFE_API_KEY` from env or `.env`. Must show an estimate and get explicit confirmation before spending. 401/403 aborts immediately. Resumable via `work/jev.json`.

**Orchestration tolerance.** The `label` phase is allowed to fail partially: if ≥ 95% of files got labels, the sort continues and the rest fall through to catch-all folders. Changing `categories.json` invalidates cached labels, detected by a SHA-1 fingerprint stored at `work/labels/.categories`.

### 7.3 Label merge precedence (apply)

In order, each step overriding the last:

1. Claude labels, all `work/labels/*.json` merged in sorted filename order.
2. Jev's answer wins **if its confidence ≥ 0.7**, or if Claude has no answer for that id.
3. **Kind guard:** if the chosen folder does not exist, or its `kind` does not match the file's kind, the file goes to the **last folder of its own kind** — which is why the catch-all must be last. Counted and reported.
4. Hand moves from `work/overrides.json` (made in the dashboard) win over everything.

Folder directory name = category `label` with `&` → `and` and `/` → `-`. Filename collisions become `<base>__<id><ext>`. Re-running reads the previous `sorted.csv`, deletes exactly the files it made last time, prunes empty directories, and rebuilds — so it is idempotent without touching anything it did not create. On macOS, same-disk copies use `cp -c` (APFS clone: instant, no extra space), falling back to `shutil.copy2`.

### 7.4 HTTP API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/state` | Everything the UI needs: categories, source/limit/sorted, file count and total bytes, per-step completion flags, `jev_key` and `claude_cli` availability, override count, the live `job` object, platform. |
| GET | `/api/labels` | Labels written *so far*, for the live animation (Claude batches + Jev answers ≥ 0.7 confidence). |
| GET | `/api/file/{id}` | The original file. HTTP Range supported for video seeking. HEIC/HEIF/TIFF/BMP are converted to JPEG on the fly (max 2400px) because browsers cannot display them. `.mov` is served as `video/mp4`. |
| POST | `/api/sort` | Start the whole pipeline. Validates source exists, labeller is available; decides whether a re-scan is needed by comparing source path and limit. |
| POST | `/api/run` | Run one phase alone (`scan`, `dupes`, `claude`, `jev`, `estimate`, `apply`). |
| POST | `/api/peek` | Right after a folder is picked: count photos/videos/bytes (skipping dotfolders and `* (sorted)`), generate up to 60 random 64px previews (seed 3), suggest `<source> (sorted)` as the destination. |
| POST | `/api/categories` | Save the folder list. Rejects duplicate keys, missing labels, or losing the last photo or video folder. |
| POST | `/api/move` | Record a hand re-file into `overrides.json` *and* `labels.json`. |
| POST | `/api/open` | Reveal a file, or open a sorted folder, in the OS file manager. |
| POST | `/api/pick` | Native folder picker. |

Mutating requests are guarded by an `Origin` check against `127.0.0.1:<port>` / `localhost:<port>`. The server binds `127.0.0.1` only.

### 7.5 Dashboard behaviour

Three modes: **setup** → **running** → **done**.

- **Setup** is a numbered card: 1. choose photos (native picker, or type a path, or "Last time: …"), 2. choose destination (default `<source> (sorted)`), 3. Start sorting, with a time estimate. **Advanced** reveals: folder chips with remove and `+` add, the Claude/Jev choice with a token estimate and a PAID badge, and a "Try 200 random files first" checkbox.
- **Centre stage** is a rotating Fibonacci sphere of up to 320 thumbnail tiles (golden-angle distribution, rotation `0.00035`/ms, tilt `sin(t/4000) × 0.35`, depth-based scale/opacity/z-index). Before a source is chosen it shows the peek previews; after the scan it is rebuilt from the real library.
- **Running** polls `/api/state` every 900ms, shows a phase checklist, an elapsed/remaining timer, and a progress bar. As labels arrive, each thumbnail **flies** from its sphere position into its folder card — Web Animations API, 650–1050ms, `cubic-bezier(.55,0,.25,1)`, randomised mid-point arc and rotation. Arrivals are spread across frames (`ceil(queue/45)` per frame) so batch delivery still looks continuous.
- **Folder cards** hold 12 preview slots (the duplicates card is double-width with 24), with a count badge that pops and a card flash on each arrival.
- **Done** shows a count-up, 200-particle confetti burst in theme colours, duplicate and space-freed chips. Clicking a folder opens a browsing grid (120 at a time); clicking a photo opens a lightbox with arrow-key navigation, a **Move to** dropdown, and "Show original".
- **Edit folders** is a dialog: emoji, name, the plain-language `rule` the model reads, photo/video toggle, delete.
- **Time estimates**, calibrated on a 2020 MacBook with 1,136 files / 10.7 GB:
  `scan = 4 + files×0.025 + GB×9` · `dupes = 2 + (files/1000)²×4` · `label = 12 + files×0.012 + ceil(batches/4)×14` · `apply = 2 + files×0.018`
- **URL parameters:** `?demo` (fake camera roll), `?d=<seconds>` (replay length, default 12), `?auto` (replay on load), `?source=&dest=` (prefill both). Space replays. Theme toggle persists to `localStorage`.
- **Demo mode** (`demo.py`) draws ~1,000 procedural placeholder thumbnails — per-category shape generators for screenshots, documents, memes, landscapes, city nights, food, pets, people — plus a fake inventory, labels and 38 fake duplicate groups. No real photos.

### 7.6 What the live app actually shows on Windows

The reference was opened at http://127.0.0.1:8765/ on this Windows machine, mid-design, in the state left by a real 208-file sort of a local wedding-photo folder. Observed, not inferred:

- **The setup card has no "Choose folder" button at all.** Because `S.platform !== "darwin"`, the UI falls straight through to a bare text input — whose placeholder is `/Users/you/Pictures/Camera roll`, a macOS path, shown to a Windows user. This is the single worst UX defect in the reference and it is invisible from the source until you see it rendered. The replica's picker (§8.4) removes it.
- **"Open in Finder"** is the literal button label in the folder dialog on Windows. The replica says "Show in File Explorer" / "Show in Finder" / "Show in file manager" per platform.
- Folder card titles truncate with an ellipsis at this width ("Documents & rece…", "Memes & saved p…", "Screen recordi…"). Faithful behaviour, must be carried over, with the full label as a `title` tooltip.
- The real sort put 174 of 183 photos into one folder (People & family) — correct for a wedding album, and a useful reminder that the dashboard must look right when one card holds nearly everything and nine cards are empty.
- Empty folder cards render their full 12-slot grid; the duplicates card is double-width with 24 slots. Both confirmed visually in light and dark themes.
- Light/dark toggle, folder browsing grid, count badges and the "N sorted" done panel all behave as §7.5 describes.

Screenshots of the done view, the browse dialog and the Windows setup card were captured for side-by-side diffing in phase 8.

### 7.7 Verified toolchain on this machine

Node v26.13.1, npm 12.2.1, Python 3.11.0, `claude` on PATH, `ffmpeg` installed, git 2.55. Nothing in §8 needs installing first. Note that `claude` resolves via a shim in `~/.local/bin`, which is why the `shutil.which` widening in §8.4 is load-bearing rather than theoretical.

## 8. The replica's architecture

### 8.1 Layout

```
Photo-Sorter/
  pyproject.toml              # deps, console script, pytest + ruff config
  README.md  LICENSE  CLAUDE.md  AGENTS.md
  categories.json             # same 14 default folders, unchanged
  photosorter/
    __init__.py
    __main__.py               # python -m photosorter  (serve | scan | dupes | label | apply | demo)
    config.py                 # paths, port, env; one Settings object
    platform.py               # THE platform seam layer (§8.4)
    models.py                 # pydantic: FileRecord, DupeGroup, Category, JobState, AppState
    core/                     # pure, importable, tested — no HTTP, no printing
      scan.py  dupes.py  sheets.py  apply.py  categories.py
      labelers/__init__.py  claude.py  jev.py       # a Labeler protocol
    jobs.py                   # job runner: phases, cancellation, progress events
    api/
      app.py                  # FastAPI app, StaticFiles mount, origin guard
      routes_state.py  routes_jobs.py  routes_files.py  routes_folders.py
    picker.py                 # folder picker, run as a child process (§8.4)
  web/
    package.json  vite.config.ts  tsconfig.json  index.html
    src/
      main.tsx  App.tsx
      api/client.ts  api/types.ts        # generated from the OpenAPI schema
      hooks/useAppState.ts  useJobEvents.ts
      components/  Topbar  KpiRow  FolderCard  Stage  SetupCard  RunCard
                   FoldersDialog  BrowseDialog  Lightbox  Toast
      anim/sphere.ts  fly.ts  confetti.ts   # imperative, outside React
      styles/tokens.css                     # ported verbatim
      styles/*.module.css                   # app.css + components.css, value-for-value
    dist/                     # committed, so end users need only Python
  tests/                      # pytest
  web/src/**/*.test.ts        # vitest
  data/   work/               # runtime, gitignored
```

Two deliberate departures from the reference's layout: runtime output moves from `dashboard/data/` to a top-level `data/` (the frontend is a build artefact now, so data has no business living inside it), and the four scripts become a tested `core/` package with thin CLI wrappers.

### 8.2 Progress: events, not stdout scraping

The reference runs each phase as a subprocess and regex-matches `PROGRESS n total` from its stdout. The replica calls `core` functions directly in a worker thread; each accepts an optional `on_progress(done, total)` callback. `jobs.py` turns those into typed events on an `asyncio.Queue`, served as Server-Sent Events at `GET /api/events`. The frontend subscribes once instead of polling 67 times a minute.

`GET /api/state` remains, unchanged in shape, for the initial load and as a reconnect fallback — an SSE stream that drops must not strand the UI, and a reload mid-sort must still reattach to a running job exactly as the reference does.

Cancellation is added, because it is near-free once jobs are in-process and the reference's only way to stop a long sort is killing the server: a cooperative `threading.Event` checked between files. Phase-level resumability (cached label batches, scan skipped when source and limit are unchanged) is preserved exactly.

### 8.3 Frontend

React 18 + TypeScript + Vite. One `useReducer` store plus two hooks (`useAppState`, `useJobEvents`); no state-management library for a single-page local app. API types are generated from FastAPI's OpenAPI schema, so a backend contract change breaks the build instead of the UI.

**The animation stays out of React.** `sphere.ts`, `fly.ts` and `confetti.ts` own their DOM nodes behind a ref, driven by one `requestAnimationFrame` loop, exactly as the reference does. React renders the chrome — cards, panels, dialogs, KPIs — and never the 320 tiles. This is the single most important implementation constraint in the frontend; routing 320 transforms per frame through the component tree will drop frames and the replica will feel wrong.

`prefers-reduced-motion` is honoured (the reference already skips confetti; the replica also skips the fly arcs and lands tiles directly), and the dialogs get real focus traps and `aria` wiring — accessibility is in the "never cut" column.

### 8.4 Platform seams — all three, properly

Everything OS-specific lives in `photosorter/platform.py`. Nothing else in the codebase branches on `sys.platform`.

| Seam | Windows | macOS | Linux |
|---|---|---|---|
| **Folder picker** | `tkinter.filedialog.askdirectory` in a **child process** | same | same, plus a `python3-tk` detection message |
| **Copy** | `shutil.copy2` | `cp -c -p` APFS clone, falling back to `copy2` | `cp --reflink=auto`, falling back to `copy2` |
| **Reveal file** | `explorer /select,<backslash path>` | `open -R <path>` | `xdg-open <parent dir>` |
| **Open folder** | `os.startfile` | `open` | `xdg-open` |
| **Text I/O** | explicit `encoding="utf-8"` everywhere | same | same |
| **Paths** | `pathlib.Path` throughout | same | same |
| **`claude` lookup** | `shutil.which` over `claude`, `claude.cmd`, `claude.exe`, `claude.ps1` | `claude` | `claude` |
| **Browser launch** | `webbrowser.open` | same | same |

Four of these are bugs in the reference, not merely missing ports:

1. **Encoding.** `common.py` opens files with no `encoding=`, so on Windows it uses cp1252 and the emoji in `categories.json` crash it. This is precisely why the reference needs `$env:PYTHONUTF8='1'` to run here. The replica sets `encoding="utf-8"` explicitly and **drops the need for that environment variable**.
2. **Path separators.** `source.rstrip("/")` and `abspath(dest).startswith(abspath(src) + os.sep)` mishandle `D:\...\photos\`. `pathlib` with `Path.is_relative_to` fixes it.
3. **Folder picker.** Returning `None` off macOS and letting the UI fall back silently is the worst of both. `tkinter` covers all three; where it is genuinely unavailable (a Linux box without `python3-tk`), the UI says so explicitly and offers path entry.
4. **Picker process isolation.** `tkinter` must own the main thread on macOS, which cannot be reconciled with uvicorn's event loop in-process. Running the dialog as a short-lived child process that prints the chosen path solves this on all three platforms at once, and a crashed dialog cannot take the server down.

### 8.5 Testing

`pytest` for the backend. The tests that matter are the pure-logic ones the reference has none of:

- **Union-find duplicate grouping** — exact, near, mixed chains, the keeper-selection tie-break, and the PNG pixel guard both triggering and not.
- **Google Takeout sidecar matching** — plain names, `supplemental-metadata` truncation, and the `IMG_1(1).JPG` numbered-copy case.
- **Label merge precedence** — Claude only, Jev winning at ≥ 0.7, Jev losing below it, kind-mismatch falling to the last folder of that kind, overrides winning over everything.
- **`apply` filename collisions and idempotent rebuild** — the second run must leave exactly the same tree and must not delete anything it did not create. This test is the guard on the "never touch originals" rule.
- **Path handling** on Windows-style paths, including the "destination inside source" rejection.
- **API contract** via `httpx`, including the `Origin` guard rejecting a foreign origin and Range requests on `/api/file/{id}`.

`vitest` for the frontend: the time-estimate formulas, the label-to-folder targeting, the queue-spreading maths, and the reducer transitions. The animation itself is verified by eye against the reference, not unit-tested.

A smoke test runs the full pipeline over the procedural demo library with a **stubbed labeller**, so CI never needs the `claude` CLI or a paid API key.

## 9. Roadmap

Nine phases. Each ends with something runnable and verified; nothing depends on a later phase.

| # | Phase | Delivers | Done when |
|---|---|---|---|
| 1 | **Scaffold** | `pyproject.toml`, package skeleton, `config.py`, `models.py`, `platform.py`, Vite + React + TS app, ruff, pytest, vitest, CI | `pytest` and `vitest` run green and empty; `python -m photosorter --help` works |
| 2 | **Platform layer** | `platform.py` + `picker.py` complete, with tests | Picker opens, copy/reveal/open work, verified on Windows; mac/Linux branches reviewed and unit-tested with fakes |
| 3 | **Core: scan + dupes** | `core/scan.py`, `core/dupes.py`, CLI wrappers | Scanning the demo folder produces an identical `inventory.json` shape; dupe tests pass including the PNG guard |
| 4 | **Core: sheets + labellers + apply** | `core/sheets.py`, `labelers/`, `core/apply.py` | Label-merge and collision/idempotency tests pass; a real `claude -p` batch returns usable labels |
| 5 | **API + jobs** | FastAPI app, all routes, `jobs.py`, SSE events, origin guard | Full pipeline runs end-to-end over the demo library via HTTP with live events; API tests pass |
| 6 | **Frontend shell** | Topbar, KPI row, folder cards, setup card, dialogs, theme, ported CSS tokens | Setup flow works against the real API; looks like the reference in both themes |
| 7 | **Animation** | `sphere.ts`, `fly.ts`, `confetti.ts`, run card, timer, replay | 60fps with 320 tiles; replay and `?d=` match the reference's feel |
| 8 | **Demo + parity sweep** | `demo.py` port, `?demo`/`?auto`/`?source=`/`?dest=`, README, `CLAUDE.md` | Every row of §7.5 checked against the reference side by side in Chrome |
| 9 | **Cross-platform verification** | Platform notes, install docs, launchers for all three | Windows verified fully; Linux verified if a box is available; macOS branches reviewed line-by-line and flagged honestly as unverified |

Phases 3, 4 and 6 contain independent units and are the natural candidates for parallel subagents. Phases 2, 5, 7 and 9 are sequential — they are where the integration risk lives.

## 10. What is left to the builder

- Component decomposition inside `web/src/components/`, and whether CSS Modules or a single global stylesheet per component reads better once the tokens are in.
- Exact SSE event schema (a typed discriminated union is expected; the field names are the builder's).
- Whether `core/` phase functions take a progress callback or return a generator — both satisfy §8.2.
- Thread-pool sizes beyond the reference's defaults (8 scan / 4 label / 6 Jev), which are kept unless measurement says otherwise.
- Error-message wording, subject to the reference's house style: plain words, "folder" not "directory", one question at a time.
- Whether `categories.json` lives at the repo root (as in the reference) or under `data/`. Root is expected, for continuity.

## 11. Calls I made, not decisions the owner gave me

Listed so they can be checked rather than discovered:

1. **FastAPI + uvicorn, React + TypeScript + Vite, pytest + vitest, ruff.** "Modernized, best practices" was the instruction; these are the picks.
2. **SSE instead of polling**, with `/api/state` retained as the reconnect fallback.
3. **`data/` and `work/` move to the repo root**, out of the frontend directory.
4. **The built frontend (`web/dist/`) is committed**, so end users need Python only and not Node.
5. **The folder picker runs as a child process**, to resolve tkinter's main-thread requirement on macOS.
6. **Job cancellation is added** — the one capability beyond parity, because it is nearly free in-process and the reference's only way to stop a sort is killing the server.
7. **The Jev labeller is kept**, behind the same estimate-and-confirm gate. Dropping it would lose documented behaviour.
8. **Windows is the verified platform**; macOS and Linux branches are written correctly and their verification status is reported honestly rather than claimed.
9. **Default port stays 8765, with a `--port` flag.** The parity sweep in phase 8 runs the replica on 8766 so it can sit beside the reference on 8765 for side-by-side diffing.
10. **Dev runs the Vite dev server with `/api` and `/events` proxied to uvicorn**; production serves `web/dist/` from FastAPI's `StaticFiles`. One command (`python -m photosorter serve --dev`) starts both.
11. **Single-client assumption is kept.** SSE broadcasts to every connected tab, but the job model stays single-job, as in the reference. Two browser tabs will not corrupt anything; they just both watch.
12. **No migration from the reference's `dashboard/data/`.** The replica starts clean; the reference is left untouched and keeps working.
13. **MIT licence and upstream attribution are carried over** regardless of whether this is ever published.

## 12. Answered: scale and platform

**Scale: no upper limit.** The library size is unbounded; the user supplies the source folder path and the destination path. This is a hard requirement, and it rules out four things the reference does. See §13.

**Platform: Windows now, macOS later.** The owner has a Mac and will test there afterwards. Both platforms are first-class in the code; Windows is the only one verified in this build. Linux is written to the same standard and labelled unverified. Nothing may be macOS-only or Windows-only at any seam.

## 13. Designing for an unbounded library

The reference quietly assumes a few thousand files. At 100,000 it fails in four distinct ways. Each needs a different answer.

### 13.1 Duplicate detection must not be O(n²)

`dupes.py` compares every file against every other: `2 + (files/1000)² × 4` seconds — 6s at 1k, 7 minutes at 10k, **2½ hours at 50k, 11 hours at 100k**. Unusable.

**Replacement: multi-index hashing (pigeonhole banding).** Exact duplicates come from a `sha256 → [ids]` dict in one pass, O(n). For near-duplicates, split each 64-bit pHash into **5 bands** (13/13/13/13/12 bits). Two hashes within Hamming distance 4 must agree exactly on at least one band — with 5 bands and at most 4 differing bits, the pigeonhole principle guarantees one clean band. So: index `(band_index, band_value) → [ids]`, and compare only within buckets. Verify every candidate pair with the true Hamming distance, preserving the existing rules exactly (same `kind` only, distance ≤ 4, and the PNG pixel guard).

This is exact, not approximate: it finds every pair the reference's nested loop would find, and no others. Expected behaviour is identical; only the cost changes, from O(n²) to roughly O(n) with small buckets.

**Required guard:** a degenerate bucket. Thousands of near-blank or uniformly dark frames share band values and collapse into one huge bucket, restoring quadratic cost locally. Buckets above a cap (10,000 members) are processed but reported, and the pixel-guard comparison inside them is capped. This must be tested with a synthetic all-identical-hash library.

### 13.2 The frontend cannot receive the full inventory

`app.js` fetches the entire `inventory.json`. At 100k files that is ~40 MB of JSON holding absolute paths, hashes and dimensions the dashboard never uses.

**Replacement:** the server writes a **slim index** alongside the full inventory — `id`, `kind`, `bytes`, and nothing else (~25 bytes/record, ~3 MB at 100k) — and the frontend loads only that, plus `labels.json` and `dupes.json`. Full records are fetched per file, on demand, when the lightbox opens. The sphere is already capped at 320 tiles and the browse grid already pages at 120, so nothing else in the UI needs the full set.

### 13.3 Progress events must be throttled

One SSE event per file is 100,000 messages. Progress is emitted **at most 10 times per second and at most once per 0.5% of total**, whichever is less frequent, with a guaranteed final event per phase. The reference's `n % 20` style of reporting is replaced by this time-based throttle.

### 13.4 Disk, memory and labelling cost must be stated up front

- **Thumbnails:** ~18 KB per file (256px preview + 72px mini). At 100k that is **~1.8 GB** in `data/`. The peek step already counts the library, so the setup card must show the estimated preview size and required free space, and the scan must fail cleanly with a clear message if the disk cannot hold it.
- **Memory:** the inventory is built in a list. At 100k records that is roughly 40–60 MB — acceptable, so scanning stays in memory, but `dupes` must stream from the slim fields rather than holding thumbnails open.
- **Labelling time and cost:** 100k files is ~3,334 contact sheets, ~1,112 Claude batches. At 4 concurrent that is **well over an hour** of `claude -p` calls against the user's plan. The setup card must show this estimate before starting, the existing per-batch caching makes it resumable across days, and job cancellation (§8.2) stops it cleanly.

### 13.5 What stays unchanged

Scanning is already an 8-thread streaming walk, `apply` already copies file-by-file, and label batches are already cached and resumable. Those three scale as they are.

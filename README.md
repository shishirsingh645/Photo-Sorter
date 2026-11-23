# Photo Sorter

Point it at a camera roll. It looks at every photo and video, sorts them into folders, finds the duplicates, and you watch it happen on a live dashboard on your own computer.

A modernized, cross-platform replica of [claude-photo-sorter](https://github.com/kairothq/claude-photo-sorter): the same dashboard, the same animation, and a Python server that works on Windows as well as macOS.

- **Sorts photos and videos** into folders like Selfies, Food, Travel, Screenshots and Talking heads. Use the standard folders or make your own.
- **Finds duplicates**: identical copies, burst shots and re-saved screenshots go to a review folder, with a list of which copy was kept.
- **Never touches your originals.** It only reads them and makes sorted copies.
- **Runs on your computer.** Your photos are not uploaded anywhere. The dashboard listens on `127.0.0.1` only.

## Status

The command-line engine, the server and the dashboard are all written. **Nothing has been verified on real hardware yet**, Windows included: every platform behaviour is written but not run. The automated test suites do pass (391 Python and 219 dashboard tests), but they use fakes for the operating system, so they say nothing about the folder picker or the file manager. [`docs/platform-support.md`](docs/platform-support.md) lists each platform-specific behaviour (folder picker, copy, show in Explorer, and so on) with what to check and what the result should be. [`BUILD-TEST-LEDGER.md`](BUILD-TEST-LEDGER.md) records what has and has not been run.

## Install and run

You need **Python 3.11 or newer**. To label with Claude you also need [Claude Code](https://claude.com/claude-code) installed and signed in (the labeller runs `claude -p` and uses your own Claude plan; no API key). **ffmpeg** is optional: without it, videos get plain grey previews.

You do **not** need Node. The built dashboard is committed in `web/dist/`.

### Windows (the platform this build targets)

In PowerShell, from the folder you cloned:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
photo-sorter serve
```

Your browser opens at <http://127.0.0.1:8765/>. If PowerShell refuses to run `Activate.ps1`, run `Set-ExecutionPolicy -Scope Process RemoteSigned` first, or use `.venv\Scripts\activate.bat` in Command Prompt. To open it again later, activate the environment and run `photo-sorter serve` again.

For ffmpeg, `winget install Gyan.FFmpeg` works. The **Choose folder** button needs Python's `tkinter`, which the python.org installer includes; if it is missing the setup card says so and lets you type a path instead.

### macOS (written, not yet verified)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
photo-sorter serve
```

`brew install ffmpeg` adds video previews. On macOS the sorted copies are clones that take no extra space.

### Linux (written, not yet verified)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
photo-sorter serve
```

On Debian and Ubuntu, `sudo apt install python3-tk` enables the **Choose folder** button, and `sudo apt install ffmpeg` adds video previews. "Show in file manager" opens the folder but cannot select the file.

### Options

`photo-sorter serve --port 8766` uses another port (the default is 8765, and it tells you if that one is busy). `--no-browser` skips opening the page. Every other step is a command too: `scan`, `dupes`, `sheets`, `label`, `apply`, `sort`, `demo`. Run `photo-sorter --help`.

## Using the dashboard

1. **Choose folder**: pick the folder with your photos (a Google Photos or Apple Photos export, or any folder). Or type a path.
2. Pick where the sorted copies go. The default is right next to your photos, in `<folder> (sorted)`.
3. **Start sorting.** It shows how long it usually takes, then sorts on its own while you watch every photo fly into its folder.

| | |
|---|---|
| **Sort with Claude** (top bar) | Before sorting: asks for anything missing, then starts. After sorting: replays the animation. |
| **New sort** | Pick a new photos folder and a new place for the copies. |
| **Advanced** (setup card) | See the folders that will be made, remove any, or press **+** to add your own. Choose Claude or Jev. Try 200 random files first. |
| **Click a folder** | Browse everything in it. Click a photo for the full size, flip with the arrow keys, and **Move to** another folder if it is wrong. |
| **Edit folders** | Rename folders and describe what goes in each. |
| **Open sorted folder** | Opens the result in File Explorer, Finder or your file manager. |
| Sun / moon | Light or dark. |
| **Space** | Replays a finished sort. |

### Claude or Jev

| | Claude (default) | Jev (Advanced, optional) |
|---|---|---|
| What | Claude Code reads contact sheets of 30 previews | [TypeSafe's](https://typesafe.ai) Jev image model, one question per file |
| Cost | Included in your Claude plan | Billed per file, about 980 tokens each. The dashboard shows an estimate and asks first |
| Setup | Nothing | Put `JEV_KEY=your-key` in a `.env` file in this folder |

### Address options

Add these to the address, for example `http://127.0.0.1:8765/?demo&auto&d=20`:

| | |
|---|---|
| `?demo` | A fake camera roll, read-only. Run `photo-sorter demo` once first to make it. Nothing can be changed in it. |
| `?d=20` | How long the replay takes, in seconds (12 by default). Slower is better for screen recording. |
| `?auto` | Replays by itself once a finished sort is showing. |
| `?source=D:\Pictures\Trip&dest=D:\Pictures\Trip (sorted)` | Fills both folders in, ready to press Start. Leave `dest` out to use `<source> (sorted)`. |

## Privacy

- The dashboard only listens on `127.0.0.1`, so nothing else on your network can reach it.
- Previews, labels and the file list stay in `data/`, `demo/`, `peek/` and `work/`, which git ignores.
- With Claude, small previews are read by Claude Code the same way as anything else you share with it. With Jev, a 280px preview of each file goes to TypeSafe's API. Originals never leave your computer.

## For developers

```text
photosorter/   the Python engine and the FastAPI server
web/           the React + TypeScript + Vite dashboard
web/dist/      the built dashboard, committed so that users need only Python
tests/         the Python tests
docs/          the design spec, the plans and platform-support.md
```

Rebuild the dashboard after changing anything under `web/src/`, and commit the result:

```bash
cd web
npm ci
npm run build        # type-checks, then writes web/dist/
```

To work on the page with hot reload, run `photo-sorter serve --dev` in one terminal and `npm run dev` in `web/` in another, then open http://localhost:5173. Vite forwards `/api`, `/data`, `/demo` and `/peek` to the server on port 8765, and `--dev` is the only mode in which the server accepts a POST from Vite's origin. `npm run gen:api` regenerates `web/src/api/types.ts` from the server's schema; never edit that file by hand. Tests: `pytest` for the engine and server, `npm test` in `web/` for the dashboard.

Contributors and coding agents: read [`CLAUDE.md`](CLAUDE.md).

## Architecture

Photo Sorter is two programs that talk over HTTP on your own machine: a Python engine with a small web server, and a React dashboard that the server also hosts.

```text
 Browser                                              Python process (127.0.0.1:8765)
 ┌────────────────────────────┐   POST /api/sort     ┌────────────────────────────────────────┐
 │ React dashboard            │ ───────────────────▶ │ FastAPI app                            │
 │  hooks: useAppState        │   GET  /api/state    │  routes_*  ─▶ JobRunner (one job)      │
 │         useJobEvents       │ ◀─────────────────── │                │                       │
 │  anim:  sphere, fly, ...   │   GET  /api/events   │                ▼ worker thread         │
 │  state: reducer, library   │ ◀── SSE progress ─── │  core: scan → dupes → label → apply    │
 └──────────────┬─────────────┘                      └───────┬───────────────────────┬────────┘
                │  GET /data/*.json, /peek, /demo           ▼                       ▼
                └─────────────────────────────────▶  data/ work/ peek/ demo/     your photos
                                                      (previews, labels)        (read only)
```

### The sorting pipeline

Every step is a plain function in `photosorter/core/`, so the command line and the server run exactly the same code. A step reads the previous step's files and writes its own.

| Step | Module | What it does | Writes |
|---|---|---|---|
| **peek** | `core/peek.py` | Counts the photos and videos in a folder, picks a few previews, suggests a destination, and checks free space. Runs before you commit to a sort. | `peek/` |
| **scan** | `core/scan.py` | Walks the folder, reads each file, makes a 256px thumbnail and a 72px mini preview, computes a SHA-256 and a 64-bit perceptual hash, and reads Google Takeout dates and GPS from sidecar files. Videos get a frame from `ffmpeg` if it is installed, otherwise a grey placeholder. | `data/inventory.json`, `data/slim.json`, `data/source.json`, `data/thumbs/`, `data/mini/` |
| **dupes** | `core/dupes.py` | Groups identical files by SHA-256, then near-identical ones (burst shots, re-saved screenshots) by perceptual hash within a Hamming distance of 4. The hash is split into 5 bands so candidates are found without comparing every pair. The copy kept from each group is the largest file, then the shortest name. | `data/dupes.json` |
| **sheets** | `core/sheets.py` | Builds contact sheets of 30 numbered previews each, for the labeller to look at. | `work/sheets/` |
| **label** | `core/labelers/` | Asks a labeller to put each file in one of your folders. See below. | `work/labels/`, `data/labels.json` |
| **apply** | `core/apply.py` | Merges the labels, then copies the files into `<dest>/<folder>/`. Duplicates go to a review folder. Originals are never touched. | the sorted folders, `sorted.csv`, `duplicates.csv` |

**Labellers.** The default runs `claude -p` against the contact sheets, three sheets per batch. Each finished batch is cached in `work/labels/`, so a 100,000-file run can be stopped and resumed across days without paying for the same batch twice. Three batches failing in a row for the same reason (sign-in, quota) stops the run rather than burning through the queue. The optional Jev labeller reads `work/jev.json`; its answer is used at a confidence of 0.7 or above, or wherever Claude gave no answer. Your own corrections (`work/overrides.json`, written when you use **Move to**) always win.

**Re-sorting is safe.** A rebuild deletes only the files that the previous run's own `sorted.csv` lists, and then removes folders it left empty. Changing the set of folders, or the sample size, invalidates the cached labels so a stale label is never applied.

### The server

`photosorter/api/` is a FastAPI app. It runs **one job at a time**; starting a second one while another runs is refused with a plain-words error.

| Route | Purpose |
|---|---|
| `GET /api/state` | Everything the page needs on load: folders, picker availability, the job and its log, platform name. |
| `POST /api/peek`, `POST /api/pick` | Look inside a folder; open the native folder picker (a child process, so a hung dialog cannot freeze the server). |
| `POST /api/sort`, `POST /api/run` | Run the whole pipeline, or a single step. |
| `POST /api/cancel` | Stop at the next safe point. |
| `GET /api/events` | Server-Sent Events: progress, phase changes and the finish. |
| `GET /api/labels` | Live labels so far, merged the same way `apply` merges them. |
| `POST /api/categories`, `POST /api/move` | Save your folders; move one file to another folder. |
| `GET /api/record/{id}`, `GET /api/file/{id}` | One file's record; the original, with range requests for video. |
| `POST /api/open` | Show a file, or the sorted folder, in your file manager. |

`web/src/api/types.ts` is generated from this server's OpenAPI schema (`npm run gen:api`), so the two sides cannot drift apart silently.

**The job runner** (`photosorter/jobs.py`) runs the work on a daemon thread and talks to the HTTP layer only through events. Each browser tab gets its own bounded queue; a tab that stops reading is dropped instead of being waited on. Progress is throttled to at most 10 events a second and one per 0.5% of the total, so a 100,000-file run cannot flood the connection. Cancelling is cooperative: each phase checks a flag, and a phase that must clean up after itself (scan removes its half-written index) is never interrupted mid-way.

### The dashboard

`web/src/` is React 18 and TypeScript, built with Vite.

| Folder | Role |
|---|---|
| `api/` | A typed client. A 409 ("that file changed") is told apart from a 400 ("bad request") by status, never by matching a message. |
| `state/` | A pure reducer with four modes (loading, setup, running, done), plus the library loader that reads `data/inventory.json`. |
| `hooks/` | `useAppState` loads state and refreshes it when you return to the tab. `useJobEvents` follows the SSE stream: it reconnects after 900 ms and falls back to polling `/api/state` after three failed reconnects. |
| `anim/` | The rotating sphere, the flight of each photo into its folder, and the confetti. None of it goes through React state: the sphere is capped at 320 tiles on a golden-angle layout, tiles are shared between files, and a single `requestAnimationFrame` loop drives everything. |
| `components/` | The top bar, folder cards, setup card, running and done panels, and the four dialogs. |
| `styles/` | `tokens.css` (copied byte for byte from the reference) and the shared control rules. |

The built dashboard is committed in `web/dist/`, which is why a user needs only Python.

### Security model

The server is built for a single user on a single machine.

- It binds `127.0.0.1` only.
- **Host check on every request**, to defeat DNS rebinding: a rebinding page looks "same origin" to the browser, so the Host header is the only thing that gives it away.
- **Origin check on every mutating request**, to defeat cross-site POSTs: a page on another site can make your browser post to localhost, but it cannot hide its Origin. Under `--dev` only, Vite's origin is also accepted.
- Reading a file's record, serving the original, and moving a file all require the file's SHA-256 alongside its id, and refuse a mismatch. Ids are positions in the inventory, so after a rescan a stale id could otherwise file a photo in the wrong place permanently.
- File and folder paths are resolved and contained before they are opened.
- Your originals are opened read-only.

## Where your data lives

| Path | Holds | In git? |
|---|---|---|
| `data/` | Thumbnails, mini previews, the inventory, labels and duplicate groups for the current library. | no |
| `work/` | Contact sheets, cached label batches, your overrides, optional Jev output. | no |
| `peek/`, `demo/` | Previews from the folder you are about to sort; the fake demo library. | no |
| `categories.json` | Your folder list. | yes |
| `.env` | `JEV_KEY`, if you use Jev. | no |
| `<dest>/` | The sorted copies, `sorted.csv` and `duplicates.csv`. | n/a |

## Testing and status

```bash
pytest                    # the engine and the server
cd web && npm test        # the dashboard
cd web && npx tsc --noEmit
```

At the last run on `main`, `pytest` reported 391 passed and 3 skipped, `npm test` reported 219 passed, and the type check was clean.

Passing tests do not cover everything. The folder picker, "Show in File Explorer", "Open sorted folder", a destination on another drive, and non-ASCII filenames have never been exercised on real hardware, on any platform. `docs/platform-support.md` lists each one with what to do and what to expect. The 20-row visual parity check against the reference dashboard has not been done either. `BUILD-TEST-LEDGER.md` records what has and has not been run.

## Known limitations

- The Jev labeller only reads `work/jev.json`; it does not yet call the paid API.
- A library of more than 320 files shares tiles on the sphere, and a photo can fly out of a tile that is showing a different photo.
- "Show in file manager" opens the folder on Linux but cannot select the file.
- `serve --dev` expects the server on port 8765.
- A rescan after changing the sample size once failed with `Access is denied` on `data/slim.json` and did not reproduce in seven later runs. It looks like a transient Windows file lock.

## Documents

| | |
|---|---|
| `docs/superpowers/specs/` | The design spec: what is being built and why. |
| `docs/superpowers/plans/` | The three build plans: the core engine, the API server, the dashboard. |
| `docs/platform-support.md` | Every platform-specific behaviour, and how to verify it. |
| `BUILD-TEST-LEDGER.md` | What has been built, and what has actually been run. |
| `CLAUDE.md`, `AGENTS.md` | Rules and conventions for contributors and coding agents. |

## License

MIT

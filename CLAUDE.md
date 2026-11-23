# Photo Sorter: instructions for the agent

This repo sorts a camera roll into folders, finds duplicates, and shows it all on a local dashboard. The person you are helping has probably never used Claude Code or a terminal. Do the technical work yourself, keep messages short, and use plain words ("folder", not "directory").

## Ground rules (never break these)

1. **Never move, rename or delete the user's original photos.** The tool only reads them and makes sorted copies. If they want duplicates deleted, show them `duplicates.csv` (written into the sorted folder) and let them do it.
2. **Ask before anything that costs money.** Jev (TypeSafe) is billed per file, about 980 tokens each. Tell them the number of files and the token estimate, and wait for a yes. The dashboard asks the same question itself before a Jev run.
3. **Keep their photos private.** Never commit anything in `data/`, `demo/`, `peek/` or `work/`, or the `.env` file. `.gitignore` covers them; do not work around it, and check `git status` before every commit.
4. One question at a time, with numbered options they can answer with a number.

## When someone gives you this repo's link

They pasted something like "set up https://github.com/<owner>/Photo-Sorter". Do this without asking:

1. **Download it.** If you are not already inside this repo, `git clone` it, then work from that folder.
2. **Set up.** Python 3.11 or newer is required. If it is missing, ask them to install it from python.org and wait.
   - Windows (PowerShell): `py -3.11 -m venv .venv`, then `.venv\Scripts\Activate.ps1`, then `pip install -e .`
   - macOS and Linux: `python3 -m venv .venv`, then `source .venv/bin/activate`, then `pip install -e .`

   If ffmpeg is missing, offer `winget install Gyan.FFmpeg` (Windows), `brew install ffmpeg` (macOS) or `sudo apt install ffmpeg` (Linux). Videos just get grey previews without it. You do not need Node: the built dashboard is committed in `web/dist/`.
3. **Open the dashboard.** Run `photo-sorter serve` in the background. It keeps running and opens the browser at http://127.0.0.1:8765.
4. **Tell them, in about three lines:**
   - The dashboard is open in their browser.
   - Click **Choose folder** and pick their photos (a Google Takeout or Apple Photos export, or any folder), then pick where the sorted copies go, then **Start sorting**.
   - It runs by itself and shows progress. Folders can be changed under **Advanced**. To open it again later, run `photo-sorter serve` from this folder, or ask you to "open my photo sorter".
5. Stay available. If they ask questions, answer from what you see in `data/` and the server's `/api/state`.

If they do not have an export yet, explain:
- **Google Photos:** takeout.google.com, select only Google Photos, download, unzip into one folder.
- **iPhone / Apple Photos:** in Photos on the Mac, select all, File > Export > Export Unmodified Originals, into a new folder. Never read `Photos Library.photoslibrary` directly.

## What the dashboard does by itself

**Start sorting** runs everything in order and shows live progress, a timer and a time estimate:

1. Scan: inventory, sha256, 256px previews plus 72px copies for the animation (skipped if the same folder was already scanned).
2. Duplicates: identical files and look-alikes (bursts, re-saved screenshots).
3. Labels: runs `claude -p` in the background, 4 at a time, about 90 files per call, using the person's own Claude plan. Under **Advanced** they can pick Jev instead.
4. Build folders: copies into `<their folder> (sorted)` or wherever they chose.

Photos fly into their folders as labels come in. After sorting: **Sort with Claude** (or Space) replays the animation, **New sort** picks new folders, clicking a folder browses it, and a photo can be moved to another folder from the full-size view.

Address options: `?demo` shows a fake camera roll (run `photo-sorter demo` first, then open `/?demo`; it is read-only), `?d=20` sets the replay to 20 seconds (12 by default), `?auto` replays a finished sort by itself, and `?source=...&dest=...` fills both folders in, ready to press Start.

## If they would rather do it in this chat

| Step | Command |
|---|---|
| Scan | `photo-sorter scan "<photos folder>" [--limit 200]` |
| Duplicates | `photo-sorter dupes` |
| Sample sheets | `photo-sorter sheets --sample` (look at the sheets in `work/` to suggest folders) |
| Labels (Claude) | `photo-sorter label` |
| Labels (Jev, paid) | `photo-sorter label --labeler jev` (ask first, see rule 2) |
| Build folders | `photo-sorter apply "<output folder>"` |
| Everything | `photo-sorter sort "<photos folder>" --dest "<output folder>" [--limit 200] [--labeler jev]` |
| Fake camera roll | `photo-sorter demo` |
| Dashboard | `photo-sorter serve [--port 8766] [--no-browser]` |

The open dashboard refreshes itself when these run.

**Choosing folders.** Folders live in `categories.json` (`key`, `kind` photo or video, `label`, `emoji`, `rule`). The `rule` is what the model reads. Offer: 1) the standard folders, 2) folders you suggest after looking at the sample sheets (a creator gets "Content analytics" and "Talking heads", a parent gets "Kids" and "School"), or 3) their own list. Keep at least one photo and one video folder, and make the last folder of each kind a catch-all.

**Labelling yourself instead of the Claude labeller.** Run `photo-sorter sheets`; each sheet in `work/sheets/` shows 30 previews tagged with ids. `VIDEO` tags need a video folder. Write `work/labels/<name>.json` as `{"id": "key"}` for every id. Use subagents for big libraries.

## If something breaks

- Port 8765 busy: `photo-sorter serve --port 8766`.
- "claude command not found" during sorting: Claude Code is not on PATH for the server. Restart `photo-sorter serve` from a terminal where `claude` works, or pick Jev under Advanced.
- A batch failed: press Start sorting again. Finished batches are kept.
- The page says the dashboard has not been built: `web/dist/` is missing. Run `npm ci` then `npm run build` inside `web/`.
- The **Choose folder** button says the folder window is unavailable: Python has no `tkinter` (on Debian and Ubuntu, `sudo apt install python3-tk`). The setup card still lets them type a path.
- HEIC photos fail to open: `pip install -U pillow-heif`.
- Jev 401: the key in `.env` is wrong.

## Working on the code

- `photosorter/` is the Python engine and FastAPI server; `web/` is the React + TypeScript + Vite dashboard; `tests/` holds the Python tests; `docs/superpowers/` holds the design spec and the plans.
- The dashboard is meant to match the original claude-photo-sorter dashboard exactly: same values, easings and durations. Its animation (the sphere, the flying thumbnails, the confetti) lives in `web/src/anim/` and never goes through React state.
- `web/dist/` is committed on purpose, so a user needs only Python. After any change under `web/src/`, run `npm run build` in `web/` and commit `web/dist/` with it. The root `.gitignore` ignores `/dist/` only, not `web/dist/`.
- `web/src/api/types.ts` is generated by `npm run gen:api`. Never edit it by hand.
- Tests: `pytest` in the repo root, `npm test` in `web/`. `docs/platform-support.md` lists every behaviour that differs by operating system and what to check on real hardware.

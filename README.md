# Photo Sorter

Point it at a camera roll. It looks at every photo and video, sorts them into folders, finds the duplicates, and you watch it happen on a live dashboard on your own computer.

A modernized, cross-platform replica of [claude-photo-sorter](https://github.com/kairothq/claude-photo-sorter): the same dashboard, the same animation, and a Python server that works on Windows as well as macOS.

- **Sorts photos and videos** into folders like Selfies, Food, Travel, Screenshots and Talking heads. Use the standard folders or make your own.
- **Finds duplicates**: identical copies, burst shots and re-saved screenshots go to a review folder, with a list of which copy was kept.
- **Never touches your originals.** It only reads them and makes sorted copies.
- **Runs on your computer.** Your photos are not uploaded anywhere. The dashboard listens on `127.0.0.1` only.

## Status

The command-line engine, the server and the dashboard are all written. **Nothing has been verified on real hardware yet**, Windows included: every platform behaviour is written but not run, and the test suites have been written but not run in this build. [`docs/platform-support.md`](docs/platform-support.md) lists each platform-specific behaviour (folder picker, copy, show in Explorer, and so on) with what to check and what the result should be. [`BUILD-TEST-LEDGER.md`](BUILD-TEST-LEDGER.md) records what has and has not been run.

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

To work on the page with hot reload, run `photo-sorter serve --dev` in one terminal and `npm run dev` in `web/` in another, then open the Vite address. `npm run gen:api` regenerates `web/src/api/types.ts` from the server's schema; never edit that file by hand. Tests: `pytest` for the engine and server, `npm test` in `web/` for the dashboard.

Contributors and coding agents: read [`CLAUDE.md`](CLAUDE.md).

## License

MIT

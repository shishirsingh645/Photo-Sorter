# Photo Sorter — Plan 3: React Dashboard

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A React + TypeScript dashboard that looks and feels like the reference at http://127.0.0.1:8765/ — the rotating thumbnail sphere, photos flying into folder cards as labels arrive, the confetti finish — driven by SSE instead of polling, and working correctly on Windows where the original silently degrades.

**Architecture:** React renders the chrome — topbar, KPIs, folder cards, panels, dialogs. The animation never goes through React: `sphere.ts`, `fly.ts` and `confetti.ts` own their own DOM nodes behind a ref and run on one shared `requestAnimationFrame` loop. One `useReducer` store, two hooks, no state-management library. API types are generated from the server's OpenAPI schema.

**Tech Stack:** React 18, TypeScript, Vite, CSS Modules, Vitest + React Testing Library. Node 20+ (v26.13.1 verified on this machine).

**Spec:** `docs/superpowers/specs/2026-11-21-photo-sorter-modernized-replica-design.md`

**Depends on:** Plan 2, all tasks complete (the OpenAPI schema must exist before Task 2).

## Global Constraints

- **The 320 animated tiles must never be React state.** Routing per-frame transforms through the component tree drops frames and loses the feel the replica exists to reproduce. A reviewer rejects any task that puts tile positions in `useState`.
- `web/src/styles/tokens.css` is a **verbatim copy** of the reference's `tokens.css`. Do not restyle, rename or "improve" the tokens.
- `app.css` and `components.css` are ported **value-for-value** into CSS Modules — the same pixel values, the same easings, the same durations.
- Reference values that must be copied exactly: sphere rotation `0.00035`/ms, tilt `sin(t/4000) × 0.35`, at most **320** tiles, fly duration `650 + random × 400` ms with easing `cubic-bezier(.55,0,.25,1)`, queue release `ceil(queue.length / 45)` per frame, **12** preview slots per folder card and **24** on the duplicates card, browse page size **120**, confetti **200** particles, default replay **12** seconds.
- `prefers-reduced-motion: reduce` skips confetti and the fly arcs, landing tiles directly in place.
- Every dialog traps focus, closes on Escape, and returns focus to its opener.
- No text may say "Finder" on Windows — the file-manager name comes from `AppState.file_manager`.

## Review Focus

1. **A 100,000-file library.** The slim index is ~3 MB of JSON; nothing in the UI may build a DOM node per file or hold the full inventory. → Task 3, Task 7.
2. **A library where one folder holds almost everything and the rest are empty** — the owner's real sort put 174 of 183 photos in one card. Empty cards and one saturated card must both look right. → Task 3.
3. **A library with zero videos** (also the owner's real sort). The video column and its catch-all must render correctly with nothing in them. → Task 3.
4. **A sort that fails mid-phase.** The run card must show the error and a working "Try again", not a spinner forever. → Task 6.
5. **A narrow window.** The reference collapses to one column under 900px and hides the pill under 560px; the replica must do the same rather than overflow horizontally. → Task 3.

---

### Task 1: Frontend scaffold, design tokens and theme

**Files:**
- Create: `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/index.html`, `web/src/main.tsx`, `web/src/App.tsx`, `web/src/styles/tokens.css`, `web/src/styles/base.css`, `web/src/hooks/useTheme.ts`
- Test: `web/src/hooks/useTheme.test.ts`

**Interfaces:**
- Produces: `useTheme() -> { theme: "light" | "dark", toggle: () => void }`, persisting to `localStorage` under the key `"theme"` and falling back to `prefers-color-scheme`.

- [ ] **Step 1: Write the failing test**

```ts
it("defaults to the system preference when nothing is stored", () => { ... })
it("restores the stored theme over the system preference", () => { ... })
it("writes data-theme onto the document element", () => {
  expect(document.documentElement.dataset.theme).toBe("dark")
})
it("survives localStorage throwing in private mode", () => { ... })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test`
Expected: FAIL — module not found

- [ ] **Step 3: Scaffold the Vite app**

`npm create vite@latest` with the react-ts template, then configure `vite.config.ts` to proxy `/api` and `/events` to `http://127.0.0.1:8765` in dev and to build into `web/dist`.

- [ ] **Step 4: Copy `tokens.css` verbatim** from `D:\CODING\REA-Photo Sorter\claude-photo-sorter\dashboard\tokens.css` into `web/src/styles/tokens.css`. Do not edit it.

- [ ] **Step 5: Port the global rules** from the top of the reference's `app.css` (lines 1–9: box-sizing, `[hidden]`, html/body, base font size 13px, `overflow: hidden`, button and input fonts, icon sizing) into `web/src/styles/base.css`.

- [ ] **Step 6: Implement `useTheme`** and set `<title>Sorting my camera roll</title>` and the reference's inline SVG favicon in `index.html`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd web && npm test`
Expected: 4 passed

- [ ] **Step 8: Commit**

```bash
git add web/
git commit -m "feat: vite react scaffold with ported design tokens"
```

---

### Task 2: Typed API client and the two hooks

**Files:**
- Create: `web/src/api/types.ts` (generated), `web/src/api/client.ts`, `web/src/state/reducer.ts`, `web/src/hooks/useAppState.ts`, `web/src/hooks/useJobEvents.ts`
- Test: `web/src/state/reducer.test.ts`, `web/src/hooks/useJobEvents.test.ts`

**Interfaces:**
- Consumes: Plan 2's `openapi.json`.
- Produces:
  - `client.getState()`, `getLabels()`, `getRecord(id)`, `sort(args)`, `run(args)`, `cancel()`, `peek(source)`, `saveCategories(cats)`, `move(id, key)`, `open(args)`, `pick(prompt)` — all typed, all throwing `ApiError` carrying the server's plain-words message.
  - `reducer(state, action)` over `Mode = "loading" | "setup" | "running" | "done"`.
  - `useAppState()` — initial load plus reconnect fallback.
  - `useJobEvents(onEvent)` — subscribes to `/api/events`, reconnects with backoff, and falls back to polling `/api/state` every 900 ms after three failed reconnects.

- [ ] **Step 1: Write the failing test**

```ts
it("moves from setup to running when a sort starts", () => { ... })
it("moves to done when the job finishes with code 0", () => { ... })
it("moves to a failed run state when the job finishes non-zero", () => { ... })
it("starts in running mode when the initial state has a live sort job", () => { ... })

// Review Focus — a dropped stream
it("falls back to polling after three failed reconnects", async () => { ... })
it("stops polling once the stream comes back", async () => { ... })
it("surfaces the server's error message verbatim on a 400", async () => {
  await expect(client.sort(bad)).rejects.toThrow("Choose the folder with your photos first.")
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test`
Expected: FAIL — module not found

- [ ] **Step 3: Generate `types.ts`** from the running server's schema, and add an `npm run gen:api` script so it can be regenerated when the backend changes.

- [ ] **Step 4: Implement `client.ts`, `reducer.ts` and both hooks**

`useJobEvents` uses `EventSource`. The polling fallback exists because a laptop waking from sleep is a normal event, not an error — Plan 2's Review Focus 2.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd web && npm test`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add web/src/api web/src/state web/src/hooks
git commit -m "feat: typed api client, reducer and sse hooks"
```

---

### Task 3: Chrome — topbar, KPI row, folder cards

**Files:**
- Create: `web/src/components/Topbar.tsx`, `KpiRow.tsx`, `FolderCard.tsx`, `Board.tsx`, `Toast.tsx`, `Icon.tsx`, plus a `.module.css` beside each
- Test: `web/src/components/FolderCard.test.tsx`, `KpiRow.test.tsx`, `Board.test.tsx`

**Interfaces:**
- Produces:
  - `<Topbar mode pill onNewSort onSortWithClaude onEditFolders onOpenSorted />`
  - `<KpiRow checked photos videos foldersMade foldersTotal dupes saved progress />`
  - `<FolderCard category count slots onOpen />` — exposes `slotRefs` so `fly.ts` can target them.
  - `<Board photoCats videoCats />`
  - `Icon` — the reference's 15 inlined Lucide paths, same names.

- [ ] **Step 1: Write the failing test**

```tsx
it("renders twelve slots on a normal card and twenty-four on the duplicates card", () => { ... })
it("truncates a long folder name and keeps the full name as a tooltip", () => {
  expect(screen.getByTitle("Documents & receipts")).toBeInTheDocument()
})
it("hides the count badge until the first file lands", () => { ... })
it("formats space saved as MB below a gigabyte and GB above", () => {
  expect(fmtSize(262_000_000)).toBe("262 MB")
  expect(fmtSize(2_100_000_000)).toBe("2.1 GB")
})

// Review Focus 2 — one saturated card, the rest empty
it("renders correctly when one card holds 174 files and nine are empty", () => {
  render(<Board ... />)
  expect(screen.getAllByRole("button", { name: /folder/i })).toHaveLength(10)
  expect(screen.getByText("174")).toBeInTheDocument()
})

// Review Focus 3 — no videos
it("renders the video column with no videos and no crash", () => { ... })

// Review Focus 1 — large library
it("renders no more DOM nodes for 100k files than for 1k", () => { ... })

// Review Focus 5 — narrow window
it("collapses to a single column below 900px", () => { ... })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the components and port their CSS**

Port the reference's `.topbar`, `.mx-kpis`, `.mx-kpi`, `.board`, `.col`, `.cards`, `.card`, `.ch`, `.grid`, `.slot` rules and both media queries value-for-value. The duplicates card keeps `grid-column: 1 / -1` and 12 grid columns; normal cards use 6.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npm test`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add web/src/components
git commit -m "feat: topbar, kpi row and folder cards"
```

---

### Task 4: The setup card

**Files:**
- Create: `web/src/components/SetupCard.tsx`, `AdvancedPanel.tsx`, `estimates.ts`, plus CSS modules
- Test: `web/src/components/SetupCard.test.tsx`, `web/src/components/estimates.test.ts`

**Interfaces:**
- Produces:
  - `<SetupCard state pick onChoose onStart />`
  - `phaseEstimates(files, bytes, scan) -> {scan, dupes, label, apply}`
  - `roughly(seconds) -> string`

**This task fixes the worst defect found in the live app:** on Windows the reference shows no folder picker at all, only a text box with a macOS placeholder.

- [ ] **Step 1: Write the failing test**

```ts
it("matches the reference's estimate formulas", () => {
  const e = phaseEstimates(1136, 10.7e9, true)
  expect(e.scan).toBeCloseTo(4 + 1136 * 0.025 + 10.7 * 9, 1)
  expect(e.dupes).toBeCloseTo(2 + Math.pow(1.136, 2) * 4, 1)
  expect(e.apply).toBeCloseTo(2 + 1136 * 0.018, 1)
})
it("phrases short durations as 'under a minute'", () => {
  expect(roughly(40)).toBe("under a minute")
  expect(roughly(200)).toBe("about 3 min")
})
```

```tsx
it("shows a Choose folder button on every platform, Windows included", () => {
  render(<SetupCard state={{ platform: "win32", picker_available: true }} />)
  expect(screen.getByRole("button", { name: /choose folder/i })).toBeInTheDocument()
})
it("never shows a mac path placeholder on Windows", () => {
  expect(screen.queryByPlaceholderText(/\/Users\//)).toBeNull()
})
it("falls back to path entry with a reason when the picker is unavailable", () => { ... })
it("offers the last used folder as a shortcut", () => { ... })
it("suggests '<source> (sorted)' as the destination", () => { ... })
it("warns when the disk cannot hold the previews", () => {
  expect(screen.getByText(/free space/i)).toBeInTheDocument()
})
it("shows the estimated time and the Claude labelling time for a large library", () => { ... })
it("disables Start until both folders are chosen", () => { ... })
it("adds and removes folders under Advanced", () => { ... })
it("keeps the new folder before the catch-all of its kind", () => { ... })
it("shows the PAID badge and token estimate for Jev", () => { ... })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `estimates.ts`** with the four formulas and `roughly`, copied exactly from spec §7.5.

- [ ] **Step 4: Implement `SetupCard` and `AdvancedPanel`**

The three numbered steps, the peek summary, the time estimate, and Advanced with folder chips, the labeller choice and the 200-file sample checkbox. The picker button is always offered when `picker_available`; path entry is the labelled fallback, never a silent one, and its placeholder is built from the platform (`D:\Pictures\Camera roll` on Windows).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd web && npm test`
Expected: 13 passed

- [ ] **Step 6: Commit**

```bash
git add web/src/components
git commit -m "feat: setup card with a working picker on every platform"
```

---

### Task 5: The animation layer

**Files:**
- Create: `web/src/anim/sphere.ts`, `fly.ts`, `confetti.ts`, `loop.ts`, `web/src/components/Stage.tsx`
- Test: `web/src/anim/sphere.test.ts`, `fly.test.ts`

**Interfaces:**
- Produces:
  - `createSphere(container: HTMLElement, srcs: string[]) -> Sphere` with `.draw(dt)`, `.tileFor(id)`, `.retire(tile)`, `.clear()`; at most 320 tiles on a golden-angle Fibonacci distribution.
  - `flyToSlot(tile, slotEl, img, onLand)` — Web Animations API.
  - `burstConfetti(canvas, origin, colors)` — 200 particles.
  - `startLoop(fn)` / `stopLoop()` — one shared rAF loop.
  - `<Stage mode items />`

**No tile position may live in React state.**

- [ ] **Step 1: Write the failing test**

```ts
it("caps the sphere at 320 tiles however many files there are", () => {
  expect(createSphere(el, srcs(100_000)).tiles.length).toBe(320)
})
it("distributes tiles on a unit sphere", () => {
  for (const t of sphere.tiles) expect(t.x ** 2 + t.y ** 2 + t.z ** 2).toBeCloseTo(1, 5)
})
it("shares tiles between files when there are more files than tiles", () => { ... })
it("retires a tile only once its last file has flown", () => { ... })
it("releases ceil(queue/45) files per frame", () => {
  expect(releaseCount(900)).toBe(20)
  expect(releaseCount(1)).toBe(1)
})
it("uses the reference's fly duration and easing", () => {
  expect(opts.easing).toBe("cubic-bezier(.55,0,.25,1)")
  expect(opts.duration).toBeGreaterThanOrEqual(650)
  expect(opts.duration).toBeLessThanOrEqual(1050)
})
it("lands tiles directly when reduced motion is requested", () => {
  matchMediaReduced()
  flyToSlot(tile, slot, img, onLand)
  expect(onLand).toHaveBeenCalledImmediately()
})
it("writes transforms to the DOM, not through React", () => {
  sphere.draw(16)
  expect(sphere.tiles[0].el.style.transform).toMatch(/translate3d/)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `sphere.ts`**

Golden angle `π(3 − √5)`; per frame, rotate by `dt × 0.00035`, tilt by `sin(now/4000) × 0.35`, and set each tile's `translate3d` + `scale`, opacity `0.2 + depth × 0.8` and `zIndex` from depth. `will-change: transform` and `backface-visibility: hidden` on the tile images, as in the reference.

- [ ] **Step 4: Implement `fly.ts` and `confetti.ts`**

The fly arc is a three-keyframe animation with a randomised mid-point (`±120px` horizontally, `−60 − random×80` vertically) and rotation, ending scaled to the destination slot. Confetti reads its colours from the CSS custom properties `--brand-solid`, `--green`, `--accent`, `--faint`, `--ink` so it follows the theme.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd web && npm test`
Expected: 8 passed

- [ ] **Step 6: Verify 60fps by hand**

Run the dashboard against a scan of at least 1,000 files and watch the fly phase in Chrome's performance panel.
Expected: no sustained frame drops; the sphere holds 320 tiles.

- [ ] **Step 7: Commit**

```bash
git add web/src/anim web/src/components/Stage.tsx
git commit -m "feat: sphere, fly and confetti animation outside react"
```

---

### Task 6: The running panel and the done panel

**Files:**
- Create: `web/src/components/RunCard.tsx`, `DonePanel.tsx`, `progress.ts`, plus CSS modules
- Test: `web/src/components/RunCard.test.tsx`, `progress.test.ts`

**Interfaces:**
- Produces:
  - `overallProgress(job, estimates) -> number`
  - `remainingSeconds(job, estimates) -> number`
  - `<RunCard job onRetry onCancel />`, `<DonePanel total folders dupes saved onReplay />`

- [ ] **Step 1: Write the failing test**

```ts
it("weights each phase by its estimate, not evenly", () => { ... })
it("returns 1 when the job reaches the done phase", () => { ... })
it("switches from the estimate to the measured rate above 15% of a phase", () => { ... })
it("never reports less than two seconds left for a running phase", () => { ... })
```

```tsx
it("marks finished phases with a tick and the current one as active", () => { ... })

// Review Focus 4 — a failed sort
it("shows the error log and a working Try again when the job fails", () => {
  render(<RunCard job={{ running: false, code: 1, log: ["boom"] }} />)
  expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
  expect(screen.getByRole("button", { name: /try again/i })).toBeEnabled()
})
it("never shows a running spinner for a job that has stopped", () => { ... })
it("offers Cancel only while a job is running", () => { ... })
it("counts up the total and fires confetti on the done panel", () => { ... })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `progress.ts`, `RunCard` and `DonePanel`**

The elapsed/remaining timer is painted from the shared rAF loop, not a React interval, so it does not re-render the tree every frame. Cancel is new in the replica (spec §8.2) and must be clearly labelled as stopping the sort, not undoing it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npm test`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add web/src/components
git commit -m "feat: running panel with phase progress, cancel and done panel"
```

---

### Task 7: Dialogs — folders, browse, lightbox, paid confirm

**Files:**
- Create: `web/src/components/Dialog.tsx`, `FoldersDialog.tsx`, `BrowseDialog.tsx`, `Lightbox.tsx`, `PaidConfirm.tsx`, plus CSS modules
- Test: one test file per component

**Interfaces:**
- Produces: `<Dialog>` with focus trap and Escape handling, plus the four dialogs above.

- [ ] **Step 1: Write the failing test**

```tsx
it("traps focus inside the dialog and restores it to the opener on close", () => { ... })
it("closes on Escape and on a scrim click but not on a content click", () => { ... })

it("requires every folder to have a name before saving", () => { ... })
it("generates a unique key from the folder name", () => { ... })
it("refuses to save without at least one photo and one video folder", () => { ... })

// Review Focus 1 — large library
it("shows 120 thumbnails at a time with a Show more button", () => {
  render(<BrowseDialog items={make(5000)} />)
  expect(screen.getAllByRole("img")).toHaveLength(120)
})
it("says the file manager's real name for the platform", () => {
  expect(screen.getByRole("button", { name: /show in file explorer/i })).toBeInTheDocument()
  expect(screen.queryByText(/finder/i)).toBeNull()
})
it("shows an empty-folder message rather than a blank grid", () => { ... })

it("moves between photos with the arrow keys and stops at both ends", () => { ... })
it("moves a photo to another folder and reports it", () => { ... })
it("offers only folders matching the file's kind in Move to", () => { ... })
it("loads the full record lazily when opened", () => { ... })
it("plays a video with controls instead of showing it as an image", () => { ... })

it("states the file count and token estimate before spending on Jev", () => { ... })
it("returns false when the paid dialog is dismissed", () => { ... })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `Dialog` and the four dialogs**

`BrowseDialog` pages at 120 and `Lightbox` fetches `/api/record/{id}?sha=<the record's sha256>` on open (**the `sha` is required - a bare call returns 400**, and a 409 means the folder was rescanned since the page loaded, so reload rather than retry) — together these are what keep a 100,000-file library usable (spec §13.2). Port the reference's `.fb-dialog`, `.browse`, `.lightbox` and `.pc-*` CSS value-for-value.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npm test`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add web/src/components
git commit -m "feat: folders, browse, lightbox and paid confirm dialogs"
```

---

### Task 8: Demo mode, URL parameters, and the parity sweep

**Files:**
- Modify: `web/src/App.tsx`, `web/src/hooks/useAppState.ts`
- Create: `web/src/demo.ts`, `README.md`, `CLAUDE.md`, `AGENTS.md`
- Test: `web/src/demo.test.ts`, `web/src/App.test.tsx`

**Interfaces:**
- Produces: support for `?demo`, `?d=<seconds>`, `?auto`, `?source=`, `?dest=`, and the Space key replay.

- [ ] **Step 1: Write the failing test**

```tsx
it("reads the demo library from demo/ instead of the api", () => { ... })
it("blocks api writes in demo mode with an explanatory toast", () => { ... })
it("uses ?d=20 as the replay length", () => { expect(replayMs()).toBe(20000) })
it("defaults the replay to 12 seconds", () => { ... })
it("replays by itself with ?auto once the dashboard is done", () => { ... })
it("prefills both folders from ?source= and ?dest=", () => { ... })
it("replays on Space but not while typing in a field", () => { ... })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test`
Expected: FAIL

- [ ] **Step 3: Implement the URL parameter handling and demo mode.**

- [ ] **Step 4: Build the frontend and commit `web/dist/`**

Run: `cd web && npm run build`
Expected: `web/dist/index.html` and its assets exist; `photo-sorter serve` now serves the real dashboard.

- [ ] **Step 5: Run the parity sweep**

Start the replica on 8766 and open the reference on 8765 side by side. Walk every row of spec §7.5 and §7.6 in **both light and dark themes**, with the demo library, and record any difference:

- [ ] setup card, with and without a picker
- [ ] sphere before and after a source is chosen
- [ ] running phases, timer, progress bar
- [ ] files flying into cards; card flash and badge pop
- [ ] done panel, count-up, confetti, chips
- [ ] folder browse, lightbox, arrow keys, Move to
- [ ] edit folders dialog
- [ ] replay via the top-bar button and via Space
- [ ] truncated folder names, empty cards, the saturated card
- [ ] the window narrowed below 900px and below 560px

- [ ] **Step 6: Write `README.md`, `CLAUDE.md` and `AGENTS.md`**

`README.md` covers install and run for all three platforms, with Windows first and macOS/Linux marked as written-but-unverified. `CLAUDE.md` carries over the reference's agent playbook — the ground rules about never touching originals, asking before anything paid, and keeping photo data out of git — updated for this repo's commands. `AGENTS.md` points at `CLAUDE.md`.

- [ ] **Step 7: Commit**

```bash
git add web/ README.md CLAUDE.md AGENTS.md
git commit -m "feat: demo mode, url parameters and built dashboard"
```

---

### Task 9: Windows verification pass

**Files:**
- Create: `docs/platform-support.md`
- Test: manual, recorded in that document.

- [ ] **Step 1: Sort a real folder end to end on Windows**

Use a real local camera-roll folder with non-ASCII filenames, `--limit 200` first, then in full, through the dashboard.
Expected: completes, folders built, both CSVs written, source folder byte-identical before and after.

- [ ] **Step 2: Verify each platform seam by hand on Windows**

- [ ] folder picker opens and returns a path
- [ ] "Show in File Explorer" reveals a file, selected
- [ ] "Open sorted folder" opens the destination
- [ ] a destination on another drive works
- [ ] Devanagari and emoji filenames survive scan, label and copy
- [ ] the app runs **without** `PYTHONUTF8=1` set

- [ ] **Step 3: Write `docs/platform-support.md`**

A table of every seam from spec §8.4 with its status: Windows *verified* with the date, macOS *written, not yet verified*, Linux *written, not yet verified*. State plainly which rows have been exercised on real hardware and which have only unit tests with fakes. Do not describe unverified rows as working.

- [ ] **Step 4: Commit**

```bash
git add docs/platform-support.md
git commit -m "docs: windows verification results and platform support status"
```

---

## Done when

The replica at 127.0.0.1:8766 is indistinguishable from the reference at 8765 across every row of the parity sweep, a real camera roll sorts correctly on Windows without `PYTHONUTF8`, every test passes, and `docs/platform-support.md` states honestly what has and has not been verified.

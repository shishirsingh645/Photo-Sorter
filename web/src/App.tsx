import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import * as api from "./api/client"
import type { AppState } from "./api/client"
import { Player } from "./anim/player"
import type { Sphere } from "./anim/sphere"
import styles from "./App.module.css"
import type { Labeler } from "./components/AdvancedPanel"
import { Board } from "./components/Board"
import type { BoardCard, BoardHandle } from "./components/Board"
import { BrowseDialog } from "./components/BrowseDialog"
import { DonePanel } from "./components/DonePanel"
import { phaseEstimates } from "./components/estimates"
import type { FolderCategory } from "./components/FolderCard"
import { FoldersDialog } from "./components/FoldersDialog"
import { KpiRow } from "./components/KpiRow"
import layers from "./components/Layers.module.css"
import { PaidConfirm } from "./components/PaidConfirm"
import { overallProgress } from "./components/progress"
import { RunCard } from "./components/RunCard"
import { SetupCard } from "./components/SetupCard"
import type { Picked } from "./components/SetupCard"
import { Stage } from "./components/Stage"
import { TitleRow } from "./components/TitleRow"
import { Toast } from "./components/Toast"
import { Topbar } from "./components/Topbar"
import type { Pill } from "./components/Topbar"
import { installDemoGuard, loadDemoState, readParams, replayMs } from "./demo"
import { fmt, tilde } from "./format"
import { useAppState } from "./hooks/useAppState"
import { useJobEvents } from "./hooks/useJobEvents"
import { REVIEW_KEY, targetOf } from "./state/board"
import { inFolder, loadDupeIds, loadLabelsFile, loadLibrary, loadSlim, miniOf, setLibraryBase } from "./state/library"
import type { LibraryItem, SlimItem } from "./state/library"
import type { Mode, StreamEvent } from "./state/reducer"

const NAMES: Record<string, string> = {
  scan: "Looking at every file",
  dupes: "Finding duplicates",
  label: "Claude is sorting your photos",
  apply: "Building your folders",
}
const LABELLING = ["label", "apply", "done"] // the phases during which labels.json has something in it
const PROMPT = { source: "Choose the folder with your photos", dest: "Choose where to save the sorted folders" }
const REVIEW: FolderCategory = { key: REVIEW_KEY, label: "Duplicates", emoji: "🗂️" }
const NO_PICK: Picked = { source: null, dest: null, peek: null }
const NO_CATS: AppState["categories"] = []
const NO_STAGE: { mini: string }[] = []

const messageOf = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong.")
/** The server hands back bare file names for a peek's previews (peek/0000.jpg); the page reads them from /peek. */
const previewUrl = (name: string) => (name.includes("/") ? name : `/peek/${name}`)

type Dialog = null | { kind: "folders" } | { kind: "browse"; folder: FolderCategory; items: LibraryItem[] }

/** The reference's per-run bookkeeping: which library the board holds, and what the poll has fetched. */
interface Lib {
  kind: "none" | "static" | "live"
  loading: Promise<void> | null
  dupes: Promise<void> | null
  lastLabelsAt: number
}
const freshLib = (): Lib => ({ kind: "none", loading: null, dupes: null, lastLabelsAt: 0 })

/** useJobEvents opens an EventSource as soon as it mounts, so demo mode (which has no server stream) leaves it out. */
function JobEvents({ onEvent }: { onEvent: (e: StreamEvent) => void }) {
  useJobEvents(onEvent)
  return null
}

export function App() {
  const [opts] = useState(readParams)
  setLibraryBase(opts.demo ? "/demo" : "/data") // before any effect below loads a file
  const { state, dispatch, error } = useAppState(opts.demo ? loadDemoState : undefined)
  const { mode: rmode, app, job } = state

  // ---- what is on screen ------------------------------------------------------------------------------
  const [items, setItems] = useState<SlimItem[]>([])
  const [pick, setPick] = useState<Picked>(NO_PICK)
  const [labeler, setLabeler] = useState<Labeler>("claude")
  const [sample, setSample] = useState(false)
  const [savedCats, setSavedCats] = useState<AppState["categories"] | null>(null)
  const [runInfo, setRunInfo] = useState({ files: 0, bytes: 0 })
  const [dialog, setDialog] = useState<Dialog>(null)
  const [paid, setPaid] = useState<{ files: number; resolve: (spend: boolean) => void } | null>(null)
  const [toast, setToast] = useState({ text: "", on: false })
  // A sort that has just ended in this page keeps showing the run card until its last file has landed.
  const [finishing, setFinishing] = useState(false)
  const [replaying, setReplaying] = useState(false)
  const [burst, setBurst] = useState(0) // each celebration remounts the done panel, live
  const [epoch, setEpoch] = useState(0) // a new key makes the Stage build a fresh sphere
  const [replayAt, setReplayAt] = useState(0)
  const [, setFrame] = useState(0)

  const mode: Mode = rmode === "done" && finishing ? "running" : rmode
  const categories = savedCats ?? app?.categories ?? NO_CATS
  useEffect(() => setSavedCats(null), [app?.categories]) // a fresh answer from the server wins over the last save

  // ---- what the animation reads ------------------------------------------------------------------------
  const boardRef = useRef<BoardHandle>(null)
  const layerRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const setupRef = useRef<HTMLDivElement>(null)
  const sphereRef = useRef<Sphere | null>(null)
  const onSphere = useCallback((s: Sphere | null) => void (sphereRef.current = s), [])
  const keys = useMemo(() => new Set(categories.map((c) => c.key)), [categories])
  // The latest of what callbacks outside React's render (the player, a timer, an await) need to read.
  const cur = useRef({ mode, keys, job, items, byId: new Map<number, SlimItem>(), replaying, onFinished: () => {} })
  cur.current.mode = mode
  cur.current.keys = keys
  cur.current.job = job
  cur.current.items = items
  cur.current.replaying = replaying
  const lib = useRef(freshLib())
  const runGen = useRef(0) // answers that come back after a new run, or a New sort, belong to the old one
  const began = useRef<number | null | undefined>(undefined) // the `started` of the run already begun
  const toastTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const inventory = useRef<Promise<Map<number, LibraryItem>> | null>(null)

  const showToast = useCallback((text: string) => {
    setToast({ text, on: true })
    clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToast((t) => ({ ...t, on: false })), 3200)
  }, [])
  useEffect(() => () => clearTimeout(toastTimer.current), [])
  useLayoutEffect(() => (opts.demo ? installDemoGuard(showToast) : undefined), [opts.demo, showToast])
  useEffect(() => {
    if (error) showToast(error.message)
  }, [error, showToast])

  const [player] = useState(
    () =>
      new Player({
        layer: () => layerRef.current,
        sphere: () => sphereRef.current,
        slot: (key, n) => {
          const slots = boardRef.current?.get(key)?.slotRefs
          return slots?.length ? slots[n % slots.length] : null
        },
        centre: () => {
          const r = stageRef.current?.getBoundingClientRect()
          if (!r) return { sx: innerWidth / 2, sy: innerHeight / 2, s: 1 }
          return { sx: r.left + r.width / 2, sy: r.top + r.height * (cur.current.mode === "running" ? 0.42 : 0.5), s: 1 }
        },
        keyOf: (it) => targetOf(it, cur.current.keys),
        miniOf,
        changed: () => setFrame((f) => f + 1),
        finished: () => cur.current.onFinished(),
      }),
  )
  useEffect(() => () => player.stop(), [player])

  const setLibrary = useCallback((loaded: SlimItem[]) => {
    cur.current.byId = new Map(loaded.map((it) => [it.id, it]))
    cur.current.items = loaded
    setItems(loaded)
  }, [])

  // The last file has landed, in a live sort or a replay. A tick later, so the last card's flash is painted before the
  // board stops being live and the done panel takes over.
  cur.current.onFinished = () => {
    setTimeout(() => {
      setFinishing(false)
      setReplaying(false)
      setBurst((b) => b + 1)
    }, 0)
  }

  // ---- a sort that is already done: the whole result at once, no animation and no confetti (showDone(false)) ----
  useEffect(() => {
    if (rmode !== "done" || finishing || lib.current.kind !== "none") return
    lib.current.kind = "static"
    const gen = runGen.current
    loadSlim(true).then(
      (loaded) => {
        if (gen !== runGen.current) return
        setLibrary(loaded)
        player.load(loaded)
        player.fillStatic()
      },
      (e) => {
        lib.current.kind = "none"
        showToast(messageOf(e))
      },
    )
  }, [rmode, finishing, player, setLibrary, showToast])

  // New folders after a save: put the finished result back on the new cards. Not mid-run, which they do not touch.
  useEffect(() => {
    const c = cur.current
    if (c.mode === "done" && !c.replaying && c.items.length) player.fillStatic()
  }, [keys, player])

  // ---- a live sort -------------------------------------------------------------------------------------
  function beginRunning() {
    runGen.current++
    lib.current = { ...freshLib(), kind: "live" }
    setLibrary([])
    player.load([])
    player.startLive()
    setFinishing(true)
    setReplaying(false)
    setBurst(0)
    setEpoch((e) => e + 1)
  }
  useEffect(() => {
    if (opts.demo || !job.running || job.step !== "sort" || began.current === job.started) return
    began.current = job.started ?? null
    beginRunning()
  }, [job.running, job.step, job.started])

  /** After the scan, the sphere's preview photos give way to the real library (the reference's libraryLoaded). */
  function ensureLibrary(): Promise<void> {
    const L = lib.current
    const gen = runGen.current
    L.loading ??= loadSlim(false).then(
      (loaded) => {
        if (gen !== runGen.current) return
        setLibrary(loaded)
        player.load(loaded)
        player.startLive()
        setRunInfo({ files: loaded.length, bytes: loaded.reduce((s, r) => s + r.bytes, 0) })
      },
      (e) => {
        L.loading = null
        throw e
      },
    )
    return L.loading
  }
  /** dupes.json is written by the duplicates phase, so it is read once labelling starts. */
  function ensureDupes(): Promise<void> {
    const L = lib.current
    L.dupes ??= loadDupeIds().then(
      (ids) => {
        for (const it of cur.current.items) it.dupe = ids.has(it.id)
      },
      (e) => {
        L.dupes = null
        throw e
      },
    )
    return L.dupes
  }

  const polling = useRef(false)
  async function pollRun() {
    if (polling.current) return
    polling.current = true
    const gen = runGen.current
    try {
      const phase = cur.current.job.phase
      if (!phase || phase === "scan") return
      await ensureLibrary()
      if (!LABELLING.includes(phase) || gen !== runGen.current) return
      await ensureDupes()
      if (Date.now() - lib.current.lastLabelsAt > 1200) {
        lib.current.lastLabelsAt = Date.now()
        const labels = await api.getLabels().catch(() => ({}) as Record<string, string>)
        for (const [id, key] of Object.entries(labels)) {
          const it = cur.current.byId.get(+id)
          if (it && !player.has(it.id)) {
            it.cat = key
            player.enqueue(it)
          }
        }
      }
    } catch {
      /* the library or the labels are not there yet; the next tick tries again */
    } finally {
      polling.current = false
    }
  }
  useEffect(() => {
    if (!finishing || opts.demo || !job.running) return
    void pollRun()
    const t = setInterval(() => void pollRun(), 900)
    return () => clearInterval(t)
  }, [finishing, job.running, job.phase])

  // The sort has ended: take the final labels (hand moves included), let everything still waiting fly, then celebrate.
  useEffect(() => {
    if (!(rmode === "done" && finishing)) return
    const gen = runGen.current
    void (async () => {
      try {
        await ensureLibrary()
        await ensureDupes()
        const final = await loadLabelsFile()
        if (gen !== runGen.current) return
        for (const it of cur.current.items) {
          if (final[it.id]) it.cat = final[it.id]
          player.enqueue(it)
        }
        player.finish()
      } catch (e) {
        showToast(messageOf(e))
        setFinishing(false)
      }
    })()
  }, [rmode, finishing])

  // A sort that stopped or failed: the run card shows what happened (the reference's "Sorting stopped" toast).
  useEffect(() => {
    if (!finishing || rmode !== "running" || job.running || (job.code ?? 0) === 0) return
    player.stop()
    setFinishing(false)
    showToast("Sorting stopped. See the details in the panel.")
  }, [finishing, rmode, job.running, job.code, player, showToast])

  // The size of the library for the estimates, until the library itself says.
  useEffect(() => {
    if (app && app.files && !runInfo.files) setRunInfo({ files: app.files, bytes: app.bytes })
  }, [app, runInfo.files])

  // ---- replay ------------------------------------------------------------------------------------------
  function replay() {
    if (!cur.current.items.length) return
    player.reset() // synchronously, so the first frame of the replay already shows empty cards
    setReplaying(true)
    setEpoch((e) => e + 1)
    setReplayAt((n) => n + 1)
  }
  useEffect(() => {
    if (replayAt) player.startReplay(replayMs()) // after the Stage has built its new sphere
  }, [replayAt, player])

  // Space replays a finished sort (app.js 729-732). The done panel listens for it itself, but it is not on screen
  // while a replay plays, and pressing Space again then starts over.
  useEffect(() => {
    if (!replaying) return
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as Element | null)?.matches?.("input, textarea, select") || document.querySelector('[role="dialog"]')) return
      if (e.code === "Space") {
        e.preventDefault()
        replay()
      }
    }
    addEventListener("keydown", onKey)
    return () => removeEventListener("keydown", onKey)
  }, [replaying])

  // ?auto: a finished dashboard replays by itself once it has been up for a moment.
  const autoFired = useRef(false)
  const autoReady = opts.auto && mode === "done" && !replaying && burst === 0 && items.length > 0
  useEffect(() => {
    if (!autoReady || autoFired.current) return
    const t = setTimeout(() => {
      autoFired.current = true
      replay()
    }, 1200)
    return () => clearTimeout(t)
  }, [autoReady])

  // ---- choosing folders --------------------------------------------------------------------------------
  const peekSeq = useRef(0)
  /** The reference's choose(). A source is looked at first: its answer is what the setup card and the sphere show.
   * Resolves to the folder that was accepted, or null. */
  async function choose(key: "source" | "dest", path: string | null): Promise<string | null> {
    if (!path) {
      if (key === "source") peekSeq.current++
      setPick((p) => (key === "source" ? NO_PICK : { ...p, dest: null })) // new photos drop the destination with them
      return null
    }
    if (key === "dest") {
      setPick((p) => ({ ...p, dest: path }))
      return path
    }
    const seq = ++peekSeq.current
    setPick({ source: path, dest: null, peek: null })
    try {
      const r = await api.peek(path)
      if (seq !== peekSeq.current) return null
      if (!r.photos && !r.videos) {
        showToast("No photos or videos in that folder.")
        setPick(NO_PICK)
        return null
      }
      setPick({ source: r.source, dest: null, peek: r })
      return r.source
    } catch (e) {
      if (seq !== peekSeq.current) return null
      showToast(messageOf(e))
      setPick(NO_PICK)
      return null
    }
  }
  async function pickFolder(key: "source" | "dest") {
    try {
      const r = await api.pick(PROMPT[key])
      if (r.path) await choose(key, r.path)
      else if (r.reason) showToast(r.reason)
    } catch (e) {
      showToast(messageOf(e))
    }
  }

  // ?source= and ?dest= fill both folders in, ready to press Start. Not in demo mode, and not over a sort in progress.
  const urlApplied = useRef(false)
  useEffect(() => {
    if (opts.demo || !opts.source || urlApplied.current || rmode === "loading" || !app) return
    urlApplied.current = true
    if (rmode === "running") return
    void (async () => {
      if (rmode === "done") newSort()
      const source = await choose("source", opts.source)
      if (source) await choose("dest", opts.dest || `${source} (sorted)`)
    })()
  }, [rmode, app])

  // ---- starting, stopping, starting over ---------------------------------------------------------------
  const confirmPaid = (files: number) => new Promise<boolean>((resolve) => setPaid({ files, resolve }))
  async function startSorting() {
    if (!app || !pick.source || !pick.dest) return
    const files = pick.peek ? pick.peek.photos + pick.peek.videos : 0
    if (labeler === "jev") {
      if (!app.jev_key) return showToast("Add JEV_KEY=your-key to a .env file in this folder to use Jev.")
      if (!(await confirmPaid(Math.min(files, sample ? 200 : files)))) return // a paid run waits for a yes (app.js 479-482)
    }
    if (labeler === "claude" && app.claude_cli === false)
      return showToast("Claude Code isn't installed on this computer. Install it, or pick Jev under Advanced.")
    try {
      const next = await api.sort({ source: pick.source, dest: pick.dest, labeler, limit: sample ? 200 : 0 })
      setRunInfo({
        files: sample ? Math.min(200, files) : files,
        bytes: pick.peek ? pick.peek.bytes * (sample ? Math.min(1, 200 / Math.max(1, files)) : 1) : 0,
      })
      dispatch({ type: "state", state: next })
    } catch (e) {
      showToast(messageOf(e))
    }
  }
  /** The top-bar button: asks for whatever is missing, then starts. After sorting it replays. */
  function sortWithClaude() {
    if (mode === "running" || mode === "loading") return
    if (mode === "done") return replay()
    if (!pick.source || !pick.dest) {
      if (app?.picker_available) return void pickFolder(pick.source ? "dest" : "source")
      return setupRef.current?.querySelector<HTMLElement>("input, button")?.focus() // the card's own path box
    }
    void startSorting()
  }
  function newSort() {
    runGen.current++
    lib.current = freshLib()
    player.load([])
    setLibrary([])
    setRunInfo({ files: 0, bytes: 0 })
    setPick(NO_PICK)
    peekSeq.current++
    setFinishing(false)
    setReplaying(false)
    setBurst(0)
    setEpoch((e) => e + 1)
    dispatch({ type: "reset" })
  }
  /** "Try again" and "Start again": the same folders, or, with none chosen in this page, back to the setup card. */
  function retry() {
    if (pick.source && pick.dest) void startSorting()
    else newSort()
  }

  // ---- dialogs -----------------------------------------------------------------------------------------
  /** The whole inventory, once, the first time a folder is opened (spec 13.2): never at page load. */
  function ensureInventory() {
    inventory.current ??= loadLibrary().then(
      (list) => new Map(list.map((r) => [r.id, r])),
      (e) => {
        inventory.current = null
        throw e
      },
    )
    return inventory.current
  }
  async function openFolder(c: FolderCategory) {
    if (mode === "setup" || mode === "loading") return // the cards are inert while choosing folders (app.js 120)
    try {
      const full = await ensureInventory()
      // A snapshot, as the reference's `all`: a move must not shrink the list under an open lightbox.
      const list = cur.current.items.flatMap((it) => {
        const r = inFolder(it, c.key) ? full.get(it.id) : undefined
        return r ? [{ ...r, cat: it.cat, dupe: it.dupe }] : []
      })
      setDialog({ kind: "browse", folder: c, items: list })
    } catch (e) {
      showToast(messageOf(e))
    }
  }
  function moved(item: LibraryItem, key: string) {
    const it = cur.current.byId.get(item.id)
    if (it) {
      it.cat = key
      it.dupe = false
    }
    if (cur.current.mode === "done" && !cur.current.replaying) player.fillStatic()
  }
  const openSorted = () => void api.open({ folder: "" }).catch((e) => showToast(messageOf(e)))

  // ---- what the page shows -----------------------------------------------------------------------------
  const L = player.landings
  const estimates = useMemo(
    () => ({ ...phaseEstimates(runInfo.files, runInfo.bytes, (job.phases ?? []).includes("scan")) }),
    [runInfo, job.phases],
  )
  const totalBytes = useMemo(() => items.reduce((s, r) => s + r.bytes, 0), [items])
  const previews = useMemo(() => {
    const names: unknown = pick.source && pick.peek ? pick.peek.previews : null
    return Array.isArray(names) ? (names as string[]).map((n) => ({ mini: previewUrl(n) })) : NO_STAGE
  }, [pick.source, pick.peek])
  const minis = useMemo(() => items.map((it) => ({ mini: miniOf(it) })), [items])
  // Identity-stable across SSE events: it changes with the library and the folder chosen, never with the job.
  const stageItems = useMemo(
    () => (mode === "setup" ? previews : mode === "running" ? (items.length ? minis : previews) : replaying ? minis : NO_STAGE),
    [mode, replaying, previews, minis, items.length],
  )

  const card = (c: FolderCategory): BoardCard => ({
    category: c,
    count: L.count(c.key),
    slots: L.recent(c.key, c.key === REVIEW_KEY ? 24 : 12).map(miniOf),
  })
  const folders = (kind: string) =>
    categories.filter((c) => c.kind === kind).map((c) => card({ key: c.key, label: c.label, emoji: c.emoji }))

  const scanning = mode === "running" && job.phase === "scan"
  const progress = mode === "running" ? overallProgress(job, estimates) * 100 : items.length ? (L.landed / items.length) * 100 : 0
  const source = mode === "setup" ? pick.source : app?.source
  const sourceText = source ? tilde(source) + (app?.limit && mode !== "setup" ? ` · sample of ${fmt(app.limit)}` : "") : ""

  const pill = ((): Pill => {
    const demo = opts.demo ? " · demo" : ""
    if (mode === "loading") return { kind: null, text: `Loading${demo}` }
    if (mode === "setup") return { kind: null, text: `Choose your photos${demo}` }
    if (mode === "running") {
      if (job.running || finishing) return { kind: "busy", text: `${NAMES[job.phase ?? ""] || "Working"}${demo}` }
      return { kind: null, text: `Stopped${demo}` }
    }
    return replaying ? { kind: "busy", text: `Claude is looking at every photo & video${demo}` } : { kind: "live", text: `Sorted${demo}` }
  })()

  return (
    <>
      {!opts.demo && <JobEvents onEvent={(e) => dispatch({ type: "event", event: e, now: Date.now() / 1000 })} />}
      <Topbar mode={mode} pill={pill} onNewSort={newSort} onSortWithClaude={sortWithClaude} />
      <main className={styles.app}>
        <TitleRow
          total={items.length}
          source={sourceText}
          showTotal={items.length > 0 && mode !== "setup"}
          onEditFolders={() => app && setDialog({ kind: "folders" })}
          onOpenSorted={openSorted}
          canOpenSorted={mode === "done" && Boolean(app?.sorted)}
        />
        <KpiRow
          checked={scanning ? job.done : Math.max(L.released, mode === "running" ? Math.max(runInfo.files, app?.files ?? 0) : 0)}
          photos={L.photos}
          videos={L.videos}
          foldersMade={L.made(categories.map((c) => c.key))}
          foldersTotal={categories.length}
          dupes={L.dupes}
          saved={L.saved}
          progress={progress}
          totalBytes={items.length && mode !== "setup" ? totalBytes : undefined}
        />
        <Board
          ref={boardRef}
          photoCats={folders("photo")}
          videoCats={[...folders("video"), card(REVIEW)]}
          onOpen={(c) => (mode === "setup" ? undefined : void openFolder(c))}
          live={mode === "running" || replaying}
        >
          <div ref={stageRef} className={styles.fill}>
            {mode === "setup" && app && (
              <div ref={setupRef} className={styles.setupHost}>
                <SetupCard
                  state={{ ...app, categories }}
                  pick={pick}
                  onChoose={(key, path) => void choose(key, path)}
                  labeler={labeler}
                  sample={sample}
                  onLabeler={setLabeler}
                  onSample={setSample}
                  onCategoriesSaved={setSavedCats}
                  onStart={() => void startSorting()}
                />
              </div>
            )}
            {mode === "running" && (
              <RunCard
                job={job}
                estimates={estimates}
                onRetry={retry}
                onCancel={() => void api.cancel().catch((e) => showToast(messageOf(e)))}
              />
            )}
            {mode === "done" && !replaying && (items.length > 0 || burst > 0) && (
              <DonePanel
                key={burst}
                total={items.length}
                folders={categories.length}
                dupes={L.dupes}
                saved={L.saved}
                onReplay={replay}
                live={burst > 0}
              />
            )}
          </div>
        </Board>
      </main>

      <Stage key={epoch} mode={mode} items={stageItems} onSphere={onSphere} />
      <div ref={layerRef} className={layers.fly} />
      <Toast text={toast.text} on={toast.on} />

      {/* The dialogs sit at the root, outside <main> and the board: Dialog is position: fixed, and a transformed or
          overflowing ancestor would trap it (and, for the lightbox, its own entrance animation). */}
      {dialog?.kind === "folders" && (
        <FoldersDialog
          categories={categories}
          onSaved={(cats) => {
            setSavedCats(cats) // a plain setter: the setup card's catch must never see a failure from here
            setDialog(null) // saving stays true until the parent closes the dialog
            if (mode === "done") showToast("Saved. Press New sort and sort again so files can use the new folders.")
          }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "browse" && (
        <BrowseDialog
          folder={dialog.folder}
          items={dialog.items}
          categories={categories}
          fileManager={app?.file_manager ?? "file manager"}
          sorted={Boolean(app?.sorted) && !opts.demo}
          onMoved={moved}
          onClose={() => setDialog(null)}
        />
      )}
      {paid && (
        <PaidConfirm
          files={paid.files}
          onResolve={(spend) => {
            paid.resolve(spend)
            setPaid(null)
          }}
        />
      )}
    </>
  )
}

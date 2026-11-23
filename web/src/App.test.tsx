import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { App } from "./App"
import { stopLoop } from "./anim/loop"
import { DEMO_NOTICE, DEMO_SOURCE } from "./demo"

// The assembly: each test mounts the real App against a fake server, because what can go wrong here is a component
// that was never rendered or a prop that was never passed, and only a whole page shows that.

const cats = [
  { key: "beach", kind: "photo", label: "Beach", emoji: "🏖️", rule: "the beach" },
  { key: "other-photos", kind: "photo", label: "Other photos", emoji: "📷", rule: "the rest" },
  { key: "clips", kind: "video", label: "Clips", emoji: "🎬", rule: "videos" },
]
// ids 0 and 1 are beach photos, 1 is also a duplicate, 2 is a clip: 54 MB in all
const slim = [
  { id: 0, kind: "photo", bytes: 2_000_000 },
  { id: 1, kind: "photo", bytes: 2_000_000 },
  { id: 2, kind: "video", bytes: 50_000_000 },
]
const labels = { "0": "beach", "1": "beach", "2": "clips" }
const dupes = [{ keep: 0, dupes: [1] }]
const inventory = slim.map((r) => ({
  ...r, path: `/p/${r.id}.jpg`, name: `IMG_${r.id}.jpg`, ext: ".jpg", sha256: `sha${r.id}`, w: 1, h: 1, duration: 0,
})) // fmt: skip

const job = (over = {}) => ({
  step: null, running: false, code: null, phase: null, phases: [], done: 0, total: 0,
  started: null, phase_started: null, timings: {}, log: [], ...over,
}) // fmt: skip
const appState = (over = {}) => ({
  categories: cats, source: null, limit: null, sorted: null, files: 0, bytes: 0,
  steps: { scan: false, dupes: false, label: false, jev_labels: false, apply: false },
  jev_key: false, claude_cli: true, overrides: 0, job: job(), platform: "win32",
  file_manager: "File Explorer", picker_available: false, picker_reason: "", ...over,
}) // fmt: skip
const peekOf = (b: { source: string }) => ({
  source: b.source, photos: 5, videos: 0, bytes: 5_000_000, previews: ["0000.jpg"],
  suggested_dest: `${b.source} (sorted)`, preview_bytes_needed: 90_000, free_bytes: 1e12,
}) // fmt: skip

const demoFiles = {
  "/demo/categories.json": cats,
  "/demo/slim.json": slim,
  "/demo/labels.json": labels,
  "/demo/dupes.json": dupes,
  "/demo/inventory.json": inventory,
}
const doneFiles = {
  "/api/state": appState({
    steps: { scan: true, dupes: true, label: true, jev_labels: false, apply: true },
    source: "/Users/me/Pics", limit: 200, sorted: "/Users/me/Pics (sorted)",
  }), // fmt: skip
  "/data/slim.json": slim,
  "/data/labels.json": labels,
  "/data/dupes.json": dupes,
  "/data/inventory.json": inventory,
  "/api/categories": { ok: true, count: 3 },
  "/api/open": { ok: true },
}

/** A fetch that answers from `routes` (by path, query ignored) and remembers every call. */
function serve(routes: Record<string, unknown>) {
  const calls: { url: string; method: string; body?: unknown }[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined
      calls.push({ url: String(input), method: init?.method ?? "GET", body })
      const route = routes[String(input).split("?")[0]]
      if (route === undefined) return new Response(JSON.stringify({ error: "not found" }), { status: 404 })
      return new Response(JSON.stringify(typeof route === "function" ? route(body) : route))
    }),
  )
  return calls
}
const to = <T extends { url: string }>(calls: T[], url: string) => calls.filter((c) => c.url === url)

/** Mounts the page at `/` + search, as if that address had been typed. */
function open(search: string) {
  history.replaceState(null, "", `/${search}`)
  return render(<App />)
}

beforeEach(() => {
  vi.stubGlobal("requestAnimationFrame", vi.fn(() => 1))
  vi.stubGlobal("cancelAnimationFrame", vi.fn())
  vi.stubGlobal("EventSource", class { close() {} })
  localStorage.clear()
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  history.replaceState(null, "", "/")
  delete document.body.dataset.mode
})

const PLAYING = "Claude is looking at every photo & video · demo"

describe("demo mode", () => {
  it("reads the demo library from demo/ instead of the api", async () => {
    const calls = serve(demoFiles)
    open("?demo")
    expect(await screen.findByRole("button", { name: "Beach folder, 1 file" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Duplicates folder, 1 file" })).toBeInTheDocument()
    expect(screen.getByText("Sorted · demo")).toBeInTheDocument()
    const urls = calls.map((c) => c.url)
    expect(urls).toContain("/demo/categories.json")
    expect(urls).toContain("/demo/slim.json")
    expect(urls.filter((u) => u.startsWith("/api/"))).toEqual([]) // no state, no stream: the demo needs no server
  })

  it("renders the title row and the total size, and offers no sorted folder to open", async () => {
    serve(demoFiles)
    open("?demo")
    expect(screen.getByRole("heading", { name: "Sorting my camera roll" })).toBeInTheDocument()
    expect(await screen.findByText("54 MB in total")).toBeInTheDocument() // KpiRow's totalBytes
    expect(screen.getByText(DEMO_SOURCE)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Open sorted folder/ })).not.toBeInTheDocument()
  })

  it("has one theme button, and the top bar stays mounted to keep body[data-mode]", async () => {
    serve(demoFiles)
    open("?demo")
    await screen.findByRole("button", { name: "Beach folder, 1 file" })
    expect(screen.getAllByRole("button", { name: /Switch to (dark|light) mode/ })).toHaveLength(1)
    expect(document.body.dataset.mode).toBe("done")
  })

  it("shows a photo's thumbnail in the lightbox, because the demo has no originals to open", async () => {
    serve(demoFiles)
    open("?demo")
    fireEvent.click(await screen.findByRole("button", { name: "Beach folder, 1 file" }))
    const browse = await screen.findByRole("dialog", { name: "Beach" })
    fireEvent.click(within(browse).getByRole("button", { name: "IMG_0.jpg" }))
    const lightbox = await screen.findByRole("dialog", { name: "IMG_0.jpg" })
    expect(within(lightbox).getByRole("img", { name: "IMG_0.jpg" })).toHaveAttribute("src", "/demo/thumbs/0.jpg")
    expect(within(lightbox).queryByRole("alert")).not.toBeInTheDocument() // not the demo notice
  })

  it("blocks api writes with an explanatory toast", async () => {
    const calls = serve(demoFiles)
    open("?demo")
    await screen.findByRole("button", { name: "Beach folder, 1 file" })
    fireEvent.click(screen.getByRole("button", { name: /Edit folders/ }))
    fireEvent.click(await screen.findByRole("button", { name: "Save folders" }))
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(DEMO_NOTICE))
    expect(screen.getByRole("alert")).toHaveTextContent(DEMO_NOTICE)
    expect(to(calls, "/api/categories")).toHaveLength(0) // the request never left the page
  })

  it("replays by itself with ?auto once the dashboard is done", async () => {
    serve(demoFiles)
    open("?demo&auto")
    await screen.findByRole("button", { name: "Beach folder, 1 file" })
    expect(screen.getByText("Sorted · demo")).toBeInTheDocument()
    expect(await screen.findByText(PLAYING, {}, { timeout: 4000 })).toBeInTheDocument() // after about 1.2 s
  })

  it("does not replay by itself without ?auto", async () => {
    serve(demoFiles)
    open("?demo")
    await screen.findByRole("button", { name: "Beach folder, 1 file" })
    await new Promise((r) => setTimeout(r, 1500))
    expect(screen.getByText("Sorted · demo")).toBeInTheDocument()
  })

  it("replays on Space but not while typing in a field", async () => {
    serve(demoFiles)
    open("?demo")
    await screen.findByRole("button", { name: "Beach folder, 1 file" })
    const field = document.createElement("input")
    document.body.append(field)

    fireEvent.keyDown(field, { code: "Space" })
    expect(screen.getByText("Sorted · demo")).toBeInTheDocument() // typing a space is not a replay

    fireEvent.keyDown(document.body, { code: "Space" })
    expect(await screen.findByText(PLAYING)).toBeInTheDocument()
    field.remove()
  })

  it("replays from the top-bar button", async () => {
    serve(demoFiles)
    open("?demo")
    await screen.findByRole("button", { name: "Beach folder, 1 file" })
    fireEvent.click(screen.getByRole("button", { name: /Sort with Claude/ }))
    expect(await screen.findByText(PLAYING)).toBeInTheDocument()
  })

  it("loads the full inventory once, on the first folder opened, and shows the dialog at the app root", async () => {
    const calls = serve(demoFiles)
    open("?demo")
    const card = await screen.findByRole("button", { name: "Beach folder, 1 file" })
    expect(to(calls, "/demo/inventory.json")).toHaveLength(0) // not at page load

    fireEvent.click(card)
    const dialog = await screen.findByRole("dialog", { name: "Beach" })
    expect(to(calls, "/demo/inventory.json")).toHaveLength(1)
    expect(dialog.closest("main")).toBeNull() // outside the page, so nothing transformed can trap it
    expect(within(dialog).getByRole("button", { name: "IMG_0.jpg" })).toBeInTheDocument()

    fireEvent.keyDown(document, { key: "Escape" })
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    fireEvent.click(card)
    await screen.findByRole("dialog", { name: "Beach" })
    expect(to(calls, "/demo/inventory.json")).toHaveLength(1) // once, however many times a folder is opened
  })
})

describe("a sort that is already done", () => {
  it("shows the source with its sample size, the title row, and a button for the sorted folder", async () => {
    const calls = serve(doneFiles)
    open("")
    expect(await screen.findByText("~/Pics · sample of 200")).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Sorting my camera roll" })).toBeInTheDocument()
    const openSorted = await screen.findByRole("button", { name: /Open sorted folder/ })
    expect(await screen.findByText("54 MB in total")).toBeInTheDocument()
    expect(to(calls, "/data/inventory.json")).toHaveLength(0) // the slim index is what the board reads

    fireEvent.click(openSorted)
    await waitFor(() => expect(to(calls, "/api/open")).toHaveLength(1))
    expect(to(calls, "/api/open")[0].body).toEqual({ folder: "" }) // "" is the sorted folder itself
  })

  it("offers no sorted folder when none has been written", async () => {
    serve({ ...doneFiles, "/api/state": appState({ steps: { scan: true, dupes: true, label: true, jev_labels: false, apply: true } }) })
    open("")
    await screen.findByRole("button", { name: "Beach folder, 1 file" })
    expect(screen.queryByRole("button", { name: /Open sorted folder/ })).not.toBeInTheDocument()
  })

  it("closes the folders dialog after a save, and says to press New sort", async () => {
    const calls = serve(doneFiles)
    open("")
    await screen.findByRole("button", { name: /Open sorted folder/ })
    fireEvent.click(screen.getByRole("button", { name: /Edit folders/ }))
    fireEvent.click(await screen.findByRole("button", { name: "Save folders" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(screen.getByRole("status")).toHaveTextContent(/Saved\. Press New sort and sort again/)
    expect(to(calls, "/api/categories")).toHaveLength(1)
  })

  it("keeps a folder's list as it was opened when a photo is moved out, and asks for the file with its sha", async () => {
    serve({ ...doneFiles, "/api/record/0": inventory[0], "/api/move": { ok: true } })
    open("")
    fireEvent.click(await screen.findByRole("button", { name: "Beach folder, 1 file" }))
    const browse = await screen.findByRole("dialog", { name: "Beach" })
    expect(within(browse).getByText("1")).toBeInTheDocument()

    fireEvent.click(within(browse).getByRole("button", { name: "IMG_0.jpg" }))
    const select = await screen.findByRole("combobox", { name: "Move to folder" })
    await waitFor(() => expect(document.querySelector("img[src^='/api/file/']")).not.toBeNull())
    expect(document.querySelector("img[src^='/api/file/']")?.getAttribute("src")).toBe("/api/file/0?sha=sha0")

    fireEvent.change(select, { target: { value: "other-photos" } })
    expect(await screen.findByText(/Moved to Other photos/)).toBeInTheDocument()
    // the board follows the move ...
    expect(await screen.findByRole("button", { name: "Beach folder, 0 files" })).toBeInTheDocument()
    // ... but the open list does not shrink under the lightbox
    expect(within(browse).getByText("1")).toBeInTheDocument()
  })
})

describe("choosing folders", () => {
  it("leaves the folder cards inert while the setup card is up", async () => {
    const calls = serve({ "/api/state": appState(), "/data/inventory.json": inventory })
    open("")
    await screen.findByRole("heading", { name: "Choose your photos" })
    expect(document.body.dataset.mode).toBe("setup")
    fireEvent.click(screen.getByRole("button", { name: /Beach folder/ }))
    await new Promise((r) => setTimeout(r, 30))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(to(calls, "/data/inventory.json")).toHaveLength(0)
  })

  it("prefills both folders from ?source= and ?dest=", async () => {
    const calls = serve({ "/api/state": appState(), "/api/peek": peekOf })
    open("?source=%2FUsers%2Fme%2FPics&dest=%2FUsers%2Fme%2Fout")
    expect(await screen.findByTitle("/Users/me/Pics")).toBeInTheDocument()
    expect(await screen.findByTitle("/Users/me/out")).toBeInTheDocument()
    expect(to(calls, "/api/peek").map((c) => c.body)).toEqual([{ source: "/Users/me/Pics" }])
    expect(to(calls, "/api/sort")).toHaveLength(0) // ready to press Start, not started
  })

  it("chooses the folder next to the photos when ?dest= is left out", async () => {
    serve({ "/api/state": appState(), "/api/peek": peekOf })
    open("?source=%2FUsers%2Fme%2FPics")
    expect(await screen.findByTitle("/Users/me/Pics (sorted)")).toBeInTheDocument()
  })

  it("starts over from the setup card when a done dashboard is opened with ?source=", async () => {
    serve({ ...doneFiles, "/api/peek": peekOf })
    open("?source=%2FUsers%2Fme%2FPhotos")
    expect(await screen.findByTitle("/Users/me/Photos")).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Photos" })).toBeInTheDocument()
  })
})

describe("starting a sort", () => {
  const running = appState({
    jev_key: true,
    job: job({ step: "sort", running: true, phase: "scan", phases: ["scan", "dupes", "label", "apply"], started: 1000, phase_started: 1000 }),
  }) // fmt: skip

  it("asks before a paid Jev run, and starts nothing if the answer is no", async () => {
    const calls = serve({ "/api/state": appState({ jev_key: true }), "/api/peek": peekOf, "/api/sort": running })
    open("?source=%2FUsers%2Fme%2FPics&dest=%2FUsers%2Fme%2Fout")
    await screen.findByTitle("/Users/me/out")
    fireEvent.click(screen.getByRole("button", { name: /Advanced/ }))
    fireEvent.click(screen.getByLabelText(/Jev by TypeSafe/))
    const start = () => fireEvent.click(screen.getByRole("button", { name: /Start sorting/ }))

    start()
    const confirm = await screen.findByRole("dialog", { name: "Label with Jev" })
    expect(within(confirm).getByText("5 files, about 4,900 tokens")).toBeInTheDocument()
    expect(to(calls, "/api/sort")).toHaveLength(0) // nothing is spent before the yes

    fireEvent.click(within(confirm).getByRole("button", { name: "Close" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    await new Promise((r) => setTimeout(r, 30))
    expect(to(calls, "/api/sort")).toHaveLength(0) // a no is a no

    start()
    fireEvent.click(await screen.findByRole("button", { name: "Spend tokens" }))
    await waitFor(() => expect(to(calls, "/api/sort")).toHaveLength(1))
    expect(to(calls, "/api/sort")[0].body).toEqual({ source: "/Users/me/Pics", dest: "/Users/me/out", labeler: "jev", limit: 0 })
  })

  it("starts a Claude run without asking, and shows the run card", async () => {
    const calls = serve({ "/api/state": appState(), "/api/peek": peekOf, "/api/sort": { ...running, jev_key: false } })
    open("?source=%2FUsers%2Fme%2FPics&dest=%2FUsers%2Fme%2Fout")
    await screen.findByTitle("/Users/me/out")
    fireEvent.click(screen.getByRole("button", { name: /Start sorting/ }))
    expect(await screen.findByRole("button", { name: "Stop sorting" })).toBeInTheDocument()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(to(calls, "/api/sort")[0].body).toMatchObject({ labeler: "claude" })
    expect(document.body.dataset.mode).toBe("running")
  })
})


// ---- a live sort -----------------------------------------------------------------------------------------------------
// The path the rAF stub keeps dark everywhere above: the library swap, the flights, the finish, the live done panel, and
// the state the server writes late (source.json when the scan ends, `sorted` when the apply ends). Here the event stream
// and the frame loop are both driven by hand, and the fake server answers each phase with what the real one would have
// written by then. The page only offers the "claude" and "jev" labellers (the server's "stub" is not a choice on it), and
// this fake server labels nothing itself, so the run needs neither.

/** The one EventSource the page opens. */
class Stream {
  static last: Stream | null = null
  onmessage: ((m: { data: string }) => void) | null = null
  constructor(readonly url: string) {
    Stream.last = this
  }
  close() {}
}
const emit = async (e: object) => {
  await act(async () => {
    Stream.last!.onmessage!({ data: JSON.stringify(e) })
  })
}
/** Lets what React scheduled after a render (the effects of an answer that arrived outside act) run. */
const settle = () => act(() => new Promise<void>((r) => setTimeout(r, 30)))
let queued: FrameRequestCallback[] = []
/** One animation frame, taken far enough on that a count-up has finished. */
const frame = () =>
  act(() => {
    const run = queued
    queued = []
    for (const fn of run) fn(performance.now() + 10_000)
  })
/** Steps frames until `check` stops throwing: a flight, a landing and the release of the next file each take one. */
const frames = (check: () => void) =>
  waitFor(() => {
    frame()
    check()
  })

const SRC = "/Users/me/Pics"
const PREFILL = "?source=%2FUsers%2Fme%2FPics&dest=%2FUsers%2Fme%2Fout"
const sortJob = (over = {}) =>
  job({ step: "sort", running: true, phase: "scan", phases: ["scan", "dupes", "label", "apply"], started: 1000, phase_started: 1000, ...over })
const ALL = { scan: true, dupes: true, label: true, jev_labels: false, apply: true }
const inventory2 = inventory.map((r) => ({ ...r, name: `RUN2_${r.id}.jpg` })) // the second sort's library names its files differently

/** The server as a sort moves through it. `/api/sort` answers before the scan has written anything. */
function liveServer() {
  const srv = { state: appState() as unknown, sort: appState({ job: sortJob() }) as unknown, inventory: inventory as unknown }
  const routes: Record<string, unknown> = {
    "/api/state": () => srv.state,
    "/api/sort": () => srv.sort,
    "/api/peek": peekOf,
    "/api/labels": { "0": "beach" },
  }
  const calls = serve(routes)
  return {
    calls,
    srv,
    /** The scan has ended: its files are on disk, and /api/state knows the source. */
    scanned(state: unknown) {
      routes["/data/slim.json"] = slim
      routes["/data/dupes.json"] = dupes
      routes["/data/inventory.json"] = () => srv.inventory
      srv.state = state
    },
    /** The apply has ended: the final labels are on disk, and /api/state knows the sorted folder. */
    applied(state: unknown) {
      routes["/data/labels.json"] = labels
      srv.state = state
    },
  }
}
type Live = ReturnType<typeof liveServer>

/** Through the scan and into labelling, until file 0 has landed in Beach. `seen` is what the title row shows once
 * the state has been taken again. */
async function labelled(live: Live, started: number, seen: string, over = {}) {
  live.scanned(appState({ source: SRC, files: 3, bytes: 54_000_000, job: sortJob({ started, phase: "dupes" }), ...over }))
  await emit({ type: "phase_started", phase: "dupes" })
  await screen.findByText(seen)
  await emit({ type: "phase_started", phase: "label" })
  await frames(() => expect(screen.getByRole("button", { name: "Beach folder, 1 file" })).toBeInTheDocument())
}
/** The sort ends, and every file still waiting flies; the dashboard is done once its last one has landed. */
async function ended(live: Live, started: number) {
  live.applied(appState({ source: SRC, files: 3, bytes: 54_000_000, sorted: "/Users/me/out", steps: ALL, job: sortJob({ started, running: false, code: 0, phase: "apply" }) }))
  await emit({ type: "job_finished", step: "sort", code: 0 })
  await frames(() => expect(screen.getByText(/with one prompt/)).toBeInTheDocument())
}

describe("a live sort", () => {
  beforeEach(() => {
    queued = []
    Stream.last = null
    vi.stubGlobal("requestAnimationFrame", (fn: FrameRequestCallback) => queued.push(fn))
    vi.stubGlobal("EventSource", Stream)
    // reduced motion: a flight lands where it starts, so one frame is all a file needs, and no confetti is drawn
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("reduce"), media: q }))
    stopLoop() // an earlier test's stub left the loop believing a frame is already on its way
  })

  it("takes the state again when the scan ends and when the sort ends, and keeps folders shut until the scan is over", async () => {
    const live = liveServer()
    open(PREFILL)
    await screen.findByTitle("/Users/me/out")
    fireEvent.click(screen.getByRole("button", { name: /Start sorting/ }))
    await screen.findByRole("button", { name: "Stop sorting" })
    // /api/sort answered before the scan wrote source.json, so the title row has no source yet
    expect(screen.queryByText("~/Pics")).not.toBeInTheDocument()

    // a folder opened now has no inventory to show; reading it would cache an empty one for the whole page
    await settle()
    fireEvent.click(screen.getByRole("button", { name: /Beach folder/ }))
    await settle()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(to(live.calls, "/data/inventory.json")).toHaveLength(0)
    expect(to(live.calls, "/api/state")).toHaveLength(1)

    await labelled(live, 1000, "~/Pics") // the title row learns the source from the state asked for when the scan ended
    expect(to(live.calls, "/api/state")).toHaveLength(2)

    await ended(live, 1000)
    expect(await screen.findByRole("button", { name: /Open sorted folder/ })).toBeInTheDocument() // `sorted` came with the last refresh
    expect(to(live.calls, "/api/state")).toHaveLength(3)
    expect(screen.getByText("Sorted")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Duplicates folder, 1 file" })).toBeInTheDocument() // every file landed
    expect(screen.getByRole("button", { name: "Clips folder, 1 file" })).toBeInTheDocument()
  })

  it("reads each sort's own inventory, not the one cached for the sort before it", async () => {
    const live = liveServer()
    open(PREFILL)
    await screen.findByTitle("/Users/me/out")
    fireEvent.click(screen.getByRole("button", { name: /Start sorting/ }))
    await screen.findByRole("button", { name: "Stop sorting" })
    await labelled(live, 1000, "~/Pics")
    await ended(live, 1000)

    fireEvent.click(await screen.findByRole("button", { name: "Beach folder, 1 file" }))
    const first = await screen.findByRole("dialog", { name: "Beach" })
    expect(within(first).getByRole("button", { name: "IMG_0.jpg" })).toBeInTheDocument()
    expect(to(live.calls, "/data/inventory.json")).toHaveLength(1)
    fireEvent.keyDown(document, { key: "Escape" })
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())

    // New sort, the same photos again, and a library that now names its files differently
    fireEvent.click(screen.getByRole("button", { name: /New sort/ }))
    fireEvent.click(await screen.findByRole("button", { name: /Last time/ }))
    fireEvent.click(await screen.findByRole("button", { name: /Next to my photos/ }))
    live.srv.inventory = inventory2
    live.srv.sort = appState({ source: SRC, job: sortJob({ started: 2000, phase_started: 2000 }) })
    fireEvent.click(await screen.findByRole("button", { name: /Start sorting/ }))
    await screen.findByRole("button", { name: "Stop sorting" })
    await labelled(live, 2000, "~/Pics · sample of 100", { limit: 100 })

    fireEvent.click(screen.getByRole("button", { name: "Beach folder, 1 file" }))
    const second = await screen.findByRole("dialog", { name: "Beach" })
    expect(within(second).getByRole("button", { name: "RUN2_0.jpg" })).toBeInTheDocument()
    expect(within(second).queryByRole("button", { name: "IMG_0.jpg" })).toBeNull()
    expect(to(live.calls, "/data/inventory.json")).toHaveLength(2)
  })
})

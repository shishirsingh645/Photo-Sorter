import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { App } from "./App"
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

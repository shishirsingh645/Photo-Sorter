import { afterEach, describe, expect, it, vi } from "vitest"
import { DEMO_NOTICE, DEMO_SOURCE, installDemoGuard, loadDemoState, readParams, replayMs } from "./demo"
import { initialState, reducer } from "./state/reducer"
import { loadSlim, setLibraryBase, thumbOf } from "./state/library"

const cats = [
  { key: "beach", kind: "photo", label: "Beach", emoji: "🏖️", rule: "the beach" },
  { key: "clips", kind: "video", label: "Clips", emoji: "🎬", rule: "videos" },
]

/** A fetch that answers from `files` and remembers what it was asked for. */
function serve(files: Record<string, unknown>) {
  const fetch = vi.fn(async (url: string) =>
    url in files ? new Response(JSON.stringify(files[url])) : new Response("not found", { status: 404 }),
  )
  vi.stubGlobal("fetch", fetch)
  return fetch
}

afterEach(() => {
  setLibraryBase("/data")
  vi.unstubAllGlobals()
})

describe("replayMs", () => {
  it("uses ?d=20 as the replay length", () => {
    expect(replayMs("?demo&d=20")).toBe(20000)
  })

  it("defaults the replay to 12 seconds", () => {
    expect(replayMs("")).toBe(12000)
    expect(replayMs("?demo")).toBe(12000)
  })

  it("reads it the reference's way: anything that is not a positive number is the default", () => {
    expect(replayMs("?d=abc")).toBe(12000)
    expect(replayMs("?d=0")).toBe(12000)
    expect(replayMs("?d=2.5")).toBe(2500)
  })

  it("reads the live address when called with no argument", () => {
    history.replaceState(null, "", "/?d=7")
    expect(replayMs()).toBe(7000)
    history.replaceState(null, "", "/")
  })
})

describe("readParams", () => {
  it("reads ?demo and ?auto as flags and ?source= and ?dest= as paths", () => {
    expect(readParams("?demo&auto")).toEqual({ demo: true, auto: true, source: null, dest: null })
    expect(readParams("?source=D%3A%5CPics&dest=D%3A%5COut")).toEqual({
      demo: false,
      auto: false,
      source: "D:\\Pics",
      dest: "D:\\Out",
    })
    expect(readParams("")).toEqual({ demo: false, auto: false, source: null, dest: null })
  })
})

describe("demo mode reads the demo folder, not the api", () => {
  it("loads the folders and the library from /demo and asks the server for nothing", async () => {
    setLibraryBase("/demo")
    const fetch = serve({
      "/demo/categories.json": cats,
      "/demo/slim.json": [
        { id: 0, kind: "photo", bytes: 1 },
        { id: 1, kind: "video", bytes: 2 },
      ],
      "/demo/labels.json": { "0": "beach", "1": "clips" },
      "/demo/dupes.json": [],
    })

    const state = await loadDemoState()
    const items = await loadSlim(true)

    expect(items.map((i) => [i.id, i.cat])).toEqual([
      [0, "beach"],
      [1, "clips"],
    ])
    expect(thumbOf({ id: 4 })).toBe("/demo/thumbs/4.jpg")
    const asked = fetch.mock.calls.map((c) => c[0])
    expect(asked.length).toBeGreaterThan(0)
    expect(asked.every((u) => u.startsWith("/demo/"))).toBe(true)
    expect(asked.some((u) => u.startsWith("/api/"))).toBe(false)

    // everything has been sorted, so the page opens on the finished result, with nothing to open in a file manager
    expect(state.source).toBe(DEMO_SOURCE)
    expect(state.sorted).toBeNull()
    expect(reducer(initialState, { type: "state", state }).mode).toBe("done")
  })

  it("says so, in plain words, when the demo has not been built", async () => {
    setLibraryBase("/demo")
    serve({})
    await expect(loadDemoState()).rejects.toThrow(/photo-sorter demo/)
  })
})

describe("installDemoGuard", () => {
  it("refuses an api write with an explanatory toast, and answers in the server's own error shape", async () => {
    const real = vi.fn(async () => new Response("{}"))
    vi.stubGlobal("fetch", real)
    const toast = vi.fn()
    const undo = installDemoGuard(toast)

    const res = await fetch("/api/move", { method: "POST", body: "{}" })

    expect(toast).toHaveBeenCalledExactlyOnceWith(DEMO_NOTICE)
    expect(res.status).toBe(400)
    expect(await res.json()).toEqual({ error: DEMO_NOTICE })
    expect(real).not.toHaveBeenCalled() // nothing reached the server
    undo()
  })

  it("refuses an api read too, but without a toast, and lets the demo's own files through", async () => {
    const real = vi.fn(async () => new Response("[]"))
    vi.stubGlobal("fetch", real)
    const toast = vi.fn()
    const undo = installDemoGuard(toast)

    expect((await fetch("/api/record/3?sha=x")).status).toBe(400)
    expect(toast).not.toHaveBeenCalled()
    expect(real).not.toHaveBeenCalled()

    expect((await fetch("/demo/slim.json")).status).toBe(200)
    expect(real).toHaveBeenCalledExactlyOnceWith("/demo/slim.json", undefined)
    undo()
  })

  it("puts the real fetch back when undone", async () => {
    const real = vi.fn(async () => new Response("{}"))
    vi.stubGlobal("fetch", real)
    installDemoGuard(vi.fn())()
    expect((await fetch("/api/state")).status).toBe(200)
    expect(real).toHaveBeenCalledTimes(1)
  })
})

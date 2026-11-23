import { afterEach, describe, expect, it, vi } from "vitest"
import { folderItems, inFolder, loadSlim, miniOf, setLibraryBase, thumbOf } from "./library"
import { loadLibrary } from "./library"

const rec = (id: number, kind = "photo") => ({
  id, path: `/p/${id}.jpg`, name: `${id}.jpg`, ext: ".jpg", kind, bytes: 1, sha256: `sha${id}`, w: 1, h: 1, duration: 0,
}) // fmt: skip

function serve(files: Record<string, unknown>) {
  const fetch = vi.fn(async (url: string) =>
    url in files ? new Response(JSON.stringify(files[url])) : new Response("not found", { status: 404 }),
  )
  vi.stubGlobal("fetch", fetch)
  return fetch
}

describe("loadLibrary", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("keeps each record's sha256 and adds its folder and whether it is a duplicate", async () => {
    const fetch = serve({
      "/data/inventory.json": [rec(0), rec(1), rec(2)],
      "/data/labels.json": { "0": "beach", "1": "beach" },
      "/data/dupes.json": [{ keep: 0, dupes: [1] }],
    })
    const items = await loadLibrary()
    expect(fetch.mock.calls.map((c) => c[0]).sort()).toEqual(["/data/dupes.json", "/data/inventory.json", "/data/labels.json"])
    expect(items.map((i) => [i.id, i.sha256, i.cat, i.dupe])).toEqual([
      [0, "sha0", "beach", false],
      [1, "sha1", "beach", true],
      [2, "sha2", undefined, false],
    ])
  })

  it("gives an empty library before the first scan, when the files are not there", async () => {
    serve({})
    expect(await loadLibrary()).toEqual([])
  })

  it("fails loudly, rather than reading as empty, when the inventory is damaged or the server errors", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (url.endsWith("inventory.json") ? new Response("{oops") : new Response("{}"))))
    await expect(loadLibrary()).rejects.toMatchObject({ name: "ApiError" })

    vi.stubGlobal("fetch", vi.fn(async (url: string) => (url.endsWith("inventory.json") ? new Response("{}") : new Response("[]"))))
    await expect(loadLibrary()).rejects.toThrow(/not a list/)

    vi.stubGlobal("fetch", vi.fn(async (url: string) => (url.endsWith("labels.json") ? new Response("boom", { status: 500 }) : new Response("[]"))))
    await expect(loadLibrary()).rejects.toMatchObject({ status: 500 })
  })

  it("rejects with the unreachable message when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")))
    await expect(loadLibrary()).rejects.toMatchObject({ status: 0 })
  })
})

describe("folderItems", () => {
  const items = [
    { ...rec(0), kind: "photo" as const, cat: "beach", dupe: false },
    { ...rec(1), kind: "photo" as const, cat: "beach", dupe: true },
    { ...rec(2), kind: "photo" as const, cat: "trips", dupe: false },
  ]
  it("lists a folder's own files, and every duplicate under the review folder", () => {
    expect(folderItems(items, "beach").map((i) => i.id)).toEqual([0])
    expect(folderItems(items, "_dupes").map((i) => i.id)).toEqual([1])
  })
})

describe("loadSlim", () => {
  afterEach(() => {
    setLibraryBase("/data")
    vi.unstubAllGlobals()
  })
  const slim = [
    { id: 0, kind: "photo", bytes: 5 },
    { id: 1, kind: "video", bytes: 9 },
  ]

  it("reads the slim index, never the full inventory, with each file's folder and duplicate flag", async () => {
    const fetch = serve({
      "/data/slim.json": slim,
      "/data/labels.json": { "0": "beach", "1": "clips" },
      "/data/dupes.json": [{ keep: 0, dupes: [1] }],
    })
    const items = await loadSlim(true)
    expect(fetch.mock.calls.map((c) => c[0]).sort()).toEqual(["/data/dupes.json", "/data/labels.json", "/data/slim.json"])
    expect(items).toEqual([
      { id: 0, kind: "photo", bytes: 5, cat: "beach", dupe: false },
      { id: 1, kind: "video", bytes: 9, cat: "clips", dupe: true },
    ])
  })

  it("leaves the folders out for a run in progress, whose labels.json is still the last run's", async () => {
    serve({ "/data/slim.json": slim, "/data/labels.json": { "0": "beach" } })
    expect((await loadSlim(false)).map((i) => i.cat)).toEqual([undefined, undefined])
  })

  it("follows the base, so ?demo reads /demo", async () => {
    setLibraryBase("/demo")
    const fetch = serve({ "/demo/slim.json": slim })
    await loadSlim(true)
    expect(fetch.mock.calls.every((c) => String(c[0]).startsWith("/demo/"))).toBe(true)
    expect(thumbOf({ id: 3 })).toBe("/demo/thumbs/3.jpg")
    expect(miniOf({ id: 3 })).toBe("/demo/mini/3.jpg")
  })

  it("refuses a slim index that is not a list", async () => {
    serve({ "/data/slim.json": {} })
    await expect(loadSlim(true)).rejects.toThrow(/not a list/)
  })
})

describe("inFolder", () => {
  it("is the one rule for what a folder holds: its own files, or every duplicate for review", () => {
    expect(inFolder({ cat: "beach", dupe: false }, "beach")).toBe(true)
    expect(inFolder({ cat: "beach", dupe: true }, "beach")).toBe(false)
    expect(inFolder({ cat: "beach", dupe: true }, "_dupes")).toBe(true)
    expect(inFolder({ cat: undefined, dupe: false }, "_dupes")).toBe(false)
  })
})

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { createSphere, releaseCount, type Sphere } from "./sphere"

const srcs = (n: number) => Array.from({ length: n }, (_, i) => `/api/mini/${i}.jpg`)

/** jsdom has no layout, so the host's box is stubbed; the maths under test is real. */
function host(w = 800, h = 600) {
  const el = document.createElement("div")
  el.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: w, height: h, right: w, bottom: h, x: 0, y: 0 }) as DOMRect
  document.body.append(el)
  return el
}

describe("createSphere", () => {
  let el: HTMLElement
  beforeEach(() => {
    document.body.replaceChildren()
    el = host()
  })

  it("caps the sphere at 320 tiles however many files there are", () => {
    expect(createSphere(el, srcs(100_000)).tiles.length).toBe(320)
    expect(el.querySelectorAll("img").length).toBe(320)
    expect(createSphere(el, srcs(12)).tiles.length).toBe(12)
  })

  it("distributes tiles on a unit sphere", () => {
    const sphere = createSphere(el, srcs(1_000))
    for (const t of sphere.tiles) expect(t.x ** 2 + t.y ** 2 + t.z ** 2).toBeCloseTo(1, 5)
    // tile 1 sits one golden angle round from tile 0, whose z is 0 - the unit-length check
    // above holds for any angle, so this is what pins pi(3 - sqrt 5)
    expect(Math.atan2(sphere.tiles[1].z, sphere.tiles[1].x)).toBeCloseTo(Math.PI * (3 - Math.sqrt(5)), 10)
    // the golden angle spreads them: no two tiles share a position
    expect(new Set(sphere.tiles.map(t => `${t.x},${t.y}`)).size).toBe(320)
  })

  it("shares tiles between files when there are more files than tiles", () => {
    const sphere = createSphere(el, srcs(640))
    const first = Array.from({ length: 320 }, (_, i) => sphere.tileFor(`f${i}`))
    expect(new Set(first).size).toBe(320)
    // the 321st file reuses the first tile, and keeps it on later asks
    expect(sphere.tileFor("f320")).toBe(first[0])
    expect(sphere.tileFor("f320")).toBe(first[0])
    expect(el.querySelectorAll("img").length).toBe(320)
  })

  it("retires a tile only once its last file has flown", () => {
    const sphere = createSphere(el, srcs(640))
    const tile = sphere.tileFor("f0")!
    // tiles are handed out in ask order, so the 321st distinct file is the one that reuses the first tile
    for (let i = 1; i < 320; i++) sphere.tileFor(`f${i}`)
    expect(sphere.tileFor("f320")).toBe(tile)
    expect(tile.left).toBe(2)

    sphere.retire(tile, "f0")
    expect(tile.alive).toBe(true)
    expect(tile.el.style.opacity).not.toBe("0")

    sphere.retire(tile, "f320")
    expect(tile.alive).toBe(false)
    expect(tile.el.style.opacity).toBe("0")
  })

  it("counts a file's retire once, however many times it is repeated", () => {
    const sphere = createSphere(el, srcs(640))
    const tile = sphere.tileFor("f0")!
    for (let i = 1; i < 320; i++) sphere.tileFor(`f${i}`)
    expect(sphere.tileFor("f320")).toBe(tile)

    sphere.retire(tile, "f0")
    sphere.retire(tile, "f0") // a duplicate must not eat f320's share
    expect(tile.left).toBe(1)
    expect(tile.alive).toBe(true)

    sphere.retire(tile, "f320")
    expect(tile.alive).toBe(false)
  })

  it("centres and sizes on the anchor box when one is given, not on the host", () => {
    // the host is 800x600; the anchor is a 200x400 column starting at x 300, y 100: centre (400, 300), R 0.36 * 200
    const stage = { left: 300, top: 100, width: 200, height: 400 } as DOMRect
    const sphere = createSphere(el, srcs(100), () => stage)
    sphere.draw(16)
    for (const t of sphere.tiles) {
      expect(Math.abs(t.sx - 400)).toBeLessThanOrEqual(72 + 1e-6)
      expect(Math.abs(t.sy - 300)).toBeLessThanOrEqual(72 + 1e-6)
    }
    const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length
    expect(Math.abs(mean(sphere.tiles.map(t => t.sx)) - 400)).toBeLessThan(8)
  })

  it("lifts and shrinks the anchored sphere while a sort runs, as the reference's geom() does", () => {
    el.dataset.mode = "running"
    const stage = { left: 300, top: 100, width: 200, height: 400 } as DOMRect
    const sphere = createSphere(el, srcs(100), () => stage)
    sphere.draw(16)
    for (const t of sphere.tiles) {
      expect(Math.abs(t.sx - 400)).toBeLessThanOrEqual(64 + 1e-6) // 0.32 * 200
      expect(Math.abs(t.sy - 268)).toBeLessThanOrEqual(64 + 1e-6) // 100 + 400 * 0.42
    }
  })

  it("falls back to the host while the anchor has nothing to measure", () => {
    const sphere = createSphere(el, srcs(100), () => null)
    sphere.draw(16)
    // 0.36 * 600 = 216 around (400, 300): well outside the 72 an anchored sphere here would stay within
    expect(Math.max(...sphere.tiles.map(t => Math.abs(t.sx - 400)))).toBeGreaterThan(150)
    for (const t of sphere.tiles) expect(Math.abs(t.sx - 400)).toBeLessThanOrEqual(216 + 1e-6)
  })

  it("places every tile as soon as it is built, before any frame", () => {
    const sphere = createSphere(el, srcs(50))
    for (const t of sphere.tiles) expect(t.el.style.transform).toMatch(/translate3d/)
  })

  it("releases ceil(queue/45) files per frame", () => {
    expect(releaseCount(900)).toBe(20)
    expect(releaseCount(1)).toBe(1)
    expect(releaseCount(0)).toBe(1)
    expect(releaseCount(46)).toBe(2)
  })

  it("writes transforms to the DOM, not through React", () => {
    const sphere: Sphere = createSphere(el, srcs(320))
    sphere.draw(16)
    const t = sphere.tiles[0]
    // the code writes `translate3d(Xpx,Ypx,0)`, exactly as the reference does; reading it back gets the
    // browser's own serialization, which spaces the commas and renders the bare 0 as 0px.
    expect(t.el.style.transform).toMatch(/translate3d\(\s*-?[\d.]+px,\s*-?[\d.]+px,\s*0(px)?\)\s*scale\([\d.]+\)/)
    expect(t.el.style.opacity).not.toBe("")
    expect(t.el.style.zIndex).not.toBe("")
    expect(t.el.style.willChange).toBe("transform")
    expect(t.el.style.backfaceVisibility).toBe("hidden")
    // the rotation advances, so a later frame writes a different transform
    const before = sphere.tiles.map(x => x.el.style.transform)
    sphere.draw(500)
    expect(sphere.tiles.map(x => x.el.style.transform)).not.toEqual(before)
  })

  it("stops drawing a retired tile and drops every node on clear", () => {
    const sphere = createSphere(el, srcs(320))
    sphere.draw(16)
    const tile = sphere.tiles[0]
    sphere.retire(tile, "f0")
    const frozen = tile.el.style.transform
    sphere.draw(16)
    expect(tile.el.style.transform).toBe(frozen)

    sphere.clear()
    expect(sphere.tiles.length).toBe(0)
    expect(el.querySelectorAll("img").length).toBe(0)
    expect(() => sphere.draw(16)).not.toThrow()
    expect(sphere.tileFor("f0")).toBeUndefined()
  })
})

describe("the shared frame loop", () => {
  const frames: FrameRequestCallback[] = []
  const raf = vi.fn((fn: FrameRequestCallback) => frames.push(fn))
  const cancel = vi.fn()

  beforeEach(() => {
    frames.length = 0
    raf.mockClear()
    cancel.mockClear()
    vi.stubGlobal("requestAnimationFrame", raf)
    vi.stubGlobal("cancelAnimationFrame", cancel)
  })
  afterEach(() => vi.unstubAllGlobals())

  it("drives every subscriber from one rAF, and stopLoop cancels the pending frame", async () => {
    const { startLoop, stopLoop } = await import("./loop")
    const a = vi.fn()
    const b = vi.fn()
    const stopA = startLoop(a)
    startLoop(b)
    expect(raf).toHaveBeenCalledTimes(1) // one loop, two subscribers

    frames.pop()!(performance.now() + 16)
    expect(a).toHaveBeenCalledTimes(1)
    expect(b).toHaveBeenCalledTimes(1)

    stopA()
    frames.pop()!(performance.now() + 32)
    expect(a).toHaveBeenCalledTimes(1)
    expect(b).toHaveBeenCalledTimes(2)

    // a frame is pending now; stopLoop must cancel it, not just forget the subscribers
    expect(frames).toHaveLength(1)
    stopLoop()
    expect(cancel).toHaveBeenCalledTimes(1)
    expect(cancel).toHaveBeenCalledWith(raf.mock.results[raf.mock.results.length - 1].value)
  })

  it("stops itself when the last subscriber unsubscribes from inside its own frame", async () => {
    const { startLoop, stopLoop } = await import("./loop")
    let stop = () => {}
    const once = vi.fn(() => stop())
    stop = startLoop(once)

    frames.pop()!(performance.now() + 16)
    expect(once).toHaveBeenCalledTimes(1)
    expect(frames).toHaveLength(0) // no frame requested for an empty loop
    expect(raf).toHaveBeenCalledTimes(1)

    // and the loop wakes up again for the next subscriber
    startLoop(vi.fn())
    expect(raf).toHaveBeenCalledTimes(2)
    stopLoop()
  })
})

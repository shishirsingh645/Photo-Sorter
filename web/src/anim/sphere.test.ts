import { beforeEach, describe, expect, it, vi } from "vitest"
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
    expect(sphere.tileFor("f320")).toBe(tile)
    expect(tile.left).toBe(2)

    sphere.retire(tile)
    expect(tile.alive).toBe(true)
    expect(tile.el.style.opacity).not.toBe("0")

    sphere.retire(tile)
    expect(tile.alive).toBe(false)
    expect(tile.el.style.opacity).toBe("0")
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
    expect(t.el.style.transform).toMatch(/translate3d\(-?[\d.]+px,-?[\d.]+px,0\) scale\([\d.]+\)/)
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
    sphere.retire(tile)
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
  it("drives every subscriber from one rAF and stops when the last one leaves", async () => {
    const { startLoop, stopLoop } = await import("./loop")
    const frames: FrameRequestCallback[] = []
    const raf = vi.fn((fn: FrameRequestCallback) => (frames.push(fn), frames.length))
    vi.stubGlobal("requestAnimationFrame", raf)
    vi.stubGlobal("cancelAnimationFrame", vi.fn())

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

    stopLoop()
    frames.pop()!(performance.now() + 48)
    expect(b).toHaveBeenCalledTimes(2)
    vi.unstubAllGlobals()
  })
})

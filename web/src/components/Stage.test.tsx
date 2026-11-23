import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { render } from "@testing-library/react"
import { Stage } from "./Stage"
import type { Sphere } from "../anim/sphere"

const items = (n: number) => Array.from({ length: n }, (_, i) => ({ mini: `/api/mini/${i}.jpg` }))
const srcsOf = (container: HTMLElement) =>
  [...container.querySelectorAll("img")].map(i => i.getAttribute("src"))

describe("Stage", () => {
  beforeEach(() => {
    vi.stubGlobal("requestAnimationFrame", vi.fn(() => 1))
    vi.stubGlobal("cancelAnimationFrame", vi.fn())
  })
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("hands the built sphere out, and null when it is torn down", () => {
    const onSphere = vi.fn<(s: Sphere | null) => void>()
    const { unmount } = render(<Stage mode="setup" items={items(5)} onSphere={onSphere} />)
    expect(onSphere).toHaveBeenCalledTimes(1)
    const sphere = onSphere.mock.calls[0][0]!
    expect(sphere.tiles).toHaveLength(5)
    expect(sphere.tileFor("a")).toBeDefined()

    unmount()
    expect(onSphere).toHaveBeenLastCalledWith(null)
  })

  it("centres the sphere on the anchor it is given, not on its own viewport-sized layer", () => {
    // jsdom has no layout, so the layer measures 0x0: a sphere that ignored the anchor would sit at 0,0
    const stage = { left: 300, top: 100, width: 200, height: 400 } as DOMRect
    const onSphere = vi.fn<(s: Sphere | null) => void>()
    render(<Stage mode="setup" items={items(30)} onSphere={onSphere} anchor={() => stage} />)
    for (const t of onSphere.mock.calls[0][0]!.tiles) {
      expect(Math.abs(t.sx - 400)).toBeLessThanOrEqual(72 + 1e-6)
      expect(Math.abs(t.sy - 300)).toBeLessThanOrEqual(72 + 1e-6)
    }
  })

  it("keeps the same sphere when items is a new array with the same thumbnails", () => {
    const onSphere = vi.fn<(s: Sphere | null) => void>()
    const { rerender } = render(<Stage mode="running" items={items(5)} onSphere={onSphere} />)
    rerender(<Stage mode="running" items={items(5)} onSphere={onSphere} />)
    expect(onSphere).toHaveBeenCalledTimes(1) // no teardown, no rebuild
  })

  it("rebuilds when the thumbnails really change", () => {
    const onSphere = vi.fn<(s: Sphere | null) => void>()
    const { rerender } = render(<Stage mode="setup" items={items(5)} onSphere={onSphere} />)
    rerender(<Stage mode="setup" items={items(6)} onSphere={onSphere} />)
    expect(onSphere.mock.calls.map(c => c[0] === null)).toEqual([false, true, false])
    expect(onSphere.mock.calls[2][0]!.tiles).toHaveLength(6)
  })

  it("shuffles the thumbnails instead of showing them in caller order", () => {
    vi.spyOn(Math, "random").mockReturnValue(0)
    const { container } = render(<Stage mode="setup" items={items(10)} />)
    const shown = srcsOf(container)
    expect([...shown].sort()).toEqual(items(10).map(i => i.mini).sort()) // nothing lost
    expect(shown).not.toEqual(items(10).map(i => i.mini)) // but not in order
  })
})

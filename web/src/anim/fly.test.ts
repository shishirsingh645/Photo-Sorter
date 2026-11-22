import { afterEach, describe, expect, it, vi } from "vitest"
import { flyToSlot } from "./fly"

function motion(reduced: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((q: string) => ({ matches: reduced && q.includes("reduce"), media: q })),
  )
}

/** jsdom has neither layout nor the Web Animations API, so both are stubbed here. */
function slot(x = 400, y = 300, size = 42) {
  const el = document.createElement("div")
  el.getBoundingClientRect = () =>
    ({
      left: x,
      top: y,
      width: size,
      height: size,
      right: x + size,
      bottom: y + size,
      x,
      y,
    }) as DOMRect
  document.body.append(el)
  return el
}

function flyingImg() {
  const img = document.createElement("img")
  const animate = vi.fn(
    (_frames: Keyframe[], _opts: KeyframeAnimationOptions) => ({}) as Animation,
  )
  img.animate = animate as unknown as typeof img.animate
  document.body.append(img)
  return { img, animate }
}

const tile = { sx: 120, sy: 90, s: 1.1 }
const SIZE = 28 * tile.s
const nums = (transform: unknown) =>
  // only the numbers inside the parens, so the "3" in translate3d is not one of them
  [...String(transform).matchAll(/(?<=[(,])-?\d+(?:\.\d+)?/g)].map(m => Number(m[0]))

afterEach(() => vi.unstubAllGlobals())

describe("flyToSlot", () => {
  it("uses the reference's fly duration and easing", () => {
    motion(false)
    const { img, animate } = flyingImg()
    flyToSlot(tile, slot(), img, vi.fn())

    expect(animate).toHaveBeenCalledTimes(1)
    const [frames, opts] = animate.mock.calls[0]
    expect(opts.easing).toBe("cubic-bezier(.55,0,.25,1)")
    expect(opts.duration as number).toBeGreaterThanOrEqual(650)
    expect(opts.duration as number).toBeLessThanOrEqual(1050)

    // a three-keyframe arc: the tile's place on the sphere, a lifted mid-point, the slot
    expect(frames).toHaveLength(3)
    const [fromX, fromY, , fromScale] = nums(frames[0].transform)
    expect(fromX).toBeCloseTo(tile.sx - SIZE / 2)
    expect(fromY).toBeCloseTo(tile.sy - SIZE / 2)
    expect(fromScale).toBe(1)

    expect(frames[1].offset).toBe(0.45)
    expect(String(frames[1].transform)).toMatch(/scale\(1\.2\) rotate\(-?[\d.]+deg\)/)

    const [toX, toY, , toScale] = nums(frames[2].transform)
    expect(toX).toBe(400)
    expect(toY).toBe(300)
    expect(toScale).toBeCloseTo(42 / SIZE) // ends the size of the slot it lands in

    // sized from the tile's last drawn scale, as the reference does
    expect(parseFloat(img.style.width)).toBeCloseTo(SIZE)
    expect(img.style.height).toBe(img.style.width)
  })

  it("lifts the mid-point within the reference's random bounds", () => {
    motion(false)
    const { img, animate } = flyingImg()
    for (let i = 0; i < 50; i++) flyToSlot(tile, slot(), img, vi.fn())

    for (const [frames] of animate.mock.calls) {
      const [x, y] = nums(frames[1].transform)
      // the keyframe is the mid-point offset by half a tile
      const across = x + SIZE / 2 - (tile.sx + 400) / 2
      const lift = y + SIZE / 2 - (tile.sy + 300) / 2
      expect(across).toBeGreaterThanOrEqual(-60)
      expect(across).toBeLessThanOrEqual(60)
      expect(lift).toBeLessThanOrEqual(-60)
      expect(lift).toBeGreaterThanOrEqual(-140)
    }
  })

  it("lands tiles directly when reduced motion is requested", () => {
    motion(true)
    const { img, animate } = flyingImg()
    const onLand = vi.fn()
    flyToSlot(tile, slot(), img, onLand)

    expect(onLand).toHaveBeenCalledTimes(1) // immediately, on this very call
    expect(animate).not.toHaveBeenCalled()
    expect(img.isConnected).toBe(false)
  })

  it("removes the flying node and lands it when the arc finishes", () => {
    motion(false)
    const img = document.createElement("img")
    const finishers: Array<() => void> = []
    img.animate = (() => ({
      set onfinish(fn: () => void) {
        finishers.push(fn)
      },
    })) as unknown as typeof img.animate
    document.body.append(img)
    const onLand = vi.fn()

    flyToSlot(tile, slot(), img, onLand)
    expect(onLand).not.toHaveBeenCalled()
    expect(img.isConnected).toBe(true)

    finishers[0]()
    expect(onLand).toHaveBeenCalledTimes(1)
    expect(img.isConnected).toBe(false)
  })
})

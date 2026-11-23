import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { Mock } from "vitest"
import type { SlimItem } from "../state/library"
import { flyToSlot } from "./fly"
import { startLoop } from "./loop"
import { Player } from "./player"
import type { PlayerHost } from "./player"
import type { Sphere } from "./sphere"

vi.mock("./fly", () => ({ flyToSlot: vi.fn() }))
vi.mock("./loop", () => ({ startLoop: vi.fn() }))

const item = (id: number, over: Partial<SlimItem> = {}): SlimItem => ({ id, kind: "photo", bytes: 10, dupe: false, cat: "beach", ...over })

let frame: ((dt: number, now: number) => void) | null
let tile: { sx: number; sy: number; s: number }
let sphere: { tileFor: ReturnType<typeof vi.fn>; retire: ReturnType<typeof vi.fn> }
let slot: HTMLElement
let host: PlayerHost & { changed: Mock<() => void>; finished: Mock<() => void> }

/** The landing callback of the nth flight. */
const landing = (n: number) => (vi.mocked(flyToSlot).mock.calls[n][3] as () => void)()

beforeEach(() => {
  frame = null
  vi.mocked(flyToSlot).mockReset()
  vi.mocked(startLoop).mockReset()
  vi.mocked(startLoop).mockImplementation((fn) => {
    frame = fn
    return () => {
      frame = null
    }
  })
  tile = { sx: 10, sy: 20, s: 1 }
  sphere = { tileFor: vi.fn(() => tile), retire: vi.fn() }
  slot = document.createElement("div")
  host = {
    layer: () => document.createElement("div"),
    sphere: () => sphere as unknown as Sphere,
    slot: () => slot,
    centre: () => ({ sx: 0, sy: 0, s: 1 }),
    keyOf: (it) => it.cat ?? "_dupes",
    miniOf: (it) => `/data/mini/${it.id}.jpg`,
    changed: vi.fn<() => void>(),
    finished: vi.fn<() => void>(),
  }
})
afterEach(() => vi.restoreAllMocks())

describe("Player, live", () => {
  it("retires a tile with the same id string it was asked for the tile with", () => {
    const p = new Player(host)
    p.load([item(7)])
    p.startLive()
    p.enqueue(item(7))
    frame!(16, 100)
    expect(sphere.tileFor).toHaveBeenCalledWith("7")
    expect(sphere.retire).toHaveBeenCalledWith(tile, "7")
  })

  it("flies a queued file from its tile to its card's slot, with its small preview", () => {
    const p = new Player(host)
    const a = item(0)
    p.load([a])
    p.startLive()
    p.enqueue(a)
    frame!(16, 100)
    const [from, to, img] = vi.mocked(flyToSlot).mock.calls[0]
    expect(from).toBe(tile)
    expect(to).toBe(slot)
    expect((img as HTMLImageElement).getAttribute("src")).toBe("/data/mini/0.jpg")
  })

  it("releases a batch over several frames, ceil(queued / 45) at a time", () => {
    const all = Array.from({ length: 100 }, (_, i) => item(i))
    const p = new Player(host)
    p.load(all)
    p.startLive()
    all.forEach((it) => p.enqueue(it))
    frame!(16, 100)
    expect(vi.mocked(flyToSlot)).toHaveBeenCalledTimes(3) // ceil(100 / 45)
    frame!(16, 116)
    expect(vi.mocked(flyToSlot)).toHaveBeenCalledTimes(6) // ceil(97 / 45)
  })

  it("flies a file once, however often its label arrives", () => {
    const a = item(0)
    const p = new Player(host)
    p.load([a])
    p.startLive()
    p.enqueue(a)
    p.enqueue(a) // already waiting
    frame!(16, 100)
    p.enqueue(a) // already flown
    frame!(16, 116)
    expect(vi.mocked(flyToSlot)).toHaveBeenCalledTimes(1)
  })

  it("lands a file in its card only when the flight ends, and says so once a frame", () => {
    const a = item(0)
    const p = new Player(host)
    p.load([a, item(1)])
    p.startLive()
    p.enqueue(a)
    frame!(16, 100)
    expect(p.landings.count("beach")).toBe(0) // still in the air
    host.changed.mockClear()
    landing(0)
    expect(p.landings.count("beach")).toBe(1)
    frame!(16, 116)
    expect(host.changed).toHaveBeenCalledTimes(1)
  })

  it("celebrates only when the sort has ended and the last file has landed", () => {
    const all = [item(0), item(1)]
    const p = new Player(host)
    p.load(all)
    p.startLive()
    all.forEach((it) => p.enqueue(it))
    frame!(16, 100) // one a frame: ceil(2 / 45) = 1
    frame!(16, 116)
    landing(0)
    landing(1)
    expect(host.finished).not.toHaveBeenCalled() // everything landed, but labels could still be arriving
    p.finish()
    expect(host.finished).toHaveBeenCalledTimes(1)
  })

  it("celebrates at once when it is told the sort ended after the last file had already landed", () => {
    const a = item(0)
    const p = new Player(host)
    p.load([a])
    p.startLive()
    p.enqueue(a)
    frame!(16, 100)
    landing(0)
    p.finish()
    expect(host.finished).toHaveBeenCalledTimes(1)
  })

  it("lands a file where the card is, even when there is no slot to fly to", () => {
    host.slot = () => null
    const a = item(0)
    const p = new Player(host)
    p.load([a])
    p.startLive()
    p.enqueue(a)
    frame!(16, 100)
    expect(vi.mocked(flyToSlot)).not.toHaveBeenCalled()
    expect(p.landings.count("beach")).toBe(1)
  })

  it("flies from the middle of the stage when the sphere has no tile for a file", () => {
    sphere.tileFor.mockReturnValue(undefined)
    const a = item(0)
    const p = new Player(host)
    p.load([a])
    p.startLive()
    p.enqueue(a)
    frame!(16, 100)
    expect(vi.mocked(flyToSlot).mock.calls[0][0]).toEqual({ sx: 0, sy: 0, s: 1 })
    expect(sphere.retire).not.toHaveBeenCalled()
  })

  it("ignores a flight that lands after the board was reset", () => {
    const a = item(0)
    const p = new Player(host)
    p.load([a])
    p.startLive()
    p.enqueue(a)
    frame!(16, 100)
    p.reset()
    landing(0)
    expect(p.landings.count("beach")).toBe(0)
  })
})

describe("Player, replay", () => {
  const four = [item(0), item(1), item(2), item(3)]
  beforeEach(() => vi.spyOn(performance, "now").mockReturnValue(0))

  it("spreads the files over the replay along the reference's ease", () => {
    const p = new Player(host)
    p.load(four)
    p.startReplay(1000)
    frame!(16, 0)
    expect(vi.mocked(flyToSlot)).toHaveBeenCalledTimes(0)
    frame!(16, 500) // ease(0.5) = 0.5
    expect(vi.mocked(flyToSlot)).toHaveBeenCalledTimes(2)
    frame!(16, 1000)
    expect(vi.mocked(flyToSlot)).toHaveBeenCalledTimes(4)
  })

  it("sends every file once, in some order, and celebrates when the last one lands", () => {
    const p = new Player(host)
    p.load(four)
    p.startReplay(1000)
    frame!(16, 1000)
    const flown = vi.mocked(flyToSlot).mock.calls.map((c) => (c[2] as HTMLImageElement).getAttribute("src")).sort()
    expect(flown).toEqual([0, 1, 2, 3].map((i) => `/data/mini/${i}.jpg`))
    for (let i = 0; i < 3; i++) landing(i)
    expect(host.finished).not.toHaveBeenCalled()
    landing(3)
    expect(host.finished).toHaveBeenCalledTimes(1)
  })

  it("starts from empty cards", () => {
    const p = new Player(host)
    p.load(four)
    p.fillStatic()
    expect(p.landings.landed).toBe(4)
    p.startReplay(1000)
    expect(p.landings.landed).toBe(0)
    expect(p.landings.released).toBe(0)
  })
})

describe("Player, a finished sort", () => {
  it("fills every card at once, with no flights and no celebration", () => {
    const p = new Player(host)
    p.load([item(0), item(1, { cat: "clips", kind: "video" }), item(2, { dupe: true })])
    p.fillStatic()
    expect([p.landings.count("beach"), p.landings.count("clips")]).toEqual([1, 1])
    expect(p.landings.dupes).toBe(1)
    expect(p.landings.released).toBe(3)
    expect(vi.mocked(flyToSlot)).not.toHaveBeenCalled()
    expect(host.finished).not.toHaveBeenCalled()
    expect(host.changed).toHaveBeenCalledTimes(1)
  })
})

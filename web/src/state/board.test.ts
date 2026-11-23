import { describe, expect, it } from "vitest"
import { Landings, REVIEW_KEY, targetOf } from "./board"
import type { SlimItem } from "./library"

const item = (id: number, over: Partial<SlimItem> = {}): SlimItem => ({ id, kind: "photo", bytes: 10, dupe: false, ...over })

describe("targetOf", () => {
  const keys = new Set(["beach", "clips"])
  it("sends a file to its folder, a duplicate to review, and a file with no folder left there too", () => {
    expect(targetOf(item(0, { cat: "beach" }), keys)).toBe("beach")
    expect(targetOf(item(1, { cat: "beach", dupe: true }), keys)).toBe(REVIEW_KEY)
    expect(targetOf(item(2, { cat: "deleted-folder" }), keys)).toBe(REVIEW_KEY)
    expect(targetOf(item(3), keys)).toBe(REVIEW_KEY)
  })
})

describe("Landings", () => {
  it("counts photos, videos and duplicates apart, and what the duplicates take up", () => {
    const L = new Landings()
    L.land("beach", item(0))
    L.land("clips", item(1, { kind: "video" }))
    L.land(REVIEW_KEY, item(2, { dupe: true, bytes: 500 }))
    L.land(REVIEW_KEY, item(3, { dupe: true, kind: "video", bytes: 700 }))
    expect([L.photos, L.videos, L.dupes, L.saved, L.landed]).toEqual([1, 1, 2, 1200, 4])
    expect(L.count("beach")).toBe(1)
    expect(L.count("nowhere")).toBe(0)
  })

  it("lists the newest landings first, as many as a card has slots", () => {
    const L = new Landings()
    for (let i = 0; i < 15; i++) L.land("beach", item(i))
    expect(L.recent("beach", 12).map((i) => i.id)).toEqual([14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3])
    expect(L.recent("beach", 100)).toHaveLength(15)
    expect(L.recent("nowhere", 12)).toEqual([])
  })

  it("counts the folders that have anything in them", () => {
    const L = new Landings()
    L.land("beach", item(0))
    expect(L.made(["beach", "clips", "trips"])).toBe(1)
  })

  it("forgets everything on reset", () => {
    const L = new Landings()
    L.land("beach", item(0))
    L.released = 5
    L.reset()
    expect([L.photos, L.landed, L.released, L.count("beach")]).toEqual([0, 0, 0, 0])
  })
})

import { describe, expect, it } from "vitest"
import { phaseEstimates, roughly } from "./estimates"

describe("estimates", () => {
  it("matches the reference's estimate formulas", () => {
    const e = phaseEstimates(1136, 10.7e9, true)
    expect(e.scan).toBeCloseTo(4 + 1136 * 0.025 + 10.7 * 9, 1)
    expect(e.dupes).toBeCloseTo(2 + Math.pow(1.136, 2) * 4, 1)
    expect(e.apply).toBeCloseTo(2 + 1136 * 0.018, 1)
    // batches = ceil(ceil(1136/30)/3) = ceil(38/3) = 13; ceil(13/4) = 4
    expect(e.label).toBeCloseTo(12 + 1136 * 0.012 + 4 * 14, 1)
    expect(phaseEstimates(1136, 10.7e9, false).scan).toBe(0)
  })

  it("pins the batch divisors through the label step", () => {
    // label - 12 - files*0.012 = 14 x ceil(batches/4), batches = ceil(ceil(files/30)/3): the step moves at 30*3*4 files
    const rounds = (files: number) => Math.round((phaseEstimates(files, 0).label - 12 - files * 0.012) / 14)
    // 30/31 and 90/91 move `batches` (1,1 and 1,2) but not the rounds, so the output cannot tell them apart; they are pinned flat
    expect([30, 31, 90, 91].map(rounds)).toEqual([1, 1, 1, 1])
    expect([360, 361, 362].map(rounds)).toEqual([1, 2, 2])
    expect([1080, 1081].map(rounds)).toEqual([3, 4])
  })

  it("phrases short durations as 'under a minute'", () => {
    expect(roughly(40)).toBe("under a minute")
    expect(roughly(49.9)).toBe("under a minute")
    expect(roughly(50)).toBe("about a minute")
    expect(roughly(89.9)).toBe("about a minute")
    expect(roughly(90)).toBe("about 2 min") // round(1.5) is 2
    expect(roughly(70)).toBe("about a minute")
    expect(roughly(200)).toBe("about 3 min")
  })
})

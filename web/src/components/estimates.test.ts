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

  it("phrases short durations as 'under a minute'", () => {
    expect(roughly(40)).toBe("under a minute")
    expect(roughly(70)).toBe("about a minute")
    expect(roughly(200)).toBe("about 3 min")
  })
})

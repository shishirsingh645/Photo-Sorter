import { describe, expect, it } from "vitest"
import type { JobState } from "../api/client"
import { overallProgress, remainingSeconds } from "./progress"

const job = (over: Partial<JobState> = {}): JobState => ({
  running: true, phases: ["scan", "dupes", "label"], phase: "scan", done: 0, total: 0, ...over,
}) // fmt: skip
const est = { scan: 10, dupes: 10, label: 80 }

describe("overallProgress", () => {
  it("weights each phase by its estimate, not evenly", () => {
    // two of three phases finished is 20% of the time, not 67%
    expect(overallProgress(job({ phase: "label" }), est)).toBeCloseTo(0.2)
    // half way through the long phase adds half of its 80
    expect(overallProgress(job({ phase: "label", done: 5, total: 10 }), est)).toBeCloseTo(0.6)
    // the first phase finished is a tenth, not a third
    expect(overallProgress(job({ phase: "dupes" }), est)).toBeCloseTo(0.1)
  })

  it("returns 1 when the job reaches the done phase", () => {
    expect(overallProgress(job({ phase: "done" }), est)).toBe(1)
  })

  it("treats a phase with no estimate as zero weight", () => {
    expect(overallProgress(job({ phases: ["scan", "apply"], phase: "apply" }), { scan: 10 })).toBe(1)
    expect(overallProgress(job({ phases: ["scan", "apply"], phase: "scan", done: 5, total: 10 }), { scan: 10 })).toBeCloseTo(0.5)
  })

  it("is 0 with no phases, and never above 1", () => {
    expect(overallProgress(job({ phases: [], phase: null }), est)).toBe(0)
    expect(overallProgress(job({ phase: "label", done: 99, total: 10 }), est)).toBe(1)
  })
})

describe("remainingSeconds", () => {
  // one phase of 100 s that started at t=0
  const one = (over: Partial<JobState>) => job({ phases: ["label"], phase: "label", phase_started: 0, ...over })
  const e = { label: 100 }

  it("switches from the estimate to the measured rate above 15% of a phase", () => {
    // 10% done after 40 s: still the estimate, 100 - 40
    expect(remainingSeconds(one({ done: 10, total: 100 }), e, 40)).toBe(60)
    // exactly 15% is not above 15%
    expect(remainingSeconds(one({ done: 15, total: 100 }), e, 40)).toBe(60)
    // 50% done after 40 s: the measured rate says 40 s more, not the estimate's 60
    expect(remainingSeconds(one({ done: 50, total: 100 }), e, 40)).toBe(40)
    // just above 15% the measured rate already rules: 40 / 0.16 - 40, not the estimate's 60
    expect(remainingSeconds(one({ done: 16, total: 100 }), e, 40)).toBeCloseTo(210)
    expect(remainingSeconds(one({ done: 20, total: 100 }), e, 40)).toBeCloseTo(160)
  })

  it("counts a phase with no estimate as zero and a phase that has not started as nothing spent", () => {
    // apply has no estimate: it adds nothing, and the current phase still has 100 - 40 to go
    expect(remainingSeconds(job({ phases: ["label", "apply"], phase: "label", phase_started: 0 }), e, 40)).toBe(60)
    // no phase_started yet: nothing spent, so the whole estimate remains
    expect(remainingSeconds(one({ phase_started: null }), e, 40)).toBe(100)
  })

  it("never reports less than two seconds left for a running phase", () => {
    expect(remainingSeconds(one({}), e, 500)).toBe(2) // far past its estimate
    expect(remainingSeconds(one({ done: 100, total: 100 }), e, 40)).toBe(2) // finished its work, not its phase
  })

  it("adds the estimates of the phases still to come, and none of those behind", () => {
    const j = job({ phase: "dupes", phase_started: 0 })
    // dupes: 10 - 4 = 6, then label's 80; scan is behind us
    expect(remainingSeconds(j, est, 4)).toBe(86)
  })
})

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { JobState } from "../api/client"
import { STOPPED } from "./progress"
import { RunCard } from "./RunCard"

// The shared loop is the seam: capture the frame callbacks so a test can drive them.
const frames = vi.hoisted(() => ({ subs: new Set<(dt: number, now: number) => void>() }))
vi.mock("../anim/loop", () => ({
  startLoop: (fn: (dt: number, now: number) => void) => {
    frames.subs.add(fn)
    return () => frames.subs.delete(fn)
  },
}))

const est = { scan: 10, dupes: 10, label: 80, apply: 20 }
const job = (over: Partial<JobState> = {}): JobState => ({
  running: true, step: "sort", code: null, phases: ["scan", "dupes", "label", "apply"], phase: "label",
  done: 0, total: 0, started: Date.now() / 1000 - 75, phase_started: Date.now() / 1000 - 10, timings: {}, log: [], ...over,
}) // fmt: skip
const card = (j: JobState, handlers: { onRetry?: () => void; onCancel?: () => void } = {}) =>
  render(<RunCard job={j} estimates={est} onRetry={handlers.onRetry ?? vi.fn()} onCancel={handlers.onCancel ?? vi.fn()} />)

beforeEach(() => frames.subs.clear())
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("RunCard", () => {
  it("marks finished phases with a tick and the current one as active", () => {
    const { container } = card(job())
    const [scan, dupes, label, apply] = Array.from(container.querySelectorAll("li"))
    for (const done of [scan, dupes]) {
      expect(done).toHaveAttribute("data-state", "ok")
      expect(done.querySelector("[data-icon='check']")).not.toBeNull()
    }
    expect(label).toHaveAttribute("data-state", "now")
    expect(label).toHaveAttribute("aria-current", "step")
    expect(label.querySelector("[data-icon='check']")).toBeNull()
    expect(apply).not.toHaveAttribute("data-state")
    expect(screen.getByText("Claude is sorting your photos")).toBeInTheDocument()
  })

  // Review Focus 4 — a failed sort
  it("shows the error log and a working Try again when the job fails", () => {
    const onRetry = vi.fn()
    card({ running: false, code: 1, phases: ["scan", "dupes"], phase: "dupes", done: 0, total: 0, log: ["a", "boom"] }, { onRetry })
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
    expect(screen.getByText(/boom/)).toBeInTheDocument()
    const retry = screen.getByRole("button", { name: /try again/i })
    expect(retry).toBeEnabled()
    fireEvent.click(retry)
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it("tells a deliberate Stop from a failure", () => {
    const onRetry = vi.fn()
    card(job({ running: false, code: 1, log: ["Looking at files", STOPPED] }), { onRetry })
    expect(screen.queryByText(/something went wrong/i)).not.toBeInTheDocument()
    expect(screen.getByText("Stopped")).toBeInTheDocument()
    expect(screen.queryByText(/Stopped at your request/)).not.toBeInTheDocument() // the log is for failures
    fireEvent.click(screen.getByRole("button", { name: /start again/i }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it("reads a STOPPED line that is not the last line as a failure", () => {
    card(job({ running: false, code: 1, log: [STOPPED, "boom"] }))
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument()
    expect(screen.queryByText("Stopped")).not.toBeInTheDocument()
  })

  it("never shows a running spinner for a job that has stopped", () => {
    for (const j of [job({ running: false, code: 1, log: ["boom"] }), job({ running: false, code: 1, log: [STOPPED] })]) {
      const { container, unmount } = card(j)
      expect(container.querySelector("[data-state='now']")).toBeNull()
      expect(container.querySelector("[aria-current]")).toBeNull()
      unmount()
    }
  })

  it("offers Cancel only while a job is running", () => {
    const onCancel = vi.fn()
    const { unmount } = card(job(), { onCancel })
    const stop = screen.getByRole("button", { name: /stop sorting/i })
    // clearly a stop, not an undo
    expect(screen.getByText(/does not undo anything/i)).toBeInTheDocument()
    fireEvent.click(stop)
    expect(onCancel).toHaveBeenCalledTimes(1)
    unmount()

    for (const j of [job({ running: false, code: 1, log: ["boom"] }), job({ running: false, code: 1, log: [STOPPED] }), job({ running: false, code: 0 })]) {
      const again = card(j)
      expect(screen.queryByRole("button", { name: /stop sorting/i })).not.toBeInTheDocument()
      again.unmount()
    }
  })

  it("paints the timer from the shared loop, once, without re-subscribing", () => {
    const { container, rerender } = card(job())
    expect(frames.subs.size).toBe(1)
    const timer = container.querySelector("b + span")!
    expect(timer.textContent).toMatch(/^1:1[5-6] · /) // 75 s elapsed, then a time left or "almost done"
    rerender(<RunCard job={job({ done: 5, total: 10 })} estimates={est} onRetry={vi.fn()} onCancel={vi.fn()} />)
    expect(frames.subs.size).toBe(1)
    timer.textContent = ""
    act(() => frames.subs.forEach(f => f(16, 0)))
    expect(timer.textContent).toMatch(/^1:1\d · /)
  })

  it("counts the time left down between updates instead of up", () => {
    const T = 1_000_000 // seconds
    let offset = 0
    vi.spyOn(Date, "now").mockImplementation(() => (T + offset) * 1000)
    // 20% through the phase after 300 s: the measured rate says 1200 s more, "about 20 min"
    const j = job({ phases: ["label"], phase: "label", done: 20, total: 100, started: T - 300, phase_started: T - 300 })
    const { container } = card(j)
    const timer = container.querySelector("b + span")!
    const minutes = () => Number(/about (\d+) min left/.exec(timer.textContent!)![1])
    const seen = [minutes()]
    for (const at of [120, 240, 360]) {
      offset = at // no new event: done and total are frozen
      act(() => frames.subs.forEach(f => f(16, 0)))
      seen.push(minutes())
    }
    expect(seen).toEqual([20, 18, 16, 14])
  })
})

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { JobState } from "../api/client"
import { DonePanel } from "./DonePanel"
import { STOPPED } from "./progress"
import { RunCard } from "./RunCard"

// The shared loop and the confetti are the seams: capture the frame callbacks so a test can drive them.
const frames = vi.hoisted(() => ({ subs: new Set<(dt: number, now: number) => void>() }))
const burst = vi.hoisted(() => vi.fn())
vi.mock("../anim/loop", () => ({
  startLoop: (fn: (dt: number, now: number) => void) => {
    frames.subs.add(fn)
    return () => frames.subs.delete(fn)
  },
}))
vi.mock("../anim/confetti", () => ({ burstConfetti: burst }))

const est = { scan: 10, dupes: 10, label: 80, apply: 20 }
const job = (over: Partial<JobState> = {}): JobState => ({
  running: true, step: "sort", code: null, phases: ["scan", "dupes", "label", "apply"], phase: "label",
  done: 0, total: 0, started: Date.now() / 1000 - 75, phase_started: Date.now() / 1000 - 10, timings: {}, log: [], ...over,
}) // fmt: skip
const card = (j: JobState, handlers: { onRetry?: () => void; onCancel?: () => void } = {}) =>
  render(<RunCard job={j} estimates={est} onRetry={handlers.onRetry ?? vi.fn()} onCancel={handlers.onCancel ?? vi.fn()} />)

beforeEach(() => frames.subs.clear())
afterEach(cleanup)

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
    expect(apply).toHaveAttribute("data-state", "")
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
})

describe("DonePanel", () => {
  it("counts up the total and fires confetti on the done panel", () => {
    vi.spyOn(performance, "now").mockReturnValue(1000)
    const onReplay = vi.fn()
    render(<DonePanel total={1136} folders={13} dupes={40} saved={2_400_000_000} onReplay={onReplay} />)
    expect(screen.getByText("0")).toBeInTheDocument()
    expect(burst).toHaveBeenCalledTimes(1)
    expect(burst.mock.calls[0][0]).toBeInstanceOf(HTMLCanvasElement)

    act(() => frames.subs.forEach(f => f(16, 1450))) // half way through the 900 ms count
    const mid = Number(screen.getByText(/sorted/).firstElementChild!.textContent!.replace(/,/g, ""))
    expect(mid).toBeGreaterThan(0)
    expect(mid).toBeLessThan(1136)

    act(() => frames.subs.forEach(f => f(16, 2000)))
    expect(screen.getByText("1,136")).toBeInTheDocument()
    expect(frames.subs.size).toBe(0) // the count unsubscribes itself

    expect(screen.getByText("13 folders")).toBeInTheDocument()
    expect(screen.getByText(/40 duplicates/)).toBeInTheDocument()
    expect(screen.getByText(/2\.4 GB freed/)).toBeInTheDocument()

    fireEvent.keyDown(window, { code: "Space" })
    expect(onReplay).toHaveBeenCalledTimes(1)
    vi.restoreAllMocks()
  })
})

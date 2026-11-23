import { describe, expect, it } from "vitest"
import type { AppState, JobState } from "../api/client"
import { initialState, reducer } from "./reducer"
import type { Action, State } from "./reducer"

const job = (over: Partial<JobState> = {}): JobState => ({
  step: null, running: false, code: null, phase: null, phases: [], done: 0, total: 0,
  started: null, phase_started: null, timings: {}, log: [], ...over,
}) // fmt: skip

const app = (j: Partial<JobState> = {}, apply = false): AppState => ({
  categories: [], source: "C:/photos", limit: null, sorted: apply ? "C:/sorted" : null, files: 0, bytes: 0,
  steps: { scan: false, dupes: false, label: false, jev_labels: false, apply },
  jev_key: false, claude_cli: true, overrides: 0, job: job(j),
  platform: "windows", file_manager: "Explorer", picker_available: true, picker_reason: "",
}) // fmt: skip

const live = { step: "sort", running: true, phase: "scan", phases: ["scan", "dupes", "label", "apply"] }
const load = (s: State, a: AppState) => reducer(s, { type: "state", state: a })
const event = (s: State, e: Extract<Action, { type: "event" }>["event"], now = 100) =>
  reducer(s, { type: "event", event: e, now })

describe("reducer", () => {
  it("moves from setup to running when a sort starts", () => {
    const setup = load(initialState, app())
    expect(setup.mode).toBe("setup")
    const running = load(setup, app(live)) // what POST /api/sort answers with
    expect(running.mode).toBe("running")
    expect(running.job.running).toBe(true)
    expect(running.job.phases).toEqual(live.phases)
  })

  it("moves to done when the job finishes with code 0", () => {
    let s = load(initialState, app(live))
    s = event(s, { type: "phase_started", phase: "apply" }, 250)
    s = event(s, { type: "progress", phase: "apply", done: 9, total: 10 })
    expect(s.job).toMatchObject({ phase: "apply", done: 9, total: 10, phase_started: 250 })
    s = event(s, { type: "job_finished", step: "sort", code: 0 })
    expect(s.mode).toBe("done")
    expect(s.job).toMatchObject({ running: false, code: 0 })
  })

  it("moves to a failed run state when the job finishes non-zero", () => {
    let s = load(initialState, app(live))
    s = event(s, { type: "log", message: "boom" })
    s = event(s, { type: "job_finished", step: "sort", code: 1 })
    // Still "running": the run card owns the failure view (log + Try again). It is not "done".
    expect(s.mode).toBe("running")
    expect(s.job).toMatchObject({ running: false, code: 1, log: ["boom"] })
    // ...and a reload of the page lands on the same failed view, not on setup.
    expect(load(initialState, app({ step: "sort", running: false, code: 1, log: ["boom"] })).mode).toBe("running")
  })

  it("starts in running mode when the initial state has a live sort job", () => {
    expect(load(initialState, app(live)).mode).toBe("running")
    // A live scan alone is not a sort, and a finished sort with copies is done.
    expect(load(initialState, app({ step: "scan", running: true })).mode).toBe("setup")
    expect(load(initialState, app({ step: "sort", code: 0 }, true)).mode).toBe("done")
  })

  it("keeps the user's New sort choice across a refresh, but a live sort still wins", () => {
    const done = load(initialState, app({ step: "sort", code: 0 }, true))
    const fresh = reducer(done, { type: "reset" })
    expect(fresh.mode).toBe("setup")
    expect(load(fresh, app({ step: "sort", code: 0 }, true)).mode).toBe("setup")
    expect(load(fresh, app(live)).mode).toBe("running")
  })

  it("applies a polled snapshot like a loaded state", () => {
    const s = event(load(initialState, app(live)), { type: "snapshot", state: app({ step: "sort", code: 0 }, true) })
    expect(s.mode).toBe("done")
    expect(s.job.running).toBe(false)
  })
})

import type { AppState, JobEvent, JobState } from "../api/client"

export type Mode = "loading" | "setup" | "running" | "done"

/** A failed (or stopped) sort stays in "running": the run card is what shows its log and Try again. */
export interface State {
  mode: Mode
  app: AppState | null
  job: JobState
}

/** What useJobEvents delivers: the server's events, plus a whole-state snapshot from the polling fallback
 * and from the resync after a dropped stream comes back. */
export type StreamEvent = JobEvent | { type: "snapshot"; state: AppState }

export type Action =
  | { type: "state"; state: AppState } // initial load, a sort's response, or a snapshot
  | { type: "event"; event: StreamEvent; now: number } // `now` in seconds, like the server's `started`
  | { type: "reset" } // "New sort": back to the setup card

const LOG_LINES = 200 // the server's own cap on /api/state's log

const IDLE: JobState = {
  step: null, running: false, code: null, phase: null, phases: [], done: 0, total: 0,
  started: null, phase_started: null, timings: {}, log: [],
} // fmt: skip

export const initialState: State = { mode: "loading", app: null, job: IDLE }

function modeOf(app: AppState): Mode {
  const { job } = app
  if (job.step === "sort" && (job.running || (job.code ?? 0) !== 0)) return "running"
  return app.steps.apply ? "done" : "setup"
}

function applyEvent(job: JobState, e: JobEvent, now: number): JobState {
  switch (e.type) {
    case "phase_started":
      return { ...job, phase: e.phase, done: 0, total: 0, phase_started: now }
    case "progress":
      return { ...job, phase: e.phase, done: e.done, total: e.total }
    case "log":
      return { ...job, log: [...(job.log ?? []), e.message].slice(-LOG_LINES) }
    case "job_finished":
      return { ...job, running: false, code: e.code }
  }
}

export function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "state": {
      const app = action.state
      // A refresh must not undo the user's choice: after "New sort" (setup) or while looking at a finished
      // sort (done), only a sort that is live right now may pull the page back into "running".
      const settled = state.mode === "setup" || state.mode === "done"
      const mode = settled ? (app.job.step === "sort" && app.job.running ? "running" : state.mode) : modeOf(app)
      return { mode, app, job: app.job }
    }
    case "reset":
      return { ...state, mode: "setup" }
    case "event": {
      const e = action.event
      if (e.type === "snapshot") return reducer(state, { type: "state", state: e.state })
      const job = applyEvent(state.job, e, action.now)
      // Only a sort's end moves the mode: a finished scan or labelling pass is not "done".
      const ended = e.type === "job_finished" && e.step === "sort"
      const mode = ended ? (e.code === 0 ? "done" : "running") : state.mode
      return { ...state, job, mode }
    }
  }
}

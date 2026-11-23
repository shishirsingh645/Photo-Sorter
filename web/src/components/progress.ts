import type { JobState } from "../api/client"

/** Estimated seconds per phase, keyed by phase name (the reference's `phaseEstimates`). */
export type Estimates = Record<string, number>

/** The line photosorter/jobs.py logs when a job ends because the user pressed Stop. */
export const STOPPED = "Stopped at your request."

/** app.js 300-310: each phase counts for its estimated share of the whole; the current one by its own fraction. */
export function overallProgress(job: JobState, est: Estimates): number {
  const phases = job.phases ?? []
  if (!phases.length) return 0
  const total = phases.reduce((s, p) => s + (est[p] ?? 0), 0) || 1
  let done = 0
  for (const p of phases) {
    if (p === job.phase) {
      done += (est[p] ?? 0) * (job.total ? job.done / job.total : 0)
      break
    }
    done += est[p] ?? 0
  }
  return job.phase === "done" ? 1 : Math.min(1, done / total)
}

/** app.js 313-326. `now` is in seconds, like `job.phase_started`. The current phase never counts as under two
 * seconds left; once it is past 15% the measured rate replaces the estimate. */
export function remainingSeconds(job: JobState, est: Estimates, now = Date.now() / 1000): number {
  let left = 0
  let seen = false
  for (const p of job.phases ?? []) {
    if (p === job.phase) {
      seen = true
      const spent = job.phase_started == null ? 0 : now - job.phase_started
      const frac = job.total ? job.done / job.total : 0
      const guess = frac > 0.15 ? spent / frac - spent : (est[p] ?? 0) - spent
      left += Math.max(2, guess)
    } else if (seen) left += est[p] ?? 0
  }
  return left
}

/** app.js 12-13. */
export const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`
export const roughly = (s: number) => (s < 50 ? "under a minute" : s < 90 ? "about a minute" : `about ${Math.round(s / 60)} min`)

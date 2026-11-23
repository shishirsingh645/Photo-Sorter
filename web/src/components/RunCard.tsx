import { useEffect, useRef } from "react"
import { startLoop } from "../anim/loop"
import type { JobState } from "../api/client"
import { Icon } from "./Icon"
import { mmss, remainingSeconds, roughly, STOPPED } from "./progress"
import type { Estimates } from "./progress"
import styles from "./RunCard.module.css"

export interface RunCardProps {
  job: JobState
  /** Seconds per phase for this run; setup's `phaseEstimates(files, bytes, scan)` makes them. */
  estimates: Estimates
  onRetry: () => void
  /** Stops the sort. The server then ends the job with code 1 and the log line STOPPED. */
  onCancel: () => void
}

/** app.js 300 and 547. */
const NAMES: Record<string, string> = {
  scan: "Looking at every file",
  dupes: "Finding duplicates",
  label: "Claude is sorting your photos",
  apply: "Building your folders",
}
const SHORT: Record<string, string> = { scan: "Scan", dupes: "Duplicates", label: "Label", apply: "Folders" }

/** What the run card is showing. `mode` stays "running" for a sort that failed or was stopped, so this is
 * read from the job itself: a stopped job is `running: false`, `code: 1` and a last log line of STOPPED. */
function kindOf(job: JobState): "running" | "stopped" | "failed" | "idle" {
  if (job.running) return "running"
  if ((job.code ?? 0) === 0) return "idle"
  return job.log?.at(-1) === STOPPED ? "stopped" : "failed"
}

export function RunCard({ job, estimates, onRetry, onCancel }: RunCardProps) {
  const kind = kindOf(job)
  const timer = useRef<HTMLSpanElement>(null)

  // The timer is written straight to the DOM from the shared frame loop, so a tick never re-renders the tree.
  const latest = useRef({ job, estimates, kind })
  latest.current = { job, estimates, kind }
  useEffect(() => {
    const paint = () => {
      const el = timer.current
      const { job: j, estimates: est, kind: k } = latest.current
      if (!el || !j.started) return
      let text: string
      if (k === "running") {
        const now = Date.now() / 1000
        const left = remainingSeconds(j, est, now)
        text = `${mmss(Math.max(0, now - j.started))} · ${left > 5 ? roughly(left) + " left" : "almost done"}`
      } else {
        // the server sends no end time: what its phases measured is the nearest thing to elapsed
        const spent = Object.values(j.timings ?? {}).reduce((s, t) => s + t, 0)
        text = `${mmss(spent)} · ${k === "idle" ? "done" : k}`
      }
      if (el.textContent !== text) el.textContent = text
    }
    paint()
    return startLoop(paint)
  }, [])

  const phases = job.phases ?? []
  const cur = phases.indexOf(job.phase ?? "")
  const pct = job.total ? Math.round((job.done / job.total) * 100) : 0
  const title = kind === "failed" ? "Something went wrong" : kind === "stopped" ? "Stopped" : (job.phase && NAMES[job.phase]) || "Getting ready"

  return (
    <div className={styles.panel}>
      <div className={styles.run}>
        <div className={styles.runH}>
          <b>{title}</b>
          <span className={styles.num} ref={timer} />
        </div>
        <div className={styles.pbar}>
          <i style={{ width: `${kind === "failed" ? 100 : pct}%` }} />
        </div>
        <ol className={styles.phases}>
          {phases.map((p, idx) => {
            const state =
              job.phase === "done" || idx < cur
                ? "ok"
                : p === job.phase
                  ? kind === "failed"
                    ? "bad"
                    : kind === "running"
                      ? "now"
                      : ""
                  : ""
            return (
              <li key={p} data-state={state} aria-current={state === "now" ? "step" : undefined}>
                {state === "ok" ? <Icon name="check" /> : <i />}
                {SHORT[p] ?? p}
              </li>
            )
          })}
        </ol>
        {kind === "failed" && <pre className={styles.log}>{(job.log ?? []).slice(-8).join("\n")}</pre>}
        {kind === "stopped" && <p className={styles.note}>You stopped this sort.</p>}
        {(kind === "failed" || kind === "stopped") && (
          <button className={`${styles.btn} ${styles.solid}`} onClick={onRetry}>
            {kind === "failed" ? "Try again" : "Start again"}
          </button>
        )}
        {kind === "running" && (
          <div className={styles.acts}>
            <p className={styles.note}>Stopping ends the sort. It does not undo anything already done.</p>
            <button className={styles.btn} onClick={onCancel}>
              <Icon name="x" />
              Stop sorting
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

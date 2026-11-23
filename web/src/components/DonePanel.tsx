import { useEffect, useRef } from "react"
import { createPortal } from "react-dom"
import { burstConfetti } from "../anim/confetti"
import { startLoop } from "../anim/loop"
import { fmtSize } from "../format"
import styles from "./DonePanel.module.css"
import layers from "./Layers.module.css"
import { Icon } from "./Icon"

export interface DonePanelProps {
  total: number
  folders: number
  dupes: number
  /** Bytes the duplicates would free. */
  saved: number
  /** Space plays the sort back, as in the reference. */
  onReplay: () => void
  /** True only for a sort that has just finished: it counts the total up and bursts confetti. Loading a sort that
   * finished earlier (the default) shows the number as it is, like the reference's `showDone(false)`. */
  live?: boolean
}

const fmt = (n: number) => Math.round(n).toLocaleString("en-US")
const ease = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2) // app.js 237
const COUNT_MS = 900

export function DonePanel({ total, folders, dupes, saved, onReplay, live = false }: DonePanelProps) {
  const root = useRef<HTMLDivElement>(null)
  const count = useRef<HTMLSpanElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const burst = useRef(false) // StrictMode mounts twice; one burst per panel
  const replay = useRef(onReplay)
  replay.current = onReplay

  // The count and the burst both run on the shared frame loop; neither puts a frame into React state.
  useEffect(() => {
    const el = count.current
    if (!live || !el) return
    const start = performance.now()
    const stop = startLoop((_dt, now) => {
      const p = Math.min(1, (now - start) / COUNT_MS)
      el.textContent = fmt(total * ease(p))
      if (p >= 1) stop()
    })
    return stop
  }, [total, live])

  useEffect(() => {
    if (!live || burst.current || !canvas.current || !root.current) return
    burst.current = true
    const r = root.current.getBoundingClientRect()
    burstConfetti(canvas.current, { x: r.left + r.width / 2, y: r.top + r.height / 2 })
  }, [live])

  // app.js 729-732
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as Element | null
      if (t?.matches?.("input, textarea, select") || document.querySelector('[role="dialog"]')) return
      if (e.code === "Space") {
        e.preventDefault()
        replay.current()
      }
    }
    addEventListener("keydown", onKey)
    return () => removeEventListener("keydown", onKey)
  }, [])

  return (
    <>
      <div className={styles.center} ref={root}>
        <div className={styles.check}>
          <Icon name="check" />
        </div>
        <div className={styles.big}>
          <span ref={count}>{live ? "0" : fmt(total)}</span> sorted
        </div>
        <div className={`mx-sub ${styles.sub}`}>
          into <b>{folders} folders</b> with one prompt
        </div>
        <div className={styles.chips}>
          <span className={styles.chip}>🗂️ {fmt(dupes)} duplicates</span>
          <span className={styles.chip}>💾 {fmtSize(saved)} freed</span>
        </div>
      </div>
      {/* the layer sits at the page's top level: inside .center it would be stacked under the top bar */}
      {createPortal(<canvas className={layers.confetti} ref={canvas} aria-hidden="true" />, document.body)}
    </>
  )
}

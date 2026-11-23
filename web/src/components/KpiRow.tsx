import type { CSSProperties } from "react"
import { fmtSize } from "../format"
import styles from "./KpiRow.module.css"

export interface KpiRowProps {
  checked: number
  photos: number
  videos: number
  foldersMade: number
  foldersTotal: number
  dupes: number
  /** Bytes the duplicates take up; shown as MB or GB. */
  saved: number
  /** 0 to 100, like the reference's bar width. The bar turns green at 100. */
  progress: number
}

const n = (v: number) => v.toLocaleString("en-US")

export function KpiRow(p: KpiRowProps) {
  const pct = Math.min(100, Math.max(0, p.progress))
  return (
    <section className={styles.kpis} style={{ "--n": 6 } as CSSProperties}>
      <div className={styles.kpi}>
        <h3>Files checked</h3>
        <b>{n(p.checked)}</b>
        <small>photos &amp; videos</small>
      </div>
      <div className={styles.kpi}>
        <h3>Photos sorted</h3>
        <b>{n(p.photos)}</b>
        <small>&nbsp;</small>
      </div>
      <div className={styles.kpi}>
        <h3>Videos sorted</h3>
        <b>{n(p.videos)}</b>
        <small>&nbsp;</small>
      </div>
      <div className={styles.kpi}>
        <h3>Folders made</h3>
        <b>
          <span>{n(p.foldersMade)}</span>
          <span className={styles.of}>/{n(p.foldersTotal)}</span>
        </b>
        <small>&nbsp;</small>
      </div>
      <div className={styles.kpi}>
        <h3>Duplicates</h3>
        <b>{n(p.dupes)}</b>
        <small>moved to review</small>
      </div>
      <div className={styles.kpi}>
        <h3>Space saved</h3>
        <b>{fmtSize(p.saved)}</b>
        <small>if you delete them</small>
      </div>
      <div
        className={styles.progress}
        data-done={pct >= 100}
        role="progressbar"
        aria-label="Sorting progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
      >
        <i style={{ width: `${pct}%` }} />
      </div>
    </section>
  )
}

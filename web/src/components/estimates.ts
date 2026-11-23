/* Spec §7.5, calibrated on a 2020 MacBook with 1,136 files / 10.7 GB (reference app.js lines 288-299). */
export interface Estimates {
  scan: number
  dupes: number
  label: number
  apply: number
}

export function phaseEstimates(files: number, bytes: number, scan = true): Estimates {
  const batches = Math.ceil(Math.ceil(files / 30) / 3)
  return {
    scan: scan ? 4 + files * 0.025 + (bytes / 1e9) * 9 : 0,
    dupes: 2 + Math.pow(files / 1000, 2) * 4,
    label: 12 + files * 0.012 + Math.ceil(batches / 4) * 14,
    apply: 2 + files * 0.018,
  }
}

/** Reference app.js line 13. */
export const roughly = (s: number): string =>
  s < 50 ? "under a minute" : s < 90 ? "about a minute" : `about ${Math.round(s / 60)} min`

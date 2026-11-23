/** The reference app.js line 8: a whole number with thousands separators. */
export const fmt = (n: number) => Math.round(n).toLocaleString("en-US")

/** The reference app.js line 10, for a path shown on the page: a Mac home folder becomes ~. */
export const tilde = (p: string) => p.replace(/^\/Users\/[^/]+/, "~")

/** Bytes as the reference app writes them: whole MB below a gigabyte, one-decimal GB above. */
export const fmtSize = (bytes: number): string =>
  bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB`

/** Bytes as the reference app writes them: whole MB below a gigabyte, one-decimal GB above. */
export const fmtSize = (bytes: number): string =>
  bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB`

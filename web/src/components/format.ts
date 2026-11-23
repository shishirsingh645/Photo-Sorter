// The reference app.js 8-9, verbatim.
export const fmt = (n: number) => Math.round(n).toLocaleString("en-US")
export const size = (b: number) => (b >= 1e9 ? (b / 1e9).toFixed(1) + " GB" : Math.round(b / 1e6) + " MB")

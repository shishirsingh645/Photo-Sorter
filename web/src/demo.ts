/** The page's URL parameters and demo mode (the reference's app.js 1-8 and 47-49):
 *  ?demo        the fake camera roll in demo/, read-only
 *  ?d=20        how long the replay takes, in seconds (12 by default)
 *  ?auto        replay by itself once the dashboard shows a finished sort
 *  ?source=...&dest=...   fill both folders in, ready to press Start */

import { ApiError } from "./api/client"
import type { AppState } from "./api/client"
import { loadCategories } from "./state/library"

export interface UrlOptions {
  demo: boolean
  auto: boolean
  source: string | null
  dest: string | null
}

/** `?d=` is read the reference's way, `+params.get("d") || 12`: anything that is not a positive number is 12. */
export const replayMs = (search: string = location.search) =>
  (+(new URLSearchParams(search).get("d") ?? "") || 12) * 1000

export function readParams(search: string = location.search): UrlOptions {
  const p = new URLSearchParams(search)
  return { demo: p.has("demo"), auto: p.has("auto"), source: p.get("source") || null, dest: p.get("dest") || null }
}

export const DEMO_SOURCE = "~/Pictures/Camera roll (demo)"
export const DEMO_NOTICE = "This is the demo. Run photo-sorter serve to sort your own photos."

/** The state the reference built by hand for the demo, `S = { source, platform: "demo" }`, filled in to the shape the
 * server sends. Everything has been scanned and sorted, so the reducer lands in "done"; `sorted` is null, so there is
 * no sorted folder to open. */
export async function loadDemoState(): Promise<AppState> {
  const categories = await loadCategories()
  if (!categories.length) throw new ApiError("There is no demo yet. Run photo-sorter demo, then reload this page.", 404)
  return {
    categories,
    source: DEMO_SOURCE,
    limit: null,
    sorted: null,
    files: 0,
    bytes: 0,
    steps: { scan: true, dupes: true, label: true, jev_labels: false, apply: true },
    jev_key: false,
    claude_cli: false,
    overrides: 0,
    job: { step: null, running: false, code: null, phase: null, phases: [], done: 0, total: 0, started: null, phase_started: null, timings: {}, log: [] },
    platform: "demo",
    file_manager: "file manager",
    picker_available: false,
    picker_reason: "",
  } // fmt: skip
}

/** In demo mode nothing may reach the server's API: the reference's `api()` refused, with a toast. The dialogs and the
 * setup card call the API client themselves, so the one place that sees every call is `fetch`. A refused call
 * answers 400 with the notice in the server's own error shape, so each component shows it where it shows any
 * failure. `onBlocked` (the toast) runs for a write; a read is refused without one, since the lightbox reads on
 * every photo. Returns the undo. */
export function installDemoGuard(onBlocked: (notice: string) => void): () => void {
  const real = globalThis.fetch
  globalThis.fetch = (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url
    if (!/^(https?:\/\/[^/]+)?\/api\//.test(url)) return real(input, init)
    const method = (init?.method ?? (typeof input === "object" && "method" in input ? input.method : "GET")).toUpperCase()
    if (method !== "GET") onBlocked(DEMO_NOTICE)
    return Promise.resolve(new Response(JSON.stringify({ error: DEMO_NOTICE }), { status: 400 }))
  }
  return () => {
    globalThis.fetch = real
  }
}

import type { components } from "./types"

type Schemas = components["schemas"]
export type AppState = Schemas["AppState"]
export type JobState = Schemas["JobState"]
export type CategoryIn = Schemas["CategoryIn"]
export type SortArgs = Schemas["SortIn"]
export type RunArgs = Schemas["RunIn"]
export type OpenArgs = Schemas["OpenIn"]

// The server's dict-returning routes carry no response schema, so these mirror what the routes build.
export interface PeekResult {
  source: string
  photos: number
  videos: number
  bytes: number
  /** Bare file names, "0000.jpg": the page reads them from /peek/. */
  previews: string[]
  suggested_dest: string
  preview_bytes_needed: number
  free_bytes: number
}
export interface PickResult {
  path: string | null
  reason: string
}
/** One inventory record, as `FileRecord.to_dict` writes it. `sha256` is what `getRecord` and `move` check. */
export interface FileRecord {
  id: number
  path: string
  name: string
  ext: string
  kind: "photo" | "video"
  bytes: number
  sha256: string
  w: number
  h: number
  duration: number
  phash?: string
  taken?: number
  geo?: [number, number]
  error?: string
}

/** What /api/events sends (photosorter/jobs.py). */
export type JobEvent =
  | { type: "phase_started"; phase: string }
  | { type: "progress"; phase: string; done: number; total: number }
  | { type: "log"; message: string }
  | { type: "job_finished"; step: string; code: number }

/** Every failure carries the server's own plain-words message. `status` is the HTTP status, or 0 when the
 * server could not be reached at all. Callers branch on `status` (409: the file changed under us, 400: a
 * bad request) and on `busy`, never on the wording. */
export class ApiError extends Error {
  readonly status: number
  /** Another job is already running, so this start was refused. */
  readonly busy: boolean
  constructor(message: string, status: number, busy = false) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.busy = busy
  }
}

export const UNREACHABLE = "Can't reach the Photo Sorter server. Is it still running?"

// shortcut: the server refuses a second job with the same 400 + {"error"} as every other bad request, with
// no code to tell them apart, so busy is recognised by JobBusy's sentence (jobs.py). Upgrade when the
// server gives that refusal its own status or code.
const BUSY = /is already running/

/** The server's two error shapes: routes send {"error": "words"}, the middleware and HTTPException send
 * {"detail": "words"}, and request validation sends {"detail": [{"msg": ...}]}. */
function messageOf(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const { error, detail } = body as { error?: unknown; detail?: unknown }
    if (typeof error === "string" && error) return error
    if (typeof detail === "string" && detail) return detail
    if (Array.isArray(detail)) {
      const msgs = detail.map((d) => (d && typeof d.msg === "string" ? d.msg : "")).filter(Boolean)
      if (msgs.length) return msgs.join(" ")
    }
  }
  return `The server could not do that (error ${status}).`
}

async function request<T>(method: "GET" | "POST", url: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(UNREACHABLE, 0)
  }
  let data: unknown = null
  try {
    data = await res.json()
  } catch {
    /* an empty or non-JSON body (a proxy's error page) falls through to the generic sentence */
  }
  if (!res.ok) {
    const message = messageOf(data, res.status)
    throw new ApiError(message, res.status, res.status === 400 && BUSY.test(message))
  }
  return data as T
}

const post = <T>(url: string, body?: unknown) => request<T>("POST", url, body ?? {})

export const getState = () => request<AppState>("GET", "/api/state")
export const getLabels = () => request<Record<string, string>>("GET", "/api/labels")
/** `sha` is the record's sha256 as the page last saw it: a 409 means the folder was rescanned since. */
export const getRecord = (id: number, sha: string) =>
  request<FileRecord>("GET", `/api/record/${id}?sha=${encodeURIComponent(sha)}`)
export const sort = (args: SortArgs) => post<AppState>("/api/sort", args)
export const run = (args: RunArgs) => post<AppState>("/api/run", args)
export const cancel = () => post<AppState>("/api/cancel")
export const peek = (source: string) => post<PeekResult>("/api/peek", { source })
export const saveCategories = (categories: CategoryIn[]) =>
  post<{ ok: true; count: number }>("/api/categories", { categories })
/** `sha` as for `getRecord`: the server refuses a move without it, and a 409 means the id is stale. */
export const move = (id: number, key: string, sha: string) => post<{ ok: true }>("/api/move", { id, key, sha })
export const open = (args: OpenArgs) => post<{ ok: true }>("/api/open", args)
export const pick = (prompt: string) => post<PickResult>("/api/pick", { prompt })

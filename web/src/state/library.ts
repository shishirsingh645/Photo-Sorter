import { ApiError, UNREACHABLE } from "../api/client"
import type { AppState, FileRecord } from "../api/client"

/** One inventory record plus where the sort put it. `sha256` is what the lightbox hands to getRecord and move. */
export interface LibraryItem extends FileRecord {
  cat?: string
  dupe: boolean
}

// Where the page reads its files from: /data, or /demo for ?demo (api/static.py mounts both). Set once, by App,
// before anything loads.
let base = "/data"
export const setLibraryBase = (b: "/data" | "/demo") => {
  base = b
}

// The static files the server mounts at /data (api/static.py). A 404 is just "not scanned yet" (null); any
// other failure, or a body that is not JSON, is a real load failure and says so rather than reading as empty.
async function getJSON(url: string): Promise<unknown> {
  let res: Response
  try {
    res = await fetch(url, { cache: "no-store" })
  } catch {
    throw new ApiError(UNREACHABLE, 0)
  }
  if (res.status === 404) return null
  if (!res.ok) throw new ApiError(`Could not load ${url} (error ${res.status}).`, res.status)
  try {
    return await res.json()
  } catch {
    throw new ApiError(`${url} could not be read. It may be damaged, so scan the folder again.`, res.status)
  }
}

/** The reference's loadLibrary: inventory.json, with each record's folder (labels.json, which /api/move
 * keeps in step) and whether dupes.json lists it as a duplicate. Kept here, not in client.ts. */
export async function loadLibrary(): Promise<LibraryItem[]> {
  const [inv, labels, dupes] = await Promise.all(
    ["inventory", "labels", "dupes"].map((n) => getJSON(`${base}/${n}.json`)),
  )
  const cats = (labels && typeof labels === "object" ? labels : {}) as Record<string, string>
  const dupeIds = new Set(((Array.isArray(dupes) ? dupes : []) as { dupes: number[] }[]).flatMap((g) => g.dupes))
  if (inv != null && !Array.isArray(inv)) throw new ApiError("/data/inventory.json is not a list of files. Scan the folder again.", 200)
  return ((inv ?? []) as FileRecord[]).map((r) => ({ ...r, cat: cats[r.id], dupe: dupeIds.has(r.id) }))
}

/** Whether a file belongs in a folder, as the reference's openFolder decides: its own files, or every duplicate
 * for "_dupes". */
export const inFolder = (it: { cat?: string; dupe: boolean }, key: string) =>
  key === "_dupes" ? it.dupe : !it.dupe && it.cat === key

/** What the reference's openFolder lists. */
export const folderItems = (items: LibraryItem[], key: string) => items.filter((i) => inFolder(i, key))

export const thumbOf = (it: { id: number }) => `${base}/thumbs/${it.id}.jpg`
/** The 72px copy the animation uses: small enough that hundreds can be on screen at once. */
export const miniOf = (it: { id: number }) => `${base}/mini/${it.id}.jpg`

/** What the board needs of a file (the slim index: spec 13.2), plus where the sort put it. The full record is
 * fetched only when a folder is opened. */
export interface SlimItem {
  id: number
  kind: "photo" | "video"
  bytes: number
  cat?: string
  dupe: boolean
}

const dupeIdsOf = (dupes: unknown) =>
  new Set(((Array.isArray(dupes) ? dupes : []) as { dupes: number[] }[]).flatMap((g) => g.dupes))

/** The reference's loadLibrary, on the slim index instead of the full inventory: slim.json, with each file's
 * folder (labels.json, left out for a run still in progress) and whether dupes.json lists it. */
export async function loadSlim(withLabels: boolean): Promise<SlimItem[]> {
  const [slim, labels, dupes] = await Promise.all(["slim", "labels", "dupes"].map((n) => getJSON(`${base}/${n}.json`)))
  if (slim != null && !Array.isArray(slim)) throw new ApiError(`${base}/slim.json is not a list of files. Scan the folder again.`, 200)
  const cats = (withLabels && labels && typeof labels === "object" ? labels : {}) as Record<string, string>
  const dupeIds = dupeIdsOf(dupes)
  return ((slim ?? []) as { id: number; kind: "photo" | "video"; bytes: number }[]).map((r) => ({
    id: r.id,
    kind: r.kind,
    bytes: r.bytes,
    cat: cats[r.id],
    dupe: dupeIds.has(r.id),
  }))
}

/** categories.json, which only the demo folder carries: a real run reads its folders from /api/state. */
export const loadCategories = async () => ((await getJSON(`${base}/categories.json`)) ?? []) as AppState["categories"]

/** dupes.json, which the duplicates phase writes: absent (an empty set) until then. */
export const loadDupeIds = async () => dupeIdsOf(await getJSON(`${base}/dupes.json`))

/** labels.json as the sort left it, hand moves included. */
export const loadLabelsFile = async () => ((await getJSON(`${base}/labels.json`)) ?? {}) as Record<string, string>

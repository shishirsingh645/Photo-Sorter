import { ApiError, UNREACHABLE } from "../api/client"
import type { FileRecord } from "../api/client"

/** One inventory record plus where the sort put it. `sha256` is what the lightbox hands to getRecord and move. */
export interface LibraryItem extends FileRecord {
  cat?: string
  dupe: boolean
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
    ["inventory", "labels", "dupes"].map((n) => getJSON(`/data/${n}.json`)),
  )
  const cats = (labels && typeof labels === "object" ? labels : {}) as Record<string, string>
  const dupeIds = new Set(((Array.isArray(dupes) ? dupes : []) as { dupes: number[] }[]).flatMap((g) => g.dupes))
  if (inv != null && !Array.isArray(inv)) throw new ApiError("/data/inventory.json is not a list of files. Scan the folder again.", 200)
  return ((inv ?? []) as FileRecord[]).map((r) => ({ ...r, cat: cats[r.id], dupe: dupeIds.has(r.id) }))
}

/** What the reference's openFolder lists: a folder's own files, or every duplicate for "_dupes". */
export const folderItems = (items: LibraryItem[], key: string) =>
  items.filter((i) => (key === "_dupes" ? i.dupe : !i.dupe && i.cat === key))

export const thumbOf = (it: LibraryItem) => `/data/thumbs/${it.id}.jpg`

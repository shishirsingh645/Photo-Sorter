import { ApiError, UNREACHABLE } from "../api/client"
import type { FileRecord } from "../api/client"

/** One inventory record plus where the sort put it. `sha256` is what the lightbox hands to getRecord and move. */
export interface LibraryItem extends FileRecord {
  cat?: string
  dupe: boolean
}

// The static files the server mounts at /data (api/static.py). A missing one is just "not scanned yet".
async function getJSON(url: string): Promise<unknown> {
  let res: Response
  try {
    res = await fetch(url, { cache: "no-store" })
  } catch {
    throw new ApiError(UNREACHABLE, 0)
  }
  if (!res.ok) return null
  return res.json().catch(() => null)
}

/** The reference's loadLibrary: inventory.json, with each record's folder (labels.json, which /api/move
 * keeps in step) and whether dupes.json lists it as a duplicate. Kept here, not in client.ts. */
export async function loadLibrary(): Promise<LibraryItem[]> {
  const [inv, labels, dupes] = await Promise.all(
    ["inventory", "labels", "dupes"].map((n) => getJSON(`/data/${n}.json`)),
  )
  const cats = (labels && typeof labels === "object" ? labels : {}) as Record<string, string>
  const dupeIds = new Set(((Array.isArray(dupes) ? dupes : []) as { dupes: number[] }[]).flatMap((g) => g.dupes))
  return (Array.isArray(inv) ? (inv as FileRecord[]) : []).map((r) => ({ ...r, cat: cats[r.id], dupe: dupeIds.has(r.id) }))
}

/** What the reference's openFolder lists: a folder's own files, or every duplicate for "_dupes". */
export const folderItems = (items: LibraryItem[], key: string) =>
  items.filter((i) => (key === "_dupes" ? i.dupe : !i.dupe && i.cat === key))

export const thumbOf = (it: LibraryItem) => `/data/thumbs/${it.id}.jpg`

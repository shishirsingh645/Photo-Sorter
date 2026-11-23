import type { SlimItem } from "./library"

/** The duplicates card is a made-up category (app.js: catBy._dupes); FolderCard exports the same key. */
export const REVIEW_KEY = "_dupes"

/** The reference's `targetOf`: a duplicate goes to review, and so does a file whose folder no longer exists. */
export const targetOf = (it: SlimItem, keys: ReadonlySet<string>) =>
  it.dupe ? REVIEW_KEY : it.cat !== undefined && keys.has(it.cat) ? it.cat : REVIEW_KEY

/** What has landed in each folder so far, and the counters the top row shows (the reference's `c.landed`,
 * `stats`, `released` and `landed`). Plain data: the player writes it, the page reads it after a frame. */
export class Landings {
  private lists = new Map<string, SlimItem[]>()
  photos = 0
  videos = 0
  dupes = 0
  /** Bytes the duplicates take up. */
  saved = 0
  /** Files that have finished landing. */
  landed = 0
  /** Files that have left the sphere (in flight or landed). */
  released = 0

  reset() {
    this.lists.clear()
    this.photos = this.videos = this.dupes = this.saved = this.landed = this.released = 0
  }

  land(key: string, it: SlimItem) {
    const list = this.lists.get(key)
    if (list) list.push(it)
    else this.lists.set(key, [it])
    if (it.dupe) {
      this.dupes++
      this.saved += it.bytes
    } else if (it.kind === "video") this.videos++
    else this.photos++
    this.landed++
  }

  count(key: string) {
    return this.lists.get(key)?.length ?? 0
  }

  /** The last `n` files to land in a folder, newest first: what its preview slots show. */
  recent(key: string, n: number): SlimItem[] {
    return (this.lists.get(key) ?? []).slice(-n).reverse()
  }

  /** How many of these folders have anything in them ("Folders made"). */
  made(keys: readonly string[]) {
    return keys.filter((k) => this.count(k) > 0).length
  }
}

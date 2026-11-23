/** Plays files out of the sphere and into their folder cards, for a live sort and for the replay: the reference's
 *  `release`, `land`, `tick` and the replay's `order`. It owns no React state. What the page shows, it reads from
 *  `landings` after `changed()` fires, and it tells the page when the last file has landed with `finished()`. */

import { Landings } from "../state/board"
import type { SlimItem } from "../state/library"
import { flyToSlot } from "./fly"
import type { FlySource } from "./fly"
import { startLoop } from "./loop"
import { releaseCount } from "./sphere"
import type { Sphere } from "./sphere"

/** The reference's `ease` (app.js 237), which spreads a replay: slow, then fast, then slow. */
const ease = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2)

/** What the player needs from the page. */
export interface PlayerHost {
  /** The full-viewport layer the flying thumbnails are appended to. */
  layer(): HTMLElement | null
  sphere(): Sphere | null
  /** The `n`th landing place of a folder card; the card wraps, as `c.queued++ % c.slots.length` does. */
  slot(key: string, n: number): HTMLElement | null
  /** Where a file with no tile flies from: the middle of the stage. */
  centre(): FlySource
  keyOf(it: SlimItem): string
  miniOf(it: SlimItem): string
  /** The landings changed; called at most once a frame. */
  changed(): void
  /** Every file has landed, in a replay or in a live finish. */
  finished(): void
}

type Run = "idle" | "live" | "replay"

export class Player {
  readonly landings = new Landings()
  private items: SlimItem[] = []
  private order: number[] = []
  private flown = new Set<number>()
  private queue: SlimItem[] = []
  private head = 0 // the queue is read from here; shift() on a 100,000-long array is not free
  private queued = new Set<number>()
  private cursor = new Map<string, number>()
  private run: Run = "idle"
  private finishing = false
  private dirty = false
  private t0 = 0
  private replayMs = 0
  private gen = 0 // a flight that lands after a reset belongs to the old board
  private unsubscribe: (() => void) | null = null

  constructor(private host: PlayerHost) {}

  /** The library the board is playing. */
  load(items: SlimItem[]) {
    this.items = items
    this.reset()
  }

  /** The reference's buildCards: every card empty, every file back in the sphere. */
  reset() {
    this.stop()
    this.gen++
    this.landings.reset()
    this.flown.clear()
    this.queue = []
    this.head = 0
    this.queued.clear()
    this.cursor.clear()
    this.finishing = false
    this.host.layer()?.replaceChildren()
    this.mark()
  }

  /** The reference's fillStatic: the finished result, with no animation. */
  fillStatic() {
    this.reset()
    const L = this.landings
    for (const it of this.items) {
      this.flown.add(it.id)
      L.released++
      L.land(this.host.keyOf(it), it)
    }
    this.dirty = false
    this.host.changed()
  }

  /** A live sort: labels arrive in batches through `enqueue`, and fly out a few at a time. */
  startLive() {
    this.reset()
    this.run = "live"
    this.subscribe()
  }

  /** A label has arrived for this file. A file already flown, or already waiting, is left alone. */
  enqueue(it: SlimItem) {
    if (this.flown.has(it.id) || this.queued.has(it.id)) return
    this.queued.add(it.id)
    this.queue.push(it)
  }

  /** The sort has ended and every remaining file is queued: celebrate once the last one lands. */
  finish() {
    this.finishing = true
    this.checkDone()
  }

  /** The replay: every file flies once, in a shuffled order, spread over `ms` along `ease`. */
  startReplay(ms: number) {
    this.reset()
    this.order = this.items.map((_, i) => i)
    for (let i = this.order.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[this.order[i], this.order[j]] = [this.order[j], this.order[i]]
    }
    this.run = "replay"
    this.replayMs = ms
    this.t0 = performance.now()
    this.subscribe()
  }

  has(id: number) {
    return this.flown.has(id) || this.queued.has(id)
  }

  /** Stops the loop and drops what is waiting. Files already in the air still land. */
  stop() {
    this.run = "idle"
    this.unsubscribe?.()
    this.unsubscribe = null
  }

  private subscribe() {
    this.unsubscribe ??= startLoop((_dt, now) => this.tick(now))
  }

  private mark() {
    this.dirty = true
  }

  private flush() {
    if (!this.dirty) return
    this.dirty = false
    this.host.changed()
  }

  private tick(now: number) {
    if (this.run === "replay") {
      const n = this.items.length
      const want = Math.min(n, Math.floor(n * ease(Math.min(1, (now - this.t0) / this.replayMs))))
      while (this.landings.released < want) this.release(this.items[this.order[this.landings.released]])
    } else if (this.run === "live" && this.head < this.queue.length) {
      // labels arrive in batches: spread them out so it flows
      const n = releaseCount(this.queue.length - this.head)
      for (let i = 0; i < n && this.head < this.queue.length; i++) this.release(this.queue[this.head++])
    }
    this.flush()
  }

  private release(it: SlimItem) {
    const L = this.landings
    L.released++ // counted first: the replay's while loop must advance even if the file was flown already
    if (this.flown.has(it.id)) return
    this.flown.add(it.id)
    const key = this.host.keyOf(it)
    const at = this.cursor.get(key) ?? 0
    this.cursor.set(key, at + 1)
    const slot = this.host.slot(key, at)
    const layer = this.host.layer()
    const sphere = this.host.sphere()
    const id = String(it.id) // the one string both tileFor and retire are given
    const tile = sphere?.tileFor(id)
    if (sphere && tile) sphere.retire(tile, id)
    if (!slot || !layer) return this.land(key, it, this.gen) // nowhere to fly to: it simply arrives
    const img = document.createElement("img")
    img.src = this.host.miniOf(it)
    img.alt = ""
    layer.append(img)
    const gen = this.gen
    flyToSlot(tile ?? this.host.centre(), slot, img, () => this.land(key, it, gen))
  }

  private land(key: string, it: SlimItem, gen: number) {
    if (gen !== this.gen) return
    this.landings.land(key, it)
    this.mark()
    this.checkDone()
  }

  private checkDone() {
    const done = this.landings.landed >= this.items.length
    const celebrate = (this.run === "replay" && done) || (this.run === "live" && this.finishing && done)
    if (!celebrate) return
    this.stop()
    this.flush()
    this.host.finished()
  }
}

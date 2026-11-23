/** The rotating thumbnail sphere. It owns its own <img> nodes and writes their
 *  transforms straight to the DOM every frame — no tile position ever reaches React. */

/** At most this many <img> nodes, however many files the library holds. */
const MAX_TILES = 320
const TILE_PX = 28

export type Tile = {
  el: HTMLImageElement
  /** unit-sphere position */
  x: number
  y: number
  z: number
  /** files still waiting to fly out of this tile */
  left: number
  /** last drawn screen position and scale, which fly.ts starts its arc from */
  sx: number
  sy: number
  s: number
  alive: boolean
}

export type Sphere = {
  tiles: Tile[]
  draw(dt: number): void
  tileFor(id: string): Tile | undefined
  /** `id` makes a repeat retire for the same file a no-op, like the reference's `flown` set. */
  retire(tile: Tile, id?: string): void
  clear(): void
}

/** Labels arrive in batches; spread each batch over frames so it flows. */
export const releaseCount = (queued: number) => Math.max(1, Math.ceil(queued / 45))

export function createSphere(container: HTMLElement, srcs: string[]): Sphere {
  container.replaceChildren()
  const total = srcs.length
  const T = Math.min(total, MAX_TILES)
  const golden = Math.PI * (3 - Math.sqrt(5))
  const tiles: Tile[] = []

  for (let i = 0; i < T; i++) {
    const y = 1 - (i / Math.max(1, T - 1)) * 2,
      r = Math.sqrt(1 - y * y),
      th = golden * i
    const el = document.createElement("img")
    el.src = srcs[i]
    el.alt = ""
    Object.assign(el.style, {
      position: "absolute",
      left: "0",
      top: "0",
      width: `${TILE_PX}px`,
      height: `${TILE_PX}px`,
      borderRadius: "4px",
      willChange: "transform",
      backfaceVisibility: "hidden",
    })
    container.append(el)
    // files are handed out round-robin, so tile i carries every file whose index ≡ i (mod T)
    tiles.push({
      el,
      x: Math.cos(th) * r,
      y,
      z: Math.sin(th) * r,
      left: Math.floor((total - i - 1) / T) + 1,
      sx: 0,
      sy: 0,
      s: 1,
      alive: true,
    })
  }

  const owner = new Map<string, Tile>()
  const flown = new Set<string>()
  let next = 0
  let rot = 0

  const sphere: Sphere = {
    tiles,

    draw(dt) {
      if (!tiles.length) return
      rot += dt * 0.00035
      const tilt = Math.sin(performance.now() / 4000) * 0.35
      const r = container.getBoundingClientRect()
      // the reference pulls the sphere up and in while a sort runs; Stage puts the mode here
      const running = container.dataset.mode === "running"
      // viewport coordinates, as in the reference, so tile positions and slot rects
      // share one frame — the container is a full-viewport fixed layer (see Stage)
      const cx = r.left + r.width / 2,
        cy = r.top + r.height * (running ? 0.42 : 0.5),
        R = Math.min(r.width, r.height) * (running ? 0.32 : 0.36)
      const ca = Math.cos(rot),
        sa = Math.sin(rot),
        cb = Math.cos(tilt),
        sb = Math.sin(tilt)
      for (const t of tiles) {
        if (!t.alive) continue
        const x = t.x * ca + t.z * sa
        let z = -t.x * sa + t.z * ca
        const y = t.y * cb - z * sb
        z = t.y * sb + z * cb
        const depth = (z + 1) / 2
        t.s = 0.45 + depth * 0.75
        t.sx = cx + x * R
        t.sy = cy + y * R
        const half = TILE_PX / 2
        t.el.style.transform = `translate3d(${(t.sx - half).toFixed(1)}px,${(t.sy - half).toFixed(1)}px,0) scale(${t.s.toFixed(3)})`
        t.el.style.opacity = (0.2 + depth * 0.8).toFixed(2)
        t.el.style.zIndex = String(Math.round(depth * 100))
      }
    },

    /** The tile a file flies out of. Files share tiles once there are more files than tiles. */
    tileFor(id) {
      if (!tiles.length) return undefined
      let t = owner.get(id)
      if (!t) {
        t = tiles[next++ % tiles.length]
        owner.set(id, t)
      }
      return t
    },

    /** One of the tile's files has flown; the tile goes dark only when its last one has. */
    retire(tile, id) {
      if (id !== undefined) {
        if (flown.has(id)) return
        flown.add(id)
      }
      if (--tile.left <= 0) {
        tile.alive = false
        tile.el.style.opacity = "0"
      }
    },

    clear() {
      container.replaceChildren()
      tiles.length = 0
      owner.clear()
      flown.clear()
    },
  }
  // place every tile now, so none paints stacked at 0,0 until the first frame
  sphere.draw(0)
  return sphere
}

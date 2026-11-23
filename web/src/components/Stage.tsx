import { useEffect, useRef } from "react"
import { createSphere, type Sphere } from "../anim/sphere"
import { startLoop } from "../anim/loop"

/** Plan 3's modes, typed structurally — the reducer that owns them lives in Task 2. */
type Mode = "loading" | "setup" | "running" | "done"

/** Anything carrying a thumbnail URL; the sphere needs nothing else from an item. */
export type StageItem = { mini: string }

/**
 * The sphere's host layer. It subscribes to the shared frame loop and tears both
 * the subscription and the tiles down on unmount. Tile positions are written
 * straight to the DOM inside sphere.ts and never pass through React.
 */
export function Stage({
  mode,
  items,
  onSphere,
  anchor,
}: {
  mode: Mode
  items: StageItem[]
  /** Called with the live sphere after each build and with null on teardown; later tasks fly files out of it. */
  onSphere?: (s: Sphere | null) => void
  /** The box the sphere centres and sizes itself on (the reference's #stage). Read every frame; the layer
   *  itself is the whole viewport, which is where it would otherwise measure. */
  anchor?: () => DOMRect | null
}) {
  const host = useRef<HTMLDivElement>(null)
  const cb = useRef(onSphere)
  cb.current = onSphere
  const anchorRef = useRef(anchor)
  anchorRef.current = anchor

  // Rebuild only when the thumbnail list really changes: a reducer that hands over a new
  // `items` array per SSE event must not reset retired tiles and mid-flight mappings.
  const prev = useRef<string[]>([])
  const next = items.map(it => it.mini)
  if (next.length !== prev.current.length || next.some((u, i) => u !== prev.current[i])) prev.current = next
  const srcs = prev.current

  useEffect(() => {
    const el = host.current
    if (!el) return
    // like the reference, show a random 320 rather than the first 320 in caller order
    const shuffled = [...srcs]
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
    }
    const sphere = createSphere(el, shuffled, () => anchorRef.current?.() ?? null)
    const stop = startLoop(dt => sphere.draw(dt))
    cb.current?.(sphere)
    return () => {
      stop()
      sphere.clear()
      cb.current?.(null)
    }
  }, [srcs])

  return (
    <div
      ref={host}
      data-mode={mode}
      aria-hidden="true"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 2,
        pointerEvents: "none",
        opacity: mode === "setup" ? 0.3 : 1,
        transition: "opacity var(--dur-4)",
      }}
    />
  )
}

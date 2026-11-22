import { useEffect, useRef } from "react"
import { createSphere } from "../anim/sphere"
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
export function Stage({ mode, items }: { mode: Mode; items: StageItem[] }) {
  const host = useRef<HTMLDivElement>(null)

  // `items` must be a stable array: a new one rebuilds all 320 tiles
  useEffect(() => {
    const el = host.current
    if (!el) return
    const sphere = createSphere(
      el,
      items.map(it => it.mini),
    )
    const stop = startLoop(dt => sphere.draw(dt))
    return () => {
      stop()
      sphere.clear()
    }
  }, [items])

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

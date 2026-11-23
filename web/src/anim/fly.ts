/** The arc a thumbnail flies along, from its place on the sphere into a folder slot. */

import type { Tile } from "./sphere"

/** Only what the arc needs: where the tile was last drawn and how big it was. */
export type FlySource = Pick<Tile, "sx" | "sy" | "s">

const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches

/**
 * `img` must already be in a full-viewport fixed overlay (the fly layer); flyToSlot
 * positions and sizes it, animates it to `slotEl`, then removes it and calls `onLand`.
 */
export function flyToSlot(
  tile: FlySource,
  slotEl: HTMLElement,
  img: HTMLImageElement,
  onLand: () => void,
) {
  const to = slotEl.getBoundingClientRect()
  const s = 28 * (tile.s || 1)
  // the arc's keyframes are translate offsets from 0,0, so the img must be pinned there itself
  Object.assign(img.style, { position: "absolute", left: "0", top: "0", width: `${s}px`, height: `${s}px` })

  if (reducedMotion()) {
    img.remove()
    onLand()
    return
  }

  const mx = (tile.sx + to.left) / 2 + (Math.random() - 0.5) * 120
  const my = (tile.sy + to.top) / 2 - 60 - Math.random() * 80
  const a = img.animate(
    [
      { transform: `translate3d(${tile.sx - s / 2}px,${tile.sy - s / 2}px,0) scale(1)` },
      {
        transform: `translate3d(${mx - s / 2}px,${my - s / 2}px,0) scale(1.2) rotate(${(Math.random() - 0.5) * 50}deg)`,
        offset: 0.45,
      },
      { transform: `translate3d(${to.left}px,${to.top}px,0) scale(${to.width / s})` },
    ],
    { duration: 650 + Math.random() * 400, easing: "cubic-bezier(.55,0,.25,1)" },
  )
  a.onfinish = () => {
    img.remove()
    onLand()
  }
}

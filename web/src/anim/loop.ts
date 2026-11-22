/** The one requestAnimationFrame loop. Every animated thing subscribes here;
 *  nothing starts a frame loop of its own (the reference's single `tick`). */

export type Frame = (dt: number, now: number) => void

const subs = new Set<Frame>()
let raf = 0
let last = 0

function tick(now: number) {
  const dt = now - last
  last = now
  for (const fn of [...subs]) fn(dt, now)
  raf = subs.size ? requestAnimationFrame(tick) : 0
}

/** Subscribe to the shared loop; returns the unsubscribe for this one callback. */
export function startLoop(fn: Frame): () => void {
  subs.add(fn)
  if (!raf) {
    last = performance.now()
    raf = requestAnimationFrame(tick)
  }
  return () => {
    subs.delete(fn)
  }
}

/** Drop every subscriber and cancel the frame. */
export function stopLoop() {
  subs.clear()
  if (raf) cancelAnimationFrame(raf)
  raf = 0
}

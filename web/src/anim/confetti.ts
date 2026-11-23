/** The finish burst. A plain canvas, 200 paper rectangles, on the shared frame loop. */

import { startLoop } from "./loop"

const SWATCHES = ["--brand-solid", "--green", "--accent", "--faint", "--ink"]

/** The theme's own colours, so the burst follows light/dark without hard-coded hex. */
function themeColors() {
  const css = getComputedStyle(document.documentElement)
  return SWATCHES.map(v => css.getPropertyValue(v).trim()).filter(Boolean)
}

export function burstConfetti(
  canvas: HTMLCanvasElement,
  origin: { x: number; y: number },
  colors: string[] = themeColors(),
) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return
  const ctx = canvas.getContext("2d")
  if (!ctx || !colors.length) return

  const dpr = devicePixelRatio || 1
  canvas.width = innerWidth * dpr
  canvas.height = innerHeight * dpr
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  const ps = Array.from({ length: 200 }, () => ({
    x: origin.x,
    y: origin.y - 40,
    vx: (Math.random() - 0.5) * 14,
    vy: -Math.random() * 13 - 3,
    w: 5 + Math.random() * 5,
    h: 3 + Math.random() * 4,
    r: Math.random() * 6,
    vr: (Math.random() - 0.5) * 0.3,
    c: colors[Math.floor(Math.random() * colors.length)],
  }))

  const start = performance.now()
  const stop = startLoop((_dt, now) => {
    ctx.clearRect(0, 0, innerWidth, innerHeight)
    const a = Math.max(0, 1 - (now - start) / 3200)
    if (a <= 0) {
      stop()
      return
    }
    for (const p of ps) {
      p.vy += 0.32
      p.vx *= 0.985
      p.x += p.vx
      p.y += p.vy
      p.r += p.vr
      ctx.save()
      ctx.translate(p.x, p.y)
      ctx.rotate(p.r)
      ctx.globalAlpha = a
      ctx.fillStyle = p.c
      ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h)
      ctx.restore()
    }
  })
}

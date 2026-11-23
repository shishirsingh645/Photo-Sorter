import { describe, expect, it } from "vitest"
import css from "./components.css?raw"

describe("components.css", () => {
  // No component owns this block, so each task assumed another did; this is what notices if it goes missing again.
  it("carries the reference's reduced-motion block: 1 ms durations, and no entrance animation", () => {
    const at = css.indexOf("@media (prefers-reduced-motion: reduce)")
    expect(at).toBeGreaterThan(-1)
    const block = css.slice(at)
    expect(block).toContain("animation-duration: 1ms !important")
    expect(block).toContain("transition-duration: 1ms !important")
    expect(block).toContain("animation-iteration-count: 1 !important")
    expect(block).toMatch(/\.mx-rise \{ animation: none; \}/)
  })
})

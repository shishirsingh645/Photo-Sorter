import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { Topbar } from "./Topbar"
import type { TopbarProps } from "./Topbar"

const props = (over: Partial<TopbarProps> = {}): TopbarProps => ({
  mode: "setup",
  pill: { kind: null, text: "Choose your photos" },
  onNewSort: vi.fn(),
  onSortWithClaude: vi.fn(),
  ...over,
})

beforeEach(() => localStorage.clear())
afterEach(() => {
  localStorage.clear()
  delete document.body.dataset.mode
  delete document.documentElement.dataset.theme
})

describe("Topbar", () => {
  it("offers New sort only when the sort is done", () => {
    const { rerender } = render(<Topbar {...props({ mode: "setup" })} />)
    expect(screen.queryByRole("button", { name: /new sort/i })).toBeNull()
    for (const mode of ["loading", "running"] as const) {
      rerender(<Topbar {...props({ mode })} />)
      expect(screen.queryByRole("button", { name: /new sort/i })).toBeNull()
    }
    rerender(<Topbar {...props({ mode: "done" })} />)
    expect(screen.getByRole("button", { name: /new sort/i })).toBeInTheDocument()
  })

  it("carries no folder buttons: those belong to the title row", () => {
    render(<Topbar {...props({ mode: "done" })} />)
    expect(screen.queryByRole("button", { name: /edit folders/i })).toBeNull()
    expect(screen.queryByRole("button", { name: /open sorted/i })).toBeNull()
  })

  it("fires the two action callbacks", () => {
    const p = props({ mode: "done" })
    render(<Topbar {...p} />)
    fireEvent.click(screen.getByRole("button", { name: /new sort/i }))
    fireEvent.click(screen.getByRole("button", { name: /sort with claude/i }))
    expect(p.onNewSort).toHaveBeenCalledTimes(1)
    expect(p.onSortWithClaude).toHaveBeenCalledTimes(1)
  })

  it("shows the pill text", () => {
    render(<Topbar {...props({ pill: { kind: "busy", text: "Finding duplicates" } })} />)
    expect(screen.getByText("Finding duplicates")).toBeInTheDocument()
  })

  it("mirrors the mode onto <body> on the first render, follows changes, and removes it on unmount", () => {
    const { rerender, unmount } = render(<Topbar {...props({ mode: "setup" })} />)
    expect(document.body.dataset.mode).toBe("setup")
    rerender(<Topbar {...props({ mode: "running" })} />)
    expect(document.body.dataset.mode).toBe("running")
    unmount()
    expect(document.body.dataset.mode).toBeUndefined()
  })

  it("labels the theme button for the mode it would switch to, and flips it on click", () => {
    localStorage.setItem("theme", "dark")
    render(<Topbar {...props()} />)
    const btn = screen.getByRole("button", { name: "Switch to light mode" })
    fireEvent.click(btn)
    expect(screen.getByRole("button", { name: "Switch to dark mode" })).toBeInTheDocument()
    expect(document.documentElement.dataset.theme).toBe("light")
  })
})

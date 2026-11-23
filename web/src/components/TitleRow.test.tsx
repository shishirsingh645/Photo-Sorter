import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { TitleRow } from "./TitleRow"
import type { TitleRowProps } from "./TitleRow"

const props = (over: Partial<TitleRowProps> = {}): TitleRowProps => ({
  total: 1136,
  source: "~/Pictures/Camera roll",
  showTotal: true,
  onEditFolders: vi.fn(),
  onOpenSorted: vi.fn(),
  canOpenSorted: true,
  ...over,
})

describe("TitleRow", () => {
  it("shows the title, the formatted total and the source", () => {
    render(<TitleRow {...props()} />)
    expect(screen.getByRole("heading", { name: "Sorting my camera roll" })).toBeInTheDocument()
    expect(screen.getByText("1,136")).toBeInTheDocument()
    expect(screen.getByText("~/Pictures/Camera roll")).toBeInTheDocument()
  })

  it("hides the total until there is something to count", () => {
    render(<TitleRow {...props({ showTotal: false })} />)
    expect(screen.queryByText("1,136")).toBeNull()
  })

  it("offers Open sorted folder only when a sorted folder can be opened", () => {
    const { rerender } = render(<TitleRow {...props({ canOpenSorted: false })} />)
    expect(screen.queryByRole("button", { name: /open sorted folder/i })).toBeNull()
    rerender(<TitleRow {...props({ canOpenSorted: true })} />)
    expect(screen.getByRole("button", { name: /open sorted folder/i })).toBeInTheDocument()
  })

  it("always offers Edit folders and fires both callbacks", () => {
    const p = props()
    render(<TitleRow {...p} />)
    screen.getByRole("button", { name: /edit folders/i }).click()
    screen.getByRole("button", { name: /open sorted folder/i }).click()
    expect(p.onEditFolders).toHaveBeenCalledTimes(1)
    expect(p.onOpenSorted).toHaveBeenCalledTimes(1)
  })
})

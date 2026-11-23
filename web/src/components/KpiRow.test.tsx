import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { KpiRow } from "./KpiRow"
import type { KpiRowProps } from "./KpiRow"

const base: KpiRowProps = {
  checked: 1136, photos: 800, videos: 300, foldersMade: 7, foldersTotal: 12, dupes: 36, saved: 262_000_000, progress: 40,
} // fmt: skip

describe("KpiRow", () => {
  it("shows the six figures with thousands separators and a made/total folder count", () => {
    render(<KpiRow {...base} />)
    expect(screen.getByText("1,136")).toBeInTheDocument()
    expect(screen.getByText("800")).toBeInTheDocument()
    expect(screen.getByText("300")).toBeInTheDocument()
    expect(screen.getByText("7")).toBeInTheDocument()
    expect(screen.getByText("/12")).toBeInTheDocument()
    expect(screen.getByText("36")).toBeInTheDocument()
  })

  it("formats space saved as MB below a gigabyte and GB above", () => {
    const { rerender } = render(<KpiRow {...base} saved={262_000_000} />)
    expect(screen.getByText("262 MB")).toBeInTheDocument()
    rerender(<KpiRow {...base} saved={2_100_000_000} />)
    expect(screen.getByText("2.1 GB")).toBeInTheDocument()
  })

  it("draws the progress bar at the given percentage, clamped, and marks it done at 100", () => {
    const { rerender } = render(<KpiRow {...base} progress={40} />)
    const bar = screen.getByRole("progressbar")
    expect(bar).toHaveAttribute("aria-valuenow", "40")
    expect(bar.firstElementChild).toHaveStyle({ width: "40%" })
    expect(bar).toHaveAttribute("data-done", "false")

    rerender(<KpiRow {...base} progress={250} />)
    expect(screen.getByRole("progressbar").firstElementChild).toHaveStyle({ width: "100%" })
    expect(screen.getByRole("progressbar")).toHaveAttribute("data-done", "true")
  })

  it("says photos & videos until the library size is known, then the size in total", () => {
    const { rerender } = render(<KpiRow {...base} />)
    expect(screen.getByText("photos & videos")).toBeInTheDocument()
    rerender(<KpiRow {...base} totalBytes={10_700_000_000} />)
    expect(screen.getByText("10.7 GB in total")).toBeInTheDocument()
    expect(screen.queryByText("photos & videos")).toBeNull()
  })
})

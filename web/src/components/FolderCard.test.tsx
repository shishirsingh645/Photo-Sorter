import { createRef } from "react"
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { fmtSize } from "../format"
import { FolderCard } from "./FolderCard"
import type { FolderCardHandle } from "./FolderCard"

const docs = { key: "documents", label: "Documents & receipts", emoji: "📄" }
const dupes = { key: "_dupes", label: "Duplicates", emoji: "🗂️" }

describe("FolderCard", () => {
  it("renders twelve slots on a normal card and twenty-four on the duplicates card", () => {
    const normal = createRef<FolderCardHandle>()
    const { unmount } = render(<FolderCard ref={normal} category={docs} count={0} slots={[]} onOpen={vi.fn()} />)
    const slots = screen.getAllByTestId("slot")
    expect(slots).toHaveLength(12)
    // the seam fly.ts relies on: one ref per slot, the slot elements themselves, in order
    expect(normal.current?.slotRefs).toHaveLength(12)
    slots.forEach((el, i) => expect(normal.current?.slotRefs[i]).toBe(el))
    unmount()

    const wide = createRef<FolderCardHandle>()
    render(<FolderCard ref={wide} category={dupes} count={0} slots={[]} onOpen={vi.fn()} />)
    expect(screen.getAllByTestId("slot")).toHaveLength(24)
    expect(wide.current?.slotRefs).toHaveLength(24)
    expect(wide.current?.slotRefs.every(el => el instanceof HTMLDivElement)).toBe(true)
  })

  it("truncates a long folder name and keeps the full name as a tooltip", () => {
    render(<FolderCard category={docs} count={0} slots={[]} onOpen={vi.fn()} />)
    expect(screen.getByTitle("Documents & receipts")).toBeInTheDocument()
    expect(screen.getByTitle("Documents & receipts")).toHaveTextContent("Documents & receipts")
  })

  it("hides the count badge until the first file lands", () => {
    const { rerender } = render(<FolderCard category={docs} count={0} slots={[]} onOpen={vi.fn()} />)
    const badge = screen.getByText("0")
    expect(badge).toHaveAttribute("data-on", "false")
    expect(badge).toHaveAttribute("aria-hidden", "true")

    rerender(<FolderCard category={docs} count={1} slots={["/a.jpg"]} onOpen={vi.fn()} />)
    expect(screen.getByText("1")).toHaveAttribute("data-on", "true")
    expect(screen.getByText("1")).toHaveAttribute("aria-hidden", "false")
  })

  it("fills slots from the preview list and leaves the rest empty", () => {
    render(<FolderCard category={docs} count={2} slots={["/a.jpg", "/b.jpg"]} onOpen={vi.fn()} />)
    const slots = screen.getAllByTestId("slot")
    expect(slots[0].querySelector("img")).toHaveAttribute("src", "/a.jpg")
    expect(slots[1].querySelector("img")).toHaveAttribute("src", "/b.jpg")
    expect(slots[2].querySelector("img")).toBeNull()
  })

  it("passes its category to onOpen when clicked", () => {
    const onOpen = vi.fn()
    render(<FolderCard category={docs} count={3} slots={[]} onOpen={onOpen} />)
    screen.getByRole("button", { name: /documents & receipts folder/i }).click()
    expect(onOpen).toHaveBeenCalledWith(docs)
  })

  it("formats space saved as MB below a gigabyte and GB above", () => {
    expect(fmtSize(262_000_000)).toBe("262 MB")
    expect(fmtSize(2_100_000_000)).toBe("2.1 GB")
    expect(fmtSize(0)).toBe("0 MB")
  })
})

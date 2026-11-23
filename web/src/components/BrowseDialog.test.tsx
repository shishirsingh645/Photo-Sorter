import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  getRecord: vi.fn(),
  open: vi.fn(),
}))
import { ApiError, getRecord, open } from "../api/client"
import type { LibraryItem } from "../state/library"
import { BrowseDialog } from "./BrowseDialog"

const make = (n: number, kind: "photo" | "video" = "photo"): LibraryItem[] =>
  Array.from({ length: n }, (_, i) => ({
    id: i, path: `/pics/${i}.jpg`, name: `IMG_${i}.jpg`, ext: ".jpg", kind, bytes: 2_000_000,
    sha256: `sha${i}`, w: 4, h: 3, duration: kind === "video" ? 12.4 : 0, cat: "beach", dupe: false,
  })) // fmt: skip
const categories = [{ key: "beach", kind: "photo", label: "Beach", emoji: "🏖️" }]

const props = {
  folder: { key: "beach", label: "Beach", emoji: "🏖️" },
  categories,
  fileManager: "File Explorer",
  sorted: true,
  onMoved: vi.fn(),
  onClose: vi.fn(),
}

describe("BrowseDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(open).mockResolvedValue({ ok: true })
    vi.mocked(getRecord).mockImplementation(async (id) => make(id + 1)[id])
  })
  afterEach(cleanup)

  it("shows 120 thumbnails at a time with a Show more button", () => {
    render(<BrowseDialog {...props} items={make(5000)} />)
    expect(screen.getAllByRole("img")).toHaveLength(120)
    expect(screen.getByText("5,000")).toBeInTheDocument() // the folder's whole count, not the page's

    fireEvent.click(screen.getByRole("button", { name: "Show 120 more" }))
    expect(screen.getAllByRole("img")).toHaveLength(240)
  })

  it("offers only what is left on the last page, then no button", () => {
    render(<BrowseDialog {...props} items={make(130)} />)
    expect(screen.getAllByRole("img")).toHaveLength(120)
    fireEvent.click(screen.getByRole("button", { name: "Show 10 more" }))
    expect(screen.getAllByRole("img")).toHaveLength(130)
    expect(screen.queryByRole("button", { name: /more/ })).toBeNull()
  })

  it("loads each thumbnail lazily from the static previews", () => {
    render(<BrowseDialog {...props} items={make(2)} />)
    const [first] = screen.getAllByRole("img")
    expect(first).toHaveAttribute("src", "/data/thumbs/0.jpg")
    expect(first).toHaveAttribute("loading", "lazy")
  })

  it("says the file manager's real name for the platform", () => {
    render(<BrowseDialog {...props} items={make(3)} />)
    expect(screen.getByRole("button", { name: /show in file explorer/i })).toBeInTheDocument()
    expect(screen.queryByText(/finder/i)).toBeNull()

    cleanup()
    render(<BrowseDialog {...props} fileManager="Finder" items={make(3)} />)
    expect(screen.getByRole("button", { name: "Show in Finder" })).toBeInTheDocument()
  })

  it("asks the server to open the folder under the name it has on disk", () => {
    const { rerender } = render(<BrowseDialog {...props} folder={{ key: "fd", label: "Food & Drink?" }} items={make(1)} />)
    fireEvent.click(screen.getByRole("button", { name: /show in file explorer/i }))
    expect(open).toHaveBeenLastCalledWith({ folder: "Food and Drink-" })

    rerender(<BrowseDialog {...props} folder={{ key: "_dupes", label: "Duplicates" }} items={make(1)} />)
    fireEvent.click(screen.getByRole("button", { name: /show in file explorer/i }))
    expect(open).toHaveBeenLastCalledWith({ folder: "_Review/duplicates" })
  })

  it("offers no file-manager button before anything has been sorted", () => {
    render(<BrowseDialog {...props} sorted={false} items={make(3)} />)
    expect(screen.queryByRole("button", { name: /show in/i })).toBeNull()
  })

  it("shows an empty-folder message rather than a blank grid", () => {
    render(<BrowseDialog {...props} items={[]} />)
    expect(screen.getByText("Nothing in this folder yet.")).toBeInTheDocument()
    expect(screen.queryAllByRole("img")).toHaveLength(0)
    expect(screen.queryByRole("button", { name: /more/ })).toBeNull()
  })

  it("marks a video thumbnail with its length", () => {
    render(<BrowseDialog {...props} items={make(2, "video")} />)
    expect(screen.getAllByText("▶ 12s")).toHaveLength(2)
  })

  it("reports a refused open in words instead of failing silently", async () => {
    vi.mocked(open).mockRejectedValue(new ApiError("That folder does not exist inside the sorted folder.", 400))
    render(<BrowseDialog {...props} items={make(1)} />)
    fireEvent.click(screen.getByRole("button", { name: /show in file explorer/i }))
    expect(await screen.findByRole("alert")).toHaveTextContent("That folder does not exist inside the sorted folder.")
  })
})

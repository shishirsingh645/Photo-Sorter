import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useState } from "react"
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  getRecord: vi.fn(),
  move: vi.fn(),
  open: vi.fn(),
}))
import { ApiError, getRecord, move, open } from "../api/client"
import type { LibraryItem } from "../state/library"
import { BrowseDialog } from "./BrowseDialog"
import { Lightbox } from "./Lightbox"

const item = (id: number, kind: "photo" | "video" = "photo", cat = "beach"): LibraryItem => ({
  id, path: `/pics/${id}`, name: `IMG_${id}`, ext: ".jpg", kind, bytes: 2_000_000, sha256: `sha${id}`,
  w: 4, h: 3, duration: 0, cat, dupe: false,
}) // fmt: skip
const categories = [
  { key: "beach", kind: "photo", label: "Beach", emoji: "🏖️" },
  { key: "trips", kind: "photo", label: "Trips", emoji: "✈️" },
  { key: "clips", kind: "video", label: "Clips", emoji: "🎬" },
]
const REFUSED_STALE = "The folder was rescanned since this page loaded. Reload the page."

function Host({ items, start = 0, onMoved = vi.fn() }: { items: LibraryItem[]; start?: number; onMoved?: () => void }) {
  const [index, setIndex] = useState(start)
  return <Lightbox items={items} index={index} categories={categories} onIndex={setIndex} onMoved={onMoved} onClose={vi.fn()} />
}
const key = (k: string, target: Element = document.body) => fireEvent.keyDown(target, { key: k })

describe("Lightbox", () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(getRecord).mockImplementation(async (id) => item(id))
    vi.mocked(move).mockResolvedValue({ ok: true })
    vi.mocked(open).mockResolvedValue({ ok: true })
  })
  afterEach(cleanup)

  it("moves between photos with the arrow keys and stops at both ends", () => {
    render(<Host items={[item(0), item(1), item(2)]} />)
    expect(screen.getByText(/1 of 3/)).toBeInTheDocument()

    key("ArrowLeft") // already at the start
    expect(screen.getByText(/1 of 3/)).toBeInTheDocument()
    key("ArrowRight")
    expect(screen.getByText(/2 of 3/)).toBeInTheDocument()
    key("ArrowRight")
    expect(screen.getByText(/3 of 3/)).toBeInTheDocument()
    key("ArrowRight") // already at the end
    expect(screen.getByText(/3 of 3/)).toBeInTheDocument()
    key("ArrowLeft")
    expect(screen.getByText(/2 of 3/)).toBeInTheDocument()

    // The on-screen arrows do the same, and also stop at the ends.
    fireEvent.click(screen.getByRole("button", { name: "Previous" }))
    fireEvent.click(screen.getByRole("button", { name: "Previous" }))
    expect(screen.getByText(/1 of 3/)).toBeInTheDocument()
  })

  it("opens with focus on the dialog, not on the Move to select", () => {
    render(<Host items={[item(0), item(1)]} />)
    expect(screen.getByRole("dialog")).toHaveFocus()
    expect(screen.getByRole("combobox", { name: "Move to folder" })).not.toHaveFocus()
  })

  it("navigates, and never moves the photo, when an arrow key is pressed with the select focused", () => {
    render(<Host items={[item(0), item(1), item(2)]} />)
    const select = screen.getByRole("combobox", { name: "Move to folder" })
    select.focus()

    // fireEvent returns false when preventDefault() was called: the browser must not also change the select.
    expect(key("ArrowRight", select)).toBe(false)
    expect(screen.getByText(/2 of 3/)).toBeInTheDocument()
    expect(key("ArrowLeft", select)).toBe(false)
    expect(screen.getByText(/1 of 3/)).toBeInTheDocument()
    expect(move).not.toHaveBeenCalled()
  })

  it("keeps navigating with the arrow keys after a move", async () => {
    render(<Host items={[item(0), item(1)]} />)
    const select = screen.getByRole("combobox", { name: "Move to folder" })
    select.focus()
    fireEvent.change(select, { target: { value: "trips" } })
    await screen.findByRole("status")
    key("ArrowRight", select)
    expect(screen.getByText(/2 of 2/)).toBeInTheDocument()
    expect(move).toHaveBeenCalledTimes(1) // only the deliberate move
  })

  it("shows that it is loading until the record arrives, then the photo", async () => {
    let arrive!: (r: LibraryItem) => void
    vi.mocked(getRecord).mockReturnValue(new Promise((res) => (arrive = res)))
    render(<Host items={[item(0)]} />)
    expect(screen.getByText("Loading…")).toBeInTheDocument()
    expect(screen.queryByRole("img")).toBeNull()
    arrive(item(0))
    expect(await screen.findByRole("img", { name: "IMG_0" })).toBeInTheDocument()
    expect(screen.queryByText("Loading…")).toBeNull()
  })

  it("moves a photo to another folder and reports it", async () => {
    const onMoved = vi.fn()
    const items = [item(7)]
    render(<Host items={items} onMoved={onMoved} />)
    const select = screen.getByRole("combobox", { name: "Move to folder" })
    expect(select).toHaveValue("beach")

    fireEvent.change(select, { target: { value: "trips" } })

    // The sha travels with the move: it is what stops a stale id misfiling a photo for good.
    expect(move).toHaveBeenCalledWith(7, "trips", "sha7")
    expect(await screen.findByRole("status")).toHaveTextContent("Moved to Trips. It moves on disk the next time you sort.")
    expect(onMoved).toHaveBeenCalledWith(items[0], "trips")
    expect(select).toHaveValue("trips")
  })

  it("tells a 409 from a 400 on a move: reload for the first, only the server's words for the second", async () => {
    const onMoved = vi.fn()
    render(<Host items={[item(1)]} onMoved={onMoved} />)
    const select = screen.getByRole("combobox", { name: "Move to folder" })

    vi.mocked(move).mockRejectedValueOnce(new ApiError(REFUSED_STALE, 409))
    fireEvent.change(select, { target: { value: "trips" } })
    const stale = await screen.findByRole("alert")
    expect(stale).toHaveTextContent(REFUSED_STALE)
    expect(within(stale).getByRole("button", { name: "Reload page" })).toBeInTheDocument()

    vi.mocked(move).mockRejectedValueOnce(new ApiError('There is no folder called "x".', 400))
    fireEvent.change(select, { target: { value: "trips" } })
    const refused = await screen.findByText(/The server refused that request/)
    expect(refused).toHaveTextContent('There is no folder called "x".')
    expect(within(screen.getByRole("alert")).queryByRole("button", { name: "Reload page" })).toBeNull()

    // A refused move changes nothing: the select still shows the folder the file is in.
    expect(select).toHaveValue("beach")
    expect(onMoved).not.toHaveBeenCalled()
  })

  it("offers only folders matching the file's kind in Move to", () => {
    const { rerender } = render(<Lightbox items={[item(1, "photo")]} index={0} categories={categories} onIndex={vi.fn()} onMoved={vi.fn()} onClose={vi.fn()} />)
    const labels = () => within(screen.getByRole("combobox", { name: "Move to folder" })).getAllByRole("option").map((o) => o.textContent)
    expect(labels()).toEqual([`${categories[0].emoji} Beach`, `${categories[1].emoji} Trips`])

    rerender(<Lightbox items={[item(2, "video", "clips")]} index={0} categories={categories} onIndex={vi.fn()} onMoved={vi.fn()} onClose={vi.fn()} />)
    expect(labels()).toEqual([`${categories[2].emoji} Clips`])
  })

  it("asks to choose a folder, rather than showing the first one, for a file that is in none", () => {
    render(<Lightbox items={[{ ...item(3), cat: undefined }]} index={0} categories={categories} onIndex={vi.fn()} onMoved={vi.fn()} onClose={vi.fn()} />)
    const select = screen.getByRole("combobox", { name: "Move to folder" })
    expect(select).toHaveValue("")
    expect(within(select).getByRole("option", { name: "Choose a folder" })).toBeDisabled()
  })

  it("loads the full record lazily when opened", async () => {
    const items = [item(4), item(5)]
    render(<BrowseDialog folder={{ key: "beach", label: "Beach" }} items={items} categories={categories} fileManager="File Explorer" sorted onMoved={vi.fn()} onClose={vi.fn()} />)
    expect(getRecord).not.toHaveBeenCalled() // a folder of thousands fetches nothing until a photo is opened

    fireEvent.click(screen.getByRole("button", { name: "IMG_5" }))
    expect(getRecord).toHaveBeenCalledTimes(1)
    expect(getRecord).toHaveBeenCalledWith(5, "sha5")

    // The photo itself is requested with the sha as well: the file route refuses a bare id.
    const photo = await vi.waitFor(() => {
      const p = document.querySelector("img[src^='/api/file/']") // not the thumbnails, which are /data/thumbs
      expect(p).not.toBeNull()
      return p!
    })
    expect(photo.getAttribute("src")).toBe("/api/file/5?sha=sha5")
    expect(photo).toHaveAttribute("alt", "IMG_5")

    key("ArrowLeft") // navigating fetches the next record, not before
    expect(getRecord).toHaveBeenLastCalledWith(4, "sha4")
    expect(getRecord).toHaveBeenCalledTimes(2)
  })

  it("does not show the photo when the record says the folder was rescanned", async () => {
    vi.mocked(getRecord).mockRejectedValue(new ApiError(REFUSED_STALE, 409))
    render(<Host items={[item(8)]} />)
    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent(REFUSED_STALE)
    expect(within(alert).getByRole("button", { name: "Reload page" })).toBeInTheDocument()
    expect(screen.queryByRole("img")).toBeNull()
    expect(screen.getByRole("button", { name: /show original/i })).toBeDisabled()
  })

  it("plays a video with controls instead of showing it as an image", async () => {
    render(<Host items={[item(9, "video", "clips")]} />)
    const video = await vi.waitFor(() => {
      const v = document.querySelector("video")
      expect(v).not.toBeNull()
      return v!
    })
    expect(video).toHaveAttribute("controls")
    expect(video.getAttribute("src")).toBe("/api/file/9?sha=sha9")
    expect(screen.queryByRole("img")).toBeNull()
  })

  it("shows the original through the file manager once the record is confirmed", async () => {
    render(<Host items={[item(6)]} />)
    const button = screen.getByRole("button", { name: /show original/i })
    await vi.waitFor(() => expect(button).toBeEnabled())
    fireEvent.click(button)
    expect(open).toHaveBeenCalledWith({ id: 6 })
  })

  it("in the demo shows the thumbnail itself, a video's too, and never asks for the record", () => {
    const at = (i: number) => (
      <Lightbox items={[item(3), item(9, "video", "clips")]} index={i} categories={categories} onIndex={vi.fn()} onMoved={vi.fn()} onClose={vi.fn()} demo />
    )
    const { rerender } = render(at(0))
    expect(screen.getByRole("img", { name: "IMG_3" })).toHaveAttribute("src", "/data/thumbs/3.jpg")
    expect(screen.queryByText("Loading…")).toBeNull()

    rerender(at(1))
    expect(screen.getByRole("img", { name: "IMG_9" })).toHaveAttribute("src", "/data/thumbs/9.jpg")
    expect(document.querySelector("video")).toBeNull() // the demo has no video files, only its thumbnail
    expect(getRecord).not.toHaveBeenCalled()
  })

  it("reaches the lightbox from the browse dialog's own demo flag", () => {
    render(<BrowseDialog folder={{ key: "beach", label: "Beach" }} items={[item(0)]} categories={categories} fileManager="File Explorer" sorted={false} onMoved={vi.fn()} onClose={vi.fn()} demo />)
    fireEvent.click(screen.getByRole("button", { name: "IMG_0" }))
    const lightbox = screen.getAllByRole("dialog")[1]
    expect(within(lightbox).getByRole("img", { name: "IMG_0" })).toHaveAttribute("src", "/data/thumbs/0.jpg")
    expect(getRecord).not.toHaveBeenCalled()
  })

  it("closes on Escape without closing the dialog under it, and returns focus to the thumbnail", async () => {
    render(<BrowseDialog folder={{ key: "beach", label: "Beach" }} items={[item(0), item(1)]} categories={categories} fileManager="File Explorer" sorted onMoved={vi.fn()} onClose={vi.fn()} />)
    const thumb = screen.getByRole("button", { name: "IMG_1" })
    thumb.focus()
    fireEvent.click(thumb)
    expect(screen.getAllByRole("dialog")).toHaveLength(2)
    expect(screen.getAllByRole("dialog")[1]).toHaveFocus() // the lightbox itself, not its select

    key("Escape")
    const dialogs = screen.getAllByRole("dialog")
    expect(dialogs).toHaveLength(1)
    expect(dialogs[0]).toHaveAccessibleName("Beach")
    expect(thumb).toHaveFocus()
  })
})

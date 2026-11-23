import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "../api/client"
import type { AppState, PeekResult } from "../api/client"
import * as client from "../api/client"
import { SetupCard } from "./SetupCard"
import type { Picked } from "./SetupCard"

vi.mock("../api/client", async (orig) => ({
  ...(await orig<typeof import("../api/client")>()),
  pick: vi.fn(),
  saveCategories: vi.fn(),
}))

const cat = (key: string, label: string, kind = "photo") => ({ key, kind, label, emoji: "📁", rule: label })
const state = (over: Partial<AppState> = {}): AppState =>
  ({
    categories: [cat("people", "People"), cat("other", "Other"), cat("clips", "Clips", "video"), cat("misc-video", "Misc video", "video")],
    source: null, limit: null, sorted: null, files: 0, bytes: 0,
    steps: { scan: false, dupes: false, label: false, jev_labels: false, apply: false },
    jev_key: false, claude_cli: true, overrides: 0,
    job: { running: false, done: 0, total: 0 },
    platform: "win32", file_manager: "Explorer", picker_available: true, picker_reason: "",
    ...over,
  }) as AppState // fmt: skip
const peek = (over: Partial<PeekResult> = {}): PeekResult => ({
  source: "D:\\Photos", photos: 90, videos: 10, bytes: 2e9, previews: 20,
  suggested_dest: "D:\\Photos (sorted)", preview_bytes_needed: 1e6, free_bytes: 1e12, ...over,
}) // fmt: skip
const none: Picked = { source: null, dest: null, peek: null }
const both: Picked = { source: "D:\\Photos", dest: "D:\\Photos (sorted)", peek: peek() }

const show = (s: AppState, p: Picked = none) => {
  const onChoose = vi.fn()
  const onStart = vi.fn()
  render(<SetupCard state={s} pick={p} onChoose={onChoose} onStart={onStart} />)
  return { onChoose, onStart }
}

beforeEach(() => vi.resetAllMocks())

describe("SetupCard", () => {
  it("shows a Choose folder button on every platform, Windows included", () => {
    show(state({ platform: "win32", picker_available: true }))
    expect(screen.getByRole("button", { name: /choose folder/i })).toBeInTheDocument()
  })

  it("never shows a mac path placeholder on Windows", () => {
    show(state({ platform: "win32", picker_available: false, picker_reason: "x" }))
    expect(screen.queryByPlaceholderText(/\/Users\//)).toBeNull()
    expect(screen.getByPlaceholderText("D:\\Pictures\\Camera roll")).toBeInTheDocument()
  })

  it("falls back to path entry with a reason when the picker is unavailable", () => {
    const { onChoose } = show(state({ picker_available: false, picker_reason: "No folder window on this server." }))
    expect(screen.queryByRole("button", { name: /choose folder/i })).toBeNull()
    expect(screen.getByText(/No folder window on this server\./)).toBeInTheDocument()
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "  D:\\Pics " } })
    fireEvent.click(screen.getByRole("button", { name: "Use" }))
    expect(onChoose).toHaveBeenCalledWith("source", "D:\\Pics")
  })

  it("offers the last used folder as a shortcut", () => {
    const { onChoose } = show(state({ source: "D:\\Last" }))
    fireEvent.click(screen.getByRole("button", { name: /last time: D:\\Last/i }))
    expect(onChoose).toHaveBeenCalledWith("source", "D:\\Last")
  })

  it("suggests '<source> (sorted)' as the destination", () => {
    const { onChoose } = show(state(), { source: "D:\\Photos", dest: null, peek: null })
    expect(screen.getByText("D:\\Photos (sorted)")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /next to my photos/i }))
    expect(onChoose).toHaveBeenCalledWith("dest", "D:\\Photos (sorted)")
  })

  it("warns when the disk cannot hold the previews", () => {
    show(state(), { ...both, peek: peek({ preview_bytes_needed: 5e9, free_bytes: 1e9 }) })
    expect(screen.getByText(/free space/i)).toHaveTextContent("5.0 GB")
  })

  it("shows the estimated time and the Claude labelling time for a large library", () => {
    // 3,000 files, 30 GB: scan 349 + dupes 38 + label 174 + apply 56 = 617 s
    show(state(), { ...both, peek: peek({ photos: 2500, videos: 500, bytes: 30e9 }) })
    expect(screen.getByText(/Usually about 10 min for 3,000 files/)).toBeInTheDocument()
    expect(screen.getByText(/Claude labelling takes about 3 min/)).toBeInTheDocument()
  })

  it("disables Start until both folders are chosen", () => {
    const { onStart } = show(state(), { source: "D:\\Photos", dest: null, peek: peek() })
    expect(screen.getByRole("button", { name: /start sorting/i })).toBeDisabled()
    expect(onStart).not.toHaveBeenCalled()
  })

  it("starts with the chosen labeller and sample size once both are chosen", () => {
    const { onStart } = show(state(), both)
    fireEvent.click(screen.getByRole("button", { name: /start sorting/i }))
    expect(onStart).toHaveBeenCalledWith({ labeler: "claude", limit: 0 })
  })

  it("adds and removes folders under Advanced", async () => {
    vi.mocked(client.saveCategories).mockResolvedValue({ ok: true, count: 0 })
    show(state(), both)
    fireEvent.click(screen.getByRole("button", { name: /advanced/i }))
    fireEvent.click(screen.getByRole("button", { name: "Remove People" }))
    await waitFor(() => expect(client.saveCategories).toHaveBeenCalledTimes(1))
    expect(vi.mocked(client.saveCategories).mock.calls[0][0].map((c) => c.key)).toEqual(["other", "clips", "misc-video"])
    expect(screen.queryByRole("button", { name: "Remove People" })).toBeNull() // gone at once, not after a refresh
  })

  it("keeps the new folder before the catch-all of its kind", async () => {
    vi.mocked(client.saveCategories).mockResolvedValue({ ok: true, count: 0 })
    show(state(), both)
    fireEvent.click(screen.getByRole("button", { name: /advanced/i }))
    fireEvent.click(screen.getByRole("button", { name: "Add a video folder" }))
    fireEvent.change(screen.getByLabelText("Folder name"), { target: { value: "Drone Shots!" } })
    fireEvent.click(screen.getByRole("button", { name: "Add" }))
    await waitFor(() => expect(client.saveCategories).toHaveBeenCalledTimes(1))
    const sent = vi.mocked(client.saveCategories).mock.calls[0][0]
    expect(sent.map((c) => c.key)).toEqual(["people", "other", "clips", "drone-shots", "misc-video"])
    expect(sent[3]).toMatchObject({ kind: "video", label: "Drone Shots!", emoji: "🎬", rule: "Drone Shots!" })
  })

  it("shows the PAID badge and token estimate for Jev", () => {
    show(state({ jev_key: true }), { ...both, peek: peek({ photos: 1000, videos: 0 }) })
    fireEvent.click(screen.getByRole("button", { name: /advanced/i }))
    expect(screen.getByText("PAID")).toBeInTheDocument()
    expect(screen.getByText(/about 980,000 tokens/)).toBeInTheDocument()
  })

  it("applies the picked folder, and says nothing when the window is simply closed", async () => {
    vi.mocked(client.pick).mockResolvedValueOnce({ path: "D:\\Chosen", reason: "" })
    const { onChoose } = show(state())
    fireEvent.click(screen.getByRole("button", { name: /choose folder/i }))
    await waitFor(() => expect(onChoose).toHaveBeenCalledWith("source", "D:\\Chosen"))
    vi.mocked(client.pick).mockResolvedValueOnce({ path: null, reason: "" })
    fireEvent.click(screen.getByRole("button", { name: /choose folder/i }))
    await waitFor(() => expect(client.pick).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("tells the user when a folder window is already open, and when the server is unreachable", async () => {
    vi.mocked(client.pick).mockRejectedValueOnce(new ApiError("A folder window is already open. Please use it, or close it first.", 409))
    show(state())
    fireEvent.click(screen.getByRole("button", { name: /choose folder/i }))
    expect(await screen.findByRole("alert")).toHaveTextContent("A folder window is already open")
    vi.mocked(client.pick).mockRejectedValueOnce(new ApiError(client.UNREACHABLE, 0))
    fireEvent.click(screen.getByRole("button", { name: /choose folder/i }))
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Can't reach the Photo Sorter server"))
  })

  it("moves to path entry with the server's reason when the picker turns out to be unavailable", async () => {
    vi.mocked(client.pick).mockResolvedValueOnce({ path: null, reason: "No display is available." })
    show(state())
    fireEvent.click(screen.getByRole("button", { name: /choose folder/i }))
    expect(await screen.findByRole("alert")).toHaveTextContent("No display is available.")
    expect(screen.getByPlaceholderText("D:\\Pictures\\Camera roll")).toBeInTheDocument()
  })
})

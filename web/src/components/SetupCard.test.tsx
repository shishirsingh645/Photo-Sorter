import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "../api/client"
import type { AppState, PeekResult } from "../api/client"
import * as client from "../api/client"
import { SetupCard } from "./SetupCard"
import type { Picked, SetupCardProps } from "./SetupCard"

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
  source: "D:\\Photos", photos: 90, videos: 10, bytes: 2e9, previews: [],
  suggested_dest: "D:\\Photos (sorted)", preview_bytes_needed: 1e6, free_bytes: 1e12, ...over,
}) // fmt: skip
const none: Picked = { source: null, dest: null, peek: null }
const both: Picked = { source: "D:\\Photos", dest: "D:\\Photos (sorted)", peek: peek() }

const show = (s: AppState, p: Picked = none, over: Partial<SetupCardProps> = {}) => {
  const onChoose = vi.fn()
  const onStart = vi.fn()
  const onLabeler = vi.fn()
  const onSample = vi.fn()
  const onCategoriesSaved = vi.fn()
  render(
    <SetupCard
      state={s} pick={p} labeler="claude" sample={false}
      onChoose={onChoose} onStart={onStart} onLabeler={onLabeler} onSample={onSample} onCategoriesSaved={onCategoriesSaved}
      {...over}
    />,
  ) // fmt: skip
  return { onChoose, onStart, onLabeler, onSample, onCategoriesSaved }
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

  it("shows Start only once both folders are chosen", () => {
    const { onStart } = show(state(), { source: "D:\\Photos", dest: null, peek: peek() })
    expect(screen.queryByRole("button", { name: /start sorting/i })).toBeNull()
    expect(onStart).not.toHaveBeenCalled()
  })

  it("shows no Start at all before a source is chosen", () => {
    show(state())
    expect(screen.queryByRole("button", { name: /start sorting/i })).toBeNull()
  })

  it("starts once both are chosen, and takes the labeller and sample from its props", () => {
    const { onStart } = show(state({ jev_key: true }), both, { labeler: "jev", sample: true })
    fireEvent.click(screen.getByRole("button", { name: /advanced/i }))
    expect(screen.getByRole("radio", { name: /jev/i })).toBeChecked()
    expect(screen.getByRole("checkbox")).toBeChecked()
    fireEvent.click(screen.getByRole("button", { name: /start sorting/i }))
    expect(onStart).toHaveBeenCalledTimes(1)
  })

  it("reports a labeller or sample change to its parent", () => {
    const { onLabeler, onSample } = show(state(), both)
    fireEvent.click(screen.getByRole("button", { name: /advanced/i }))
    fireEvent.click(screen.getByRole("radio", { name: /jev/i }))
    expect(onLabeler).toHaveBeenCalledWith("jev")
    fireEvent.click(screen.getByRole("checkbox"))
    expect(onSample).toHaveBeenCalledWith(true)
  })

  it("blocks a Claude start only when the server says the CLI is missing, and clears the notice on a labeller change", () => {
    const { onStart } = show(state({ claude_cli: false }), both)
    fireEvent.click(screen.getByRole("button", { name: /start sorting/i }))
    expect(onStart).not.toHaveBeenCalled()
    expect(screen.getByRole("alert")).toHaveTextContent(/not installed|isn.t installed/)
    fireEvent.click(screen.getByRole("button", { name: /advanced/i }))
    fireEvent.click(screen.getByRole("radio", { name: /jev/i }))
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("starts normally when claude_cli is absent from the state", () => {
    const { onStart } = show({ ...state(), claude_cli: undefined } as unknown as AppState, both)
    fireEvent.click(screen.getByRole("button", { name: /start sorting/i }))
    expect(onStart).toHaveBeenCalledTimes(1)
  })

  it("adds and removes folders under Advanced", async () => {
    vi.mocked(client.saveCategories).mockResolvedValue({ ok: true, count: 0 })
    const { onCategoriesSaved } = show(state(), both)
    fireEvent.click(screen.getByRole("button", { name: /advanced/i }))
    fireEvent.click(screen.getByRole("button", { name: "Remove People" }))
    await waitFor(() => expect(client.saveCategories).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(onCategoriesSaved).toHaveBeenCalledTimes(1))
    expect(onCategoriesSaved.mock.calls[0][0].map((c: { key: string }) => c.key)).toEqual(["other", "clips", "misc-video"])
    expect(vi.mocked(client.saveCategories).mock.calls[0][0].map((c) => c.key)).toEqual(["other", "clips", "misc-video"])
    expect(screen.queryByRole("button", { name: "Remove People" })).toBeNull() // gone at once, not after a refresh
  })

  it("does not tell the parent about a save the server refused, and puts the chip back", async () => {
    vi.mocked(client.saveCategories).mockRejectedValue(new ApiError("Those folders could not be saved.", 400))
    const { onCategoriesSaved } = show(state(), both)
    fireEvent.click(screen.getByRole("button", { name: /advanced/i }))
    fireEvent.click(screen.getByRole("button", { name: "Remove People" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Those folders could not be saved.")
    expect(onCategoriesSaved).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "Remove People" })).toBeInTheDocument()
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
    await waitFor(() => expect(screen.getByRole("button", { name: /choose folder/i })).toBeEnabled())
    fireEvent.click(screen.getByRole("button", { name: /choose folder/i }))
    await waitFor(() => expect(client.pick).toHaveBeenCalledTimes(2))
    // picking clears after the awaits: wait for that before looking for a notice that must not exist
    await waitFor(() => expect(screen.getByRole("button", { name: /choose folder/i })).toBeEnabled())
    expect(onChoose).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("shows the server's reason when the folder window crashed instead of closing", async () => {
    vi.mocked(client.pick).mockResolvedValueOnce({ path: null, reason: "The folder window did not work." })
    show(state())
    fireEvent.click(screen.getByRole("button", { name: /choose folder/i }))
    expect(await screen.findByRole("alert")).toHaveTextContent("The folder window did not work.")
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

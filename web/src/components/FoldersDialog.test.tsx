import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  saveCategories: vi.fn(),
}))
import { ApiError, saveCategories } from "../api/client"
import { FoldersDialog } from "./FoldersDialog"

const cats = [
  { key: "people", kind: "photo", label: "People", emoji: "👪", rule: "photos of people" },
  { key: "clips", kind: "video", label: "Clips", emoji: "🎬", rule: "short videos" },
]

function setup() {
  const onSaved = vi.fn()
  const onClose = vi.fn()
  render(<FoldersDialog categories={cats} onSaved={onSaved} onClose={onClose} />)
  return { onSaved, onClose }
}
const save = () => fireEvent.click(screen.getByRole("button", { name: "Save folders" }))
const names = () => screen.getAllByLabelText("Folder name") as HTMLInputElement[]
const rename = (i: number, value: string) => fireEvent.change(names()[i], { target: { value } })

describe("FoldersDialog", () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(saveCategories).mockResolvedValue({ ok: true, count: 0 })
  })
  afterEach(cleanup)

  it("requires every folder to have a name before saving", async () => {
    const { onSaved } = setup()
    fireEvent.click(screen.getByRole("button", { name: "Photo folder" })) // a blank new row, after People
    save()
    expect(await screen.findByRole("alert")).toHaveTextContent("Every folder needs a name.")
    expect(saveCategories).not.toHaveBeenCalled()

    rename(1, "   ") // spaces are still no name
    save()
    expect(saveCategories).not.toHaveBeenCalled()

    rename(1, "Beach")
    save()
    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1))
    expect(saveCategories).toHaveBeenCalledTimes(1)
  })

  it("generates a unique key from the folder name", async () => {
    const { onSaved } = setup()
    fireEvent.click(screen.getByRole("button", { name: "Photo folder" }))
    fireEvent.click(screen.getByRole("button", { name: "Photo folder" }))
    fireEvent.click(screen.getByRole("button", { name: "Video folder" }))
    rename(1, " People! ") // slugs to "people", which the existing folder already owns
    rename(2, "people")
    rename(4, "Clips") // the video group lists the existing Clips first, then the new row
    expect(names().map((n) => n.value)).toEqual(["People", " People! ", "people", "Clips", "Clips"])
    save()
    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1))

    const sent = vi.mocked(saveCategories).mock.calls[0][0]
    // Existing keys are never rewritten; each new key avoids every other key, existing or new.
    expect(sent.map((c) => c.key)).toEqual(["people", "clips", "people-2", "people-3", "clips-2"])
    expect(new Set(sent.map((c) => c.key)).size).toBe(sent.length)
    // The saved name is trimmed, and a blank rule falls back to the name.
    expect(sent[2]).toMatchObject({ label: "People!", rule: "People!", kind: "photo" })
    expect(sent[0]).toMatchObject({ label: "People", rule: "photos of people" })
    expect(onSaved).toHaveBeenCalledWith(sent)
  })

  it("refuses to save without at least one photo and one video folder", async () => {
    setup()
    fireEvent.click(screen.getByRole("button", { name: "Delete Clips" }))
    save()
    expect(await screen.findByRole("alert")).toHaveTextContent(/at least one video folder/)
    expect(saveCategories).not.toHaveBeenCalled()

    cleanup()
    setup()
    fireEvent.click(screen.getByRole("button", { name: "Delete People" }))
    save()
    expect(await screen.findByRole("alert")).toHaveTextContent(/at least one photo folder/)
    expect(saveCategories).not.toHaveBeenCalled()
  })

  it("says what the server said when it refuses the list, and does not report a save", async () => {
    vi.mocked(saveCategories).mockRejectedValue(new ApiError("Labelling is running, so folders cannot change.", 409))
    const { onSaved } = setup()
    save()
    expect(await screen.findByRole("alert")).toHaveTextContent("Labelling is running, so folders cannot change.")
    expect(onSaved).not.toHaveBeenCalled()
  })
})

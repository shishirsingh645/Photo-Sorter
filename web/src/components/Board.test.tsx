import { createRef } from "react"
import { render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { Board } from "./Board"
import type { BoardCard, BoardHandle } from "./Board"

const card = (key: string, count = 0, slots: string[] = []): BoardCard => ({
  category: { key, label: key, emoji: "📁" },
  count,
  slots,
})
const photos = (n: number, count = 0) => Array.from({ length: n }, (_, i) => card(`photo-${i}`, count))
const videos = (n: number) => Array.from({ length: n }, (_, i) => card(`video-${i}`))
const dupes = (count = 0, slots: string[] = []) => card("_dupes", count, slots)

describe("Board", () => {
  // Review Focus 2 — one saturated card, the rest empty
  it("renders correctly when one card holds 174 files and nine are empty", () => {
    render(<Board photoCats={photos(5)} videoCats={[...videos(4), dupes(174)]} onOpen={vi.fn()} />)
    expect(screen.getAllByRole("button", { name: /folder/i })).toHaveLength(10)
    expect(screen.getByText("174")).toBeInTheDocument()
    // only the saturated card shows its badge
    expect(screen.getAllByText("0").filter(el => el.getAttribute("data-on") === "true")).toHaveLength(0)
    expect(screen.getByText("174")).toHaveAttribute("data-on", "true")
  })

  // Review Focus 3 — no videos
  it("renders the video column with no videos and no crash", () => {
    render(<Board photoCats={photos(3, 4)} videoCats={[]} onOpen={vi.fn()} />)
    const col = screen.getByRole("region", { name: "Videos" })
    expect(within(col).getByText("Videos")).toBeInTheDocument()
    expect(within(col).getByText("0")).toBeInTheDocument()
    expect(within(col).queryAllByRole("button")).toHaveLength(0)
    // the photo column is unaffected: 3 cards, total 12
    const left = screen.getByRole("region", { name: "Photos" })
    expect(within(left).getAllByRole("button")).toHaveLength(3)
    expect(within(left).getByText("12")).toBeInTheDocument()
  })

  it("leaves duplicates out of the Videos total", () => {
    const vids = [card("video-0", 5), dupes(40)]
    render(<Board photoCats={[]} videoCats={vids} onOpen={vi.fn()} />)
    const col = screen.getByRole("region", { name: "Videos" })
    expect(within(col).getAllByText("5")).toHaveLength(2) // the card badge and the column total
    expect(within(col).getByText("40")).toBeInTheDocument() // the badge alone
  })

  // Review Focus 1 — large library
  it("renders no more DOM nodes for 100k files than for 1k", () => {
    const full = (per: number) => ({
      photoCats: photos(5, per),
      videoCats: [...videos(4), dupes(per)],
    })
    const small = full(1_000)
    const big = full(100_000)
    const a = render(<Board {...small} onOpen={vi.fn()} />)
    const smallNodes = a.container.querySelectorAll("*").length
    a.unmount()
    const b = render(<Board {...big} onOpen={vi.fn()} />)
    expect(b.container.querySelectorAll("*").length).toBe(smallNodes)
    expect(screen.getAllByTestId("slot")).toHaveLength(5 * 12 + 4 * 12 + 24)
  })

  it("exposes every card's preview slots by category key", () => {
    const ref = createRef<BoardHandle>()
    render(<Board ref={ref} photoCats={photos(2)} videoCats={[dupes()]} onOpen={vi.fn()} />)
    expect([...ref.current!.keys()].sort()).toEqual(["_dupes", "photo-0", "photo-1"])
    expect(ref.current!.get("photo-1")!.slotRefs).toHaveLength(12)
    expect(ref.current!.get("_dupes")!.slotRefs).toHaveLength(24)
  })

  it("puts the stage between the two columns", () => {
    render(
      <Board photoCats={photos(1)} videoCats={[]} onOpen={vi.fn()}>
        <p>the stage</p>
      </Board>,
    )
    const [left, mid, right] = Array.from(screen.getByText("the stage").parentElement!.parentElement!.children)
    expect(left).toBe(screen.getByRole("region", { name: "Photos" }))
    expect(mid).toContainElement(screen.getByText("the stage"))
    expect(right).toBe(screen.getByRole("region", { name: "Videos" }))
  })

  // Review Focus 5 — narrow window. jsdom evaluates no media queries and vitest blanks CSS modules (even with
  // ?raw), so read the stylesheet from disk and assert the rule is in it. The specifier is built at run time
  // because the project carries no @types/node.
  it("collapses to a single column below 900px", async () => {
    const { readFileSync } = await import(/* @vite-ignore */ "node:" + "fs")
    const boardCss: string = readFileSync(new URL("./Board.module.css", import.meta.url), "utf8")
    const narrow = /@media \(max-width: 900px\)\s*\{[^@]*?\.board\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)\s*;/
    expect(boardCss).toMatch(narrow)
    // and wide, it is the reference's three columns
    expect(boardCss).toMatch(/\.board\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1\.25fr\) minmax\(320px, 1fr\) minmax\(0, 0\.9fr\)/)
  })
})

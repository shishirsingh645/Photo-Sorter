import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { DonePanel } from "./DonePanel"

const frames = vi.hoisted(() => ({ subs: new Set<(dt: number, now: number) => void>() }))
const burst = vi.hoisted(() => vi.fn())
vi.mock("../anim/loop", () => ({
  startLoop: (fn: (dt: number, now: number) => void) => {
    frames.subs.add(fn)
    return () => frames.subs.delete(fn)
  },
}))
vi.mock("../anim/confetti", () => ({ burstConfetti: burst }))

const panel = (props: { live?: boolean; onReplay?: () => void } = {}) =>
  render(<DonePanel total={1136} folders={13} dupes={40} saved={2_400_000_000} onReplay={props.onReplay ?? vi.fn()} live={props.live} />)
const bigN = () => screen.getByText(/sorted/).firstElementChild!.textContent

beforeEach(() => {
  frames.subs.clear()
  burst.mockClear()
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("DonePanel", () => {
  it("counts up the total and fires confetti on a live finish", () => {
    vi.spyOn(performance, "now").mockReturnValue(1000)
    panel({ live: true })
    expect(bigN()).toBe("0")
    expect(burst).toHaveBeenCalledTimes(1)
    expect(burst.mock.calls[0][0]).toBeInstanceOf(HTMLCanvasElement)

    // ease(0.25) = 4 * 0.25^3 and ease(0.5) = 0.5 of the 900 ms count
    act(() => frames.subs.forEach(f => f(16, 1225)))
    expect(bigN()).toBe("71")
    act(() => frames.subs.forEach(f => f(16, 1450)))
    expect(bigN()).toBe("568")
    act(() => frames.subs.forEach(f => f(16, 2000)))
    expect(bigN()).toBe("1,136")
    expect(frames.subs.size).toBe(0) // the count unsubscribes itself
  })

  it("shows the finished number at once, with no count and no confetti, when the sort finished earlier", () => {
    panel()
    expect(bigN()).toBe("1,136")
    expect(burst).not.toHaveBeenCalled()
    expect(frames.subs.size).toBe(0)
  })

  it("says what was sorted", () => {
    panel()
    expect(screen.getByText("13 folders")).toBeInTheDocument()
    expect(screen.getByText(/40 duplicates/)).toBeInTheDocument()
    expect(screen.getByText(/2\.4 GB freed/)).toBeInTheDocument()
  })

  it("replays on Space, except while typing", () => {
    const onReplay = vi.fn()
    panel({ onReplay })
    fireEvent.keyDown(window, { code: "Space" })
    expect(onReplay).toHaveBeenCalledTimes(1)
    const input = document.body.appendChild(document.createElement("input"))
    fireEvent.keyDown(input, { code: "Space" })
    expect(onReplay).toHaveBeenCalledTimes(1)
    input.remove()
  })
})

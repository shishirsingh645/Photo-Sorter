import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { PaidConfirm } from "./PaidConfirm"

afterEach(cleanup)

describe("PaidConfirm", () => {
  it("states the file count and token estimate before spending on Jev", () => {
    const onResolve = vi.fn()
    render(<PaidConfirm files={1234} onResolve={onResolve} />)
    // 980 tokens a file, as the reference app counts them.
    expect(screen.getByText("1,234 files, about 1,209,320 tokens")).toBeInTheDocument()
    expect(screen.getByText(/never the original/)).toBeInTheDocument()
    expect(screen.getByText(/skipped, so you can stop and resume/)).toBeInTheDocument()
    expect(onResolve).not.toHaveBeenCalled() // showing the numbers spends nothing

    fireEvent.click(screen.getByRole("button", { name: "Spend tokens" }))
    expect(onResolve).toHaveBeenCalledTimes(1)
    expect(onResolve).toHaveBeenCalledWith(true)
  })

  it("returns false when the paid dialog is dismissed", () => {
    const dismissals: [string, () => void][] = [
      ["Close", () => fireEvent.click(screen.getByRole("button", { name: "Close" }))],
      ["Escape", () => fireEvent.keyDown(document.body, { key: "Escape" })],
      ["a click on the scrim", () => fireEvent.click(screen.getByRole("dialog").parentElement!)],
    ]
    for (const [, dismiss] of dismissals) {
      const onResolve = vi.fn()
      render(<PaidConfirm files={10} onResolve={onResolve} />)
      dismiss()
      expect(onResolve).toHaveBeenCalledTimes(1)
      expect(onResolve).toHaveBeenCalledWith(false)
      cleanup()
    }
  })
})

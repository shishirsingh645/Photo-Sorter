import { afterEach, describe, expect, it, vi } from "vitest"
import { useState } from "react"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { Dialog } from "./Dialog"

afterEach(cleanup)

function Harness() {
  const [on, setOn] = useState(false)
  return (
    <>
      <button onClick={() => setOn(true)}>open</button>
      {on && (
        <Dialog label="Test" onClose={() => setOn(false)}>
          <button>first</button>
          <button>middle</button>
          <button>last</button>
        </Dialog>
      )}
    </>
  )
}

// Returns false when the key's default was prevented, i.e. when a trap took the Tab.
const tab = (shiftKey = false) => fireEvent.keyDown(document.activeElement ?? document.body, { key: "Tab", shiftKey })

describe("Dialog", () => {
  it("traps focus inside the dialog and restores it to the opener on close", () => {
    render(<Harness />)
    const opener = screen.getByText("open")
    opener.focus()
    fireEvent.click(opener)

    // Opening moves focus into the dialog, onto its first control.
    expect(screen.getByText("first")).toHaveFocus()

    // Tab walks forward and wraps from the last control to the first.
    screen.getByText("last").focus()
    tab()
    expect(screen.getByText("first")).toHaveFocus()

    // Shift+Tab wraps from the first control to the last.
    tab(true)
    expect(screen.getByText("last")).toHaveFocus()

    // Focus that has strayed outside (to the opener behind the backdrop) is pulled back in.
    opener.focus()
    tab()
    expect(screen.getByText("first")).toHaveFocus()
    opener.focus()
    tab(true)
    expect(screen.getByText("last")).toHaveFocus()

    // A Tab that is not on an edge is left to the browser: the trap must not swallow it.
    screen.getByText("middle").focus()
    const notHandled = fireEvent.keyDown(document.activeElement!, { key: "Tab" })
    expect(notHandled).toBe(true) // fireEvent returns false when preventDefault() was called

    fireEvent.keyDown(document.activeElement!, { key: "Escape" })
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(opener).toHaveFocus()
  })

  it("closes on Escape and on a scrim click but not on a content click", () => {
    const onClose = vi.fn()
    render(
      <Dialog label="Test" onClose={onClose}>
        <button>inside</button>
      </Dialog>,
    )
    const dialog = screen.getByRole("dialog")

    fireEvent.click(screen.getByText("inside"))
    fireEvent.click(dialog)
    expect(onClose).not.toHaveBeenCalled()

    // A press that began inside the dialog and was released over the scrim (dragging a text selection out)
    // is not a click on the scrim.
    fireEvent.mouseDown(dialog)
    fireEvent.click(dialog.parentElement!)
    expect(onClose).not.toHaveBeenCalled()

    fireEvent.mouseDown(dialog.parentElement!)
    fireEvent.click(dialog.parentElement!)
    expect(onClose).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(document.body, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it("sends Escape and Tab to the topmost of two stacked dialogs only", () => {
    const outer = vi.fn()
    const inner = vi.fn()
    const stack = (withInner: boolean) => (
      <>
        <Dialog label="Outer" onClose={outer}>
          <button>outer button</button>
        </Dialog>
        {withInner && (
          <Dialog label="Inner" onClose={inner} scrim={false}>
            <button>inner a</button>
            <button>inner b</button>
          </Dialog>
        )}
      </>
    )
    const { rerender } = render(stack(false))
    rerender(stack(true)) // the lightbox opens over the browse dialog, never the other way round

    // The inner dialog took focus. A Tab in the middle of it is nobody's to trap: had the outer dialog acted on
    // it too (focus is outside the outer one), it would have been prevented and focus pulled to "outer button".
    expect(screen.getByText("inner a")).toHaveFocus()
    expect(tab()).toBe(true)
    expect(screen.getByText("inner a")).toHaveFocus()
    // At the inner dialog's own edge it wraps inside the inner dialog.
    screen.getByText("inner b").focus()
    expect(tab()).toBe(false)
    expect(screen.getByText("inner a")).toHaveFocus()

    fireEvent.keyDown(document.body, { key: "Escape" })
    expect(inner).toHaveBeenCalledTimes(1)
    expect(outer).not.toHaveBeenCalled()

    // With the inner one gone, Escape reaches the outer one again.
    rerender(stack(false))
    fireEvent.keyDown(document.body, { key: "Escape" })
    expect(outer).toHaveBeenCalledTimes(1)
  })

  it("can take focus onto the dialog itself instead of its first control", () => {
    render(
      <Dialog label="Test" onClose={vi.fn()} scrim={false} initialFocus="root">
        <button>first</button>
        <button>last</button>
      </Dialog>,
    )
    expect(screen.getByRole("dialog")).toHaveFocus()
    expect(tab()).toBe(true) // forward from the dialog goes to its first control, as the browser would
    expect(tab(true)).toBe(false) // backward from the dialog wraps to the last
    expect(screen.getByText("last")).toHaveFocus()
  })
})

import { useEffect, useRef } from "react"
import type { ReactNode } from "react"
import s from "./Dialog.module.css"

interface Props {
  label: string
  onClose: () => void
  /** false for the lightbox, which has no backdrop of its own to click. */
  scrim?: boolean
  className?: string
  /** What takes focus on open: the first control (default), or the dialog itself, for a dialog whose first
   * control is one that arrow keys or typing would change (the lightbox's Move-to select). */
  initialFocus?: "first" | "root"
  children: ReactNode
}

// Open dialogs, innermost last: the lightbox sits over the browse dialog, and Escape or Tab must reach
// only the one on top.
const open: object[] = []

const FOCUSABLE = "a[href], button, input, select, textarea, video[controls], [tabindex]"
const focusables = (root: HTMLElement) =>
  [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
    (e) => !(e as HTMLButtonElement).disabled && !e.closest("[hidden]") && (!e.hasAttribute("tabindex") || e.tabIndex >= 0),
  )

export function Dialog({ label, onClose, scrim = true, className = "", initialFocus = "first", children }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const down = useRef<EventTarget | null>(null)
  const close = useRef(onClose)
  close.current = onClose

  useEffect(() => {
    const me = {}
    const root = box.current!
    const opener = document.activeElement as HTMLElement | null
    open.push(me)
    const start = initialFocus === "root" ? root : (focusables(root)[0] ?? root)
    start.focus()

    const onKey = (e: KeyboardEvent) => {
      if (open[open.length - 1] !== me || e.isComposing) return
      if (e.key === "Escape") {
        e.preventDefault()
        close.current()
      } else if (e.key === "Tab") {
        const items = focusables(root)
        const at = document.activeElement
        const first = items[0]
        const last = items[items.length - 1]
        const wrap = (to: HTMLElement) => {
          e.preventDefault()
          to.focus()
        }
        if (!first) e.preventDefault()
        else if (!e.shiftKey && (at === last || !root.contains(at))) wrap(first)
        else if (e.shiftKey && (at === first || at === root || !root.contains(at))) wrap(last)
      }
    }
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("keydown", onKey)
      open.splice(open.indexOf(me), 1)
      if (opener?.isConnected) opener.focus() // back to what opened it
    }
  }, [])

  const dialog = (cls: string) => (
    <div ref={box} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1} className={cls}>
      {children}
    </div>
  )
  if (!scrim) return dialog(className)
  // Closes only when the press began on the backdrop too, so dragging a text selection out of the dialog
  // and releasing over the backdrop does not dismiss it. A click with no press (a script) still closes.
  return (
    <div
      className={s.scrim}
      onMouseDown={(e) => (down.current = e.target)}
      onClick={(e) => {
        const pressedHere = down.current === null || down.current === e.currentTarget
        down.current = null
        if (e.target === e.currentTarget && pressedHere) onClose()
      }}
    >
      {dialog(`${s.dialog} ${className}`)}
    </div>
  )
}

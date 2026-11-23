import { forwardRef, useEffect, useImperativeHandle, useRef } from "react"
import styles from "./FolderCard.module.css"

/** The duplicates card is a made-up category (app.js: catBy._dupes); it is the wide one with 24 slots. */
export const DUPES_KEY = "_dupes"

export interface FolderCategory {
  key: string
  label: string
  emoji: string
}

/** What a card exposes through its ref: its preview slots, in order, for photos to fly into. */
export interface FolderCardHandle {
  slotRefs: readonly (HTMLDivElement | null)[]
}

export interface FolderCardProps {
  category: FolderCategory
  /** Files landed in this folder; the badge stays hidden at 0. */
  count: number
  /** Preview image URLs, newest first. A slot past the end of the list stays empty. */
  slots: readonly string[]
  onOpen: (category: FolderCategory) => void
  /** True while files are landing one by one (the reference's land(live)): only then does a new file pop the badge and flash the card. A bulk fill leaves it false. */
  live?: boolean
}

export const FolderCard = forwardRef<FolderCardHandle, FolderCardProps>(function FolderCard(
  { category, count, slots, onOpen, live = false },
  ref,
) {
  const wide = category.key === DUPES_KEY
  const slotEls = useRef<(HTMLDivElement | null)[]>([])
  const card = useRef<HTMLButtonElement>(null)
  const badge = useRef<HTMLSpanElement>(null)
  const seen = useRef(count)
  useImperativeHandle(ref, () => ({ slotRefs: slotEls.current }), [])

  // Like the reference's land(live): each new file pops the badge and flashes the card for 260ms, but a bulk fill does not.
  useEffect(() => {
    const grew = count > seen.current
    seen.current = count
    const b = badge.current
    const c = card.current
    if (!live || !grew || !b || !c) return
    b.classList.remove(styles.pop)
    void b.offsetWidth // restart the animation
    b.classList.add(styles.pop)
    c.classList.add(styles.hit)
    const t = setTimeout(() => c.classList.remove(styles.hit), 260)
    return () => {
      clearTimeout(t)
      c.classList.remove(styles.hit)
    }
  }, [count, live])

  const total = count.toLocaleString("en-US")
  return (
    <button
      ref={card}
      className={`${styles.card} ${wide ? `${styles.wide} ${styles.review}` : ""}`}
      aria-label={`${category.label} folder, ${total} ${count === 1 ? "file" : "files"}`}
      onClick={() => onOpen(category)}
    >
      <div className={styles.ch}>
        <span>{category.emoji || "📁"}</span>
        <span className={styles.name} title={category.label}>
          {category.label}
        </span>
        <span ref={badge} className={`mx-count ${styles.count}`} data-on={count > 0} aria-hidden={count === 0}>
          {total}
        </span>
      </div>
      <div className={styles.grid}>
        {Array.from({ length: wide ? 24 : 12 }, (_, i) => (
          <div
            key={i}
            className={styles.slot}
            data-testid="slot"
            ref={el => {
              slotEls.current[i] = el
            }}
          >
            {slots[i] && <img key={slots[i]} src={slots[i]} alt="" />}
          </div>
        ))}
      </div>
    </button>
  )
})

import { forwardRef, useImperativeHandle, useRef } from "react"
import type { ReactNode } from "react"
import { DUPES_KEY, FolderCard } from "./FolderCard"
import type { FolderCardHandle, FolderCardProps } from "./FolderCard"
import styles from "./Board.module.css"

/** One card's worth of props. Put the duplicates card (key "_dupes") last in `videoCats`, as the reference does. */
export type BoardCard = Omit<FolderCardProps, "onOpen">

/** Every card's handle by category key, so fly.ts can reach `get(key).slotRefs[i]`. */
export type BoardHandle = ReadonlyMap<string, FolderCardHandle>

export interface BoardProps {
  photoCats: readonly BoardCard[]
  videoCats: readonly BoardCard[]
  onOpen: FolderCardProps["onOpen"]
  /** The stage that sits between the two columns. */
  children?: ReactNode
}

const total = (cards: readonly BoardCard[]) => cards.reduce((s, c) => s + c.count, 0).toLocaleString("en-US")

export const Board = forwardRef<BoardHandle, BoardProps>(function Board({ photoCats, videoCats, onOpen, children }, ref) {
  const cards = useRef(new Map<string, FolderCardHandle>())
  useImperativeHandle(ref, () => cards.current, [])

  const column = (title: string, list: readonly BoardCard[], sum: string) => (
    <section className={styles.col} aria-label={title}>
      <div className={styles.colH}>
        <span>{title}</span>
        <em>{sum}</em>
      </div>
      <div className={styles.cards}>
        {list.map(c => (
          <FolderCard
            key={c.category.key}
            {...c}
            onOpen={onOpen}
            ref={h => {
              if (h) cards.current.set(c.category.key, h)
              else cards.current.delete(c.category.key)
            }}
          />
        ))}
      </div>
    </section>
  )

  // Duplicates are moved to review, not sorted into videos, so the Videos total leaves them out.
  return (
    <div className={styles.board}>
      {column("Photos", photoCats, total(photoCats))}
      <div className={styles.stage}>{children}</div>
      {column("Videos", videoCats, total(videoCats.filter(c => c.category.key !== DUPES_KEY)))}
    </div>
  )
})

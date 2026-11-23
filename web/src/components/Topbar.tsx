import { useEffect } from "react"
import { useTheme } from "../hooks/useTheme"
import type { Mode } from "../state/reducer"
import { Icon } from "./Icon"
import styles from "./Topbar.module.css"

/** `kind` colours the dot: live (green), busy (blinking accent) or none (grey). */
export interface Pill {
  kind: "live" | "busy" | null
  text: string
}

export interface TopbarProps {
  mode: Mode
  pill: Pill
  onNewSort: () => void
  onSortWithClaude: () => void
  onEditFolders: () => void
  onOpenSorted: () => void
}

export function Topbar({ mode, pill, onNewSort, onSortWithClaude, onEditFolders, onOpenSorted }: TopbarProps) {
  const { theme, toggle } = useTheme()
  const done = mode === "done"

  // The reference's setHeader() mirrors the mode onto <body>; the cards' setup dimming reads it.
  useEffect(() => {
    document.body.dataset.mode = mode
  }, [mode])

  return (
    <header className={styles.topbar}>
      <span className={styles.logo}>
        <i>
          <Icon name="images" />
        </i>
        photo sorter
      </span>
      <span className={styles.pill}>
        <span className={`${styles.dot} ${pill.kind ? styles[pill.kind] : ""}`} />
        <span>{pill.text}</span>
      </span>
      <span className={styles.spacer} />
      <button className={`${styles.btn} ${styles.small}`} onClick={onEditFolders}>
        <Icon name="pencil" />
        Edit folders
      </button>
      {done && (
        <button className={`${styles.btn} ${styles.small}`} onClick={onOpenSorted}>
          <Icon name="folder" />
          Open sorted folder
        </button>
      )}
      <button
        className={styles.icon}
        onClick={toggle}
        aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      >
        <Icon name={theme === "dark" ? "sun" : "moon"} />
      </button>
      {done && (
        <button className={`${styles.btn} ${styles.new}`} onClick={onNewSort}>
          <Icon name="plus" />
          New sort
        </button>
      )}
      <button className={`${styles.btn} ${styles.solid}`} onClick={onSortWithClaude}>
        <Icon name="play" />
        <span>Sort with Claude</span>
      </button>
    </header>
  )
}

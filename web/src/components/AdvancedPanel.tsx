import { useRef, useState } from "react"
import type { AppState } from "../api/client"
import { Icon } from "./Icon"
import styles from "./AdvancedPanel.module.css"

type Category = AppState["categories"][number]
type Kind = "photo" | "video"
export type Labeler = "claude" | "jev"

/** app.js TOKENS_PER_FILE. */
export const TOKENS_PER_FILE = 980

export interface AdvancedPanelProps {
  categories: Category[]
  files: number
  jevKey: boolean
  labeler: Labeler
  sample: boolean
  onLabeler: (l: Labeler) => void
  onSample: (on: boolean) => void
  onSave: (next: Category[]) => void
}

const fmt = (n: number) => Math.round(n).toLocaleString("en-US")

/** Ported from app.js advancedBox (lines 405-442). */
export function AdvancedPanel({ categories, files, jevKey, labeler, sample, onLabeler, onSample, onSave }: AdvancedPanelProps) {
  const [adding, setAdding] = useState<Kind | null>(null)
  const [label, setLabel] = useState("")
  const [rule, setRule] = useState("")
  const nameInput = useRef<HTMLInputElement>(null)

  const close = () => {
    setAdding(null)
    setLabel("")
    setRule("")
  }
  const add = (kind: Kind) => {
    const name = label.trim()
    if (!name) return nameInput.current?.focus()
    let key = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 24) || "folder"
    let i = 2
    while (categories.some((c) => c.key === key)) key = key.replace(/-\d+$/, "") + "-" + i++
    const at = categories.map((c) => c.kind).lastIndexOf(kind) // keep the catch-all folder last
    const next = categories.slice()
    next.splice(Math.max(0, at), 0, { key, kind, label: name, emoji: kind === "photo" ? "📁" : "🎬", rule: rule.trim() || name })
    onSave(next)
    close()
  }
  const onKey = (kind: Kind) => (e: React.KeyboardEvent) => {
    if (e.key === "Enter") add(kind)
    if (e.key === "Escape") close()
  }

  const chips = (kind: Kind) => (
    <div className={styles.fchips}>
      {categories
        .filter((c) => c.kind === kind)
        .map((c) => (
          <span key={c.key} className={styles.fchip}>
            {c.emoji || "📁"} {c.label}
            <button aria-label={`Remove ${c.label}`} onClick={() => onSave(categories.filter((x) => x !== c))}>
              <Icon name="x" />
            </button>
          </span>
        ))}
      {adding === kind ? (
        <span className={styles.newf}>
          <input ref={nameInput} autoFocus placeholder="Folder name" aria-label="Folder name" value={label} onChange={(e) => setLabel(e.target.value)} onKeyDown={onKey(kind)} />
          <input placeholder="What goes in it" aria-label="What goes in it" value={rule} onChange={(e) => setRule(e.target.value)} onKeyDown={onKey(kind)} />
          <button className={styles.btn} onClick={() => add(kind)}>Add</button>
        </span>
      ) : (
        <span className={`${styles.fchip} ${styles.add}`}>
          <button aria-label={`Add a ${kind} folder`} onClick={() => setAdding(kind)}>
            <Icon name="plus" />
          </button>
        </span>
      )}
    </div>
  )

  const option = (k: Labeler, title: string, text: string, paid = false) => (
    <label className={`${styles.opt} ${labeler === k ? styles.on : ""}`}>
      <input type="radio" name="labeler" checked={labeler === k} onChange={() => onLabeler(k)} />
      <span>
        <b>
          {title}
          {paid && <span className={styles.paid}>PAID</span>}
        </b>
        <small>{text}</small>
      </span>
    </label>
  )

  return (
    <div className={styles.adv}>
      <h4>Photo folders</h4>
      {chips("photo")}
      <h4>Video folders</h4>
      {chips("video")}
      <p className={styles.meta}>The last folder of each kind catches everything that fits nowhere else.</p>
      <h4>Who looks at the photos</h4>
      {option("claude", "Claude", "Uses your Claude plan. No key needed.")}
      {option(
        "jev",
        "Jev by TypeSafe",
        jevKey ? `Fast image model, billed per file: about ${fmt(files * TOKENS_PER_FILE)} tokens.` : "Needs JEV_KEY=your-key in a .env file in this folder.",
        true,
      )}
      <label className={styles.checkRow}>
        <input type="checkbox" checked={sample} onChange={(e) => onSample(e.target.checked)} />
        Try 200 random files first
      </label>
    </div>
  )
}

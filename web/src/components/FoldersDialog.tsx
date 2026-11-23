import { useState } from "react"
import { saveCategories } from "../api/client"
import type { CategoryIn } from "../api/client"
import { Dialog } from "./Dialog"
import { DialogIcon } from "./DialogIcon"
import d from "./Dialog.module.css"
import s from "./FoldersDialog.module.css"

type Row = CategoryIn & { uid: number } // `key` is "" until the row is saved

// The reference app.js openFolders' slug.
const slug = (name: string) =>
  name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 24) || "folder"

/** What the reference's saveIt does to the draft, without mutating it: trimmed names, a rule that falls back
 * to the name, and a key for each new row that no other row has. The two kind checks are the server's own
 * validate_categories, asked here so the user is told before a round trip. */
function prepare(draft: Row[]): { cats: CategoryIn[] } | { error: string } {
  if (draft.some((c) => !c.label.trim())) return { error: "Every folder needs a name." }
  for (const kind of ["photo", "video"] as const)
    if (!draft.some((c) => c.kind === kind))
      return { error: `There must be at least one ${kind} folder, so every ${kind} has somewhere to go.` }
  const used = new Set(draft.map((c) => c.key).filter(Boolean))
  const cats = draft.map(({ uid: _uid, ...c }) => {
    const label = c.label.trim()
    let key = c.key
    if (!key) {
      key = slug(label)
      for (let i = 2; used.has(key); i++) key = `${slug(label)}-${i}`
      used.add(key)
    }
    return { ...c, key, label, rule: c.rule.trim() || label }
  })
  return { cats }
}

interface Props {
  categories: readonly { key: string; kind: string; label: string; emoji: string; rule: string }[]
  /** After the server accepted the list. */
  onSaved: (cats: CategoryIn[]) => void
  onClose: () => void
}

export function FoldersDialog({ categories, onSaved, onClose }: Props) {
  const [draft, setDraft] = useState<Row[]>(() =>
    categories.map((c, uid) => ({ ...c, kind: c.kind as Row["kind"], uid })),
  )
  const [error, setError] = useState("")
  const [saving, setSaving] = useState(false)

  const edit = (uid: number, patch: Partial<CategoryIn>) =>
    setDraft((rows) => rows.map((r) => (r.uid === uid ? { ...r, ...patch } : r)))
  const add = (kind: Row["kind"]) => () =>
    setDraft((rows) => [
      ...rows,
      { uid: Math.max(-1, ...rows.map((r) => r.uid)) + 1, key: "", kind, label: "", emoji: kind === "photo" ? "📁" : "🎬", rule: "" },
    ])

  async function save() {
    const got = prepare(draft)
    if ("error" in got) return setError(got.error)
    setError("")
    setSaving(true)
    try {
      await saveCategories(got.cats)
    } catch (e) {
      setSaving(false)
      return setError((e as Error).message) // the server's own words, whatever the status
    }
    onSaved(got.cats)
  }

  const row = (c: Row) => (
    <div className={s.folderRow} key={c.uid}>
      <input className={s.emoji} value={c.emoji} aria-label="Emoji" onChange={(e) => edit(c.uid, { emoji: e.target.value })} />
      <input value={c.label} placeholder="Folder name" aria-label="Folder name" onChange={(e) => edit(c.uid, { label: e.target.value })} />
      <input
        className={s.rule}
        value={c.rule}
        placeholder="What goes in here, in plain words"
        aria-label="Rule"
        onChange={(e) => edit(c.uid, { rule: e.target.value })}
      />
      <div className={`${d.seg} ${s.seg}`}>
        {(["photo", "video"] as const).map((k) => (
          <button key={k} aria-pressed={c.kind === k} onClick={() => edit(c.uid, { kind: k })}>
            {k === "photo" ? "Photos" : "Videos"}
          </button>
        ))}
      </div>
      <button className={d.icon} aria-label={`Delete ${c.label}`} onClick={() => setDraft((rows) => rows.filter((r) => r.uid !== c.uid))}>
        <DialogIcon name="trash" />
      </button>
    </div>
  )

  return (
    <Dialog label="Edit folders" onClose={onClose}>
      <div className={d.head}>
        <h2>Folders</h2>
        <button className={d.icon} onClick={onClose} aria-label="Close">
          <DialogIcon name="x" />
        </button>
      </div>
      <div className={d.rows}>
        <div className={s.folderList}>
          <h4>Photo folders</h4>
          {draft.filter((c) => c.kind === "photo").map(row)}
          <h4>Video folders</h4>
          {draft.filter((c) => c.kind === "video").map(row)}
        </div>
        <p className={s.note}>The rule is what Claude reads, so describe each folder the way you'd explain it to a friend.</p>
        {error && (
          <p className={s.note} role="alert">
            {error}
          </p>
        )}
      </div>
      <div className={d.foot}>
        <button className={d.btn} onClick={add("photo")}>
          <DialogIcon name="plus" />
          Photo folder
        </button>
        <button className={d.btn} onClick={add("video")}>
          <DialogIcon name="plus" />
          Video folder
        </button>
        <span className={d.spacer} />
        <button className={`${d.btn} ${d.ghost}`} onClick={onClose}>
          Cancel
        </button>
        <button className={`${d.btn} ${d.solid}`} onClick={save} disabled={saving}>
          Save folders
        </button>
      </div>
    </Dialog>
  )
}

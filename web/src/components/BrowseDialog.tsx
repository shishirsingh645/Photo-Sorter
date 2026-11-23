import { useState } from "react"
import { open } from "../api/client"
import { thumbOf } from "../state/library"
import type { LibraryItem } from "../state/library"
import { Dialog } from "./Dialog"
import { Icon } from "./Icon"
import { Lightbox } from "./Lightbox"
import { fmt } from "../format"
import d from "./Dialog.module.css"
import s from "./BrowseDialog.module.css"

const PAGE = 120 // thumbnails in the DOM per "Show more", so a 100,000-file library stays usable

// The folder name apply.folder_name gives a category on disk ('&' spelled out, what Windows forbids as '-',
// trailing dots and spaces dropped); the duplicates live in a fixed review folder.
const onDisk = (key: string, label: string) =>
  key === "_dupes" ? "_Review/duplicates" : label.replace(/&/g, "and").replace(/[<>:"/\\|?*\x00-\x1f]/g, "-").replace(/[ .]+$/, "")

interface Props {
  folder: { key: string; label: string; emoji?: string }
  /** This folder's files only (see folderItems). */
  items: LibraryItem[]
  categories: readonly { key: string; kind: string; label: string; emoji: string }[]
  /** AppState.file_manager: "File Explorer", "Finder" or "file manager". */
  fileManager: string
  /** Whether a sort has written the folders yet; there is nothing to show before that. */
  sorted: boolean
  onMoved: (item: LibraryItem, key: string) => void
  onClose: () => void
}

export function BrowseDialog({ folder, items, categories, fileManager, sorted, onMoved, onClose }: Props) {
  const [shown, setShown] = useState(PAGE)
  const [viewing, setViewing] = useState<number | null>(null)
  const [error, setError] = useState("")

  async function reveal() {
    try {
      await open({ folder: onDisk(folder.key, folder.label) })
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <>
    <Dialog label={folder.label} className={s.wide} onClose={onClose}>
      <div className={d.head}>
        <h2 className={s.title}>
          {folder.emoji || "📁"} {folder.label}
          <span className="mx-count">{fmt(items.length)}</span>
        </h2>
        <div className={s.acts}>
          {sorted && (
            <button className="mx-btn small" onClick={reveal}>
              <Icon name="folder" />
              {`Show in ${fileManager}`}
            </button>
          )}
          <button className="mx-icon" onClick={onClose} aria-label="Close">
            <Icon name="x" />
          </button>
        </div>
      </div>
      {error && (
        <p className="mx-empty" style={{ padding: "12px 22px 0" }} role="alert">
          {error}
        </p>
      )}
      {items.length ? (
        <div className={s.browse}>
          {items.slice(0, shown).map((it, i) => (
            <button key={it.id} onClick={() => setViewing(i)}>
              <img src={thumbOf(it)} alt={it.name} loading="lazy" />
              {it.kind === "video" && <span className={s.vid}>{"▶ " + (it.duration ? Math.round(it.duration) + "s" : "video")}</span>}
            </button>
          ))}
          {shown < items.length && (
            <button className={`mx-btn ${s.more}`} onClick={() => setShown(shown + PAGE)}>
              {`Show ${fmt(Math.min(PAGE, items.length - shown))} more`}
            </button>
          )}
        </div>
      ) : (
        <p className="mx-empty" style={{ padding: 22 }}>
          Nothing in this folder yet.
        </p>
      )}
    </Dialog>
    {/* Beside the dialog, not inside it: its entrance animation would make it the lightbox's fixed-position parent. */}
    {viewing !== null && items[viewing] && (
      <Lightbox
        items={items}
        index={viewing}
        categories={categories}
        onIndex={setViewing}
        onMoved={onMoved}
        onClose={() => setViewing(null)}
      />
    )}
    </>
  )
}

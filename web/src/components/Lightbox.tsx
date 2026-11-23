import { useEffect, useState } from "react"
import { ApiError, getRecord, move, open } from "../api/client"
import type { FileRecord } from "../api/client"
import { thumbOf } from "../state/library"
import type { LibraryItem } from "../state/library"
import { Dialog } from "./Dialog"
import { DialogIcon } from "./DialogIcon"
import { fmt, size } from "./format"
import d from "./Dialog.module.css"
import s from "./Lightbox.module.css"

interface Props {
  items: LibraryItem[]
  index: number
  categories: readonly { key: string; kind: string; label: string; emoji: string }[]
  onIndex: (i: number) => void
  /** After the server stored the move; the caller owns the item's new folder. */
  onMoved: (item: LibraryItem, key: string) => void
  onClose: () => void
}

type Loaded = { id: number; record: FileRecord } | { id: number; error: ApiError }

/** 409 and 400 mean different things, told apart by status and never by wording: 409 is the file changing
 * under the page (a rescan), so the answer is to reload; 400 is a request the server refused. */
function Failure({ error }: { error: ApiError }) {
  if (error.status === 409)
    return (
      <>
        {error.message}{" "}
        <button className={`${d.btn} ${d.small} ${s.btn}`} onClick={() => location.reload()}>
          Reload page
        </button>
      </>
    )
  if (error.status === 400) return <>The server refused that request: {error.message}</>
  return <>{error.message}</>
}

export function Lightbox({ items, index, categories, onIndex, onMoved, onClose }: Props) {
  const item = items[index]
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [moved, setMoved] = useState<Record<number, string>>({})
  const [note, setNote] = useState<{ id: number; text?: string; error?: ApiError } | null>(null)

  // The full record, fetched when a photo is opened or navigated to. The sha is the one the inventory
  // showed us, so a rescan since then comes back as a 409 instead of a different photo.
  useEffect(() => {
    let current = true
    getRecord(item.id, item.sha256).then(
      (record) => current && setLoaded({ id: item.id, record }),
      (error: ApiError) => current && setLoaded({ id: item.id, error }),
    )
    return () => {
      current = false
    }
  }, [item.id, item.sha256])

  const go = (i: number) => i >= 0 && i < items.length && onIndex(i)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey || e.ctrlKey || e.metaKey) return
      // Arrows belong to a focused select (they would change its value, and so move the photo) and to a video's seek bar.
      if (e.target instanceof HTMLElement && /^(SELECT|INPUT|TEXTAREA|VIDEO)$/.test(e.target.tagName)) return
      if (e.key === "ArrowLeft") go(index - 1)
      else if (e.key === "ArrowRight") go(index + 1)
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  })

  const mine = loaded?.id === item.id ? loaded : null
  const record = mine && "record" in mine ? mine.record : null
  const mineNote = note?.id === item.id ? note : null
  const kinds = categories.filter((c) => c.kind === item.kind)
  const current = moved[item.id] ?? item.cat ?? ""
  const known = kinds.some((c) => c.key === current)
  const src = `/api/file/${item.id}?sha=${encodeURIComponent(item.sha256)}` // the file route needs the sha too

  async function onMove(key: string) {
    try {
      await move(item.id, key, item.sha256)
    } catch (e) {
      return setNote({ id: item.id, error: e as ApiError })
    }
    setMoved((m) => ({ ...m, [item.id]: key }))
    setNote({ id: item.id, text: `Moved to ${categories.find((c) => c.key === key)?.label}. It moves on disk the next time you sort.` })
    onMoved(item, key)
  }

  async function showOriginal() {
    try {
      await open({ id: item.id })
    } catch (e) {
      setNote({ id: item.id, error: e as ApiError })
    }
  }

  return (
    <Dialog label={item.name} onClose={onClose} scrim={false} className={s.lightbox}>
      <div className={s.media}>
        {mine && "error" in mine ? (
          <p className={s.notice} role="alert">
            <Failure error={mine.error} />
          </p>
        ) : record ? (
          item.kind === "video" ? (
            <video key={item.id} src={src} controls autoPlay playsInline poster={thumbOf(item)} />
          ) : (
            <img key={item.id} src={src} alt={item.name} />
          )
        ) : null}
      </div>
      <div className={s.bar}>
        <b>{item.name}</b>
        <small>
          {size(item.bytes)}
          {item.taken ? " · " + new Date(item.taken * 1000).toLocaleDateString() : ""} · {index + 1} of {fmt(items.length)}
        </small>
        <span className={s.spacer} />
        <small>Move to</small>
        <select
          className={`${d.select} ${s.select}`}
          aria-label="Move to folder"
          value={known ? current : ""}
          onChange={(e) => onMove(e.target.value)}
        >
          {!known && (
            <option value="" disabled>
              Choose a folder
            </option>
          )}
          {kinds.map((c) => (
            <option key={c.key} value={c.key}>
              {`${c.emoji || ""} ${c.label}`}
            </option>
          ))}
        </select>
        <button className={`${d.btn} ${d.small} ${s.btn}`} onClick={showOriginal} disabled={!record}>
          <DialogIcon name="reveal" />
          Show original
        </button>
        {mineNote?.text && <small role="status">{mineNote.text}</small>}
        {mineNote?.error && (
          <small role="alert">
            <Failure error={mineNote.error} />
          </small>
        )}
      </div>
      <button className={`${s.nav} ${s.prev}`} aria-label="Previous" onClick={() => go(index - 1)}>
        <DialogIcon name="left" />
      </button>
      <button className={`${s.nav} ${s.next}`} aria-label="Next" onClick={() => go(index + 1)}>
        <DialogIcon name="right" />
      </button>
      <button className={`${d.icon} ${s.close}`} aria-label="Close" onClick={onClose}>
        <DialogIcon name="x" />
      </button>
    </Dialog>
  )
}

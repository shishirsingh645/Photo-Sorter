import { useEffect, useState } from "react"
import { ApiError, pick as pickFolder, saveCategories } from "../api/client"
import type { AppState, PeekResult } from "../api/client"
import { fmtSize } from "../format"
import { AdvancedPanel } from "./AdvancedPanel"
import type { Labeler } from "./AdvancedPanel"
import { phaseEstimates, roughly } from "./estimates"
import { Icon } from "./Icon"
import styles from "./SetupCard.module.css"

type Key = "source" | "dest"

/** What the user has chosen so far. The parent owns it: choosing a source is what runs the peek. */
export interface Picked {
  source: string | null
  dest: string | null
  peek: PeekResult | null
}

export interface SetupCardProps {
  state: AppState
  pick: Picked
  /** `null` clears a choice (the "Change" links). The parent clears the destination with a new source. */
  onChoose: (key: Key, path: string | null) => void
  /** The labeller and the 200-file sample live with the parent, so a top-bar start sees them too. */
  labeler: Labeler
  sample: boolean
  onLabeler: (l: Labeler) => void
  onSample: (on: boolean) => void
  /** The server has the new folder list; the board and the Edit-folders dialog must follow. */
  onCategoriesSaved: (categories: AppState["categories"]) => void
  onStart: () => void
}

const fmt = (n: number) => Math.round(n).toLocaleString("en-US")
const tilde = (p: string) => p.replace(/^\/Users\/[^/]+/, "~")
const PROMPT = { source: "Choose the folder with your photos", dest: "Choose where to save the sorted folders" }

/** The placeholder follows the platform; the reference showed a macOS path to everyone. */
function examplePath(platform: string) {
  if (platform === "win32") return "D:\\Pictures\\Camera roll"
  return platform === "darwin" ? "/Users/you/Pictures/Camera roll" : "/home/you/Pictures/Camera roll"
}

/** Ported from app.js setupCard (lines 316-383). */
export function SetupCard({ state, pick, onChoose, labeler, sample, onLabeler, onSample, onCategoriesSaved, onStart }: SetupCardProps) {
  const [typing, setTyping] = useState<Key | null>(null)
  const [draft, setDraft] = useState("")
  const [advanced, setAdvanced] = useState(false)
  const [picking, setPicking] = useState(false)
  const [notice, setNotice] = useState("")
  const [cats, setCats] = useState(state.categories)
  useEffect(() => setCats(state.categories), [state.categories])

  const canPick = state.picker_available
  const { source, dest, peek: pk } = pick

  const choose = (key: Key, path: string | null) => {
    setTyping(null)
    setNotice("")
    onChoose(key, path)
  }
  const typeIn = (key: Key) => {
    setDraft("")
    setTyping(key)
  }
  const typeLink = (key: Key) => (
    <button className={styles.linkish} onClick={() => typeIn(key)}>
      or type a path
    </button>
  )
  const pickWith = async (key: Key) => {
    setPicking(true)
    setNotice("")
    try {
      const r = await pickFolder(PROMPT[key])
      if (r.path) choose(key, r.path)
      else if (r.reason) {
        setNotice(`${r.reason} Type the folder's path instead.`)
        typeIn(key)
      } // an empty reason is the user closing the window: nothing to say
    } catch (e) {
      // 409: a folder window is already open; anything else is what the server said, or that it was unreachable.
      setNotice(e instanceof ApiError ? e.message : "The folder window could not be opened.")
    } finally {
      setPicking(false)
    }
  }
  const saveCats = async (next: typeof cats) => {
    const before = cats
    setCats(next)
    try {
      await saveCategories(next.map(({ key, kind, label, emoji, rule }) => ({ key, kind: kind as "photo" | "video", label, emoji, rule })))
      onCategoriesSaved(next)
    } catch (e) {
      setCats(before)
      setNotice(e instanceof ApiError ? e.message : "The folders could not be saved.")
    }
  }

  const pathBox = (key: Key, placeholder: string) => (
    <div className={styles.typed}>
      <input
        className={styles.field}
        autoFocus
        aria-label={key === "source" ? "Photos folder path" : "Destination folder path"}
        placeholder={placeholder}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && draft.trim() && choose(key, draft.trim())}
      />
      <button className="mx-btn small solid" disabled={!draft.trim()} onClick={() => choose(key, draft.trim())}>
        Use
      </button>
    </div>
  )
  const why = !canPick && state.picker_reason ? <p className={styles.notice}>{state.picker_reason} Type the folder's path instead.</p> : null
  const note = notice ? (
    <p className={styles.notice} role="alert">
      {notice}
    </p>
  ) : null
  const chooseBtn = (key: Key, cls: string) => (
    <button className={`mx-btn ${cls}`} disabled={picking} onClick={() => void pickWith(key)}>
      <Icon name="folder" />
      {picking ? "Waiting for the folder window…" : key === "source" ? "Choose folder" : "Choose another folder"}
    </button>
  )

  const files = pk ? (sample ? Math.min(200, pk.photos + pk.videos) : pk.photos + pk.videos) : 0
  const bytes = pk ? pk.bytes * (files / Math.max(1, pk.photos + pk.videos)) : 0
  const est = phaseEstimates(files, bytes, true)
  const total = est.scan + est.dupes + est.label + est.apply
  const sug = pk?.suggested_dest || `${source} (sorted)`

  const start = () => {
    if (labeler === "jev" && !state.jev_key) return setNotice("Add JEV_KEY=your-key to a .env file in this folder to use Jev.")
    if (labeler === "claude" && state.claude_cli === false) return setNotice("Claude Code isn't installed on this computer. Install it, or pick Jev under Advanced.")
    setNotice("")
    onStart()
  }

  const done = (title: string, path: string, key: Key, extra?: React.ReactNode) => (
    <div className={`${styles.q} ${styles.done}`}>
      <span className={styles.n}>
        <Icon name="check" />
      </span>
      <div>
        <h3>{title}</h3>
        <div className={styles.picked} title={path}>
          <Icon name="folder" />
          <span>{tilde(path)}</span>
        </div>
        {extra}
      </div>
      <button className={styles.linkish} onClick={() => choose(key, null)}>
        Change
      </button>
    </div>
  )

  return (
    <div className={`${styles.setup} mx-rise`}>
      {!source ? (
        <>
          <div className={styles.q}>
            <span className={styles.n}>1</span>
            <div>
              <h2>Choose your photos</h2>
              <p>A Google Photos or Apple Photos export, or any folder with photos and videos. Nothing in it gets moved or deleted.</p>
            </div>
          </div>
          {canPick && typing !== "source" ? (
            <div className={styles.acts}>
              {chooseBtn("source", `solid ${styles.bigBtn}`)}
              {typeLink("source")}
            </div>
          ) : (
            <>
              {why}
              {pathBox("source", examplePath(state.platform))}
            </>
          )}
          {note}
          {state.source && (
            <button className={`${styles.linkish} ${styles.recent}`} onClick={() => choose("source", state.source!)}>
              Last time: {tilde(state.source)}
            </button>
          )}
        </>
      ) : (
        <>
          {done("Photos", source, "source", <p className={styles.meta}>{pk ? `${fmt(pk.photos)} photos · ${fmt(pk.videos)} videos · ${fmtSize(pk.bytes)}` : "Counting…"}</p>)}
          {pk && pk.preview_bytes_needed > pk.free_bytes && (
            <p className={styles.notice} role="alert">
              Not enough free space for the previews: they need {fmtSize(pk.preview_bytes_needed)} and {fmtSize(pk.free_bytes)} is free.
            </p>
          )}
          {!dest ? (
            <>
              <div className={styles.q}>
                <span className={styles.n}>2</span>
                <div>
                  <h2>Where should the sorted copies go?</h2>
                  <p>Your originals stay where they are. On a Mac the copies take no extra space.</p>
                </div>
              </div>
              {typing !== "dest" ? (
                <div className={`${styles.acts} ${styles.col}`}>
                  <button className={`mx-btn solid ${styles.bigBtn}`} onClick={() => choose("dest", sug)}>
                    <Icon name="check" />
                    Next to my photos
                  </button>
                  <p className={`${styles.meta} ${styles.mono}`} title={sug}>
                    {tilde(sug)}
                  </p>
                  <div className={styles.row}>
                    {canPick && chooseBtn("dest", "small")}
                    {typeLink("dest")}
                  </div>
                </div>
              ) : (
                <>
                  {why}
                  {pathBox("dest", sug)}
                  <button className={`${styles.linkish} ${styles.recent}`} onClick={() => choose("dest", sug)}>
                    Use {tilde(sug)}
                  </button>
                </>
              )}
              {note}
            </>
          ) : (
            done("Sorted copies go to", dest, "dest")
          )}
        </>
      )}
      {source && dest && (
        <>
          <div className={styles.start}>
            <button className={`mx-btn solid ${styles.bigBtn} ${styles.wide}`} onClick={start}>
              <Icon name="play" />
              Start sorting
            </button>
            <p className={styles.meta}>
              <Icon name="clock" />
              {pk
                ? ` Usually ${roughly(total)} for ${fmt(files)} files${labeler === "claude" ? `, of which Claude labelling takes ${roughly(est.label)}` : ""}`
                : " Counting files…"}
            </p>
            {note}
          </div>
          <button className={styles.advToggle} aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>
            Advanced
            <Icon name="down" />
          </button>
          {advanced && (
            <AdvancedPanel
              categories={cats}
              files={files}
              jevKey={state.jev_key}
              labeler={labeler}
              sample={sample}
              onLabeler={(l) => {
                setNotice("") // a "pick Jev" or "needs a key" notice is about the old choice
                onLabeler(l)
              }}
              onSample={onSample}
              onSave={(n) => void saveCats(n)}
            />
          )}
        </>
      )}
    </div>
  )
}

import { Dialog } from "./Dialog"
import { DialogIcon } from "./DialogIcon"
import { fmt } from "./format"
import d from "./Dialog.module.css"
import s from "./PaidConfirm.module.css"

const TOKENS_PER_FILE = 980 // the reference app.js 7

/** The reference's confirmPaid, as a component: `onResolve(true)` is "Spend tokens", `onResolve(false)` is
 * every way of dismissing it (Close, Escape, the backdrop). */
export function PaidConfirm({ files, onResolve }: { files: number; onResolve: (spend: boolean) => void }) {
  return (
    <Dialog label="Label with Jev" className={s.pc} onClose={() => onResolve(false)}>
      <div className={d.head}>
        <h2>Label with Jev</h2>
        <button className={d.icon} onClick={() => onResolve(false)} aria-label="Close">
          <DialogIcon name="x" />
        </button>
      </div>
      <div className={s.list}>
        <div className={s.choice}>
          <div>
            <b>{`${fmt(files)} files, about ${fmt(files * TOKENS_PER_FILE)} tokens`}</b>
            <p>
              Sends a small 280px preview of each file to TypeSafe's Jev model, never the original. Check the per-token
              price on console.typesafe.ai.
            </p>
          </div>
          <button className={`${d.btn} ${d.solid} ${s.btn}`} onClick={() => onResolve(true)}>
            Spend tokens
          </button>
        </div>
      </div>
      <p className={s.note}>Already-labelled files are skipped, so you can stop and resume.</p>
    </Dialog>
  )
}

import styles from "./Toast.module.css"

/** Stateless like the reference's #toast: the caller sets the text and flips `on`, and owns the hide timer. */
export function Toast({ text, on }: { text: string; on: boolean }) {
  return (
    <div className={styles.toast} data-on={on} role="status">
      {text}
    </div>
  )
}

import { Icon } from "./Icon"
import styles from "./TitleRow.module.css"

export interface TitleRowProps {
  /** Files in the library; shown in the badge beside the title. */
  total: number
  /** Where the photos come from, already tidied for display. */
  source: string
  /** The badge is hidden until there is a library and a sort to show. */
  showTotal: boolean
  onEditFolders: () => void
  onOpenSorted: () => void
  /** True when the mode is done and a sorted folder exists. */
  canOpenSorted: boolean
}

export function TitleRow({ total, source, showTotal, onEditFolders, onOpenSorted, canOpenSorted }: TitleRowProps) {
  return (
    <div className={styles.title}>
      <h1>Sorting my camera roll</h1>
      {showTotal && <span className={styles.count}>{total.toLocaleString("en-US")}</span>}
      <span className={styles.sub}>{source}</span>
      <span className={styles.spacer} />
      <button className={styles.btn} onClick={onEditFolders}>
        <Icon name="pencil" />
        Edit folders
      </button>
      {canOpenSorted && (
        <button className={styles.btn} onClick={onOpenSorted}>
          <Icon name="folder" />
          Open sorted folder
        </button>
      )}
    </div>
  )
}

import { useEffect, useRef } from "react"
import { getState } from "../api/client"
import type { JobEvent } from "../api/client"
import type { StreamEvent } from "../state/reducer"

export const RECONNECT_MS = 900
export const POLL_MS = 900
/** Failed reconnects in a row before polling /api/state takes over. */
export const POLL_AFTER = 3

/** Subscribes to /api/events. A dropped stream is reconnected every RECONNECT_MS (a laptop waking from sleep
 * is normal, not an error). After POLL_AFTER failed reconnects in a row it also polls /api/state every
 * POLL_MS and hands each answer to `onEvent` as a snapshot; the poll stops when the stream is back. */
export function useJobEvents(onEvent: (e: StreamEvent) => void): void {
  const latest = useRef(onEvent)
  latest.current = onEvent

  useEffect(() => {
    let source: EventSource | null = null
    let retry: ReturnType<typeof setTimeout> | undefined
    let poller: ReturnType<typeof setInterval> | undefined
    let errors = 0 // consecutive failed connections: the first is the drop, each later one a failed reconnect
    let stopped = false

    const snapshot = async () => {
      try {
        const state = await getState()
        if (!stopped) latest.current({ type: "snapshot", state })
      } catch {
        /* the server is still away; the next tick tries again */
      }
    }
    const stopPolling = () => {
      clearInterval(poller)
      poller = undefined
    }

    const connect = () => {
      source = new EventSource("/api/events")
      source.onopen = () => {
        // Events sent while the stream was down are gone, so ask for the whole state once.
        if (errors > 0) void snapshot()
        errors = 0
        stopPolling()
      }
      source.onmessage = (m: MessageEvent<string>) => {
        try {
          latest.current(JSON.parse(m.data) as JobEvent)
        } catch {
          /* a frame that is not JSON is not an event */
        }
      }
      source.onerror = () => {
        // Closed here and reopened below, so the delay is ours rather than the browser's own choice.
        source?.close()
        errors += 1
        if (errors > POLL_AFTER && !poller) poller = setInterval(snapshot, POLL_MS)
        retry = setTimeout(connect, RECONNECT_MS)
      }
    }

    connect()
    return () => {
      stopped = true
      source?.close()
      clearTimeout(retry)
      stopPolling()
    }
  }, [])
}

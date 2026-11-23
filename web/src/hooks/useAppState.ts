import { useCallback, useEffect, useReducer, useState } from "react"
import { getState } from "../api/client"
import type { ApiError, AppState } from "../api/client"
import { initialState, reducer } from "../state/reducer"
import type { Action, State } from "../state/reducer"

/** Loads /api/state once, and again whenever the tab comes back or the network returns: a laptop that slept
 * through a job's end has no stream to tell it so. `dispatch` is for useJobEvents and the callers' actions.
 * `load` is where the state comes from: the server, or for ?demo the demo folder's own files. */
export function useAppState(load: () => Promise<AppState> = getState): {
  state: State
  dispatch: (a: Action) => void
  error: ApiError | null
} {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [error, setError] = useState<ApiError | null>(null)

  const refresh = useCallback(async () => {
    try {
      dispatch({ type: "state", state: await load() })
      setError(null)
    } catch (e) {
      setError(e as ApiError)
    }
  }, [load])

  useEffect(() => {
    void refresh()
    const onVisible = () => document.visibilityState === "visible" && void refresh()
    document.addEventListener("visibilitychange", onVisible)
    window.addEventListener("online", refresh)
    return () => {
      document.removeEventListener("visibilitychange", onVisible)
      window.removeEventListener("online", refresh)
    }
  }, [refresh])

  return { state, dispatch, error }
}

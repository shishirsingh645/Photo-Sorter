import { useCallback, useEffect, useReducer, useState } from "react"
import { ApiError, getState } from "../api/client"
import { initialState, reducer } from "../state/reducer"
import type { Action, State } from "../state/reducer"

/** Loads /api/state once, and again whenever the tab comes back or the network returns: a laptop that slept
 * through a job's end has no stream to tell it so. `dispatch` is for useJobEvents and the callers' actions. */
export function useAppState(): { state: State; dispatch: (a: Action) => void; error: ApiError | null } {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [error, setError] = useState<ApiError | null>(null)

  const load = useCallback(async () => {
    try {
      dispatch({ type: "state", state: await getState() })
      setError(null)
    } catch (e) {
      setError(e as ApiError)
    }
  }, [])

  useEffect(() => {
    void load()
    const onVisible = () => document.visibilityState === "visible" && void load()
    document.addEventListener("visibilitychange", onVisible)
    window.addEventListener("online", load)
    return () => {
      document.removeEventListener("visibilitychange", onVisible)
      window.removeEventListener("online", load)
    }
  }, [load])

  return { state, dispatch, error }
}

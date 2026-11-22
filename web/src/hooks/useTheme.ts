import { useCallback, useLayoutEffect, useState } from "react"

export type Theme = "light" | "dark"
const KEY = "theme"

// Private mode can make any localStorage access throw; the theme then lives in memory only.
function readStored(): Theme | null {
  try {
    const v = localStorage.getItem(KEY)
    return v === "light" || v === "dark" ? v : null
  } catch {
    return null
  }
}

function initial(): Theme {
  return readStored() ?? (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light")
}

export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(initial)

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  const toggle = useCallback(() => {
    const next: Theme = theme === "dark" ? "light" : "dark"
    setTheme(next)
    try {
      localStorage.setItem(KEY, next)
    } catch {
      /* in-memory only */
    }
  }, [theme])

  return { theme, toggle }
}

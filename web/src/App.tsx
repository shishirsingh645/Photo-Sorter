import { useTheme } from "./hooks/useTheme"

export function App() {
  const { theme, toggle } = useTheme()
  return (
    <button onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
      {theme}
    </button>
  )
}

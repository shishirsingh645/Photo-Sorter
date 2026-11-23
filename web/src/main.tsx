import React from "react"
import { createRoot } from "react-dom/client"
import "./styles/tokens.css"
import "./styles/base.css"
import "./styles/components.css" // before the App, so component modules still win a tie
import { App } from "./App"

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

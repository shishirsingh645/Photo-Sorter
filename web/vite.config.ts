import { defineConfig } from "vitest/config"
import react from "@vitejs/plugin-react"

// Vite's proxy pipes responses straight through (no buffering), so SSE needs no extra option.
const api = { target: "http://127.0.0.1:8765" }

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": api, "/events": api } },
  build: { outDir: "dist" }, // relative to this folder (the Vite root): web/dist
  test: { environment: "jsdom", setupFiles: ["./src/test-setup.ts"] },
})

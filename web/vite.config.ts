import { defineConfig } from "vitest/config"
import react from "@vitejs/plugin-react"

// Vite's proxy pipes responses straight through (no buffering), so SSE needs no extra option.
// changeOrigin sends the server its own address as Host, which its DNS-rebinding guard requires. The page also reads
// /data, /demo and /peek, which the server mounts beside /api. The default port, as `photo-sorter serve` uses.
const api = { target: "http://127.0.0.1:8765", changeOrigin: true }

export default defineConfig({
  plugins: [react()],
  // The port is pinned: `photo-sorter serve --dev` accepts POSTs from exactly this origin (photosorter/api/app.py).
  server: { port: 5173, strictPort: true, proxy: { "/api": api, "/events": api, "/data": api, "/demo": api, "/peek": api } },
  build: { outDir: "dist" }, // relative to this folder (the Vite root): web/dist
  test: { environment: "jsdom", setupFiles: ["./src/test-setup.ts"], css: true },
})

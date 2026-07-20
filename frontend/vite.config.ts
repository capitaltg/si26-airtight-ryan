import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// `/api/*` is proxied to the FastAPI backend and the `/api` prefix is stripped,
// so the browser calls `/api/health` and the backend sees `/health`.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
})

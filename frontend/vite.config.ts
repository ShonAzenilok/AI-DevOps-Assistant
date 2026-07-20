import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // FastAPI backend (added later) — keeps frontend code environment-agnostic
      '/api': 'http://localhost:8000',
    },
  },
})

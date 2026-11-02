import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Where the dev server forwards /api requests. Inside docker compose Django is
// reachable as http://web:8000; when running `npm run dev` on the host it is
// http://localhost:8000.
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The browser only ever talks to the Vite server (same origin), and Vite
    // forwards /api/* to Django. Same origin means no CORS setup in Django.
    //
    // changeOrigin stays false on purpose: Django then sees Host: localhost,
    // which is in ALLOWED_HOSTS. With true it would see "web:8000" and reject
    // the request with 400 DisallowedHost.
    proxy: {
      '/api': { target: apiTarget, changeOrigin: false },
    },
    // Docker on Windows doesn't forward file-change events through bind
    // mounts, so hot reload needs polling there (enabled via docker-compose).
    watch: process.env.VITE_USE_POLLING ? { usePolling: true, interval: 300 } : undefined,
  },
  // Vitest reads this block. jsdom gives tests a browser-like `window`/`document`.
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    css: false,
    restoreMocks: true,
  },
})

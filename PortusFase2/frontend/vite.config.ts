import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// El dev server de Vite corre en 5173 y proxyea /api y /api/stream hacia Flask (5000).
// En produccion el build de dist/ lo sirve el propio Flask (ruta catch-all en app.py).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 900,
  },
})

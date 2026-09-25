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
        // Por defecto backend local (desarrollo con --mock en Windows).
        // Para apuntar a la Raspberry: $env:PORTUS_API="http://192.168.0.13:5000"; pnpm dev
        target: process.env.PORTUS_API ?? 'http://localhost:5000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 900,
  },
})

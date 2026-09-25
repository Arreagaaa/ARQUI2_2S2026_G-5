import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// El dev server de Vite corre en 5173 y proxyea /api hacia Flask (5000).
// El destino se configura en frontend/.env.local con:
//   PORTUS_API=http://192.168.0.13:5000   (backend en la Raspberry)
//   (sin .env.local o sin PORTUS_API usa http://localhost:5000, backend local)
// En produccion el build de dist/ lo sirve el propio Flask (ruta catch-all en app.py).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: env.PORTUS_API || 'http://localhost:5000',
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      chunkSizeWarningLimit: 900,
    },
  }
})

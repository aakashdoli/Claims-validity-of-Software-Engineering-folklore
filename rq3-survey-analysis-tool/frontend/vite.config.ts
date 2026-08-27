import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The API port is chosen by run.sh (it walks upward from 8000 if that port is
// already taken by something else on the machine) and handed over in .env.local.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const apiPort = env.VITE_API_PORT || '8000'
  return {
    plugins: [react()],
    server: {
      port: 5173,
      // The backend is the only source of numbers; the frontend computes none.
      proxy: {
        '/api': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      },
    },
  }
})

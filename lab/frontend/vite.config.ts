import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5174,
    proxy: {
      // Dual suggest (v2)
      '/api/v1': 'http://127.0.0.1:8100',
      '/health': 'http://127.0.0.1:8100',
      // Image detect reuses ver1 advisor when running
      '/api/detect': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})

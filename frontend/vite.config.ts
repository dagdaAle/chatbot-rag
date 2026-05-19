import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': 'http://backend:8000',
      '/health': 'http://backend:8000',
      '/docs': 'http://backend:8000',
      '/openapi.json': 'http://backend:8000',
    },
  },
  optimizeDeps: {
    include: ['react-pdf'],
  },
})

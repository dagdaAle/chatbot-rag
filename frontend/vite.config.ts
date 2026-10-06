import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': process.env.VITE_PROXY_TARGET ?? 'http://backend:8000',
      '/health': process.env.VITE_PROXY_TARGET ?? 'http://backend:8000',
    },
  },
  optimizeDeps: {
    include: ['react-pdf'],
  },
})

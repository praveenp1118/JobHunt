import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    // Allow reaching the dev server by Docker service name (e.g. for in-network
    // headless-browser screenshotting). Dev-only; prod is served by nginx.
    allowedHosts: ['frontend', 'localhost'],
    // Windows + Docker bind mounts don't propagate native file events to the
    // Linux container, so HMR needs polling to detect edits.
    watch: {
      usePolling: true,
      interval: 300,
    },
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      // WebSocket for the support chat (ws: true upgrades the connection).
      '/ws': {
        target: 'ws://backend:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})

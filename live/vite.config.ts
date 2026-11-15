import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  // QueuePilot Live reads MAIN's venue files from ../data/crowd, outside this folder.
  server: { port: 5174, strictPort: true, fs: { allow: ['..'] } },
})

import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // The Design Studio reads MAIN's results from ../data/design, outside this folder.
  server: { fs: { allow: ['..'] } },
})

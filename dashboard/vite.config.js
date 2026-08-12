import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: './', // relative paths for assets so it can be served from any subdirectory
  build: {
    outDir: resolve(__dirname, '../static/dev-debugger'),
    emptyOutDir: true,
  }
})

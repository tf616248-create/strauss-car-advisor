import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.js'],
    // the first test in a file renders the screen cold; on a busy machine that alone passed the 5s default
    testTimeout: 15000,
  },
})

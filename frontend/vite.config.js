import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    // the tests live in tests/, in the same folders as the code in src/ (tests/employee/, tests/lib/...);
    // they import the code as '@/...'. Nothing under tests/ is imported by the app, so it is never built.
    include: ['tests/**/*.test.{js,jsx}'],
    setupFiles: ['./tests/setup.js'],
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    // the first test in a file renders the screen cold; on a busy machine that alone passed the 5s default
    testTimeout: 15000,
  },
})

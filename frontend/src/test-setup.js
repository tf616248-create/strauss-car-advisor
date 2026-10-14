import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup() // no vitest globals, so Testing Library can't register this itself
  localStorage.clear()
  sessionStorage.clear()
})

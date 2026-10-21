import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup() // no vitest globals, so Testing Library can't register this itself
  localStorage.clear()
  sessionStorage.clear()
})

// jsdom plays no media: play() resolves and pause() does nothing; tests drive the video's time
// themselves (components/Intro.test.jsx)
HTMLMediaElement.prototype.play = function play() { return Promise.resolve() }
HTMLMediaElement.prototype.pause = function pause() {}

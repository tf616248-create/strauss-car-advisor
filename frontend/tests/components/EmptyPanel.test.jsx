import { readFileSync } from 'node:fs'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import EmptyPanel from '@/components/EmptyPanel'

describe('EmptyPanel', () => {
  it('explains, in the page colors: not the opening scene\'s dark full-screen styles', () => {
    const { container } = render(<EmptyPanel />)
    expect(screen.getByRole('heading', { name: 'למה רכב משנה את המשכורת?' })).toBeInTheDocument()
    // .intro is the opening scene (dark, 100svh); the panel has classes of its own
    expect(container.querySelector('.intro, [class*="intro__"]')).toBeNull()
    const css = readFileSync('src/styles.css', 'utf8')
    const rule = css.match(/\.explainer \{([^}]*)\}/)[1]
    expect(rule).not.toMatch(/background|height/)
  })
})

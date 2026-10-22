// The font: Rubik, self-hosted (no Google Fonts), only 400/500/700, only Hebrew and Latin, swap.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const fonts = readFileSync('src/fonts.css', 'utf8')
const styles = readFileSync('src/styles.css', 'utf8')
const html = readFileSync('index.html', 'utf8')

describe('the font', () => {
  it('Rubik from @fontsource, weights 400, 500, 700, Hebrew and Latin, font-display swap', () => {
    const faces = [...fonts.matchAll(/@font-face \{([^}]*)\}/g)].map((m) => m[1])
    expect(faces).toHaveLength(6)
    for (const face of faces) {
      expect(face).toMatch(/font-family: "Rubik"/)
      expect(face).toMatch(/font-display: swap/)
      expect(face).toMatch(/unicode-range:/)
      expect(face).toMatch(/url\("@fontsource\/rubik\/files\/rubik-(hebrew|latin)-(400|500|700)-normal\.woff2"\)/)
    }
  })

  it('one font for the whole site, with a system fallback', () => {
    expect(styles).toMatch(/--font: "Rubik", system-ui, sans-serif;/)
    expect(styles).toMatch(/font-family: var\(--font\);/)
    expect(styles.match(/font-family:/g)).toHaveLength(2) // :root, and inherit on the PDF icon
  })

  it('no other font, and no font from Google', () => {
    for (const text of [styles, html, fonts]) {
      expect(text).not.toMatch(/fonts\.googleapis|fonts\.gstatic|Assistant/)
    }
  })

  it('only the loaded weights are used (no faux bold)', () => {
    const weights = new Set([...styles.matchAll(/font-weight: (\d+)/g)].map((m) => m[1]))
    expect([...weights].every((w) => ['400', '500', '700'].includes(w))).toBe(true)
  })
})

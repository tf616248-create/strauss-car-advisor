// The design: the website's colors (frontend/src/styles.css, light and dark), one font (Rubik, only the
// weights the website loads: 400, 500, 700), and Kobi's answer with the website's reading tokens.
import fs from 'fs'
import path from 'path'
import { render, screen } from '@testing-library/react-native'
import { FONTS, PALETTES, READING } from '@/theme'
import Answer from '@/components/Answer'

const css = fs.readFileSync(path.join(__dirname, '../../frontend/src/styles.css'), 'utf8')
function tokens(selector) {
  const block = css.slice(css.indexOf(selector)).match(/\{([^}]*)\}/)[1]
  return Object.fromEntries([...block.matchAll(/--([\w-]+):\s*(#[0-9A-Fa-f]{6})/g)].map(([, k, v]) => [k, v.toUpperCase()]))
}
const SITE = { light: tokens(':root {'), dark: { ...tokens(':root {'), ...tokens(':root[data-theme="dark"] {') } }
const NAMES = { bg: 'bg', surface: 'surface', surface2: 'surface2', text: 'text', muted: 'muted', line: 'line', error: 'error',
  cyanText: 'brand-cyan-text', readingText: 'reading-text', cyan: 'cyan', green: 'green', orange: 'orange', onBrand: 'on-brand' }

test.each(['light', 'dark'])('the %s colors are the website\'s values', (mode) => {
  for (const [ours, theirs] of Object.entries(NAMES)) expect([ours, PALETTES[mode][ours].toUpperCase()]).toEqual([ours, SITE[mode][theirs]])
})

test('one font: Rubik, only 400, 500 and 700 (a heavier weight asked for is 700, a lighter bold is 500)', () => {
  expect(new Set(Object.values(FONTS))).toEqual(new Set(['Rubik_400Regular', 'Rubik_500Medium', 'Rubik_700Bold']))
  expect(FONTS[800]).toBe('Rubik_700Bold')
  expect(FONTS[600]).toBe('Rubik_500Medium')
  const app = fs.readFileSync(path.join(__dirname, '../App.js'), 'utf8')
  expect(app).toMatch(/@expo-google-fonts\/rubik/)
  expect(app).not.toMatch(/Assistant/)
})

test('reading: 16 with a line height of 1.7, about 0.6em between paragraphs and list items', () => {
  expect(READING).toEqual({ size: 16, lineHeight: 27, gap: 10 })
})

test('the answer: reading text color and spacing, ◦ bullets in the muted color, bold in the text cyan', async () => {
  await render(<Answer text={'פסקה עם **הדגשה**.\n\n- סעיף ראשון\n- סעיף שני'} />)
  const flat = (el) => Object.assign({}, ...[el.props.style].flat(Infinity).filter(Boolean))
  expect(flat(screen.getByText('הדגשה'))).toMatchObject({ fontFamily: 'Rubik_700Bold', color: PALETTES.light.cyanText })
  const bullets = screen.getAllByText('◦')
  expect(bullets).toHaveLength(2)
  expect(flat(bullets[0]).color).toBe(PALETTES.light.muted)
  const para = flat(screen.getByText(/פסקה עם/))
  expect(para).toMatchObject({ fontSize: 16, lineHeight: 27, color: PALETTES.light.readingText })
})

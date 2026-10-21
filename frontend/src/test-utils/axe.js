// axe-core (the engine behind vitest-axe and @axe-core/playwright), run on the rendered DOM in jsdom.
// jsdom has no layout and no CSS, so two things are checked elsewhere: color contrast (a11y.test.jsx
// computes the ratios of the color tokens in styles.css) and the real widths (checked in a browser).
import axe from 'axe-core'

const OPTIONS = {
  runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'] },
  rules: { 'color-contrast': { enabled: false } }, // needs real rendering; see above
  resultTypes: ['violations'],
}

// -> [{ id, impact, help, nodes }] for every violation, every impact (minor to critical).
// The whole document by default: page rules (one main landmark, one h1) run only on it
export async function axeViolations(node = document) {
  const { violations } = await axe.run(node, OPTIONS)
  return violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.map((n) => n.target.join(' ')) }))
}

// a phone or a computer, as the app sees it in jsdom: the window width and the media queries
// the code asks (lib/payslip.js: pointer: coarse; Intro.jsx: reduced motion)
export function viewport(width, { reduceMotion = false } = {}) {
  const phone = width < 768
  Object.defineProperty(window, 'innerWidth', { value: width, configurable: true, writable: true })
  window.matchMedia = (q) => ({
    matches: (phone && q.includes('coarse')) || (reduceMotion && q.includes('reduce'))
      || (q.includes('max-width: 767px') && phone),
    media: q, addEventListener() {}, removeEventListener() {},
  })
}

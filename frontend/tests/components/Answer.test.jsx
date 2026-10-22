import { render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { describe, expect, it, vi } from 'vitest'
import Answer from '@/components/Answer'

describe('Answer (the bot\'s Markdown)', () => {
  it('bold, headings and lists are shown formatted, without the stars', () => {
    const { container } = render(<Answer text={'## מה חסר\n1. **עיסוק מדויק** וקבוצה\n2. שכר\n\n- *בונוס* חודשי'} />)
    expect(screen.getByRole('heading', { name: 'מה חסר' })).toBeInTheDocument()
    expect(screen.getByText('עיסוק מדויק').tagName).toBe('STRONG')
    expect(screen.getByText('בונוס').tagName).toBe('EM')
    expect(container.querySelectorAll('ol > li')).toHaveLength(2)
    expect(container.querySelectorAll('ul > li')).toHaveLength(1)
    expect(container.textContent).not.toContain('**')
  })

  it('no tables: the comparison lives in the card', () => {
    const { container } = render(<Answer text={'| היום | חלופה |\n|---|---|\n| 1 | 2 |'} />)
    expect(container.querySelector('table')).toBeNull()
  })

  it('no HTML from the model, no links or images', () => {
    const { container } = render(<Answer text={'<b>x</b> [קישור](https://evil.example) ![](https://evil.example/i.png)'} />)
    expect(container.querySelector('b, a, img, script')).toBeNull()
    expect(container.textContent).toContain('קישור')
  })

  it('one link only: /profile, the employee\'s own profile, opens it here', async () => {
    const { default: userEvent } = await import('@testing-library/user-event')
    const onProfile = vi.fn()
    const { container } = render(
      <Answer text={'מלאו בפרופיל שלכם, /profile. או [כאן](https://evil.example) או [פרופיל](/profile).'}
        onProfile={onProfile} />)
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(2)
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/profile', '/profile'])
    expect(container.querySelector('a[href^="http"]')).toBeNull() // any other link stays text
    expect(container.textContent).toContain('כאן')
    await userEvent.setup().click(links[0])
    expect(onProfile).toHaveBeenCalledWith(links[0])
  })

  it('without onProfile, /profile is plain text', () => {
    const { container } = render(<Answer text={'בפרופיל: /profile'} />)
    expect(container.querySelector('a')).toBeNull()
    expect(container.textContent).toContain('/profile')
  })

  it('an unfinished bold while the answer streams in does not break', () => {
    const { container } = render(<Answer text={'הנטו **יעלה'} />)
    expect(container.textContent).toContain('יעלה')
  })
})

describe('text colors (styles.css)', () => {
  const css = readFileSync('src/styles.css', 'utf8')

  it('has the dark brand cyan for text (AA on white and on the gray surface: a11y.test.jsx)', () => {
    expect(css).toMatch(/--brand-cyan-text:\s*#0A7896/i)
  })

  it('bold words use it; the bright cyan #16BDE6 is never a text color', () => {
    expect(css).toMatch(/\.answer strong\s*{[^}]*color:\s*var\(--brand-cyan-text\)/)
    expect(css).not.toMatch(/(^|[;{\s])color:\s*(#16BDE6|var\(--cyan\))/im)
  })

  it('the "only a check" line in the header is shown on phones too (a small line under the header)', () => {
    expect(css).not.toMatch(/\.topbar__sub\s*{\s*display:\s*none/)
  })

  it('the welcome screen is centred only when it fits: on a short phone screen its top (Kobi) can still be scrolled to', () => {
    const welcome = css.match(/\.welcome\s*{([^}]*)}/)[1]
    expect(welcome).not.toMatch(/justify-content:\s*center/)
    expect(welcome).toMatch(/justify-content:\s*safe center/)
  })

  it('headings are dark text with a small cyan bar', () => {
    expect(css).toMatch(/\.answer :is\(h1, h2, h3, h4, h5, h6\)\s*{[^}]*color:\s*var\(--text\)/)
    expect(css).toMatch(/\.answer :is\(h1, h2, h3, h4, h5, h6\)::after\s*{[^}]*background:\s*var\(--cyan\)/)
  })

  it('one font on the whole page (Assistant), no handwriting; the welcome title is bold and big', () => {
    expect(css).not.toMatch(/Playpen/)
    expect([...css.matchAll(/font-family:\s*([^;]+);/g)].map((m) => m[1]).every((f) => f.startsWith('"Assistant"') || f === 'inherit')).toBe(true)
    expect(css).toMatch(/\.welcome__title\s*{[^}]*font-weight:\s*(700|800)/)
  })
})

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import cfg from '@/config/accessibility.json'
import introCfg from '@/config/intro.json'
import App from '@/App'
import AccessibilityStatement from '@/components/AccessibilityStatement'
import Intro from '@/components/Intro'
import EmployeeScreen from '@/employee/EmployeeScreen'
import RepScreen from '@/rep/RepScreen'

const S = cfg.statement
const linkIn = (container) => within(container).getByRole('link', { name: cfg.link })

describe('the accessibility statement (/accessibility)', () => {
  it('is its own page, from the address', () => {
    window.history.pushState({}, '', '/accessibility')
    render(<App />)
    expect(screen.getByRole('heading', { level: 1, name: S.title })).toBeInTheDocument()
    window.history.pushState({}, '', '/')
  })

  it('names the standard and the level, what was done, the known limits, and the date', () => {
    render(<AccessibilityStatement />)
    const text = document.body.textContent
    expect(text).toContain('ת"י 5568')
    expect(text).toContain('WCAG 2.1')
    expect(text).toContain('AA')
    for (const t of [...S.done, ...S.limits]) expect(text).toContain(t)
    expect(screen.getByText((_, el) => el?.tagName === 'TIME')).toHaveAttribute('datetime', S.checkedOn)
  })

  it('a clear placeholder for the contact - no invented name, phone or email', () => {
    render(<AccessibilityStatement />)
    expect(screen.getByText('[פרטי רכז/ת הנגישות של שטראוס – להשלמה בפיילוט]')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/@|\d{2,3}-?\d{7}/)
  })

  it('leaves the phone app out, and never claims full accessibility or approval', () => {
    render(<AccessibilityStatement />)
    const text = document.body.textContent
    expect(text).toContain('אפליקציית הטלפון')
    expect(text).toContain('נבדק והותאם ככל הניתן')
    expect(text).not.toMatch(/נגיש במלואו|מאושר|נגיש לחלוטין/)
  })

  it('a way back to Kobi', () => {
    render(<AccessibilityStatement />)
    expect(screen.getByRole('link', { name: cfg.backHome })).toHaveAttribute('href', '/')
  })
})

describe('the link at the bottom of every screen', () => {
  it('the opening scene, while it plays and at its end; reachable from the keyboard', async () => {
    window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} })
    const { container } = render(<Intro api={{ login: vi.fn() }} hasToken={false} onEnter={vi.fn()} />)
    expect(linkIn(container)).toHaveAttribute('href', '/accessibility')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: introCfg.texts.skipLabel }))
    const link = linkIn(container)
    for (let i = 0; i < 10 && document.activeElement !== link; i++) await user.tab()
    expect(link).toHaveFocus()
    delete window.matchMedia
  })

  it('the chat', () => {
    const api = { threads: vi.fn().mockResolvedValue([]), restore: vi.fn().mockRejectedValue(new Error('x')) }
    const { container } = render(<EmployeeScreen api={api} subscribe={() => () => {}} notifier={{ beep() {}, setUnread() {} }} />)
    expect(linkIn(container)).toHaveAttribute('href', '/accessibility')
  })

  it('the rep screen', () => {
    const { container } = render(<RepScreen api={{ repList: vi.fn(), repAnswer: vi.fn() }} />)
    expect(linkIn(container)).toHaveAttribute('href', '/accessibility')
  })
})

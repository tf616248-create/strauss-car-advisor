// Accessibility, WCAG 2.1 AA (and ת"י 5568, which adopts it): axe on every screen, at a phone width
// (375) and a computer width (1280). Any violation fails, of any impact: a new problem is caught here.
// Color contrast is computed from the color tokens in styles.css (jsdom cannot render colors).
import { readFileSync } from 'node:fs'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import noa from './test-fixtures/card-noa.json'
import ranking from './test-fixtures/card-ranking.json'
import specs from './test-fixtures/card-specs.json'
import rachel from './test-fixtures/card-rachel-waiting.json'
import intro from './config/intro.json'
import payslipCfg from './config/payslip.json'
import sidebarCfg from './config/sidebar.json'
import profileCfg from './config/profile.json'
import settingsCfg from './config/settings.json'
import Intro from './components/Intro'
import EmployeeApp from './employee/EmployeeApp'
import EmployeeScreen from './employee/EmployeeScreen'
import RepScreen from './rep/RepScreen'
import AccessibilityStatement from './components/AccessibilityStatement'
import { setToken } from './lib/session'
import { axeViolations, viewport } from './test-utils/axe'

const TID = '11111111-2222-3333-4444-555555555555'
const WIDTHS = [375, 1280]
// The first axe run is cold and, with every test file running at once, can pass 15s (vite.config.js).
// A test cut off then leaves axe running, and the next ones fail with "axe is already running".
vi.setConfig({ testTimeout: 45000 })

// the page as index.html makes it (jsdom starts from a bare document): its language, direction and title
const INDEX = readFileSync('index.html', 'utf8')
beforeEach(() => {
  const html = document.documentElement
  html.setAttribute('lang', INDEX.match(/<html[^>]*lang="([^"]+)"/)[1])
  html.setAttribute('dir', INDEX.match(/<html[^>]*dir="([^"]+)"/)[1])
  document.title = INDEX.match(/<title>([^<]+)<\/title>/)[1]
  window.history.replaceState(null, '', '/') // the profile dialog opens at /profile
})
afterEach(() => { delete window.matchMedia })

function chatApi(events = []) {
  return {
    login: vi.fn().mockResolvedValue({ token: 'tok' }),
    threads: vi.fn().mockResolvedValue([{ thread_id: TID, title: 'ATTO 3', updated_at: '2026-10-20T10:00:00Z' }]),
    restore: vi.fn().mockRejectedValue(new Error('none')),
    streamChat: vi.fn(async (p, onEvent) => { for (const [e, d] of events) onEvent(e, d) }),
    streamRepAnswered: vi.fn(),
    streamPayslip: vi.fn(),
    payslipImage: vi.fn().mockResolvedValue('blob:x'),
    me: vi.fn().mockResolvedValue({ employee_id: 'E01', name: 'נועה לוי' }),
    profile: vi.fn().mockResolvedValue({
      employee_id: 'E01', fields: { occupation: 'מנהל/ת מוצר', base: 15000, current_kind: 'car' },
      sources: { occupation: 'profile', base: 'payslip', current_kind: 'chat' }, group: 'ג' }),
    settings: vi.fn().mockResolvedValue({ theme: 'light', tone: 'professional' }),
    saveSettings: vi.fn(async (values) => ({ theme: 'light', tone: 'professional', ...values })),
    saveProfile: vi.fn().mockResolvedValue({ invalid: { base: { range: [1, 500000] }, occupation: { suggestions: ['מנהל/ת מוצר', 'מנהל/ת פיתוח'] } } }),
  }
}
const quiet = { subscribe: () => () => {}, notifier: { beep: vi.fn(), setUnread: vi.fn() } }

async function ask(api, text = 'אם אעבור ל-Atto 3?') {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('הודעה'), text)
  await user.click(screen.getByRole('button', { name: 'שליחה' }))
  return user
}

const expectClean = async () => expect(await axeViolations()).toEqual([])

describe.each(WIDTHS)('axe at %ipx', (width) => {
  it('the opening scene, while the video plays', async () => {
    viewport(width)
    render(<Intro api={chatApi()} hasToken={false} onEnter={vi.fn()} />)
    await expectClean()
  })

  it('the opening scene at its end, with the login card and an error', async () => {
    viewport(width)
    const api = { login: vi.fn().mockRejectedValue(Object.assign(new Error('x'), { status: 401 })) }
    render(<Intro api={api} hasToken={false} onEnter={vi.fn()} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: intro.texts.skipLabel }))
    await user.type(screen.getByLabelText(intro.texts.code), '9')
    await user.click(screen.getByRole('button', { name: intro.texts.enterLabel }))
    await screen.findByRole('alert')
    await expectClean()
  })

  it('the opening scene with a token, and with reduced motion', async () => {
    viewport(width, { reduceMotion: true })
    render(<Intro api={chatApi()} hasToken onEnter={vi.fn()} />)
    await expectClean()
  })

  it('the chat under the banner (the welcome; the sidebar closed, then open with the conversations)', async () => {
    viewport(width)
    setToken('tok')
    render(<EmployeeApp api={chatApi()} {...quiet} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: intro.texts.skipLabel }))
    await user.click(screen.getByRole('button', { name: intro.texts.enterLabel }))
    await screen.findByLabelText('הודעה')
    await expectClean()
    await user.click(screen.getByRole('button', { name: sidebarCfg.texts.toggle }))
    await screen.findByRole('navigation', { name: sidebarCfg.texts.history })
    await screen.findByText('ATTO 3')
    await screen.findByText('נועה לוי')
    await expectClean()
  })

  it('the sidebar: usage disabled ("soon"); on a phone open over the chat', async () => {
    viewport(width)
    sessionStorage.setItem('threadId', TID)
    const api = chatApi()
    render(<EmployeeScreen api={api} {...quiet} />)
    await waitFor(() => expect(api.me).toHaveBeenCalled())
    await expectClean() // closed: the strip on a computer, a header button on a phone
    await userEvent.setup().click(screen.getByRole('button', { name: sidebarCfg.texts.toggle }))
    await screen.findByText('ATTO 3')
    await screen.findByText('נועה לוי')
    await expectClean()
  })

  it('an answer with the comparison card; the panel open, then closed', async () => {
    viewport(width)
    render(<EmployeeScreen api={chatApi([['thread', { thread_id: TID }], ['card', noa], ['token', { text: 'הנטו **עולה**' }], ['done', {}]])} {...quiet} />)
    await ask()
    await screen.findByText('עולה')
    await expectClean()
    await userEvent.setup().click(screen.getByRole('button', { name: 'סגירת פאנל ההשוואה' }))
    await expectClean()
  })

  it('a waiting comparison (the rep)', async () => {
    viewport(width)
    render(<EmployeeScreen api={chatApi([['thread', { thread_id: TID }], ['card', rachel], ['done', {}]])} {...quiet} />)
    await ask(null, 'ATTO 2?')
    await screen.findAllByText(/ממתין לנציג/)
    await expectClean()
  })

  it('the ranking card and the specs card', async () => {
    viewport(width)
    render(<EmployeeScreen api={chatApi([['thread', { thread_id: TID }], ['card', ranking], ['card', specs], ['done', {}]])} {...quiet} />)
    await ask(null, 'איזה רכב?')
    await screen.findByText(/סידרתי לפי/)
    await expectClean()
  })

  it('the payslip: preview, an error, the bubble and the large view', async () => {
    viewport(width)
    sessionStorage.setItem('threadId', TID)
    URL.createObjectURL = () => 'blob:local'
    URL.revokeObjectURL = () => {}
    const api = chatApi()
    api.streamPayslip = vi.fn(async (tid, file, onEvent) => { onEvent('token', { text: 'לקחתי מהתלוש' }); onEvent('done', {}) })
    render(<EmployeeScreen api={api} {...quiet} />)
    const user = userEvent.setup({ applyAccept: false })
    const input = document.getElementById('payslip-file')
    await user.upload(input, new File(['GIF89a'], 'a.gif', { type: 'image/gif' }))
    await screen.findByRole('alert')
    await expectClean()
    await user.upload(input, new File(['png'], 'tlush.png', { type: 'image/png' }))
    await screen.findByRole('group', { name: payslipCfg.texts.attach })
    await expectClean()
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    await user.click(await screen.findByRole('button', { name: payslipCfg.texts.open }))
    await screen.findByRole('dialog')
    await expectClean()
  })

  it('the profile dialog: its fields and sources, then errors next to the fields', async () => {
    viewport(width)
    window.history.replaceState(null, '', profileCfg.path)
    render(<EmployeeScreen api={chatApi()} {...quiet} />)
    const base = await screen.findByDisplayValue('15000')
    await expectClean()
    const user = userEvent.setup()
    await user.clear(base)
    await user.type(base, '0')
    await user.click(screen.getByRole('button', { name: profileCfg.texts.save }))
    await screen.findByRole('alert')
    await expectClean()
  })

  it.each(['light', 'dark'])('the customize window, in %s mode', async (mode) => {
    viewport(width)
    sessionStorage.setItem('threadId', TID)
    const api = chatApi()
    api.settings = vi.fn().mockResolvedValue({ theme: mode, tone: 'funny' })
    render(<EmployeeScreen api={api} {...quiet} />)
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe(mode))
    await expectClean() // the chat itself in this mode
    const user = userEvent.setup()
    if (width < 768) await user.click(screen.getByRole('button', { name: sidebarCfg.texts.toggle }))
    await user.click(screen.getByRole('button', { name: sidebarCfg.texts.customize }))
    await screen.findByRole('dialog', { name: settingsCfg.texts.title })
    await expectClean()
    delete document.documentElement.dataset.theme
  })

  it('the accessibility statement', async () => {
    viewport(width)
    render(<AccessibilityStatement />)
    await expectClean()
  })

  it('the rep screen: the passcode, then the queue', async () => {
    viewport(width)
    const request = { id: '1', thread_id: 't', fields: ['carGroup'], question: 'מהי הקבוצה?', car_key: 'k', card: rachel.card }
    render(<RepScreen api={{ repList: vi.fn().mockResolvedValue([request]), repAnswer: vi.fn() }} />)
    await expectClean()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('סיסמת נציג'), 'pw')
    await user.click(screen.getByRole('button', { name: 'כניסה' }))
    await screen.findByText(request.question)
    await expectClean()
  })
})

// --- contrast: every text color on every background it is used on, light and dark ------------------
function luminance(hex) {
  const [r, g, b] = hex.match(/[\da-f]{2}/gi).map((h) => {
    const c = parseInt(h, 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const ratio = (a, b) => {
  const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m)
  return (x + 0.05) / (y + 0.05)
}

function tokens(block) {
  return Object.fromEntries([...block.matchAll(/--([\w-]+):\s*(#[\da-fA-F]{6})/g)].map((m) => [m[1], m[2]]))
}

describe('contrast (WCAG 1.4.3: 4.5:1 for text, 3:1 for large text and controls)', () => {
  const css = readFileSync('src/styles.css', 'utf8')
  const light = tokens(css.match(/:root \{([^}]*)\}/)[1])
  // dark mode is the employee's setting ("התאמה אישית"), not the computer's: :root[data-theme="dark"]
  const dark = { ...light, ...tokens(css.match(/:root\[data-theme="dark"\] \{([^}]*)\}/)[1]) }

  // [text, background, minimum]
  const PAIRS = [
    ['text', 'bg', 4.5], ['text', 'surface', 4.5], ['text', 'surface2', 4.5],
    ['muted', 'bg', 4.5], ['muted', 'surface', 4.5], ['muted', 'surface2', 4.5],
    ['brand-cyan-text', 'bg', 4.5], ['brand-cyan-text', 'surface', 4.5],
    ['error', 'bg', 4.5], ['error', 'surface', 4.5],
    ['on-brand', 'cyan', 4.5], ['on-brand', 'green', 4.5], ['on-brand', 'orange', 4.5],
  ]
  it.each(['light', 'dark'])('%s mode', (mode) => {
    const t = mode === 'light' ? light : dark
    const low = PAIRS.map(([fg, bg, min]) => [fg, bg, +ratio(t[fg], t[bg]).toFixed(2), min])
      .filter(([, , r, min]) => r < min)
    expect(low).toEqual([])
  })

  it('the intro: white text on the darkest part of its gradient over a white sky', () => {
    // the gradient is at least 0.6 black where the slogan is: white sky * 0.4 = #666666
    expect(ratio('#FFFFFF', '#666666')).toBeGreaterThanOrEqual(4.5)
  })
})

describe('the page', () => {
  it('is Hebrew, right to left', () => {
    const html = readFileSync('index.html', 'utf8')
    expect(html).toMatch(/<html lang="he" dir="rtl">/)
  })

  it('zoom: the viewport is not locked (no maximum-scale or user-scalable=no)', () => {
    const html = readFileSync('index.html', 'utf8')
    expect(html).not.toMatch(/maximum-scale|user-scalable\s*=\s*no/)
  })
})

// "התאמה אישית": a click on it in the sidebar opens a small window with two settings, kept on the
// server: light or dark (light by default, even when the computer is set to dark), and Kobi's tone.
import { readFileSync } from 'node:fs'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import cfg from '@/config/settings.json'
import sidebarCfg from '@/config/sidebar.json'
import EmployeeScreen from '@/employee/EmployeeScreen'

const T = cfg.texts
const theme = () => document.documentElement.dataset.theme

function setup({ settings = { theme: 'light', tone: 'professional' }, save } = {}) {
  const api = {
    streamChat: vi.fn(),
    streamRepAnswered: vi.fn(),
    restore: vi.fn().mockRejectedValue(new Error('none')),
    threads: vi.fn().mockResolvedValue([]),
    me: vi.fn().mockResolvedValue({ employee_id: 'E01', name: 'נועה לוי' }),
    settings: vi.fn().mockResolvedValue(settings),
    saveSettings: save ?? vi.fn(async (values) => ({ ...settings, ...values })),
  }
  const view = render(<EmployeeScreen api={api} subscribe={() => () => {}} notifier={{ beep: vi.fn(), setUnread: vi.fn() }} />)
  return { api, ...view }
}
const opener = () => screen.getByRole('button', { name: sidebarCfg.texts.customize })
async function open(user) {
  await user.click(opener())
  return screen.findByRole('dialog', { name: T.title })
}

beforeEach(() => { window.history.replaceState(null, '', '/'); delete document.documentElement.dataset.theme })
afterEach(() => { vi.restoreAllMocks(); delete window.matchMedia })

describe('the window', () => {
  it('a click on "התאמה אישית" opens it (it is a button, no longer "soon")', async () => {
    setup()
    expect(opener()).not.toHaveAttribute('aria-disabled')
    const dialog = await open(userEvent.setup())
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it('every option has a clear label, in two named groups', async () => {
    setup()
    const dialog = await open(userEvent.setup())
    const look = within(dialog).getByRole('radiogroup', { name: T.theme })
    const tone = within(dialog).getByRole('radiogroup', { name: T.tone })
    for (const label of Object.values(T.themes)) expect(within(look).getByRole('radio', { name: label })).toBeInTheDocument()
    for (const label of Object.values(T.tones)) expect(within(tone).getByRole('radio', { name: label })).toBeInTheDocument()
    expect(tone).toHaveAccessibleDescription(T.toneHint)
  })

  it('shows what is kept on the server', async () => {
    setup({ settings: { theme: 'dark', tone: 'friendly' } })
    const dialog = await open(userEvent.setup())
    expect(await within(dialog).findByRole('radio', { name: T.themes.dark })).toBeChecked()
    expect(within(dialog).getByRole('radio', { name: T.tones.friendly })).toBeChecked()
  })

  it('Esc closes it and the focus goes back to "התאמה אישית"', async () => {
    setup()
    const user = userEvent.setup()
    await open(user)
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(opener()).toHaveFocus()
  })

  it('opens and closes from the keyboard alone; the focus stays inside', async () => {
    setup()
    const user = userEvent.setup()
    opener().focus()
    await user.keyboard('{Enter}')
    const dialog = await screen.findByRole('dialog', { name: T.title })
    const close = within(dialog).getByRole('button', { name: T.close })
    expect(close).toHaveFocus()
    for (let i = 0; i < 6; i++) {
      await user.tab()
      expect(dialog).toContainElement(document.activeElement)
    }
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('✕ closes it', async () => {
    setup()
    const user = userEvent.setup()
    const dialog = await open(user)
    await user.click(within(dialog).getByRole('button', { name: T.close }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })
})

describe('light or dark', () => {
  it('light by default, even when the computer is set to dark', async () => {
    window.matchMedia = (q) => ({ matches: q.includes('dark'), media: q, addEventListener() {}, removeEventListener() {} })
    const { api } = setup()
    await waitFor(() => expect(api.settings).toHaveBeenCalled())
    expect(theme()).toBe('light')
  })

  it('the kept setting is applied when the screen opens', async () => {
    setup({ settings: { theme: 'dark', tone: 'professional' } })
    await waitFor(() => expect(theme()).toBe('dark'))
  })

  it('choosing dark applies it at once and keeps it on the server', async () => {
    const { api } = setup()
    const user = userEvent.setup()
    const dialog = await open(user)
    await user.click(within(dialog).getByRole('radio', { name: T.themes.dark }))
    expect(theme()).toBe('dark')
    expect(api.saveSettings).toHaveBeenCalledWith({ theme: 'dark' })
    expect(await within(dialog).findByText(T.saved)).toBeInTheDocument()
  })

  it('a save that fails goes back to what was there, and says so', async () => {
    setup({ save: vi.fn().mockRejectedValue(new Error('down')) })
    const user = userEvent.setup()
    const dialog = await open(user)
    await user.click(within(dialog).getByRole('radio', { name: T.themes.dark }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(T.saveError)
    expect(theme()).toBe('light')
    expect(within(dialog).getByRole('radio', { name: T.themes.light })).toBeChecked()
  })

  it('leaving the employee screen (logout) goes back to light', async () => {
    const { unmount } = setup({ settings: { theme: 'dark', tone: 'professional' } })
    await waitFor(() => expect(theme()).toBe('dark'))
    unmount()
    expect(theme()).toBe('light')
  })
})

describe('the tone', () => {
  it('choosing a tone keeps it on the server; the page is not reloaded', async () => {
    const { api } = setup()
    const user = userEvent.setup()
    const dialog = await open(user)
    const before = window.location.href
    await user.click(within(dialog).getByRole('radio', { name: T.tones.funny }))
    expect(api.saveSettings).toHaveBeenCalledWith({ tone: 'funny' })
    expect(await within(dialog).findByText(T.saved)).toBeInTheDocument()
    expect(window.location.href).toBe(before)
    expect(screen.getByLabelText('הודעה')).toBeInTheDocument() // the conversation is still there
  })
})

describe('the config', () => {
  const agent = JSON.parse(readFileSync('../backend/config/agent.json', 'utf8'))

  it('the same tones, themes and defaults as the server (agent.json)', () => {
    expect(Object.keys(T.tones)).toEqual(Object.keys(agent.tones.styles))
    expect(Object.keys(T.themes)).toEqual(agent.settings.themes)
    expect(cfg.defaults).toEqual(agent.settings.defaults)
  })

  it('dark mode comes only from the setting, not from the computer (prefers-color-scheme)', () => {
    const css = readFileSync('src/styles.css', 'utf8')
    expect(css).not.toMatch(/prefers-color-scheme/)
    expect(css).toMatch(/:root\[data-theme="dark"\] \{/)
  })
})

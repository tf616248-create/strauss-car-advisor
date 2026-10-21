// The profile dialog: "פרופיל" in the sidebar, a direct /profile link, or the link in Kobi's answer
// opens it over the conversation. Closing (✕, Esc, a click outside, the browser's Back) goes back.
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import cfg from '../config/profile.json'
import sidebarCfg from '../config/sidebar.json'
import EmployeeScreen from './EmployeeScreen'

const T = cfg.texts
const label = (name) => cfg.fields.find((f) => f.name === name).label
const VIEW = {
  employee_id: 'E01',
  fields: { occupation: 'מנהל/ת אזור מכירות', base: 14200, pension_pct: 6, current_kind: 'car', current_car: 'TUCSON' },
  sources: { occupation: 'profile', base: 'payslip', pension_pct: 'payslip', current_kind: 'chat', current_car: 'chat' },
  group: 'ג',
}

function setup({ view = VIEW, save, chat, profile, autoFocus = false } = {}) {
  const api = {
    streamChat: chat ?? vi.fn(),
    streamRepAnswered: vi.fn(),
    restore: vi.fn().mockRejectedValue(new Error('none')),
    threads: vi.fn().mockResolvedValue([]),
    me: vi.fn().mockResolvedValue({ employee_id: 'E01', name: 'נועה לוי' }),
    profile: profile ?? vi.fn().mockResolvedValue(view),
    saveProfile: save ?? vi.fn(),
  }
  render(<EmployeeScreen api={api} subscribe={() => () => {}} notifier={{ beep: vi.fn(), setUnread: vi.fn() }}
    autoFocus={autoFocus} />)
  return api
}
const openFromSidebar = async (user) => {
  const button = screen.getByRole('button', { name: sidebarCfg.texts.profile })
  await user.click(button)
  await screen.findByRole('dialog', { name: T.title })
  return button
}
const dialog = () => screen.getByRole('dialog', { name: T.title })

beforeEach(() => window.history.replaceState(null, '', '/'))
afterEach(() => vi.restoreAllMocks())

describe('opening and closing', () => {
  it('"פרופיל" in the sidebar opens it over the chat, at /profile', async () => {
    setup()
    const user = userEvent.setup()
    await openFromSidebar(user)
    expect(dialog()).toHaveAttribute('aria-modal', 'true')
    expect(window.location.pathname).toBe(cfg.path)
    expect(screen.getByLabelText('הודעה')).toBeInTheDocument() // the conversation stays underneath
  })

  it('✕ closes it: back to the previous address, the focus back on the button that opened it', async () => {
    setup()
    const user = userEvent.setup()
    const opener = await openFromSidebar(user)
    await user.click(screen.getByRole('button', { name: T.close }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(window.location.pathname).toBe('/')
    expect(opener).toHaveFocus()
  })

  it('Esc closes it', async () => {
    setup()
    const user = userEvent.setup()
    await openFromSidebar(user)
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(window.location.pathname).toBe('/')
  })

  it('a click outside closes it; a click inside does not', async () => {
    setup()
    const user = userEvent.setup()
    await openFromSidebar(user)
    await user.click(screen.getByText(T.intro))
    expect(dialog()).toBeInTheDocument()
    const opener = screen.getByRole('button', { name: sidebarCfg.texts.profile })
    await user.click(document.querySelector('.modal'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(opener).toHaveFocus() // after the click itself, not taken by it
  })

  it('a drag that starts inside and ends outside (selecting text) does not close it', async () => {
    setup()
    const user = userEvent.setup()
    await openFromSidebar(user)
    await user.pointer([{ keys: '[MouseLeft>]', target: screen.getByText(T.intro) },
      { target: document.querySelector('.modal') }, { keys: '[/MouseLeft]' }])
    expect(dialog()).toBeInTheDocument()
  })

  it('the browser\'s Back closes it', async () => {
    setup()
    const user = userEvent.setup()
    await openFromSidebar(user)
    await act(async () => { window.history.back() })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(window.location.pathname).toBe('/')
  })

  it('a direct link to /profile opens it over the conversation; closing goes to the conversation', async () => {
    window.history.replaceState(null, '', cfg.path)
    setup()
    await screen.findByRole('dialog', { name: T.title })
    await userEvent.setup().click(screen.getByRole('button', { name: T.close }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(window.location.pathname).toBe('/')
    expect(screen.getByLabelText('הודעה')).toHaveFocus()
  })

  it('a direct link, coming in from the opening scene: the focus is in the dialog, not the message box', async () => {
    window.history.replaceState(null, '', cfg.path)
    setup({ autoFocus: true })
    await screen.findByRole('dialog', { name: T.title })
    expect(screen.getByRole('button', { name: T.close })).toHaveFocus()
  })

  it('the link in Kobi\'s answer opens it', async () => {
    const chat = vi.fn(async (p, onEvent) => {
      onEvent('thread', { thread_id: '11111111-2222-3333-4444-555555555555' })
      onEvent('token', { text: 'הכי מהיר למלא בפרופיל שלכם, /profile. אפשר גם תלוש.' })
      onEvent('done', {})
    })
    setup({ chat })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'EV3?')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    const link = await screen.findByRole('link', { name: cfg.path })
    await user.click(link)
    await screen.findByRole('dialog', { name: T.title })
    expect(window.location.pathname).toBe(cfg.path)
    await user.keyboard('{Escape}')
    await waitFor(() => expect(link).toHaveFocus())
  })

  it('the focus stays inside: Tab from the last control goes to the first, Shift+Tab back', async () => {
    setup()
    const user = userEvent.setup()
    await openFromSidebar(user)
    await screen.findByDisplayValue('14200')
    const close = screen.getByRole('button', { name: T.close })
    const save = screen.getByRole('button', { name: T.save })
    save.focus()
    await user.tab()
    expect(close).toHaveFocus()
    await user.tab({ shift: true })
    expect(save).toHaveFocus()
  })
})

describe('the fields', () => {
  it('every field, with a label and its value', async () => {
    setup()
    await openFromSidebar(userEvent.setup())
    await screen.findByDisplayValue('14200')
    for (const f of cfg.fields) expect(within(dialog()).getByLabelText(f.label)).toBeInTheDocument()
    expect(screen.getByLabelText(label('occupation'))).toHaveValue('מנהל/ת אזור מכירות')
    expect(screen.getByLabelText(label('current_kind'))).toHaveValue('car')
    expect(screen.getByLabelText(label('bonus'))).toHaveValue('')
  })

  it('next to each value, where it came from', async () => {
    setup()
    await openFromSidebar(userEvent.setup())
    await screen.findByDisplayValue('14200')
    expect(screen.getByLabelText(label('occupation'))).toHaveAccessibleDescription(T.sources.profile)
    expect(screen.getByLabelText(label('base'))).toHaveAccessibleDescription(T.sources.payslip)
    expect(screen.getByLabelText(label('current_car'))).toHaveAccessibleDescription(T.sources.chat)
    expect(screen.getByLabelText(label('bonus'))).toHaveAccessibleDescription('') // no value, no source
  })

  it('the group, read only: from the occupation, or "not identified"', async () => {
    setup()
    await openFromSidebar(userEvent.setup())
    expect(await within(dialog()).findByText(T.group.replace('{group}', 'ג'))).toBeInTheDocument()
    expect(within(dialog()).queryByRole('textbox', { name: T.groupLabel })).toBeNull()
  })

  it('no group when the occupation was not found', async () => {
    setup({ view: { ...VIEW, fields: {}, sources: {}, group: null } })
    await openFromSidebar(userEvent.setup())
    expect(await within(dialog()).findByText(T.groupUnknown)).toBeInTheDocument()
  })

  it('a load that fails says so', async () => {
    setup({ profile: vi.fn().mockRejectedValue(new Error('down')) })
    await openFromSidebar(userEvent.setup())
    expect(await within(dialog()).findByText(T.loadError)).toBeInTheDocument()
  })
})

describe('saving', () => {
  it('sends only what changed (numbers as numbers, an emptied field as null), then says "נשמר"', async () => {
    const saved = { ...VIEW, fields: { ...VIEW.fields, base: 15000, bonus: 500 }, sources: { ...VIEW.sources, base: 'profile', bonus: 'profile' } }
    delete saved.fields.current_car
    const save = vi.fn().mockResolvedValue({ profile: saved })
    setup({ save })
    const user = userEvent.setup()
    await openFromSidebar(user)
    await screen.findByDisplayValue('14200')
    await user.clear(screen.getByLabelText(label('base')))
    await user.type(screen.getByLabelText(label('base')), '15,000')
    await user.type(screen.getByLabelText(label('bonus')), '500')
    await user.clear(screen.getByLabelText(label('current_car')))
    await user.click(screen.getByRole('button', { name: T.save }))
    expect(save).toHaveBeenCalledWith({ base: 15000, bonus: 500, current_car: null })
    expect(await within(dialog()).findByText(T.saved)).toBeInTheDocument()
    expect(screen.getByLabelText(label('base'))).toHaveAccessibleDescription(T.sources.profile)
  })

  it('range and occupation errors show next to their fields; nothing says "saved"', async () => {
    const save = vi.fn().mockResolvedValue({ invalid: {
      pension_pct: { range: [0, 10] },
      occupation: { suggestions: ['מנהל/ת מוצר', 'מנהל/ת פיתוח'] },
    } })
    setup({ save })
    const user = userEvent.setup()
    await openFromSidebar(user)
    await screen.findByDisplayValue('14200')
    await user.clear(screen.getByLabelText(label('pension_pct')))
    await user.type(screen.getByLabelText(label('pension_pct')), '40')
    await user.clear(screen.getByLabelText(label('occupation')))
    await user.type(screen.getByLabelText(label('occupation')), 'מנהל')
    await user.click(screen.getByRole('button', { name: T.save }))
    const pension = screen.getByLabelText(label('pension_pct'))
    await waitFor(() => expect(pension).toHaveAttribute('aria-invalid', 'true'))
    expect(pension).toHaveAccessibleDescription(expect.stringContaining('צריך להיות בין 0 ל-10'))
    expect(screen.getByLabelText(label('occupation')))
      .toHaveAccessibleDescription(expect.stringContaining('אולי: מנהל/ת מוצר, מנהל/ת פיתוח'))
    expect(screen.getByRole('alert')).toHaveTextContent(T.fixErrors)
    expect(within(dialog()).queryByText(T.saved)).toBeNull()
  })

  it('a save that fails says so', async () => {
    setup({ save: vi.fn().mockRejectedValue(new Error('down')) })
    const user = userEvent.setup()
    await openFromSidebar(user)
    await screen.findByDisplayValue('14200')
    await user.type(screen.getByLabelText(label('bonus')), '1')
    await user.click(screen.getByRole('button', { name: T.save }))
    expect(await screen.findByRole('alert')).toHaveTextContent(T.saveError)
  })
})

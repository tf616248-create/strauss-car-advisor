// The weekly limit on screen: "שימוש" in the sidebar is a progress bar with how many conversations are
// left, and at 0 Kobi does not answer - the fixed message from the server, with a mailto link, read aloud.
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import cfg from '../config/usage.json'
import sidebarCfg from '../config/sidebar.json'
import A11Y from '../config/accessibility.json'
import EmployeeScreen from './EmployeeScreen'

const T = cfg.texts
const AVG = 30589
const LIMIT = AVG * 25
const status = (used) => {
  const remaining = Math.max(0, LIMIT - used)
  return { used, limit: LIMIT, remaining, avg_tokens_per_conversation: AVG,
    conversations_left: Math.floor(remaining / AVG), blocked: remaining <= 0, resets_on: '2026-10-25' }
}
const LIMIT_TEXT = 'לשיחות נוספות אפשר לפנות ל-support@strauss-in.com'

function setup({ usage = vi.fn().mockResolvedValue(status(AVG * 5)), chat } = {}) {
  const api = {
    streamChat: chat ?? vi.fn(),
    streamRepAnswered: vi.fn(),
    restore: vi.fn().mockRejectedValue(new Error('none')),
    threads: vi.fn().mockResolvedValue([]),
    me: vi.fn().mockResolvedValue({ employee_id: 'E01', name: 'נועה לוי' }),
    usage,
  }
  render(<EmployeeScreen api={api} subscribe={() => () => {}} notifier={{ beep: vi.fn(), setUnread: vi.fn() }} />)
  return api
}
const openSidebar = (user) => user.click(screen.getByRole('button', { name: sidebarCfg.texts.toggle }))

beforeEach(() => { window.history.replaceState(null, '', '/'); localStorage.clear() })
afterEach(() => vi.restoreAllMocks())

describe('"שימוש" in the sidebar', () => {
  it('a progress bar: how much is used, and the sentence as its text', async () => {
    setup()
    await openSidebar(userEvent.setup())
    const bar = await screen.findByRole('progressbar', { name: T.barLabel })
    const sentence = T.left.replace('{n}', '20')
    await waitFor(() => expect(bar).toHaveAttribute('aria-valuetext', sentence))
    expect(bar).toHaveAttribute('aria-valuenow', '20') // 5 of 25 conversations used
    expect(bar).toHaveAttribute('aria-valuemin', '0')
    expect(bar).toHaveAttribute('aria-valuemax', '100')
    expect(screen.getByText(sentence)).toBeInTheDocument()
    expect(screen.getByText(T.resets)).toBeInTheDocument()
  })

  it('X is what is left divided by the average, rounded down', async () => {
    setup({ usage: vi.fn().mockResolvedValue(status(LIMIT - AVG * 3 - AVG / 2)) }) // 3.5 left
    await openSidebar(userEvent.setup())
    expect(await screen.findByText(T.left.replace('{n}', '3'))).toBeInTheDocument()
  })

  it('one left', async () => {
    setup({ usage: vi.fn().mockResolvedValue(status(LIMIT - AVG)) })
    await openSidebar(userEvent.setup())
    expect(await screen.findByText(T.leftOne)).toBeInTheDocument()
  })

  it('less than one conversation left', async () => {
    setup({ usage: vi.fn().mockResolvedValue(status(LIMIT - AVG / 2)) })
    await openSidebar(userEvent.setup())
    expect(await screen.findByText(T.lessThanOne)).toBeInTheDocument()
  })

  it('nothing left', async () => {
    setup({ usage: vi.fn().mockResolvedValue(status(LIMIT + 10)) })
    await openSidebar(userEvent.setup())
    const bar = await screen.findByRole('progressbar', { name: T.barLabel })
    await waitFor(() => expect(bar).toHaveAttribute('aria-valuenow', '100'))
    expect(bar).toHaveAttribute('aria-valuetext', T.none)
  })

  it('in the closed strip it is an icon that opens the sidebar (no longer "soon")', async () => {
    setup()
    const user = userEvent.setup()
    const icon = screen.getByRole('button', { name: T.label })
    expect(icon).not.toHaveAttribute('aria-disabled')
    await user.click(icon)
    expect(screen.getByRole('button', { name: sidebarCfg.texts.toggle })).toHaveAttribute('aria-expanded', 'true')
    expect(await screen.findByRole('progressbar', { name: T.barLabel })).toBeInTheDocument()
  })

  it('read again after each answer', async () => {
    const usage = vi.fn().mockResolvedValue(status(0))
    const chat = vi.fn(async (p, onEvent) => { onEvent('token', { text: 'תשובה' }); onEvent('done', {}) })
    setup({ usage, chat })
    await waitFor(() => expect(usage).toHaveBeenCalledTimes(1))
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'שאלה')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    await screen.findByText('תשובה')
    await waitFor(() => expect(usage).toHaveBeenCalledTimes(2))
  })
})

describe('at 0', () => {
  const blocked = () => vi.fn(async (p, onEvent) => {
    onEvent('limit', { message: LIMIT_TEXT, email: 'support@strauss-in.com' })
    onEvent('done', {})
  })

  it('Kobi does not answer: the fixed message, with a mailto link', async () => {
    setup({ chat: blocked() })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'שאלה')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    const list = screen.getByRole('list', { name: 'השיחה' })
    const link = await within(list).findByRole('link', { name: 'support@strauss-in.com' })
    expect(link).toHaveAttribute('href', 'mailto:support@strauss-in.com')
    expect(link.closest('li')).toHaveTextContent(LIMIT_TEXT)
    expect(within(list).queryByText('כובי · בוט')).toBeNull() // not an answer of Kobi's
  })

  it('a screen reader reads it', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    setup({ chat: blocked() })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    await user.type(screen.getByLabelText('הודעה'), 'שאלה')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    await act(async () => { vi.advanceTimersByTime(100) })
    const live = screen.getByRole('status', { name: A11Y.live.name })
    await waitFor(() => expect(live).toHaveTextContent(LIMIT_TEXT))
    vi.useRealTimers()
  })
})

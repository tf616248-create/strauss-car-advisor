// The employee's chat: a fixed layout where only the messages scroll, no page scroll when switching
// conversations, and a loading state (nothing under 300ms, so it does not flicker; "לנסות שוב" on failure).
import { readFileSync } from 'node:fs'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import cfg from '../config/chat.json'
import sidebarCfg from '../config/sidebar.json'
import { viewport } from '../test-utils/axe'
import EmployeeScreen from './EmployeeScreen'

const C = cfg.texts
const TID = '11111111-2222-3333-4444-555555555555'
const OTHER = '99999999-8888-7777-6666-555555555555'
const LIST = [
  { thread_id: OTHER, title: 'ATTO 3', updated_at: '2026-10-20T09:30:00+00:00' },
  { thread_id: TID, title: 'הראשונה', updated_at: '2026-10-19T08:00:00+00:00' },
]
const state = (tid, text) => ({ thread_id: tid, messages: [{ role: 'user', text: 'שאלה' }, { role: 'assistant', text }],
  cards: [], rep: { pending: 0, new_answers: 0 } })

function setup({ restore } = {}) {
  const api = {
    streamChat: vi.fn(),
    streamRepAnswered: vi.fn(),
    restore: restore ?? vi.fn(async (tid) => state(tid, tid === OTHER ? 'השיחה האחרת' : 'השיחה הראשונה')),
    threads: vi.fn().mockResolvedValue(LIST),
    me: vi.fn().mockResolvedValue({ employee_id: 'E01', name: 'נועה לוי' }),
  }
  render(<EmployeeScreen api={api} subscribe={() => () => {}} notifier={{ beep: vi.fn(), setUnread: vi.fn() }} />)
  return api
}
const list = () => screen.getByRole('list', { name: 'השיחה' })
const box = () => screen.getByLabelText('הודעה')
const send = () => screen.getByRole('button', { name: 'שליחה' })
const openSidebar = (user) => user.click(screen.getByRole('button', { name: sidebarCfg.texts.toggle }))

let scrolled, focusCalls
beforeEach(() => {
  sessionStorage.setItem('threadId', TID)
  localStorage.clear()
  scrolled = []
  focusCalls = []
  // the page must never scroll: scrollIntoView scrolls every ancestor, the page too
  Element.prototype.scrollIntoView = vi.fn(function () { scrolled.push(this) })
  window.scrollTo = vi.fn()
  const focus = HTMLElement.prototype.focus
  vi.spyOn(HTMLElement.prototype, 'focus').mockImplementation(function (options) {
    focusCalls.push([this, options])
    return focus.call(this, options)
  })
  Object.defineProperty(HTMLElement.prototype, 'scrollHeight', { configurable: true, get: () => 900 })
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
  delete HTMLElement.prototype.scrollHeight
  delete window.matchMedia
})

describe('switching conversations: no page scroll', () => {
  it('opening one from the history: the list starts at the last message, the focus in the box, no page scroll', async () => {
    const api = setup()
    await screen.findByText('השיחה הראשונה')
    const user = userEvent.setup()
    await openSidebar(user)
    await user.click(await screen.findByText('ATTO 3'))
    await screen.findByText('השיחה האחרת')
    expect(api.restore).toHaveBeenLastCalledWith(OTHER)
    expect(scrolled).toEqual([])
    expect(window.scrollTo).not.toHaveBeenCalled()
    expect(list().scrollTop).toBe(900) // the list itself, at its end
    await waitFor(() => expect(box()).toHaveFocus())
    expect(focusCalls.filter(([el]) => el === box()).every(([, o]) => o?.preventScroll === true)).toBe(true)
  })

  it('a new conversation: the welcome, the focus in the box, no page scroll', async () => {
    setup()
    await screen.findByText('השיחה הראשונה')
    const user = userEvent.setup()
    await user.click(within(screen.getByRole('complementary', { name: sidebarCfg.texts.label }))
      .getByRole('button', { name: sidebarCfg.texts.newConversation }))
    expect(screen.getByRole('heading', { level: 2, name: /אני כובי/ })).toBeInTheDocument()
    expect(scrolled).toEqual([])
    expect(window.scrollTo).not.toHaveBeenCalled()
    expect(box()).toHaveFocus()
    expect(focusCalls.filter(([el]) => el === box()).at(-1)[1]).toEqual({ preventScroll: true })
  })

  it('a new answer scrolls the list only, not the page', async () => {
    const api = setup()
    api.streamChat = vi.fn(async (p, onEvent) => { onEvent('token', { text: 'תשובה חדשה' }); onEvent('done', {}) })
    await screen.findByText('השיחה הראשונה')
    const user = userEvent.setup()
    await user.type(box(), 'עוד')
    await user.click(send())
    await screen.findByText('תשובה חדשה')
    expect(scrolled).toEqual([])
    expect(list().scrollTop).toBe(900)
  })
})

describe('loading a conversation', () => {
  function slow(ms, result = (tid) => state(tid, 'נטען')) {
    return vi.fn((tid) => new Promise((resolve) => setTimeout(() => resolve(result(tid)), ms)))
  }

  it('over 300ms: "טוען שיחה…" in the messages area, read aloud; the list is busy; writing waits', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    setup({ restore: slow(800) })
    expect(list()).toHaveAttribute('aria-busy', 'true')
    expect(screen.queryByText(C.loading)).toBeNull() // not yet: it would flicker
    await act(async () => { vi.advanceTimersByTime(cfg.loadingDelayMs + 10) })
    const status = screen.getByRole('status', { name: C.loading })
    expect(status).toHaveTextContent(C.loading)
    expect(box()).toHaveAttribute('aria-disabled', 'true')
    expect(box()).toHaveAttribute('readonly')
    expect(send()).toBeDisabled()
    expect(screen.queryByRole('heading', { level: 2, name: /אני כובי/ })).toBeNull() // no welcome flashing
    await act(async () => { vi.advanceTimersByTime(600) })
    expect(await screen.findByText('נטען')).toBeInTheDocument()
    expect(screen.queryByText(C.loading)).toBeNull()
    expect(list()).not.toHaveAttribute('aria-busy', 'true')
    expect(box()).not.toHaveAttribute('aria-disabled')
    expect(send()).toBeEnabled()
  })

  it('under 300ms: nothing is shown', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    setup({ restore: slow(100) })
    await act(async () => { vi.advanceTimersByTime(150) })
    expect(await screen.findByText('נטען')).toBeInTheDocument()
    await act(async () => { vi.advanceTimersByTime(cfg.loadingDelayMs * 2) })
    expect(screen.queryByText(C.loading)).toBeNull() // the delayed loader never came
  })

  it('a failure: a message and "לנסות שוב", which loads it again', async () => {
    const restore = vi.fn().mockRejectedValueOnce(Object.assign(new Error('down'), { status: 500 }))
      .mockResolvedValue(state(TID, 'נטען בפעם השנייה'))
    setup({ restore })
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(C.loadFailed)
    expect(send()).toBeDisabled()
    await userEvent.setup().click(within(alert).getByRole('button', { name: C.retry }))
    expect(await screen.findByText('נטען בפעם השנייה')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(send()).toBeEnabled()
  })

  it('a conversation that is gone (404) starts a new one, not a failure', async () => {
    setup({ restore: vi.fn().mockRejectedValue(Object.assign(new Error('gone'), { status: 404 })) })
    expect(await screen.findByRole('heading', { level: 2, name: /אני כובי/ })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(sessionStorage.getItem('threadId')).toBeNull()
    expect(send()).toBeEnabled()
  })

  it('reduced motion: only the text, no moving bubbles', async () => {
    viewport(1280, { reduceMotion: true })
    vi.useFakeTimers({ shouldAdvanceTime: true })
    setup({ restore: slow(800) })
    await act(async () => { vi.advanceTimersByTime(cfg.loadingDelayMs + 10) })
    expect(screen.getByText(C.loading)).toBeInTheDocument()
    expect(document.querySelector('.loading__bubble')).toBeNull()
  })

  it('with motion: a skeleton of bubbles next to the text', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    setup({ restore: slow(800) })
    await act(async () => { vi.advanceTimersByTime(cfg.loadingDelayMs + 10) })
    expect(document.querySelectorAll('.loading__bubble').length).toBeGreaterThan(0)
  })
})

describe('coming in from the intro', () => {
  it('the focus in the box without a scroll; once the banner has shrunk, one scroll to the chat', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    window.scrollBy = vi.fn()
    const api = { streamChat: vi.fn(), streamRepAnswered: vi.fn(), threads: vi.fn().mockResolvedValue([]),
      restore: vi.fn(async (tid) => state(tid, 'x')) }
    render(<EmployeeScreen api={api} autoFocus subscribe={() => () => {}} notifier={{ beep: vi.fn(), setUnread: vi.fn() }} />)
    expect(box()).toHaveFocus()
    expect(focusCalls.find(([el]) => el === box())[1]).toEqual({ preventScroll: true })
    expect(window.scrollBy).not.toHaveBeenCalled() // not while the banner shrinks
    const employee = document.querySelector('.employee')
    employee.getBoundingClientRect = () => ({ top: 264 })
    await act(async () => { vi.advanceTimersByTime(cfg.afterBannerMs + 10) }) // no banner here: the fallback
    expect(window.scrollBy).toHaveBeenCalledWith({ top: 264, behavior: 'smooth' })
    expect(scrolled).toEqual([])
  })

  it('with the banner: the scroll waits for the end of its shrinking, once', async () => {
    window.scrollBy = vi.fn()
    const banner = document.createElement('section')
    banner.className = 'intro intro--banner'
    document.body.prepend(banner)
    const api = { streamChat: vi.fn(), streamRepAnswered: vi.fn(), threads: vi.fn().mockResolvedValue([]),
      restore: vi.fn(async (tid) => state(tid, 'x')) }
    render(<EmployeeScreen api={api} autoFocus subscribe={() => () => {}} notifier={{ beep: vi.fn(), setUnread: vi.fn() }} />)
    document.querySelector('.employee').getBoundingClientRect = () => ({ top: 120 })
    const end = new Event('transitionend')
    end.propertyName = 'height'
    act(() => banner.dispatchEvent(end))
    act(() => banner.dispatchEvent(end))
    expect(window.scrollBy).toHaveBeenCalledTimes(1)
    expect(window.scrollBy).toHaveBeenCalledWith({ top: 120, behavior: 'smooth' })
    banner.remove()
  })
})

describe('the fixed layout', () => {
  const css = readFileSync('src/styles.css', 'utf8')

  it('the chat area is the screen\'s height (the visible part, above a phone keyboard)', () => {
    expect(css).toMatch(/\.employee \{[^}]*height:\s*var\(--app-h,\s*100dvh\)/)
  })

  it('only the messages scroll: a scroll that reaches their end does not move the page', () => {
    expect(css).toMatch(/\.chat__messages \{[^}]*overscroll-behavior:\s*contain/)
    expect(css).toMatch(/\.welcome \{[^}]*overscroll-behavior:\s*contain/)
  })

  it('a phone keyboard: the page is resized to what is left, and --app-h follows the visible height', () => {
    expect(readFileSync('index.html', 'utf8')).toMatch(/interactive-widget=resizes-content/)
    const listeners = {}
    window.visualViewport = { height: 812, addEventListener: (t, f) => { listeners[t] = f }, removeEventListener() {} }
    setup()
    expect(document.documentElement.style.getPropertyValue('--app-h')).toBe('812px')
    window.visualViewport.height = 420 // the keyboard opened
    act(() => listeners.resize())
    expect(document.documentElement.style.getPropertyValue('--app-h')).toBe('420px')
    delete window.visualViewport
  })
})

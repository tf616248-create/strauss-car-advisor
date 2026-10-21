// The sidebar on the employee screen: on the right, a narrow strip of icons by default; open, it
// pushes the chat (the comparison panel stays on the left). On a phone it opens over the chat.
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import cfg from '../config/sidebar.json'
import { viewport } from '../test-utils/axe'
import { isCramped } from './Sidebar'
import EmployeeScreen from './EmployeeScreen'

const T = cfg.texts
const TID = '11111111-2222-3333-4444-555555555555'
const OTHER = '99999999-8888-7777-6666-555555555555'
const LIST = [
  { thread_id: OTHER, title: 'ATTO 3 (2025)', updated_at: '2026-10-20T09:30:00+00:00' },
  { thread_id: TID, title: null, updated_at: '2026-10-19T08:00:00+00:00' },
]

function setup({ threads = LIST, me = { employee_id: 'E01', name: 'נועה לוי' }, onLogout = vi.fn(), chat } = {}) {
  const api = {
    streamChat: chat ?? vi.fn(async (p, onEvent) => { onEvent('thread', { thread_id: TID }); onEvent('token', { text: 'תשובה' }) }),
    streamRepAnswered: vi.fn(),
    restore: vi.fn(async (tid) => ({ thread_id: tid, messages: [{ role: 'user', text: `שאלה ${tid.slice(0, 2)}` }], cards: [], rep: { pending: 0, new_answers: 0 } })),
    threads: vi.fn().mockResolvedValue(threads),
    me: vi.fn().mockResolvedValue(me),
  }
  render(<EmployeeScreen api={api} subscribe={() => () => {}} notifier={{ beep: vi.fn(), setUnread: vi.fn() }} onLogout={onLogout} />)
  return { api, onLogout, sidebar: () => screen.getByRole('complementary', { name: T.label }) }
}
const toggle = () => screen.getByRole('button', { name: T.toggle })

beforeEach(() => { sessionStorage.setItem('threadId', TID); viewport(1280) })
afterEach(() => { delete window.matchMedia; vi.restoreAllMocks() })

describe('the sidebar on a computer', () => {
  it('starts closed: a strip of icons, the conversations list hidden', async () => {
    const { sidebar } = setup()
    expect(toggle()).toHaveAttribute('aria-expanded', 'false')
    expect(sidebar()).not.toHaveClass('sidebar--open')
    expect(screen.queryByRole('navigation', { name: T.history })).toBeNull()
    // new conversation and logout are there even closed
    expect(within(sidebar()).getByRole('button', { name: T.newConversation })).toBeInTheDocument()
    expect(within(sidebar()).getByRole('button', { name: T.logout })).toBeInTheDocument()
  })

  it('the icon opens it; it pushes the chat (not over it) and the focus is in it', async () => {
    const { sidebar } = setup()
    const user = userEvent.setup()
    await user.click(toggle())
    expect(toggle()).toHaveAttribute('aria-expanded', 'true')
    expect(sidebar()).toHaveClass('sidebar--open')
    expect(sidebar()).not.toHaveClass('sidebar--floating')
    expect(sidebar()).toContainElement(document.activeElement)
    await user.click(toggle())
    expect(toggle()).toHaveAttribute('aria-expanded', 'false')
  })

  it('the conversations icon opens it, with the focus on the open conversation', async () => {
    setup()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: T.history }))
    const nav = await screen.findByRole('navigation', { name: T.history })
    await waitFor(() => expect(within(nav).getAllByRole('button')).toHaveLength(2))
    expect(document.activeElement).toHaveAttribute('data-thread', TID)
  })

  it('top to bottom: new conversation, profile, customize, usage, then the conversations, then the name and logout', async () => {
    const { sidebar } = setup()
    await userEvent.setup().click(toggle())
    const names = within(sidebar()).getAllByRole('button').map((b) => b.dataset.item).filter(Boolean)
    expect(names).toEqual(['new', 'profile', 'customize', 'usage', 'thread', 'thread', 'logout'])
    const nav = screen.getByRole('navigation', { name: T.history })
    expect(nav.compareDocumentPosition(await screen.findByText('נועה לוי')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('customize and usage are only items for now: disabled, "soon", they do nothing', async () => {
    const { sidebar } = setup()
    const user = userEvent.setup()
    expect(within(sidebar()).getByRole('button', { name: T.profile })).not.toHaveAttribute('aria-disabled')
    for (const key of ['customize', 'usage']) {
      const item = within(sidebar()).getByRole('button', { name: new RegExp(T[key]) })
      expect(item).toHaveAttribute('aria-disabled', 'true')
      expect(item).toHaveAccessibleName(`${T[key]} ${T.soon}`)
      await user.click(item)
    }
    expect(toggle()).toHaveAttribute('aria-expanded', 'false')
  })

  it('the conversations: newest first, the open one marked, a click opens one', async () => {
    const { api } = setup()
    const user = userEvent.setup()
    await user.click(toggle())
    const nav = screen.getByRole('navigation', { name: T.history })
    const items = await within(nav).findAllByRole('button')
    expect(items.map((b) => b.dataset.thread)).toEqual([OTHER, TID])
    expect(items[0]).toHaveTextContent('ATTO 3 (2025)')
    expect(items[1]).toHaveTextContent(T.untitled) // no title yet
    expect(items[1]).toHaveAttribute('aria-current', 'true')
    await user.click(items[0])
    expect(await screen.findByText('שאלה 99')).toBeInTheDocument()
    expect(api.restore).toHaveBeenLastCalledWith(OTHER)
    expect(sessionStorage.getItem('threadId')).toBe(OTHER)
    expect(within(nav).getAllByRole('button')[0]).toHaveAttribute('aria-current', 'true')
  })

  it('no conversations yet: says so', async () => {
    sessionStorage.clear()
    setup({ threads: [] })
    await userEvent.setup().click(toggle())
    expect(await screen.findByText(T.historyEmpty)).toBeInTheDocument()
  })

  it('"new conversation" is the old button: clears the screen, disabled while an answer is written', async () => {
    let finish
    const chat = vi.fn((p, onEvent) => { onEvent('thread', { thread_id: TID }); return new Promise((r) => { finish = r }) })
    const { sidebar } = setup({ chat })
    await screen.findByText('שאלה 11')
    const user = userEvent.setup()
    const fresh = within(sidebar()).getByRole('button', { name: T.newConversation })
    await user.type(screen.getByLabelText('הודעה'), 'עוד שאלה')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    expect(fresh).toBeDisabled()
    await act(async () => { finish() })
    expect(fresh).toBeEnabled()
    await user.click(fresh)
    expect(screen.queryByText('שאלה 11')).toBeNull()
    expect(sessionStorage.getItem('threadId')).toBeNull()
  })

  it('the old buttons are gone: no "my conversations" above the messages, no logout in the header', () => {
    setup()
    expect(document.querySelector('.chat__top, .chat__new, .topbar__logout')).toBeNull()
    expect(screen.getAllByRole('button', { name: T.logout })).toHaveLength(1)
  })

  it('the name of the employee at the bottom, from the server; logout next to it', async () => {
    const { api, onLogout, sidebar } = setup()
    expect(await within(sidebar()).findByText('נועה לוי')).toBeInTheDocument()
    expect(api.me).toHaveBeenCalled()
    const user = within(sidebar()).getByText('נועה לוי').closest('.sidebar__user')
    await userEvent.setup().click(within(user).getByRole('button', { name: T.logout }))
    expect(onLogout).toHaveBeenCalled()
  })

  it('open or closed is kept in the browser', async () => {
    setup()
    await userEvent.setup().click(toggle())
    expect(localStorage.getItem(cfg.storageKey)).toBe('1')
    document.body.innerHTML = ''
    setup()
    expect(toggle()).toHaveAttribute('aria-expanded', 'true')
  })

  it('a browser that blocks storage: still works, starts closed', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    setup()
    expect(toggle()).toHaveAttribute('aria-expanded', 'false')
    await userEvent.setup().click(toggle())
    expect(toggle()).toHaveAttribute('aria-expanded', 'true')
  })

  it('the keyboard reaches everything: Tab from the toggle goes through the items', async () => {
    setup()
    const user = userEvent.setup()
    toggle().focus()
    await user.keyboard('{Enter}')
    expect(toggle()).toHaveAttribute('aria-expanded', 'true')
    await user.tab()
    expect(document.activeElement).toHaveAccessibleName(T.newConversation)
    await user.tab()
    expect(document.activeElement).toHaveAccessibleName(T.profile) // opens the profile (ProfileDialog.test.jsx)
    await user.tab()
    expect(document.activeElement).toHaveAccessibleName(`${T.customize} ${T.soon}`)
  })
})

describe('too little room for the chat', () => {
  // the chat's width as it would be with the sidebar open, below minChatWidth -> back to the strip
  it('folds back when the chat would be narrower than the minimum', () => {
    const extra = cfg.width - cfg.railWidth
    expect(isCramped(cfg.minChatWidth - 1, true)).toBe(true)
    expect(isCramped(cfg.minChatWidth, true)).toBe(false)
    expect(isCramped(cfg.minChatWidth + extra - 1, false)).toBe(true) // closed: opening would take `extra`
    expect(isCramped(cfg.minChatWidth + extra, false)).toBe(false)
  })
})

describe('the sidebar on a phone', () => {
  beforeEach(() => viewport(375))

  it('closed, there is no strip; a button in the header opens it over the chat', async () => {
    const { sidebar } = setup()
    expect(screen.queryByRole('complementary', { name: T.label })).toBeNull()
    const opener = screen.getByRole('button', { name: T.toggle })
    expect(opener).toHaveAttribute('aria-expanded', 'false')
    const user = userEvent.setup()
    await user.click(opener)
    expect(sidebar()).toHaveClass('sidebar--floating')
    expect(sidebar()).toContainElement(document.activeElement)
    expect(within(sidebar()).getByRole('button', { name: T.newConversation })).toBeInTheDocument()
    expect(within(sidebar()).getByRole('button', { name: T.logout })).toBeInTheDocument()
    expect(document.querySelector('main')).toHaveAttribute('inert')
  })

  it('Escape closes it, and the focus goes back to the header button', async () => {
    setup()
    const user = userEvent.setup()
    const opener = screen.getByRole('button', { name: T.toggle })
    await user.click(opener)
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('complementary', { name: T.label })).toBeNull()
    expect(opener).toHaveFocus()
  })

  it('the close button and a pick close it', async () => {
    setup()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: T.toggle }))
    await user.click(screen.getByRole('button', { name: T.close }))
    expect(screen.queryByRole('complementary', { name: T.label })).toBeNull()
    await user.click(screen.getByRole('button', { name: T.toggle }))
    await user.click(await screen.findByText('ATTO 3 (2025)'))
    expect(screen.queryByRole('complementary', { name: T.label })).toBeNull()
  })

  it('a phone never opens it by itself, even if it was left open on a computer', () => {
    localStorage.setItem(cfg.storageKey, '1')
    setup()
    expect(screen.queryByRole('complementary', { name: T.label })).toBeNull()
  })
})

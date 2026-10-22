// Sending a question: the page (window) never scrolls; the message list goes to its end so the question, the
// road and the answer show; "sticky bottom": an employee who scrolled up is not pulled down, a button brings them back.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import cfg from '@/config/chat.json'
import EmployeeScreen from '@/employee/EmployeeScreen'

const NEW = cfg.texts.newBelow
let emit, finish, height

function setup() {
  const api = {
    streamChat: vi.fn((params, onEvent) => {
      emit = onEvent
      onEvent('thread', { thread_id: 'T1' })
      onEvent('step', { tool: 'calculate', label: 'כובי מחשב נטו…' })
      return new Promise((r) => { finish = r })
    }),
    streamRepAnswered: vi.fn(),
    restore: vi.fn(),
    threads: vi.fn().mockResolvedValue([]),
    me: vi.fn().mockResolvedValue({ employee_id: 'E01', name: 'נועה לוי' }),
  }
  render(<EmployeeScreen api={api} subscribe={() => () => {}} notifier={{ beep: vi.fn(), setUnread: vi.fn() }} />)
  return api
}
const list = () => screen.getByRole('list', { name: 'השיחה' })
const box = () => screen.getByLabelText('הודעה')

beforeEach(() => {
  sessionStorage.clear()
  localStorage.clear()
  height = 900
  Element.prototype.scrollIntoView = vi.fn()
  window.scrollTo = vi.fn()
  window.scrollBy = vi.fn()
  Object.defineProperty(HTMLElement.prototype, 'scrollHeight', { configurable: true, get: () => height })
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get: () => 300 })
})
afterEach(() => {
  vi.restoreAllMocks()
  delete HTMLElement.prototype.scrollHeight
  delete HTMLElement.prototype.clientHeight
  delete window.matchMedia
})

async function ask(user, text = 'מה יקרה לנטו שלי?') {
  await user.type(box(), text)
  await user.click(screen.getByRole('button', { name: 'שליחה' }))
}

describe('sending a question', () => {
  it('does not scroll the page; the list is at its end, the road shows, the focus stays in the box', async () => {
    setup()
    const user = userEvent.setup()
    const y = window.scrollY
    await ask(user)
    expect(window.scrollY).toBe(y)
    expect(window.scrollTo).not.toHaveBeenCalled()
    expect(window.scrollBy).not.toHaveBeenCalled()
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled()
    expect(list().scrollTop).toBe(900)
    expect(document.querySelector('.road')).not.toBeNull()
    expect(box()).toHaveFocus()
  })

  it('a welcome choice keeps the focus in the box, without scrolling', async () => {
    setup()
    const user = userEvent.setup()
    const calls = []
    const focus = HTMLElement.prototype.focus
    vi.spyOn(HTMLElement.prototype, 'focus').mockImplementation(function (o) { calls.push([this, o]); return focus.call(this, o) })
    await user.click(document.querySelector('.welcome__choice'))
    await waitFor(() => expect(box()).toHaveFocus())
    const onBox = calls.filter(([el]) => el === box())
    expect(onBox.length).toBeGreaterThan(0)
    expect(onBox.every(([, o]) => o?.preventScroll === true)).toBe(true)
    expect(window.scrollTo).not.toHaveBeenCalled()
  })

  it('at the bottom: the list follows the streamed answer', async () => {
    setup()
    await ask(userEvent.setup())
    height = 1400
    act(() => emit('token', { text: 'תשובה ארוכה' }))
    expect(list().scrollTop).toBe(1400)
    expect(screen.queryByRole('button', { name: NEW })).toBeNull()
  })
})

describe('scrolled up: not pulled down', () => {
  it('stays where it is, and "↓ תשובה חדשה" brings it to the end', async () => {
    setup()
    const user = userEvent.setup()
    await ask(user)
    list().scrollTop = 100
    fireEvent.scroll(list())
    height = 1400
    act(() => emit('token', { text: 'תשובה ארוכה' }))
    expect(list().scrollTop).toBe(100)
    const button = await screen.findByRole('button', { name: NEW })
    list().scrollTo = vi.fn(function ({ top }) { this.scrollTop = top })
    await user.click(button)
    expect(list().scrollTo).toHaveBeenCalledWith({ top: 1400, behavior: 'smooth' })
    expect(screen.queryByRole('button', { name: NEW })).toBeNull()
    expect(window.scrollTo).not.toHaveBeenCalled()
    act(() => finish())
  })

  it('reduced motion: the button jumps, no smooth scroll', async () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener() {}, removeEventListener() {} })
    setup()
    const user = userEvent.setup()
    await ask(user)
    list().scrollTop = 100
    fireEvent.scroll(list())
    height = 1400
    act(() => emit('token', { text: 'עוד' }))
    list().scrollTo = vi.fn()
    await user.click(await screen.findByRole('button', { name: NEW }))
    expect(list().scrollTo).toHaveBeenCalledWith({ top: 1400, behavior: 'auto' })
  })

  it('a new question brings the list back to the end', async () => {
    setup()
    const user = userEvent.setup()
    await ask(user)
    act(() => { emit('token', { text: 'א' }); finish() })
    list().scrollTop = 100
    fireEvent.scroll(list())
    height = 2000
    await ask(user, 'ועוד שאלה')
    expect(list().scrollTop).toBe(2000)
  })
})

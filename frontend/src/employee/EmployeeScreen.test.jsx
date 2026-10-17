import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import noa from '../test-fixtures/card-noa.json'
import EmployeeScreen from './EmployeeScreen'

const TID = '11111111-2222-3333-4444-555555555555'

function scripted(events) {
  return vi.fn(async (params, onEvent) => { for (const [e, d] of events) onEvent(e, d) })
}

function setup({ chatEvents, repEvents = [], restore } = {}) {
  let handlers
  const api = {
    streamChat: scripted(chatEvents ?? []),
    streamRepAnswered: scripted(repEvents),
    restore: restore ?? vi.fn().mockRejectedValue(new Error('none')),
  }
  const subscribe = vi.fn((tid, h) => { handlers = h; return () => {} })
  const notifier = { beep: vi.fn(), setUnread: vi.fn() }
  render(<EmployeeScreen api={api} subscribe={subscribe} notifier={notifier} />)
  return {
    api, subscribe, notifier,
    fireChanged: () => act(() => { handlers.onChanged() }),
    fireOpen: () => act(() => { handlers.onOpen() }),
  }
}

// what GET /chat/{id} returns: the server is the source of truth
const state = (rep = { pending: 0, new_answers: 0 }, messages = [{ role: 'user', text: 'שאלה' }]) =>
  ({ thread_id: TID, messages, cards: [], rep })

// before the rep answers, then after (the database says there is a new answer)
function repAnswersOnTheServer() {
  return vi.fn()
    .mockResolvedValueOnce(state({ pending: 1, new_answers: 0 }))
    .mockResolvedValue(state({ pending: 0, new_answers: 1 }))
}

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('EmployeeScreen', () => {
  it('streams the answer, shows the running step, and puts the card beside the chat', async () => {
    const { api } = setup({ chatEvents: [
      ['thread', { thread_id: TID }],
      ['step', { tool: 'calculate', label: 'מחשב נטו…' }],
      ['card', noa],
      ['token', { text: 'הנטו שלך ' }], ['token', { text: 'יעלה' }],
      ['done', {}],
    ] })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'אם אעבור ל-Atto 3?')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))

    expect(api.streamChat.mock.calls[0][0]).toEqual({ message: 'אם אעבור ל-Atto 3?', threadId: null })
    expect(await screen.findByText('הנטו שלך יעלה')).toBeInTheDocument()
    const cards = screen.getByRole('complementary', { name: 'כרטיס השוואה' })
    expect(within(cards).getByText(noa.card.alternative.label)).toBeInTheDocument()
    expect(localStorage.getItem('threadId')).toBe(TID)
  })

  it('keeps the conversation id for the next message', async () => {
    localStorage.setItem('threadId', TID)
    const { api } = setup({ chatEvents: [['token', { text: 'בסדר' }], ['done', {}]] })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'שלום')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    await screen.findByText('בסדר')
    expect(api.streamChat.mock.calls[0][0].threadId).toBe(TID)
  })

  it('shows a calm message when the server is overloaded', async () => {
    setup({ chatEvents: [['error', { message: 'המערכת עמוסה כרגע. נסו שוב בעוד דקה.' }]] })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'שלום')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    expect(await screen.findByText('המערכת עמוסה כרגע. נסו שוב בעוד דקה.')).toBeInTheDocument()
  })

  it('keeps the part of the answer already written when an error arrives mid-answer', async () => {
    setup({ chatEvents: [
      ['token', { text: 'בדקתי את הרכב' }],
      ['error', { message: 'המערכת עמוסה כרגע. נסו שוב בעוד דקה.' }],
    ] })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'שלום')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    expect(await screen.findByText('המערכת עמוסה כרגע. נסו שוב בעוד דקה.')).toBeInTheDocument()
    expect(screen.getByText(/בדקתי את הרכב/)).toBeInTheDocument()
  })

  it('"changed": reads the conversation again, beeps, and puts (1) in the tab title', async () => {
    localStorage.setItem('threadId', TID)
    const restore = vi.fn().mockResolvedValue(state())
    const { notifier, fireChanged } = setup({ restore })
    await waitFor(() => expect(restore).toHaveBeenCalledTimes(1)) // page load
    fireChanged()
    await waitFor(() => expect(restore).toHaveBeenCalledTimes(2))
    expect(restore).toHaveBeenLastCalledWith(TID)
    expect(notifier.beep).toHaveBeenCalled()
    expect(notifier.setUnread).toHaveBeenCalledWith(1)
  })

  it('reads the conversation on page load and again when the employee returns to the tab', async () => {
    localStorage.setItem('threadId', TID)
    const restore = vi.fn().mockResolvedValue(state())
    setup({ restore })
    await waitFor(() => expect(restore).toHaveBeenCalledTimes(1))
    act(() => { document.dispatchEvent(new Event('visibilitychange')) })
    await waitFor(() => expect(restore).toHaveBeenCalledTimes(2))
  })

  it('reads the conversation again after the event stream reconnects', async () => {
    localStorage.setItem('threadId', TID)
    const restore = vi.fn().mockResolvedValue(state())
    const { fireOpen } = setup({ restore })
    await waitFor(() => expect(restore).toHaveBeenCalledTimes(1))
    fireOpen()
    await waitFor(() => expect(restore).toHaveBeenCalledTimes(2))
    fireOpen()
    await waitFor(() => expect(restore).toHaveBeenCalledTimes(3))
  })

  it('when the rep answers: beeps, marks the tab, and lets the bot recalculate', async () => {
    localStorage.setItem('threadId', TID)
    const { api, subscribe, notifier, fireChanged } = setup({
      restore: repAnswersOnTheServer(),
      repEvents: [['card', noa], ['token', { text: 'עודכן' }], ['done', {}]],
    })
    expect(subscribe).toHaveBeenCalledWith(TID, expect.objectContaining({ onChanged: expect.any(Function) }))
    await screen.findByText('שאלה')
    fireChanged()
    await waitFor(() => expect(api.streamRepAnswered).toHaveBeenCalledWith(TID, expect.any(Function)))
    expect(notifier.beep).toHaveBeenCalled()
    expect(notifier.setUnread).toHaveBeenCalledWith(1)
    expect(await screen.findByText('עודכן')).toBeInTheDocument()
    expect(screen.getByText('הנציג ענה, והחלופה מתעדכנת')).toBeInTheDocument()
  })

  it('the car arrives only when a real result (card) arrives, not when the bot starts writing', async () => {
    let emit
    let finish
    const api = {
      streamChat: vi.fn((params, onEvent) => { emit = onEvent; return new Promise((r) => { finish = r }) }),
      streamRepAnswered: vi.fn(),
      restore: vi.fn().mockRejectedValue(new Error('none')),
    }
    render(<EmployeeScreen api={api} subscribe={() => () => {}} notifier={{ beep: vi.fn(), setUnread: vi.fn() }} />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'שאלה')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))

    act(() => { emit('step', { tool: 'check_eligibility', label: 'בודק זכאות…' }) })
    expect(screen.getByRole('status')).toHaveTextContent('בודק זכאות…')
    // the bot asks a follow-up question: no calculation yet, so the car must not arrive
    act(() => { emit('token', { text: 'מה השכר שלך?' }) })
    expect(screen.getByRole('status')).not.toHaveTextContent('התשובה מוכנה')

    act(() => { emit('card', noa) })
    expect(screen.getByRole('status')).toHaveTextContent('התשובה מוכנה')
    await act(async () => { finish() })
  })

  it('the road shows only the tools this answer really used', async () => {
    let emit
    const api = {
      streamChat: vi.fn((params, onEvent) => { emit = onEvent; return new Promise(() => {}) }),
      streamRepAnswered: vi.fn(),
      restore: vi.fn().mockRejectedValue(new Error('none')),
    }
    const { container } = render(<EmployeeScreen api={api} subscribe={() => () => {}} notifier={{ beep: vi.fn(), setUnread: vi.fn() }} />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'כן, תמשיך לפי קבוצה ב')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    // nothing called yet: the car does not head to any station by guess
    expect(container.querySelectorAll('.stop')).toHaveLength(0)
    act(() => { emit('step', { tool: 'check_eligibility', label: 'בודק זכאות…' }) })
    expect([...container.querySelectorAll('.stop')].map((s) => s.textContent)).toEqual(['זכאות'])
  })

  it('a turn without a result leaves no car parked at the end', async () => {
    setup({ chatEvents: [['step', { label: 'מחפש את הרכב…' }], ['token', { text: 'באיזו שנה הרכב?' }], ['done', {}]] })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'שאלה')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    await screen.findByText('באיזו שנה הרכב?')
    expect(screen.queryByText('התשובה מוכנה')).toBeNull()
  })

  it('the comparison panel closes to a side tab and reopens', async () => {
    setup({ chatEvents: [['card', noa], ['token', { text: 'מוכן' }], ['done', {}]] })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'שאלה')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    await screen.findByText('מוכן')

    const close = screen.getByRole('button', { name: 'סגירת פאנל ההשוואה' })
    expect(close).toHaveAttribute('aria-expanded', 'true')
    await user.click(close)
    const open = screen.getByRole('button', { name: 'פתיחת פאנל ההשוואה' })
    expect(open).toHaveAttribute('aria-expanded', 'false')
    await user.click(open)
    expect(screen.getByRole('complementary', { name: 'כרטיס השוואה' })).toBeVisible()
  })

  it('reopens the panel by itself when the rep answers', async () => {
    localStorage.setItem('threadId', TID)
    const { fireChanged } = setup({
      restore: repAnswersOnTheServer(),
      repEvents: [['card', noa], ['token', { text: 'עודכן' }], ['done', {}]],
    })
    await screen.findByText('שאלה')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'סגירת פאנל ההשוואה' }))
    fireChanged()
    await screen.findByText('עודכן')
    await waitFor(() => expect(screen.getByRole('button', { name: 'סגירת פאנל ההשוואה' })).toHaveAttribute('aria-expanded', 'true'))
  })

  it('a rep answer that arrived while the page was closed is picked up on load', async () => {
    localStorage.setItem('threadId', TID)
    const { api } = setup({
      restore: vi.fn().mockResolvedValue(state({ pending: 0, new_answers: 1 })),
      repEvents: [['token', { text: 'עודכן' }], ['done', {}]],
    })
    await waitFor(() => expect(api.streamRepAnswered).toHaveBeenCalledWith(TID, expect.any(Function)))
    expect(await screen.findByText('עודכן')).toBeInTheDocument()
  })

  it('has a "talk to a rep" button with contact details', () => {
    setup()
    expect(screen.getByRole('button', { name: 'שיחה עם נציג' })).toBeInTheDocument()
  })

  it('no "new conversation" link on an empty screen', () => {
    setup()
    expect(screen.queryByRole('button', { name: /שיחה חדשה/ })).toBeNull()
  })

  it('"new conversation" clears the screen and the next message starts a new conversation', async () => {
    const { api } = setup({ chatEvents: [
      ['thread', { thread_id: TID }], ['card', noa], ['token', { text: 'הנטו עולה' }], ['done', {}],
    ] })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'שאלה ראשונה')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    await screen.findByText('הנטו עולה')

    await user.click(screen.getByRole('button', { name: /שיחה חדשה/ }))
    expect(screen.queryByText('הנטו עולה')).toBeNull()
    expect(screen.queryByText('שאלה ראשונה')).toBeNull()
    const cards = screen.getByRole('complementary', { name: 'כרטיס השוואה' })
    expect(within(cards).queryByText(noa.card.alternative.label)).toBeNull()
    expect(localStorage.getItem('threadId')).toBeNull()

    await user.type(screen.getByLabelText('הודעה'), 'שאלה חדשה')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    expect(api.streamChat.mock.calls[1][0]).toEqual({ message: 'שאלה חדשה', threadId: null })
  })

  it('"new conversation" also works on a conversation restored after a reload', async () => {
    localStorage.setItem('threadId', TID)
    setup({ restore: vi.fn().mockResolvedValue(state()) })
    await screen.findByText('שאלה')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /שיחה חדשה/ }))
    expect(screen.queryByText('שאלה')).toBeNull()
    expect(localStorage.getItem('threadId')).toBeNull()
  })

  it('"new conversation" is disabled while an answer is being written', async () => {
    let finish
    const api = {
      streamChat: vi.fn((params, onEvent) => { onEvent('thread', { thread_id: TID }); return new Promise((r) => { finish = r }) }),
      streamRepAnswered: vi.fn(),
      restore: vi.fn().mockRejectedValue(new Error('none')),
    }
    render(<EmployeeScreen api={api} subscribe={() => () => {}} notifier={{ beep: vi.fn(), setUnread: vi.fn() }} />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'שאלה')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    expect(screen.getByRole('button', { name: /שיחה חדשה/ })).toBeDisabled()
    await act(async () => { finish() })
    expect(screen.getByRole('button', { name: /שיחה חדשה/ })).toBeEnabled()
  })

  it('restores the conversation after a reload', async () => {
    localStorage.setItem('threadId', TID)
    const restore = vi.fn().mockResolvedValue({
      thread_id: TID,
      messages: [{ role: 'user', text: 'שאלה' }, { role: 'assistant', text: 'תשובה' }],
      cards: [noa],
    })
    setup({ restore })
    expect(await screen.findByText('תשובה')).toBeInTheDocument()
    const cards = screen.getByRole('complementary', { name: 'כרטיס השוואה' })
    expect(within(cards).getByText(noa.card.alternative.label)).toBeInTheDocument()
  })

  it('the "talk to a rep" button sits in the message row: button, then the text box, then send', () => {
    setup()
    const form = screen.getByLabelText('הודעה').closest('form')
    const order = [...form.querySelectorAll('.contact__btn, textarea, button[type="submit"]')].map((el) =>
      el.matches('.contact__btn') ? 'contact' : el.tagName === 'TEXTAREA' ? 'input' : 'send')
    expect(order).toEqual(['contact', 'input', 'send']) // RTL: the first is on the right
  })
  describe('welcome screen', () => {
    const CHOICES = [
      ['לעבור לרכב חשמלי', 'מה יקרה לנטו שלי אם אעבור לרכב חשמלי?'],
      ['להחליף לרכב אחר', 'מה יקרה לנטו שלי אם אחליף לרכב אחר?'],
      ['מסלול משפחתי', 'מה יקרה לנטו שלי אם אעבור למסלול המשפחתי?'],
      ['לוותר על הרכב', 'מה יקרה לנטו שלי אם אוותר על הרכב?'],
    ]

    it('shows the parked car, a greeting and four equal choices when there are no messages', () => {
      const { container } = render(<EmployeeScreen api={{ restore: vi.fn().mockRejectedValue(new Error('none')) }}
        subscribe={() => () => {}} notifier={{ beep: vi.fn(), setUnread: vi.fn() }} />)
      const welcome = screen.getByRole('region', { name: 'שלום! בואו נבדוק מה יקרה לנטו שלך' })
      expect(within(welcome).getByText('השוואה ברורה לפי כללי שטראוס ורשות המסים – תוך דקה')).toBeInTheDocument()
      expect(within(welcome).getByText(/אפשר גם לשאול: מה זה שווי שימוש\? מה זה השתתפות עצמית\?/)).toBeInTheDocument()
      expect(welcome.querySelector('.welcome__car .road__body')).not.toBeNull() // the white car with the logo
      const buttons = CHOICES.map(([label]) => within(welcome).getByRole('button', { name: label }))
      // none stands out: the bot compares, it does not recommend
      expect(new Set(buttons.map((b) => b.className))).toEqual(new Set(['welcome__choice']))
      expect(container.querySelector('.msg--hint')).toBeNull()
    })

    it.each(CHOICES)('"%s" sends the full question', async (label, question) => {
      const { api } = setup({ chatEvents: [['token', { text: 'בואו נתחיל' }], ['done', {}]] })
      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: label }))
      expect(api.streamChat.mock.calls[0][0]).toEqual({ message: question, threadId: null })
      expect(await screen.findByText(question)).toBeInTheDocument()
    })

    it('the choices are reachable from the keyboard', async () => {
      setup()
      const user = userEvent.setup()
      const first = screen.getByRole('button', { name: CHOICES[0][0] })
      first.focus()
      expect(first).toHaveFocus()
      await user.keyboard('{Enter}')
      expect(await screen.findByText(CHOICES[0][1])).toBeInTheDocument()
    })

    it('disappears after the first message', async () => {
      setup({ chatEvents: [['token', { text: 'תשובה' }], ['done', {}]] })
      const user = userEvent.setup()
      await user.type(screen.getByLabelText('הודעה'), 'שאלה')
      await user.click(screen.getByRole('button', { name: 'שליחה' }))
      await screen.findByText('תשובה')
      expect(screen.queryByRole('region', { name: 'שלום! בואו נבדוק מה יקרה לנטו שלך' })).toBeNull()
    })

    it('is not shown over a conversation restored after a reload', async () => {
      localStorage.setItem('threadId', TID)
      setup({ restore: vi.fn().mockResolvedValue(state()) })
      await screen.findByText('שאלה')
      expect(screen.queryByRole('button', { name: 'לעבור לרכב חשמלי' })).toBeNull()
    })
  })
})

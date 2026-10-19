import { readFileSync } from 'node:fs'
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
      ['step', { tool: 'calculate', label: 'כובי מחשב נטו…' }],
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
    setup({ chatEvents: [['error', { message: 'כובי עמוס כרגע. נסו שוב בעוד רגע.' }]] })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'שלום')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    expect(await screen.findByText('כובי עמוס כרגע. נסו שוב בעוד רגע.')).toBeInTheDocument()
  })

  it('keeps the part of the answer already written when an error arrives mid-answer', async () => {
    setup({ chatEvents: [
      ['token', { text: 'בדקתי את הרכב' }],
      ['error', { message: 'כובי עמוס כרגע. נסו שוב בעוד רגע.' }],
    ] })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'שלום')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    expect(await screen.findByText('כובי עמוס כרגע. נסו שוב בעוד רגע.')).toBeInTheDocument()
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

    act(() => { emit('step', { tool: 'check_eligibility', label: 'כובי בודק זכאות…' }) })
    expect(screen.getByRole('status')).toHaveTextContent('כובי בודק זכאות…')
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
    act(() => { emit('step', { tool: 'check_eligibility', label: 'כובי בודק זכאות…' }) })
    expect([...container.querySelectorAll('.stop')].map((s) => s.textContent)).toEqual(['זכאות'])
  })

  it('a turn without a result leaves no car parked at the end', async () => {
    setup({ chatEvents: [['step', { label: 'כובי מחפש את הרכב…' }], ['token', { text: 'באיזו שנה הרכב?' }], ['done', {}]] })
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
  it("the bot's Markdown is shown formatted; the employee's own text is shown as typed", async () => {
    setup({ chatEvents: [['token', { text: 'חסר לי: **עיסוק**' }], ['done', {}]] })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), '**שלום**')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    expect((await screen.findByText('עיסוק')).tagName).toBe('STRONG')
    expect(screen.getByText('**שלום**')).toBeInTheDocument()
  })

  it('the main title is "Kobi", with the product name smaller; the tab says so too', () => {
    document.title = ''
    setup()
    const h1 = screen.getByRole('heading', { level: 1 })
    expect(h1.querySelector('.topbar__name')).toHaveTextContent(/^כובי$/)
    expect(h1.querySelector('.topbar__product')).toHaveTextContent(/^יועץ הרכב של שטראוס$/)
    expect(document.title).toBe('כובי · יועץ הרכב של שטראוס')
  })

  it('the header says it is only a check: nothing changes in salary or car', () => {
    setup()
    const sub = document.querySelector('.topbar__sub')
    expect(sub).toHaveTextContent('רק בדיקה, שום דבר לא משתנה בשכר או ברכב שלכם · לפי כללי שטראוס ורשות המסים')
    expect(sub.querySelector('strong')).toHaveTextContent(/^רק בדיקה, שום דבר לא משתנה בשכר או ברכב שלכם$/)
  })

  it('the empty card panel explains why a car changes the salary and how it works (no fake table)', () => {
    const { container } = render(<EmployeeScreen api={{ restore: vi.fn().mockRejectedValue(new Error('none')) }}
      subscribe={() => () => {}} notifier={{ beep: vi.fn(), setUnread: vi.fn() }} />)
    const panel = screen.getByRole('complementary', { name: 'כרטיס השוואה' })
    expect(within(panel).getByRole('heading', { name: 'למה רכב משנה את המשכורת?' })).toBeInTheDocument()
    expect(within(panel).getByText(/המדינה רואה בו חלק מהשכר שלכם/)).toBeInTheDocument()
    expect(within(panel).getByRole('heading', { name: 'איך זה עובד?' })).toBeInTheDocument()
    expect([...panel.querySelectorAll('ol > li')].map((li) => li.textContent)).toEqual([
      'מספרים לכובי בקצרה על השכר והרכב שלכם',
      'בוחרים מה לבדוק',
      'מקבלים כאן השוואה: היום מול החלופה, וכמה יישאר לכם בכל חודש',
    ])
    expect(panel.querySelector('.ghost-card, table')).toBeNull()
    expect(panel.textContent).not.toMatch(/\d/)
    expect(container.textContent).not.toContain('כרטיס ההשוואה יופיע כאן')
  })

  it('the first comparison replaces the explanation with the real card', async () => {
    setup({ chatEvents: [['card', noa], ['token', { text: 'מוכן' }], ['done', {}]] })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'שאלה')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    await screen.findByText('מוכן')
    const panel = screen.getByRole('complementary', { name: 'כרטיס השוואה' })
    expect(within(panel).queryByRole('heading', { name: 'איך זה עובד?' })).toBeNull()
    expect(within(panel).getByText(noa.card.alternative.label)).toBeInTheDocument()
  })

  it('every bot message is signed as Kobi, a bot', async () => {
    setup({ chatEvents: [['token', { text: 'שלום' }], ['done', {}]] })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'היי')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    await screen.findByText('שלום')
    expect(screen.getByText('כובי · בוט')).toBeInTheDocument()
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
      const welcome = screen.getByRole('region', { name: 'שלום, אני כובי' })
      expect(within(welcome).getByText('רכב חברה משפיע על המשכורת שלכם, גם אם לא שמתם לב.')).toBeInTheDocument()
      expect(within(welcome).getByText('אני מראה בדיוק כמה כסף יישאר לכם בכל חודש, היום ואחרי שינוי ברכב.')).toBeInTheDocument()
      expect(within(welcome).getByRole('group', { name: 'מה תרצו לבדוק?' })).toBeInTheDocument()
      expect(within(welcome).getByText('לא בטוחים מה זה "שווי שימוש" או "השתתפות עצמית"? פשוט שאלו אותי.')).toBeInTheDocument()
      expect(welcome.textContent).not.toMatch(/\d/) // no numbers for people new to all this
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
      expect(screen.queryByRole('region', { name: 'שלום, אני כובי' })).toBeNull()
    })

    it('is not shown over a conversation restored after a reload', async () => {
      localStorage.setItem('threadId', TID)
      setup({ restore: vi.fn().mockResolvedValue(state()) })
      await screen.findByText('שאלה')
      expect(screen.queryByRole('button', { name: 'לעבור לרכב חשמלי' })).toBeNull()
    })
  })
})

// the message box grows with each line, like other chats; past ~7 lines it scrolls (styles.css)
describe('message box grows with the text', () => {
  const LINE = 24
  beforeEach(() => {
    // jsdom has no layout: the content height is one LINE per line of text
    Object.defineProperty(HTMLTextAreaElement.prototype, 'scrollHeight', {
      configurable: true, get() { return this.value.split('\n').length * LINE },
    })
  })
  afterEach(() => { delete HTMLTextAreaElement.prototype.scrollHeight })

  it('takes the height of its text, and goes back to one line after sending', async () => {
    setup({ chatEvents: [['done', {}]] })
    const user = userEvent.setup()
    const box = screen.getByLabelText('הודעה')
    await user.type(box, 'שורה 1{Shift>}{Enter}{/Shift}שורה 2{Shift>}{Enter}{/Shift}שורה 3')
    expect(box.style.height).toBe(`${3 * LINE}px`)
    await user.type(box, '{Enter}')
    await waitFor(() => expect(box.style.height).toBe(`${LINE}px`))
  })

  it('stops growing at about 7 lines and scrolls from there; the buttons stay at the bottom', () => {
    const css = readFileSync('src/styles.css', 'utf8')
    const rule = css.match(/\.chat__form textarea \{([^}]*)\}/)[1]
    expect(rule).toMatch(/max-height:\s*calc\(7 \* 1\.5em/)
    expect(rule).toMatch(/overflow-y:\s*auto/)
    expect(rule).toMatch(/line-height:\s*1\.5/)
    expect(rule).not.toMatch(/border-radius:\s*999px/) // a pill looks wrong at 7 lines
    expect(css).toMatch(/\.chat__form \{[^}]*align-items:\s*flex-end/)
  })
})

// rank_options: its card (full specs) comes over the same "card" event, and never through the model
describe('ranking card', () => {
  it('shows the ranking card beside the chat', async () => {
    const { default: ranking } = await import('../test-fixtures/card-ranking.json')
    setup({ chatEvents: [['thread', { thread_id: TID }], ['card', ranking], ['token', { text: 'סידרתי' }], ['done', {}]] })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('הודעה'), 'תסדר לי לפי זיהום')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    const cards = await screen.findByRole('complementary', { name: 'כרטיס השוואה' })
    expect(await within(cards).findByRole('heading', { name: /סידרתי לפי/ })).toBeInTheDocument()
    expect(within(cards).getAllByRole('article')).toHaveLength(ranking.card.options.length)
  })
})

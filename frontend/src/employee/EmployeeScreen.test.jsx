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
  let answered
  const api = {
    streamChat: scripted(chatEvents ?? []),
    streamRepAnswered: scripted(repEvents),
    restore: restore ?? vi.fn().mockRejectedValue(new Error('none')),
  }
  const subscribe = vi.fn((tid, cb) => { answered = cb; return () => {} })
  const notifier = { beep: vi.fn(), setUnread: vi.fn() }
  render(<EmployeeScreen api={api} subscribe={subscribe} notifier={notifier} />)
  return { api, subscribe, notifier, fireRepAnswered: () => act(() => answered()) }
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

  it('when the rep answers: beeps, marks the tab, and lets the bot recalculate', async () => {
    localStorage.setItem('threadId', TID)
    const { api, subscribe, notifier, fireRepAnswered } = setup({
      repEvents: [['card', noa], ['token', { text: 'עודכן' }], ['done', {}]],
    })
    expect(subscribe).toHaveBeenCalledWith(TID, expect.any(Function))
    fireRepAnswered()
    await waitFor(() => expect(api.streamRepAnswered).toHaveBeenCalledWith(TID, expect.any(Function)))
    expect(notifier.beep).toHaveBeenCalled()
    expect(notifier.setUnread).toHaveBeenCalledWith(1)
    expect(await screen.findByText('עודכן')).toBeInTheDocument()
    expect(screen.getByText('הנציג ענה, והחלופה מתעדכנת')).toBeInTheDocument()
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
    const { fireRepAnswered } = setup({ repEvents: [['card', noa], ['token', { text: 'עודכן' }], ['done', {}]] })
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'סגירת פאנל ההשוואה' }))
    fireRepAnswered()
    await screen.findByText('עודכן')
    expect(screen.getByRole('button', { name: 'סגירת פאנל ההשוואה' })).toHaveAttribute('aria-expanded', 'true')
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
})

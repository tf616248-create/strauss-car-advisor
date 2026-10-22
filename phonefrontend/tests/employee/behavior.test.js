// How the chat behaves: the list stays at the bottom while an answer streams in, unless the employee
// scrolled up ("↓ תשובה חדשה" brings it back); opening a conversation shows that it is loading (and a
// failure, with "לנסות שוב"); and a screen reader hears the answer once it is done, not letter by letter.
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react-native'
import * as RN from 'react-native'
import EmployeeScreen from '@/employee/EmployeeScreen'
import { clearSession, setToken } from '@/lib/session'
import { fakeApi, quiet } from './fakes'
const chat = require('@/config/chat.json')

beforeEach(() => { clearSession(); setToken('t') })
afterEach(() => jest.restoreAllMocks())

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

test('scrolled up when new words arrive: it stays put, "↓ תשובה חדשה" brings it down; a new question sticks again', async () => {
  await render(<EmployeeScreen api={fakeApi()} {...quiet()} />)
  await fireEvent.press(screen.getByText('לעבור לרכב חשמלי'))
  await screen.findByText('הנטו עולה.')
  const list = screen.getByTestId('chat-list')
  await fireEvent.scroll(list, { nativeEvent: { contentOffset: { y: 0 }, contentSize: { height: 2000 }, layoutMeasurement: { height: 500 } } })
  await fireEvent(list, 'contentSizeChange', 0, 2600) // more of the answer (or a rep answer) below
  const below = await screen.findByRole('button', { name: chat.texts.newBelow })
  await fireEvent.press(below)
  expect(screen.queryByRole('button', { name: chat.texts.newBelow })).toBeNull()
  await fireEvent.scroll(list, { nativeEvent: { contentOffset: { y: 0 }, contentSize: { height: 2600 }, layoutMeasurement: { height: 500 } } })
  await fireEvent.changeText(screen.getByLabelText('הודעה'), 'עוד שאלה')
  await fireEvent.press(screen.getByText('שליחה'))
  await fireEvent(list, 'contentSizeChange', 0, 3200)
  expect(screen.queryByRole('button', { name: chat.texts.newBelow })).toBeNull() // a new question: back to the bottom
})

test('at the bottom: no button, the list follows the answer', async () => {
  await render(<EmployeeScreen api={fakeApi()} {...quiet()} />)
  await fireEvent.press(screen.getByText('לעבור לרכב חשמלי'))
  await screen.findByText('הנטו עולה.')
  await fireEvent(screen.getByTestId('chat-list'), 'contentSizeChange', 0, 2600)
  expect(screen.queryByRole('button', { name: chat.texts.newBelow })).toBeNull()
})

const one = [{ thread_id: 'a', title: 'ATTO 3', updated_at: '2026-10-20T10:00:00Z' }]

test('opening a conversation: "טוען שיחה…" after a moment, and the box waits until it is loaded', async () => {
  const load = deferred()
  const api = fakeApi({ threads: jest.fn(async () => one), restore: jest.fn(() => load.promise) })
  await render(<EmployeeScreen api={api} {...quiet()} />)
  expect(await screen.findByText(chat.texts.loading, {}, { timeout: 2000 })).toBeTruthy()
  expect(screen.getByLabelText('הודעה').props.editable).toBe(false)
  await act(async () => { load.resolve({ messages: [{ role: 'user', text: 'שאלה ישנה' }], cards: [], rep: { pending: 0, new_answers: 0 } }) })
  expect(await screen.findByText('שאלה ישנה')).toBeTruthy()
  expect(screen.queryByText(chat.texts.loading)).toBeNull()
  expect(screen.getByLabelText('הודעה').props.editable).not.toBe(false)
})

test('it fails: says so, with "לנסות שוב"; a conversation that is gone (404) is a new one', async () => {
  const api = fakeApi({ threads: jest.fn(async () => one), restore: jest.fn(async () => { throw Object.assign(new Error('x'), { status: 500 }) }) })
  await render(<EmployeeScreen api={api} {...quiet()} />)
  const failed = await screen.findByText(chat.texts.loadFailed)
  expect(failed.props.accessibilityRole).toBe('alert')
  api.restore.mockResolvedValue({ messages: [{ role: 'user', text: 'נטען' }], cards: [], rep: { pending: 0, new_answers: 0 } })
  await fireEvent.press(screen.getByRole('button', { name: chat.texts.retry }))
  expect(await screen.findByText('נטען')).toBeTruthy()
})

test('a conversation that is gone (404): a new conversation, not a failure', async () => {
  const api = fakeApi({ threads: jest.fn(async () => one), restore: jest.fn(async () => { throw Object.assign(new Error('x'), { status: 404 }) }) })
  await render(<EmployeeScreen api={api} {...quiet()} />)
  await waitFor(() => expect(api.restore).toHaveBeenCalled())
  expect(await screen.findByText('לעבור לרכב חשמלי')).toBeTruthy()
  expect(screen.queryByText(chat.texts.loadFailed)).toBeNull()
})

test('a screen reader hears "כובי מקליד…", then the whole answer once, without the Markdown', async () => {
  const announce = jest.spyOn(RN.AccessibilityInfo, 'announceForAccessibility').mockImplementation(() => {})
  const api = fakeApi({ streamChat: jest.fn(async (_b, onEvent) => {
    onEvent('thread', { thread_id: 'th1' })
    onEvent('token', { text: 'הנטו **עולה** ב-661 ₪.' })
    onEvent('done', {})
  }) })
  await render(<EmployeeScreen api={api} {...quiet()} />)
  await fireEvent.press(screen.getByText('לעבור לרכב חשמלי'))
  await waitFor(() => expect(announce).toHaveBeenCalledWith('כובי ענה: הנטו עולה ב-661 ₪.'))
  expect(announce).toHaveBeenCalledWith('כובי מקליד…')
})

// Login and the employee screen, with a fake server (api) and no real-time connection.
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react-native'
import Login from '../src/components/Login'
import EmployeeScreen from '../src/employee/EmployeeScreen'
import { clearSession, getToken, setToken } from '../src/lib/session'
import noa from '../src/test-fixtures/card-noa.json'

beforeEach(() => clearSession())

function fakeApi(over = {}) {
  return {
    login: jest.fn(),
    threads: jest.fn(async () => []),
    restore: jest.fn(async () => ({ messages: [], cards: [], rep: { pending: 0, new_answers: 0 } })),
    streamChat: jest.fn(async (_body, onEvent) => {
      onEvent('thread', { thread_id: 'th1' })
      onEvent('step', { tool: 'calculate', label: 'כובי מחשב נטו…' })
      onEvent('card', noa)
      onEvent('token', { text: 'הנטו ' })
      onEvent('token', { text: 'עולה.' })
      onEvent('done', {})
    }),
    streamRepAnswered: jest.fn(async () => {}),
    ...over,
  }
}
const quiet = { subscribe: () => () => {}, notifier: { beep: jest.fn(), setUnread: jest.fn() } }

test('login: a wrong code says so; a right one keeps the token and goes in', async () => {
  const api = fakeApi({ login: jest.fn(async (c) => { if (c !== '1111') throw Object.assign(new Error(), { status: 401 }); return { token: 'tok' } }) })
  const onLogin = jest.fn()
  await render(<Login api={api} onLogin={onLogin} />)
  await fireEvent.changeText(screen.getByLabelText('קוד עובד'), '9')
  await fireEvent.press(screen.getByText('כניסה'))
  await screen.findByText('הקוד לא נכון. נסו שוב.')
  await fireEvent.changeText(screen.getByLabelText('קוד עובד'), '1111')
  await fireEvent.press(screen.getByText('כניסה'))
  await waitFor(() => expect(onLogin).toHaveBeenCalled())
  expect(getToken()).toBe('tok')
})

test('welcome: Kobi is a bot, four equal choices; a choice asks the full question', async () => {
  setToken('t')
  const api = fakeApi()
  await render(<EmployeeScreen api={api} {...quiet} />)
  expect(screen.getByText('שלום, אני כובי')).toBeTruthy()
  for (const l of ['לעבור לרכב חשמלי', 'להחליף לרכב אחר', 'מסלול משפחתי', 'לוותר על הרכב']) expect(screen.getByText(l)).toBeTruthy()
  await fireEvent.press(screen.getByText('לעבור לרכב חשמלי'))
  await screen.findByText('הנטו עולה.')
  expect(api.streamChat.mock.calls[0][0]).toEqual({ message: 'מה יקרה לנטו שלי אם אעבור לרכב חשמלי?', threadId: null })
  expect(screen.getByText('כובי · בוט')).toBeTruthy()
  expect(screen.queryByText('שלום, אני כובי')).toBeNull()
})

test('the comparison is its own tab, with the net change on it', async () => {
  setToken('t')
  await render(<EmployeeScreen api={fakeApi()} {...quiet} />)
  await fireEvent.press(screen.getByText('לעבור לרכב חשמלי'))
  await screen.findByText('הנטו עולה.')
  expect(screen.getAllByText(/\+661 ₪/).length).toBeGreaterThan(0) // the chip on the tab
  await fireEvent.press(screen.getByLabelText('השוואה'))
  expect(screen.getByText('הנתונים שלך')).toBeTruthy()
})

test('typing a question sends it; the next one goes to the same conversation', async () => {
  setToken('t')
  const api = fakeApi()
  await render(<EmployeeScreen api={api} {...quiet} />)
  await fireEvent.changeText(screen.getByLabelText('הודעה'), 'שאלה ראשונה')
  await fireEvent.press(screen.getByText('שליחה'))
  await screen.findByText('הנטו עולה.')
  await fireEvent.changeText(screen.getByLabelText('הודעה'), 'טעיתי, השכר 19,500')
  await fireEvent.press(screen.getByText('שליחה'))
  await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(2))
  expect(api.streamChat.mock.calls[1][0]).toEqual({ message: 'טעיתי, השכר 19,500', threadId: 'th1' })
})

test('a rep answer the bot has not used yet starts the recalculation, once', async () => {
  setToken('t')
  let rang
  const api = fakeApi({
    threads: jest.fn(async () => [{ thread_id: 'th9', title: 'ATTO 2', updated_at: '2026-10-20T10:00:00Z' }]),
    restore: jest.fn(async () => ({ messages: [{ role: 'user', text: 'BYD Atto 2?' }], cards: [], rep: { pending: 0, new_answers: 1 } })),
  })
  await render(<EmployeeScreen api={api} subscribe={(tid, h) => { rang = h; return () => {} }} notifier={quiet.notifier} />)
  await waitFor(() => expect(api.streamRepAnswered).toHaveBeenCalledWith('th9', expect.any(Function)))
  expect(screen.getByText('הנציג ענה, והחלופה מתעדכנת')).toBeTruthy()
  api.restore.mockResolvedValue({ messages: [], cards: [], rep: { pending: 0, new_answers: 0 } })
  await act(async () => { rang.onChanged() })
  expect(quiet.notifier.beep).toHaveBeenCalled()
  expect(api.streamRepAnswered).toHaveBeenCalledTimes(1)
})

test('my conversations: the list, and opening one reads it from the server', async () => {
  setToken('t')
  const api = fakeApi({ threads: jest.fn(async () => [{ thread_id: 'a', title: 'ATTO 3', updated_at: '2026-10-20T10:00:00Z' }]) })
  await render(<EmployeeScreen api={api} {...quiet} />)
  await waitFor(() => expect(api.restore).toHaveBeenCalledWith('a')) // the newest opens by itself
  await fireEvent.press(screen.getByText('השיחות שלי'))
  expect(await screen.findByText('ATTO 3')).toBeTruthy()
})

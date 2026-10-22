// The side menu: ☰ in the header opens it over the screen. New conversation, profile, customize,
// usage, my conversations, and at the bottom the employee's name and logout.
import { render, screen, fireEvent, waitFor } from '@testing-library/react-native'
import EmployeeScreen from '@/employee/EmployeeScreen'
import { clearSession, setToken } from '@/lib/session'
import { fakeApi, quiet } from './fakes'
const S = require('@/config/sidebar.json').texts

beforeEach(() => { clearSession(); setToken('t') })

async function openMenu() {
  await fireEvent.press(screen.getByRole('button', { name: S.toggle }))
  return screen.findByRole('button', { name: S.close }) // the menu is open (its name is the same as ☰'s)
}

test('☰ opens the menu over the screen: its items, the name and logout; ✕ closes it', async () => {
  const api = fakeApi({ threads: jest.fn(async () => [{ thread_id: 'a', title: 'ATTO 3', updated_at: '2026-10-20T10:00:00Z' }]) })
  await render(<EmployeeScreen api={api} {...quiet()} />)
  expect(screen.getByRole('button', { name: S.toggle }).props.accessibilityState).toMatchObject({ expanded: false })
  await openMenu()
  for (const name of [S.newConversation, S.profile, S.customize, S.logout]) expect(screen.getByRole('button', { name })).toBeTruthy()
  expect(screen.getByText(S.history)).toBeTruthy()
  expect(await screen.findByText('ATTO 3')).toBeTruthy()
  expect(await screen.findByText('נועה לוי')).toBeTruthy()
  await fireEvent.press(screen.getByRole('button', { name: S.close }))
  await waitFor(() => expect(screen.queryByRole('button', { name: S.close })).toBeNull())
})

test('new conversation: a fresh screen, and the menu closes', async () => {
  await render(<EmployeeScreen api={fakeApi()} {...quiet()} />)
  await fireEvent.press(screen.getByText('לעבור לרכב חשמלי'))
  await screen.findByText('הנטו עולה.')
  await openMenu()
  await fireEvent.press(screen.getByRole('button', { name: S.newConversation }))
  expect(await screen.findByText('לעבור לרכב חשמלי')).toBeTruthy() // the welcome again
  expect(screen.queryByText('הנטו עולה.')).toBeNull()
  expect(screen.queryByRole('button', { name: S.close })).toBeNull()
})

test('a conversation from the list opens it (read from the server); the profile item opens the profile', async () => {
  const api = fakeApi({ threads: jest.fn(async () => [
    { thread_id: 'a', title: 'ATTO 3', updated_at: '2026-10-20T10:00:00Z' },
    { thread_id: 'b', title: 'MG4', updated_at: '2026-10-19T10:00:00Z' },
  ]) })
  await render(<EmployeeScreen api={api} {...quiet()} />)
  await openMenu()
  await fireEvent.press(await screen.findByRole('button', { name: /MG4/ }))
  await waitFor(() => expect(api.restore).toHaveBeenCalledWith('b'))
  expect(screen.queryByRole('button', { name: S.close })).toBeNull()
  await openMenu()
  await fireEvent.press(screen.getByRole('button', { name: S.profile }))
  expect(await screen.findByText('הפרופיל שלי')).toBeTruthy()
})

test('logout is at the bottom of the menu', async () => {
  const onLogout = jest.fn()
  await render(<EmployeeScreen api={fakeApi()} onLogout={onLogout} {...quiet()} />)
  await openMenu()
  await fireEvent.press(screen.getByRole('button', { name: S.logout }))
  expect(onLogout).toHaveBeenCalled()
})

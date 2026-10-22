// The greeting with the first name, and the screen's texts in the employee's form of address
// (male / female / plural - plural until chosen). Errors: one wording for anyone, like the website.
import { render, screen, fireEvent, waitFor } from '@testing-library/react-native'
import EmployeeScreen from '@/employee/EmployeeScreen'
import Login from '@/components/Login'
import { streamChat } from '@/lib/api'
import { clearSession, setToken, setUnauthorizedHandler } from '@/lib/session'
import { fakeApi, quiet } from './fakes'
const chat = require('@/config/chat.json')

beforeEach(() => { clearSession(); setToken('t'); setUnauthorizedHandler(() => {}) })

const withAddress = (address, over = {}) => fakeApi({
  settings: jest.fn(async () => ({ theme: 'light', tone: 'professional', address })), ...over })

test('the greeting has the first name; without a name, the plain one', async () => {
  const { unmount } = await render(<EmployeeScreen api={fakeApi()} {...quiet()} />)
  expect(await screen.findByText('שלום נועה, אני כובי')).toBeTruthy()
  await unmount()
  await render(<EmployeeScreen api={fakeApi({ me: jest.fn(async () => ({ employee_id: 'E09', name: null })) })} {...quiet()} />)
  expect(screen.getByText(chat.welcome)).toBeTruthy()
})

test.each([
  ['male', 'מה תרצה לבדוק?', 'כתוב שאלה…', 'שלך'],
  ['female', 'מה תרצי לבדוק?', 'כתבי שאלה…', 'שלך'],
  ['plural', 'מה תרצו לבדוק?', 'כתבו שאלה…', 'שלכם'],
])('form of address %s: the welcome, the message box and the header speak that way', async (address, ask, placeholder, yours) => {
  await render(<EmployeeScreen api={withAddress(address)} {...quiet()} />)
  expect(await screen.findByText(ask)).toBeTruthy()
  expect(screen.getByLabelText('הודעה').props.placeholder).toBe(placeholder)
  expect(screen.getByText(new RegExp(`ברכב ${yours}$`))).toBeTruthy()
})

test('a new form of address saved in the profile applies at once', async () => {
  const api = withAddress('plural', {
    profile: jest.fn(async () => ({ employee_id: 'E01', fields: {}, sources: {}, group: null, address: 'plural' })),
    saveProfile: jest.fn(async () => ({ profile: { employee_id: 'E01', fields: {}, sources: {}, group: null, address: 'female' } })),
  })
  await render(<EmployeeScreen api={api} {...quiet()} />)
  await screen.findByText('מה תרצו לבדוק?')
  await fireEvent.press(screen.getByRole('button', { name: 'סרגל הצד' }))
  await fireEvent.press(await screen.findByRole('button', { name: 'פרופיל' }))
  await fireEvent.press(await screen.findByRole('radio', { name: 'נקבה' }))
  await fireEvent.press(screen.getByRole('button', { name: 'שמירה' }))
  await fireEvent.press(await screen.findByRole('button', { name: 'סגירת הפרופיל' }))
  await waitFor(() => expect(screen.getByText('מה תרצי לבדוק?')).toBeTruthy())
})

test('errors in one wording for anyone ("אפשר לנסות שוב"), never "נסו"', async () => {
  const events = []
  await streamChat({ message: 'x' }, (e, d) => events.push(d.message), jest.fn(async () => ({ ok: false, status: 429 })))
  await streamChat({ message: 'x' }, (e, d) => events.push(d.message), jest.fn(async () => { throw new Error('offline') }))
  expect(events).toEqual(['כובי עמוס כרגע. אפשר לנסות שוב בעוד רגע.', 'כובי לא מצליח להתחבר כרגע. אפשר לנסות שוב בעוד דקה.'])
  const api = { login: jest.fn(async () => { throw Object.assign(new Error(), { status: 401 }) }) }
  await render(<Login api={api} onLogin={() => {}} />)
  await fireEvent.changeText(screen.getByLabelText('קוד עובד'), '9')
  await fireEvent.press(screen.getByText('כניסה'))
  expect(await screen.findByText('הקוד לא נכון. אפשר לנסות שוב.')).toBeTruthy()
})

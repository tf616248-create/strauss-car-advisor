// The profile screen: every field to edit, the group read only, where each value came from, and "פנייה".
import { render, screen, fireEvent, waitFor } from '@testing-library/react-native'
import ProfileScreen from '@/employee/ProfileScreen'
import EmployeeScreen from '@/employee/EmployeeScreen'
import { clearSession, setToken } from '@/lib/session'
import { fakeApi, quiet } from './fakes'
const cfg = require('@/config/profile.json')
const T = cfg.texts

beforeEach(() => { clearSession(); setToken('t') })

const view = {
  employee_id: 'E01', group: 'ג', address: 'plural',
  fields: { occupation: 'מנהל/ת אזור מכירות', base: 14200, current_kind: 'car', current_car: 'TUCSON' },
  sources: { occupation: 'profile', base: 'payslip', current_car: 'chat' },
}

test('the fields, the group (by the occupation, read only), and where each value came from', async () => {
  const api = fakeApi({ profile: jest.fn(async () => view) })
  await render(<ProfileScreen api={api} onClose={() => {}} />)
  expect(await screen.findByDisplayValue('מנהל/ת אזור מכירות')).toBeTruthy()
  for (const f of cfg.fields.filter((x) => x.type !== 'kind')) expect(screen.getByLabelText(f.label)).toBeTruthy()
  expect(screen.getByDisplayValue('14200')).toBeTruthy()
  expect(screen.getByText('קבוצה ג (לפי העיסוק)')).toBeTruthy()
  expect(screen.getByText(T.sources.payslip)).toBeTruthy()
  expect(screen.getByText(T.sources.chat)).toBeTruthy()
  expect(screen.getByRole('radio', { name: T.kinds.car }).props.accessibilityState).toMatchObject({ checked: true })
})

test('saving sends only what changed (a number as a number, commas removed; an emptied field as null)', async () => {
  const api = fakeApi({ profile: jest.fn(async () => view), saveProfile: jest.fn(async () => ({ profile: { ...view, fields: { ...view.fields, base: 15500, current_car: null } } })) })
  await render(<ProfileScreen api={api} onClose={() => {}} />)
  await screen.findByDisplayValue('14200')
  await fireEvent.changeText(screen.getByLabelText(cfg.fields[1].label), '15,500')
  await fireEvent.changeText(screen.getByLabelText('הרכב של היום'), '')
  await fireEvent.press(screen.getByRole('button', { name: T.save }))
  await waitFor(() => expect(api.saveProfile).toHaveBeenCalledWith({ base: 15500, current_car: null }))
  expect(await screen.findByText(T.saved)).toBeTruthy()
})

test('"פנייה": three choices; a new one is saved with the profile', async () => {
  const api = fakeApi({ profile: jest.fn(async () => view), saveProfile: jest.fn(async () => ({ profile: { ...view, address: 'female' } })) })
  await render(<ProfileScreen api={api} onClose={() => {}} />)
  await screen.findByDisplayValue('14200')
  for (const label of Object.values(T.addresses)) expect(screen.getByRole('radio', { name: label })).toBeTruthy()
  await fireEvent.press(screen.getByRole('radio', { name: T.addresses.female }))
  await fireEvent.press(screen.getByRole('button', { name: T.save }))
  await waitFor(() => expect(api.saveProfile).toHaveBeenCalledWith({}, { address: 'female' }))
})

test('the server refuses a value: the reason next to the field, and a note for the screen reader', async () => {
  const api = fakeApi({ profile: jest.fn(async () => view), saveProfile: jest.fn(async () => ({ invalid: { base: { range: [0, 100000] }, occupation: { suggestions: ['מנהל/ת שיווק'] } } })) })
  await render(<ProfileScreen api={api} onClose={() => {}} />)
  await screen.findByDisplayValue('14200')
  await fireEvent.changeText(screen.getByLabelText(cfg.fields[1].label), '-5')
  await fireEvent.press(screen.getByRole('button', { name: T.save }))
  expect(await screen.findByText('צריך להיות בין 0 ל-100,000')).toBeTruthy()
  expect(screen.getByText('העיסוק לא נמצא. אולי: מנהל/ת שיווק')).toBeTruthy()
  expect(screen.getByText(T.fixErrors).props.accessibilityRole).toBe('alert')
})

test('it cannot load: says so; ✕ closes it', async () => {
  const onClose = jest.fn()
  await render(<ProfileScreen api={fakeApi({ profile: jest.fn(async () => { throw new Error('x') }) })} onClose={onClose} />)
  expect(await screen.findByText(T.loadError)).toBeTruthy()
  await fireEvent.press(screen.getByRole('button', { name: T.close }))
  expect(onClose).toHaveBeenCalled()
})

test('the link in the answer ("כאן") opens the profile', async () => {
  const api = fakeApi({ streamChat: jest.fn(async (_b, onEvent) => {
    onEvent('thread', { thread_id: 'th1' })
    onEvent('token', { text: 'הכי מהיר למלא אותם בפרופיל, [כאן](/profile).' })
    onEvent('done', {})
  }) })
  await render(<EmployeeScreen api={api} {...quiet()} />)
  await fireEvent.changeText(screen.getByLabelText('הודעה'), 'שאלה')
  await fireEvent.press(screen.getByText('שליחה'))
  await fireEvent.press(await screen.findByRole('link', { name: 'כאן – פתיחת הפרופיל' }))
  expect(await screen.findByText(T.title)).toBeTruthy()
})

// "התאמה אישית": the design (light, dark, system - light by default) and Kobi's tone, kept on the server.
import { render, screen, fireEvent, waitFor } from '@testing-library/react-native'
import * as RN from 'react-native'
import EmployeeScreen from '@/employee/EmployeeScreen'
import { clearSession, setToken } from '@/lib/session'
import { fakeApi, quiet } from './fakes'
const T = require('@/config/settings.json').texts
const S = require('@/config/sidebar.json').texts

beforeEach(() => { clearSession(); setToken('t') })
afterEach(() => jest.restoreAllMocks())

const LIGHT_BG = '#FFFFFF'
const DARK_BG = '#121417'
const rootBg = () => screen.getByTestId('employee-root').props.style.backgroundColor

async function openCustomize() {
  await fireEvent.press(screen.getByRole('button', { name: S.toggle }))
  await fireEvent.press(await screen.findByRole('button', { name: S.customize }))
  return screen.findByText(T.title)
}

test('light by default, even when the phone is dark', async () => {
  jest.spyOn(RN, 'useColorScheme').mockReturnValue('dark')
  await render(<EmployeeScreen api={fakeApi({ settings: jest.fn(async () => ({ theme: 'light', tone: 'professional' })) })} {...quiet()} />)
  expect(rootBg()).toBe(LIGHT_BG)
})

test('the saved design comes from the server', async () => {
  await render(<EmployeeScreen api={fakeApi({ settings: jest.fn(async () => ({ theme: 'dark', tone: 'professional' })) })} {...quiet()} />)
  await waitFor(() => expect(rootBg()).toBe(DARK_BG))
})

test('choosing dark: at once, saved, "נשמר"; "system" follows the phone', async () => {
  const api = fakeApi()
  await render(<EmployeeScreen api={api} {...quiet()} />)
  await openCustomize()
  expect(screen.getByRole('radio', { name: T.themes.light }).props.accessibilityState).toMatchObject({ checked: true })
  await fireEvent.press(screen.getByRole('radio', { name: T.themes.dark }))
  await waitFor(() => expect(api.saveSettings).toHaveBeenCalledWith({ theme: 'dark' }))
  expect(await screen.findByText(T.saved)).toBeTruthy()
  expect(rootBg()).toBe(DARK_BG)
  jest.spyOn(RN, 'useColorScheme').mockReturnValue('light')
  await fireEvent.press(screen.getByRole('radio', { name: T.themes.system }))
  await waitFor(() => expect(rootBg()).toBe(LIGHT_BG))
})

test('the tone: three choices, with what it changes; saved on the server', async () => {
  const api = fakeApi()
  await render(<EmployeeScreen api={api} {...quiet()} />)
  await openCustomize()
  for (const label of Object.values(T.tones)) expect(screen.getByRole('radio', { name: label })).toBeTruthy()
  expect(screen.getByText(T.toneHint)).toBeTruthy()
  await fireEvent.press(screen.getByRole('radio', { name: T.tones.funny }))
  await waitFor(() => expect(api.saveSettings).toHaveBeenCalledWith({ tone: 'funny' }))
})

test('a save that fails goes back to what was there, and says so', async () => {
  const api = fakeApi({ saveSettings: jest.fn(async () => { throw new Error('x') }) })
  await render(<EmployeeScreen api={api} {...quiet()} />)
  await openCustomize()
  await fireEvent.press(screen.getByRole('radio', { name: T.themes.dark }))
  expect(await screen.findByText(T.saveError)).toBeTruthy()
  expect(screen.getByRole('radio', { name: T.themes.light }).props.accessibilityState).toMatchObject({ checked: true })
  expect(rootBg()).toBe(LIGHT_BG)
  await fireEvent.press(screen.getByRole('button', { name: T.close }))
  await waitFor(() => expect(screen.queryByText(T.title)).toBeNull())
})

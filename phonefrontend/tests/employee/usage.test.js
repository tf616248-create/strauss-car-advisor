// This week's usage: a bar in the side menu with "נשארו לך כ-X שיחות השבוע", read again after every
// answer; and at 0 the server's fixed message (with its address) instead of an answer from Kobi.
import { render, screen, fireEvent, waitFor } from '@testing-library/react-native'
import * as RN from 'react-native'
import EmployeeScreen from '@/employee/EmployeeScreen'
import { usageSentence } from '@/components/UsageBar'
import { clearSession, setToken } from '@/lib/session'
import { fakeApi, quiet } from './fakes'
const U = require('@/config/usage.json').texts
const S = require('@/config/sidebar.json').texts

beforeEach(() => { clearSession(); setToken('t') })
afterEach(() => jest.restoreAllMocks())

test('the sentence: about X left, about one, less than one, none (blocked), or checking', () => {
  expect(usageSentence(null)).toBe(U.loading)
  expect(usageSentence({ conversations_left: 7, blocked: false })).toBe('נשארו לך כ-7 שיחות השבוע')
  expect(usageSentence({ conversations_left: 1, blocked: false })).toBe(U.leftOne)
  expect(usageSentence({ conversations_left: 0, blocked: false })).toBe(U.lessThanOne)
  expect(usageSentence({ conversations_left: 0, blocked: true })).toBe(U.none)
})

test('in the side menu: a progress bar (how much is used) with the sentence, and when it resets', async () => {
  const api = fakeApi({ usage: jest.fn(async () => ({ used: 30, limit: 100, remaining: 70, conversations_left: 7, blocked: false })) })
  await render(<EmployeeScreen api={api} {...quiet()} />)
  await fireEvent.press(screen.getByRole('button', { name: S.toggle }))
  const bar = await screen.findByRole('progressbar')
  expect(bar.props.accessibilityLabel).toBe(U.barLabel)
  await waitFor(() => expect(screen.getByRole('progressbar').props.accessibilityValue).toEqual({ min: 0, max: 100, now: 30, text: 'נשארו לך כ-7 שיחות השבוע' }))
  expect(screen.getByText(U.resets)).toBeTruthy()
})

test('read again after every answer', async () => {
  const api = fakeApi()
  await render(<EmployeeScreen api={api} {...quiet()} />)
  await waitFor(() => expect(api.usage).toHaveBeenCalledTimes(1))
  await fireEvent.press(screen.getByText('לעבור לרכב חשמלי'))
  await screen.findByText('הנטו עולה.')
  await waitFor(() => expect(api.usage).toHaveBeenCalledTimes(2))
})

test('at 0: the server\'s message instead of an answer, its address opens the mail app, and it is spoken', async () => {
  const announce = jest.spyOn(RN.AccessibilityInfo, 'announceForAccessibility').mockImplementation(() => {})
  const open = jest.spyOn(RN.Linking, 'openURL').mockResolvedValue(true)
  const message = 'לשיחות נוספות אפשר לפנות ל-support@strauss-in.com'
  const api = fakeApi({ streamChat: jest.fn(async (_b, onEvent) => {
    onEvent('limit', { message, email: 'support@strauss-in.com' })
    onEvent('done', {})
  }) })
  await render(<EmployeeScreen api={api} {...quiet()} />)
  await fireEvent.press(screen.getByText('לעבור לרכב חשמלי'))
  const link = await screen.findByRole('link', { name: 'support@strauss-in.com' })
  expect(screen.getByText(/לשיחות נוספות אפשר לפנות ל-/)).toBeTruthy()
  expect(screen.queryByText('כובי · בוט')).toBeNull()
  await fireEvent.press(link)
  expect(open).toHaveBeenCalledWith('mailto:support@strauss-in.com')
  await waitFor(() => expect(announce).toHaveBeenCalledWith(expect.stringContaining(message)))
})

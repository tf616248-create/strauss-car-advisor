// The opening scene: the video with the slogan by its time, "דלג", 🔇/🔊, stopping on the last frame and the
// login card; with reduced motion, a picture instead of the video. (expo-video is a fake here: tests/setup.js)
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react-native'
import * as RN from 'react-native'
import Intro from '@/components/Intro'
import EmployeeApp from '@/employee/EmployeeApp'
import { clearSession } from '@/lib/session'
import { fakeApi } from '../employee/fakes'
const cfg = require('@/config/intro.json')
const T = cfg.texts
const video = require('expo-video')
// the video and the picture are hidden from a screen reader (decoration): found with hidden elements
const HIDDEN = { includeHiddenElements: true }

beforeEach(() => { clearSession(); video.__reset() })
afterEach(() => { jest.restoreAllMocks(); jest.useRealTimers() })

const shown = (text) => screen.getByText(text).props.style.some?.((s) => s?.opacity === 1) ?? false
const at = async (seconds) => act(async () => { video.__emit('timeUpdate', { currentTime: seconds }) })
const noReduce = () => jest.spyOn(RN.AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(false)

test('the video plays muted once; the slogan by its time, then the card; at the end it stops on the frame', async () => {
  noReduce()
  await render(<Intro api={fakeApi()} onEnter={() => {}} />)
  expect(await screen.findByTestId('intro-video', HIDDEN)).toBeTruthy()
  expect(video.__player.muted).toBe(true)
  expect(video.__player.loop).toBe(false)
  expect(video.__player.play).toHaveBeenCalled()
  expect(screen.getByRole('header')).toBeTruthy() // the slogan is the screen's heading all along
  expect(shown(T.slogan)).toBe(false)
  await at(cfg.times.slogan + 0.1)
  expect(shown(T.slogan)).toBe(true)
  expect(shown(T.answer)).toBe(false)
  await at(cfg.times.answer + 0.1)
  expect(shown(T.answer)).toBe(true)
  expect(screen.queryByLabelText('קוד עובד')).toBeNull()
  await at(cfg.times.card + 0.1)
  expect(screen.getByLabelText('קוד עובד')).toBeTruthy()
  await at(cfg.times.end)
  expect(video.__player.pause).toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: T.skipLabel })).toBeNull()
})

test('"דלג" jumps to the end: the picture, the slogan and the card at once', async () => {
  noReduce()
  await render(<Intro api={fakeApi()} onEnter={() => {}} />)
  await fireEvent.press(await screen.findByRole('button', { name: T.skipLabel }))
  expect(screen.getByTestId('intro-poster', HIDDEN)).toBeTruthy()
  expect(shown(T.slogan) && shown(T.answer)).toBe(true)
  expect(screen.getByLabelText('קוד עובד')).toBeTruthy()
})

test('the sound: muted by default; 🔊 turns it on', async () => {
  noReduce()
  await render(<Intro api={fakeApi()} onEnter={() => {}} />)
  const sound = await screen.findByRole('button', { name: T.soundOn })
  await fireEvent.press(sound)
  expect(video.__player.muted).toBe(false)
  expect(screen.getByRole('button', { name: T.soundOff })).toBeTruthy()
})

test('reduced motion on the phone: a picture instead of the video, everything at once', async () => {
  jest.spyOn(RN.AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true)
  await render(<Intro api={fakeApi()} onEnter={() => {}} />)
  expect(await screen.findByTestId('intro-poster', HIDDEN)).toBeTruthy()
  expect(screen.queryByTestId('intro-video', HIDDEN)).toBeNull()
  expect(screen.getByLabelText('קוד עובד')).toBeTruthy()
})

test('a video that does not start playing in time (or fails): the picture', async () => {
  noReduce()
  jest.useFakeTimers()
  await render(<Intro api={fakeApi()} onEnter={() => {}} />)
  await act(async () => { jest.advanceTimersByTime(cfg.loadTimeoutSeconds * 1000 + 50) })
  expect(screen.getByTestId('intro-poster', HIDDEN)).toBeTruthy()
})

test('the app starts with the scene; the card logs in, then the chat', async () => {
  noReduce()
  const api = fakeApi({ login: jest.fn(async () => ({ token: 'tok' })) })
  await render(<EmployeeApp api={api} subscribe={() => () => {}} notifier={{ beep() {}, setUnread() {} }} />)
  await fireEvent.press(await screen.findByRole('button', { name: T.skipLabel }))
  await fireEvent.changeText(screen.getByLabelText('קוד עובד'), '1111')
  await fireEvent.press(screen.getByText('כניסה'))
  await waitFor(() => expect(screen.getByLabelText('הודעה')).toBeTruthy())
})

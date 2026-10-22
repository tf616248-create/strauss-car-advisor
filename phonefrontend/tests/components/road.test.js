// The car on the road drives on its own while a step runs, slowly, and never shows more than really
// happened: at most 80% of the way to the next stop until that step ends (like the website's Road).
import { render, screen, act } from '@testing-library/react-native'
import * as RN from 'react-native'
import Road, { drive, legOf, SHARE, SLOTS, START, FINISH } from '@/components/Road'

afterEach(() => { jest.restoreAllMocks(); jest.useRealTimers() })
const HIDDEN = { includeHiddenElements: true } // the scene is hidden from a screen reader; the status line speaks
const carAt = () => screen.getByTestId('road-car', HIDDEN).props.position
const motion = () => jest.spyOn(RN.AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(false)
async function frames(ms) { await act(async () => { jest.advanceTimersByTime(ms) }) }

test('a leg: from the stop really reached, up to 80% of the way to the next; never backwards', () => {
  expect(legOf('driving', 0)).toEqual({ at: START, upTo: START + SHARE * (SLOTS[0] - START) })
  expect(legOf('driving', 3)).toEqual({ at: SLOTS[2], upTo: SLOTS[2] + SHARE * (FINISH - SLOTS[2]) })
  const leg = legOf('driving', 1)
  let pos = leg.at
  for (let i = 0; i < 2000; i += 1) pos = drive(pos, leg, 0.05)
  expect(pos).toBeLessThanOrEqual(leg.upTo)
  expect(drive(70, legOf('waiting', 2), 0.1)).toBe(70) // already past the light (62): it stays, never back
})

test('the car moves before any tool is called, slowing down, and stays under the cap', async () => {
  motion()
  jest.useFakeTimers()
  await render(<Road phase="driving" stops={[]} />)
  await frames(50)
  const start = carAt()
  await frames(1000)
  const after1 = carAt()
  expect(after1).toBeGreaterThan(start)
  await frames(1000)
  expect(carAt() - after1).toBeLessThan(after1 - start)
  await frames(60000)
  expect(carAt()).toBeLessThanOrEqual(START + SHARE * (SLOTS[0] - START))
})

test('when a step ends the car reaches its stop, then drives on toward the next', async () => {
  motion()
  jest.useFakeTimers()
  const { rerender } = await render(<Road phase="driving" stops={[]} />)
  await frames(3000)
  await rerender(<Road phase="driving" stops={[{ tool: 'check_eligibility', label: 'כובי בודק זכאות…' }]} />)
  await frames(1500)
  expect(carAt()).toBeGreaterThanOrEqual(SLOTS[0])
  await frames(60000)
  expect(carAt()).toBeLessThanOrEqual(SLOTS[0] + SHARE * (SLOTS[1] - SLOTS[0]))
})

test('reduced motion: no driving - the car stands at the stop of the current step', async () => {
  jest.spyOn(RN.AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true)
  jest.useFakeTimers()
  const { rerender } = await render(<Road phase="driving" stops={[]} />)
  await frames(5000)
  expect(carAt()).toBe(START)
  await rerender(<Road phase="driving" stops={[{ tool: 'calculate', label: 'כובי מחשב נטו…' }]} />)
  await frames(5000)
  expect(carAt()).toBe(SLOTS[0])
})

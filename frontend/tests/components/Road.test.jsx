import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Road, { FINISH, SHARE, SLOTS, START, stopName } from '@/components/Road'

const stop = (tool, label) => ({ tool, label })
const LOOKUP = stop('lookup_vehicle', 'כובי מחפש את הרכב…')
const ELIG = stop('check_eligibility', 'כובי בודק זכאות…')
const CALC = stop('calculate', 'כובי מחשב נטו…')

const stopsIn = (container) => [...container.querySelectorAll('.stop')]

describe('Road', () => {
  it('names a stop by the tool really called; an unknown tool uses the server label', () => {
    expect(stopName(ELIG)).toBe('זכאות')
    expect(stopName(stop('ask_rep', 'כובי שלח שאלה לנציג התחבורה ⏳'))).toBe('שאלה לנציג')
    expect(stopName(stop('something_new', 'בודק משהו…'))).toBe('בודק משהו')
  })

  it('before any tool runs there are no stops, only the start and the finish', () => {
    const { container } = render(<Road phase="driving" stops={[]} />)
    expect(screen.getByRole('status')).toHaveTextContent('כובי חושב…')
    expect(stopsIn(container)).toHaveLength(0)
    expect(container.querySelector('.finish--done')).toBeNull()
  })

  it('adds a stop only for the tools called in this answer, in the order they ran', () => {
    // the bot only re-checks eligibility: no value-of-use stop appears
    const { container } = render(<Road phase="driving" stops={[ELIG]} label="כובי בודק זכאות…" />)
    expect(screen.getByRole('status')).toHaveTextContent('כובי בודק זכאות…')
    expect(stopsIn(container).map((s) => s.textContent)).toEqual(['זכאות'])
    expect(stopsIn(container)[0]).toHaveClass('stop--active')
  })

  it('earlier stops are done and the running one is active', () => {
    const { container } = render(<Road phase="driving" stops={[LOOKUP, ELIG]} />)
    const [first, second] = stopsIn(container)
    expect(first).toHaveClass('stop--done')
    expect(second).toHaveClass('stop--active')
  })

  it('keeps the road readable: at most three stops, the latest ones', () => {
    const { container } = render(<Road phase="driving" stops={[LOOKUP, ELIG, LOOKUP, CALC]} />)
    expect(stopsIn(container).map((s) => s.textContent)).toEqual(['זכאות', 'איתור רכב', 'חישוב נטו'])
  })

  it('reaches the finish only when the answer has a real result', () => {
    const { container } = render(<Road phase="arrived" stops={[LOOKUP, CALC]} />)
    expect(screen.getByRole('status')).toHaveTextContent('התשובה מוכנה')
    expect(container.querySelector('.finish--done')).not.toBeNull()
    expect(stopsIn(container).every((s) => s.classList.contains('stop--done'))).toBe(true)
  })

  it('stops at the light while waiting for the rep', () => {
    const { container } = render(<Road phase="waiting" stops={[LOOKUP, stop('ask_rep', 'כובי שלח שאלה לנציג התחבורה ⏳')]} />)
    expect(screen.getByRole('status')).toHaveTextContent('כובי שלח שאלה לנציג התחבורה ⏳')
    expect(container.querySelector('.road__light')).not.toBeNull()
    expect(container.querySelector('.finish--done')).toBeNull()
  })

  it('at the start line the car stands fully inside the road, with its note anchored to it', () => {
    const { container } = render(<Road phase="driving" stops={[]} />)
    const car = container.querySelector('.road__car')
    expect(car).toHaveClass('road__car--start') // no half-car shift past the right edge (styles.css)
  })

  it('leaves the start line once a stop is reached', () => {
    const { container } = render(<Road phase="driving" stops={[ELIG]} label="כובי בודק זכאות…" />)
    expect(container.querySelector('.road__car')).not.toHaveClass('road__car--start')
  })
})

// --- the car drives on its own while a step runs, and never shows more than really happened ---

describe('Road: the car keeps driving', () => {
  const carAt = (container) => parseFloat(container.querySelector('.road__car').style.right)
  const isMoving = (container) => container.querySelector('.road__car').classList.contains('road__car--moving')
  const frames = (ms) => act(() => { vi.advanceTimersByTime(ms) })

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['requestAnimationFrame', 'cancelAnimationFrame', 'setTimeout', 'clearTimeout', 'performance', 'Date'] })
  })
  afterEach(() => {
    vi.useRealTimers()
    delete window.matchMedia
  })

  it('moves before any tool is called, slowing down, and stops short of the first stop (80% of the way)', () => {
    const { container } = render(<Road phase="driving" stops={[]} />)
    const start = carAt(container)
    frames(1000)
    const after1s = carAt(container)
    expect(after1s).toBeGreaterThan(start)
    expect(isMoving(container)).toBe(true)
    frames(1000)
    expect(carAt(container) - after1s).toBeLessThan(after1s - start) // slower as it gets closer
    frames(120000)
    expect(carAt(container)).toBeLessThanOrEqual(START + SHARE * (SLOTS[0] - START))
  })

  it('the shown progress never passes the real one: sampled all along, the car stays under the cap', () => {
    const { container } = render(<Road phase="driving" stops={[]} />)
    for (let i = 0; i < 300; i += 1) {
      frames(100)
      expect(carAt(container)).toBeLessThanOrEqual(START + SHARE * (SLOTS[0] - START))
    }
  })

  it('when a step really ends, it catches up to that stop, then drives on slowly toward the next', () => {
    const { container, rerender } = render(<Road phase="driving" stops={[]} />)
    frames(3000)
    rerender(<Road phase="driving" stops={[ELIG]} label="כובי בודק זכאות…" />)
    frames(1500)
    expect(carAt(container)).toBeGreaterThanOrEqual(SLOTS[0])
    expect(isMoving(container)).toBe(true)
    frames(120000)
    expect(carAt(container)).toBeLessThanOrEqual(SLOTS[0] + SHARE * (SLOTS[1] - SLOTS[0]))
  })

  it('after the last stop it heads for the finish, but reaches it only with a real result', () => {
    const { container, rerender } = render(<Road phase="driving" stops={[LOOKUP, ELIG, CALC]} />)
    frames(120000)
    expect(carAt(container)).toBeLessThan(FINISH)
    rerender(<Road phase="arrived" stops={[LOOKUP, ELIG, CALC]} />)
    frames(3000)
    expect(carAt(container)).toBeGreaterThan(FINISH)
  })

  it('stopped (waiting for the rep): no wheels turning, no bobbing, and it does not move', () => {
    const { container } = render(<Road phase="waiting" stops={[LOOKUP, stop('ask_rep', 'כובי שלח שאלה לנציג התחבורה ⏳')]} />)
    frames(3000)
    const at = carAt(container)
    frames(3000)
    expect(carAt(container)).toBe(at)
    expect(isMoving(container)).toBe(false)
  })

  it('reduced motion: no animation - the car stands at the stop of the current step', () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener() {}, removeEventListener() {} })
    const { container, rerender } = render(<Road phase="driving" stops={[]} />)
    frames(5000)
    expect(carAt(container)).toBe(START)
    expect(isMoving(container)).toBe(false)
    rerender(<Road phase="driving" stops={[ELIG]} label="כובי בודק זכאות…" />)
    expect(carAt(container)).toBe(SLOTS[0])
    frames(5000)
    expect(carAt(container)).toBe(SLOTS[0])
  })

  it('the screen reader still hears the status only; the moving scene is hidden from it', () => {
    const { container } = render(<Road phase="driving" stops={[]} />)
    frames(2000)
    expect(screen.getByRole('status')).toHaveTextContent('כובי חושב…')
    expect(container.querySelector('.road__scene')).toHaveAttribute('aria-hidden', 'true')
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Road, { stopName } from './Road'

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

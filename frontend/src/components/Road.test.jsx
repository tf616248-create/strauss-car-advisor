import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Road, { stationIndex } from './Road'

describe('Road', () => {
  it('maps the real server step labels to stations, in tool order', () => {
    expect(stationIndex('מחפש את הרכב…')).toBe(0)
    expect(stationIndex('בודק זכאות…')).toBe(1)
    expect(stationIndex('מחשב נטו…')).toBe(2)
    expect(stationIndex('משהו אחר')).toBe(-1)
  })

  it('announces the running step and lights the stations already passed', () => {
    const { container } = render(<Road phase="driving" reached={1} label="בודק זכאות…" />)
    expect(screen.getByRole('status')).toHaveTextContent('בודק זכאות…')
    expect(container.querySelectorAll('.station--done')).toHaveLength(2)
    expect(container.querySelectorAll('.station--active')).toHaveLength(1)
  })

  it('shows the yellow light while waiting for the rep', () => {
    const { container } = render(<Road phase="waiting" reached={1} />)
    expect(screen.getByRole('status')).toHaveTextContent('⏳ ממתין לנציג')
    expect(container.querySelector('.road__light')).not.toBeNull()
  })

  it('lights every station when the answer arrives', () => {
    const { container } = render(<Road phase="arrived" reached={2} />)
    expect(container.querySelectorAll('.station--done')).toHaveLength(3)
  })
})

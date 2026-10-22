// The comparison card while the rep confirms the catalog's participation: the calculation by the catalog,
// marked "ממתין לאישור" (the text comes from the server, in the card).
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import noa from '../fixtures/card-noa.json'
import CompareCard from '@/components/CompareCard'

const AWAITING = { fields: ['participation'], label: 'ממתין לאישור', note: 'החישוב לפי סכום ההשתתפות שבקטלוג, עד שהנציג יאשר אותו.' }
const awaiting = { ...noa, card: { ...noa.card, awaiting_confirmation: AWAITING } }

describe('the card awaiting the rep\'s confirmation', () => {
  it('marks the participation of the new car, and says the calculation is by the catalog', () => {
    render(<CompareCard result={awaiting} />)
    const row = screen.getByRole('row', { name: /השתתפות/ })
    const [, alt] = within(row).getAllByRole('cell') // the cells: today, the new car, the difference
    expect(alt).toHaveTextContent('⏳ ממתין לאישור')
    expect(screen.getByText(AWAITING.note, { exact: false })).toHaveTextContent(`⏳ ${AWAITING.note}`)
    expect(screen.getByRole('group', { name: 'הפרש בנטו, לחודש' })).toHaveTextContent(/\d/) // the number is shown
  })

  it('only the fields awaiting are marked, and today\'s column never', () => {
    render(<CompareCard result={awaiting} />)
    expect(screen.getAllByText('⏳ ממתין לאישור')).toHaveLength(1)
    const [today] = within(screen.getByRole('row', { name: /השתתפות/ })).getAllByRole('cell')
    expect(today).not.toHaveTextContent('ממתין')
  })

  it('without it (a confirmed or a catalog amount): no mark', () => {
    render(<CompareCard result={noa} />)
    expect(screen.queryByText(/ממתין לאישור/)).toBeNull()
  })
})

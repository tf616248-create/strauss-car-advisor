import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import noa from '../test-fixtures/card-noa.json'
import rachel from '../test-fixtures/card-rachel-waiting.json'
import CompareCard from './CompareCard'

const shekel = (n) => `${n.toLocaleString('he-IL')} ₪`

describe('CompareCard', () => {
  it('starts with "your data" and the source of each value', () => {
    render(<CompareCard result={noa} />)
    const yours = screen.getByRole('region', { name: 'הנתונים שלך' })
    expect(within(yours).getByText(shekel(18500))).toBeInTheDocument()
    expect(within(yours).getAllByText('עובד').length).toBeGreaterThan(0)
  })

  it('shows today vs. the alternative and the ready-made difference', () => {
    render(<CompareCard result={noa} />)
    const { today, alternative, diff } = noa.card
    expect(screen.getByRole('columnheader', { name: today.label })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: alternative.label })).toBeInTheDocument()
    const net = screen.getByRole('row', { name: /נטו משוער/ })
    expect(within(net).getByText(shekel(today.values.net.value))).toBeInTheDocument()
    expect(within(net).getByText(shekel(alternative.values.net.value))).toBeInTheDocument()
    expect(within(net).getByText(`+${shekel(diff.net)}`)).toBeInTheDocument()
  })

  it('shows the two-line explanation', () => {
    render(<CompareCard result={noa} />)
    for (const line of noa.card.explanation) expect(screen.getByText(line)).toBeInTheDocument()
  })

  it('marks fields waiting for the rep', () => {
    render(<CompareCard result={rachel} />)
    const net = screen.getByRole('row', { name: /נטו משוער/ })
    expect(within(net).getByText('⏳ ממתין לנציג')).toBeInTheDocument()
  })
})

// The comparison card: the importer link of the new car only (not today's), like the ranking card's.
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import noa from '../fixtures/card-noa.json'
import CompareCard from '@/components/CompareCard'

const withLinks = (today, alt) => ({ ...noa, card: { ...noa.card,
  today: { ...noa.card.today, importer_url: today }, alternative: { ...noa.card.alternative, importer_url: alt } } })

describe('the importer link in the comparison card', () => {
  it('the alternative: the same wording as the ranking card, a new window, and a screen reader is told', () => {
    render(<CompareCard result={withLinks(undefined, 'https://bydauto.co.il/x')} />)
    const link = screen.getByRole('link', { name: `למפרט המלא אצל היבואן ← ${noa.card.alternative.label} (נפתח בחלון חדש)` })
    expect(link).toHaveAttribute('href', 'https://bydauto.co.il/x')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.getAllByRole('link')).toHaveLength(1) // today's car has none
  })

  it('both cars in the catalog: one link only, to the new car - never to today\'s', () => {
    render(<CompareCard result={withLinks('https://t.example/', 'https://a.example/')} />)
    expect(screen.getAllByRole('link').map((a) => a.getAttribute('href'))).toEqual(['https://a.example/'])
    expect(screen.getByRole('link')).toHaveAccessibleName(expect.stringContaining(noa.card.alternative.label))
  })

  it('only today\'s car has a page: no link at all', () => {
    const { container } = render(<CompareCard result={withLinks('https://t.example/', undefined)} />)
    expect(container.querySelector('a, .card__importers')).toBeNull()
  })

  it('no catalog car: no link, and no empty or broken one', () => {
    const { container } = render(<CompareCard result={noa} />)
    expect(container.querySelector('a, .card__importers')).toBeNull()
  })
})

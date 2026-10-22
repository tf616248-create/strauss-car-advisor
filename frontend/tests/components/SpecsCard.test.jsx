import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import dolphin from '../fixtures/card-specs.json'
import santaFe from '../fixtures/card-specs-none.json'
import SpecsCard from '@/components/SpecsCard'

const day = (iso) => new Date(iso).toLocaleDateString('he-IL')

describe('SpecsCard (car_specs)', () => {
  it('names the car, with spec tags', () => {
    render(<SpecsCard result={dolphin} />)
    const card = screen.getByRole('region', { name: 'מפרט הרכב' })
    expect(within(card).getByRole('heading', { name: 'BYD DOLPHIN' })).toBeInTheDocument()
    const tags = within(within(card).getByRole('list', { name: 'מפרט עיקרי' })).getAllByRole('listitem')
      .map((li) => li.textContent)
    expect(tags).toContain(`צריכה: ${dolphin.card.specs.electric_consumption.value} Wh/km`)
  })

  it('marks provisional data', () => {
    render(<SpecsCard result={dolphin} />)
    expect(screen.getAllByText('נתון ראשוני').length).toBeGreaterThan(0)
  })

  it('the source line and the importer button', () => {
    render(<SpecsCard result={dolphin} />)
    const [mot, eea] = dolphin.card.sources
    expect(screen.getByText(`מקור: משרד התחבורה, עודכן ${day(mot.fetched_at)} · EEA, עודכן ${day(eea.fetched_at)}`))
      .toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'למפרט המלא אצל היבואן ←' }))
      .toHaveAttribute('href', dolphin.card.importer_url)
  })

  it('no official data: says so, and still links to the importer', () => {
    render(<SpecsCard result={santaFe} />)
    expect(screen.getByText('אין נתון רשמי')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'מפרט עיקרי' })).toBeNull()
    expect(screen.queryByText(/^מקור:/)).toBeNull()
    expect(screen.getByRole('link', { name: 'למפרט המלא אצל היבואן ←' }))
      .toHaveAttribute('href', santaFe.card.importer_url)
  })
})

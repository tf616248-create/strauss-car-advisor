import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ranking from '../test-fixtures/card-ranking.json'
import RankingCard from './RankingCard'

const shekel = (n) => `${n.toLocaleString('he-IL')} ₪`
const day = (iso) => new Date(iso).toLocaleDateString('he-IL')

// the same card with one change, without touching the shared fixture
function withChange(change) {
  const result = structuredClone(ranking)
  change(result.card)
  return result
}

describe('RankingCard', () => {
  it('says what it sorted by, and shows 3 cars in order', () => {
    render(<RankingCard result={ranking} />)
    expect(screen.getByRole('heading', { name: 'סידרתי לפי: קבוצת זיהום' })).toBeInTheDocument()
    const cars = screen.getAllByRole('article').map((a) => within(a).getByRole('heading').textContent)
    expect(cars).toHaveLength(3)
    expect(cars).toEqual(ranking.card.options.map((o) => `${o.rank}. ${o.car}`))
  })

  it("shows each car's net and the change from today", () => {
    render(<RankingCard result={ranking} />)
    const [first] = screen.getAllByRole('article')
    const o = ranking.card.options[0]
    expect(within(first).getByText(shekel(o.net))).toBeInTheDocument()
    const d = o.diff.net
    expect(within(first).getByText(`${d > 0 ? '+' : '−'}${shekel(Math.abs(d))}`)).toBeInTheDocument()
  })

  it('shows spec tags: seats, body type, safety score, consumption', () => {
    render(<RankingCard result={ranking} />)
    const [first] = screen.getAllByRole('article')
    const { specs } = ranking.card.options[0]
    const tags = within(within(first).getByRole('list', { name: 'מפרט עיקרי' })).getAllByRole('listitem')
      .map((li) => li.textContent)
    expect(tags).toContain(`מושבים: ${specs.mispar_moshavim.value}`)
    expect(tags).toContain(`מרכב: ${specs.merkav.value}`)
    expect(tags).toContain(`ניקוד בטיחות: ${specs.nikud_betihut.value}`)
    const use = specs.electric_consumption // one value, or a range across versions
    expect(tags).toContain(`צריכה: ${'value' in use ? use.value : `${use.min}–${use.max}`} Wh/km`)
  })

  it('a small source line with the update date, and EEA when there is one', () => {
    render(<RankingCard result={ranking} />)
    const [first] = screen.getAllByRole('article')
    const [mot, eea] = ranking.card.options[0].sources
    expect(within(first).getByText(
      `מקור: משרד התחבורה, עודכן ${day(mot.fetched_at)} · EEA, עודכן ${day(eea.fetched_at)}`,
    )).toBeInTheDocument()
  })

  it('a button to the full specs at the importer', () => {
    render(<RankingCard result={ranking} />)
    const [first] = screen.getAllByRole('article')
    const link = within(first).getByRole('link', { name: 'למפרט המלא אצל היבואן ←' })
    expect(link).toHaveAttribute('href', ranking.card.options[0].importer_url)
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noreferrer'))
  })

  it('a spec that varies by trim is shown as a range', () => {
    render(<RankingCard result={withChange((card) => {
      card.options[0].specs.mispar_moshavim = { ...card.options[0].specs.mispar_moshavim, value: undefined,
        min: 5, max: 7, varies_by_trim: true }
      delete card.options[0].specs.mispar_moshavim.value
    })} />)
    const [first] = screen.getAllByRole('article')
    expect(within(first).getByText('מושבים: 5–7')).toBeInTheDocument()
    expect(within(first).getAllByText(/משתנה לפי גימור/).length).toBeGreaterThan(0)
  })

  it('an EEA range is a range of versions', () => {
    render(<RankingCard result={ranking} />)
    const [first] = screen.getAllByRole('article') // MG4: consumption differs between versions
    expect(within(first).getAllByText('טווח גרסאות').length).toBeGreaterThan(0)
  })

  it('cars waiting for the rep get their own row below, with "⏳ ממתין לנציג"', () => {
    render(<RankingCard result={withChange((card) => {
      card.needs_rep = [{ car: 'ATTO 3', fields: ['participation'] }]
    })} />)
    const waiting = screen.getByRole('group', { name: 'ממתינים לנציג' })
    expect(within(waiting).getByText('ATTO 3')).toBeInTheDocument()
    expect(within(waiting).getByText('⏳ ממתין לנציג')).toBeInTheDocument()
    expect(screen.getAllByRole('article').map((a) => a.textContent).join()).not.toContain('ATTO 3')
  })

  it('no waiting row when nobody waits', () => {
    render(<RankingCard result={ranking} />)
    expect(screen.queryByRole('group', { name: 'ממתינים לנציג' })).toBeNull()
  })

  it('electric cars: "no tailpipe emissions", not a pollution group', () => {
    render(<RankingCard result={ranking} />)
    expect(screen.getAllByText('ללא פליטות מהמפלט').length).toBe(3)
  })

  it('says when the net decided between equal cars', () => {
    render(<RankingCard result={ranking} />)
    expect(screen.getAllByText('שווים בקבוצת זיהום, סודרו לפי נטו').length).toBe(3)
  })

  it('keeps the full specs, folded', () => {
    render(<RankingCard result={ranking} />)
    const [first] = screen.getAllByRole('article')
    for (const item of Object.values(ranking.card.options[0].specs)) {
      expect(within(first).getAllByText(item.label).length).toBeGreaterThan(0)
    }
  })
})

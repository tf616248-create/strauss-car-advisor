import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ranking from '../test-fixtures/card-ranking.json'
import RankingCard from './RankingCard'

const shekel = (n) => `${n.toLocaleString('he-IL')} ₪`

describe('RankingCard', () => {
  it('says what it sorted by, and lists the cars in order', () => {
    render(<RankingCard result={ranking} />)
    expect(screen.getByRole('heading', { name: /סידרתי לפי קבוצת זיהום/ })).toBeInTheDocument()
    const cars = screen.getAllByRole('article').map((a) => within(a).getByRole('heading').textContent)
    expect(cars).toEqual(ranking.card.options.map((o) => `${o.rank}. ${o.car}`))
  })

  it('shows each car\'s net and the change from today', () => {
    render(<RankingCard result={ranking} />)
    const [first] = screen.getAllByRole('article')
    const o = ranking.card.options[0]
    expect(within(first).getByText(shekel(o.net))).toBeInTheDocument()
    const d = o.diff.net
    expect(within(first).getByText(`${d > 0 ? '+' : '−'}${shekel(Math.abs(d))}`)).toBeInTheDocument()
  })

  it('shows the full specs with their source, and the importer link', () => {
    render(<RankingCard result={ranking} />)
    const [first] = screen.getAllByRole('article')
    const specs = ranking.card.options[0].specs
    for (const item of Object.values(specs)) expect(within(first).getAllByText(item.label).length).toBeGreaterThan(0)
    expect(within(first).getAllByText(/משרד התחבורה/).length).toBeGreaterThan(0)
    expect(within(first).getByRole('link', { name: 'המפרט אצל היבואן' }))
      .toHaveAttribute('href', ranking.card.options[0].importer_url)
  })

  it('electric cars: "no tailpipe emissions", not a pollution group', () => {
    render(<RankingCard result={ranking} />)
    expect(screen.getAllByText('ללא פליטות מהמפלט').length).toBe(3)
  })

  it('says when the net decided between equal cars', () => {
    render(<RankingCard result={ranking} />)
    expect(screen.getAllByText('שווים בקבוצת זיהום, סודרו לפי נטו').length).toBe(3)
  })
})

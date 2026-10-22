// The cards: built on the server, the phone only formats them (real cards from the server, test-fixtures).
import { render, screen, fireEvent } from '@testing-library/react-native'
import CompareCard from '@/components/CompareCard'
import RankingCard from '@/components/RankingCard'
import SpecsCard from '@/components/SpecsCard'
import noa from '../fixtures/card-noa.json'
import rachel from '../fixtures/card-rachel-waiting.json'
import ranking from '../fixtures/card-ranking.json'
import specs from '../fixtures/card-specs.json'
import specsNone from '../fixtures/card-specs-none.json'

const has = (re) => expect(screen.queryAllByText(re).length).toBeGreaterThan(0)

test('comparison: your data, today vs the alternative, the net difference and the explanation', async () => {
  await render(<CompareCard result={noa} />)
  has('הנתונים שלך')
  has(/18,500/)
  has('COROLLA CROSS (2025)'); has('ATTO 3 (2025)')
  has(/\+661 ₪/)
  has('הנטו המשוער עולה ב-661 ₪ בחודש.')
  has(/טעות באחד הנתונים/)
})

test('comparison awaiting the rep\'s confirmation: calculated by the catalog, the participation marked', async () => {
  const awaiting = { fields: ['participation'], label: 'ממתין לאישור', note: 'החישוב לפי סכום ההשתתפות שבקטלוג, עד שהנציג יאשר אותו.' }
  await render(<CompareCard result={{ ...noa, card: { ...noa.card, awaiting_confirmation: awaiting } }} />)
  expect(screen.getAllByText('⏳ ממתין לאישור')).toHaveLength(1)
  has(/החישוב לפי סכום ההשתתפות שבקטלוג/)
  has(/\+661 ₪/) // the number is shown
})

test('comparison without a confirmation pending: no mark', async () => {
  await render(<CompareCard result={noa} />)
  expect(screen.queryAllByText(/ממתין לאישור/)).toHaveLength(0)
})

test('comparison waiting for the rep: the hourglass, no net number', async () => {
  await render(<CompareCard result={rachel} />)
  has(/ממתין לנציג/)
})

test('ranking: sorted by, three cars with net, the full specs folded until opened', async () => {
  await render(<RankingCard result={ranking} />)
  has(`סידרתי לפי: ${ranking.card.sort_label}`)
  for (const o of ranking.card.options) has(`${o.rank}. ${o.car}`)
  has(/למפרט המלא אצל היבואן/)
  const first = Object.values(ranking.card.options[0].specs)[0].label
  const before = screen.queryAllByText(first).length
  await fireEvent.press(screen.getAllByText('כל המפרט')[0])
  expect(screen.queryAllByText(first).length).toBeGreaterThan(before)
})

test('specs: the car and its sources; no official data says so', async () => {
  await render(<SpecsCard result={specs} />)
  has(specs.card.car)
  has(/^מקור:/)
  await render(<SpecsCard result={specsNone} />)
  has(specsNone.card.message)
})

// the importer link in the comparison card: the new car only, like the website (not today's car, not on the rep screen)
test('comparison: one importer link, for the new car, named for it; importerLink={false} leaves it out', async () => {
  const { Linking } = require('react-native')
  const open = jest.spyOn(Linking, 'openURL').mockResolvedValue(true)
  const withLinks = { ...noa, card: { ...noa.card, today: { ...noa.card.today, importer_url: 'https://t.example/' },
    alternative: { ...noa.card.alternative, importer_url: 'https://a.example/' } } }
  const { unmount } = await render(<CompareCard result={withLinks} />)
  const links = screen.getAllByRole('link')
  expect(links).toHaveLength(1)
  expect(links[0].props.accessibilityLabel).toBe(`למפרט המלא אצל היבואן ← ${noa.card.alternative.label} (נפתח בדפדפן)`)
  await fireEvent.press(links[0])
  expect(open).toHaveBeenCalledWith('https://a.example/')
  await unmount()
  await render(<CompareCard result={withLinks} importerLink={false} />)
  expect(screen.queryAllByRole('link')).toHaveLength(0)
  open.mockRestore()
})

test('comparison: only today\'s car has a page: no link at all', async () => {
  await render(<CompareCard result={{ ...noa, card: { ...noa.card, today: { ...noa.card.today, importer_url: 'https://t.example/' } } }} />)
  expect(screen.queryAllByRole('link')).toHaveLength(0)
})

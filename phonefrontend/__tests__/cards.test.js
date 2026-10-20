// The cards: built on the server, the phone only formats them (real cards from the server, test-fixtures).
import { render, screen, fireEvent } from '@testing-library/react-native'
import CompareCard from '../src/components/CompareCard'
import RankingCard from '../src/components/RankingCard'
import SpecsCard from '../src/components/SpecsCard'
import noa from '../src/test-fixtures/card-noa.json'
import rachel from '../src/test-fixtures/card-rachel-waiting.json'
import ranking from '../src/test-fixtures/card-ranking.json'
import specs from '../src/test-fixtures/card-specs.json'
import specsNone from '../src/test-fixtures/card-specs-none.json'

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

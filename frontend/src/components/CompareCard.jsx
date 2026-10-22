// Comparison card, built from the `calculate` tool result. Every number here comes
// from the server; the card only formats (rounding was already done for display).
import { useEffect, useRef, useState } from 'react'
import { ImporterLink } from './RankingCard'

const YOUR_DATA = [
  ['occupation', 'עיסוק'], ['group', 'קבוצה'], ['base', 'שכר בסיס', 'money'],
  ['commission', 'עמלות', 'money'], ['bonus', 'בונוס', 'money'], ['pension_pct', 'פנסיה', 'pct'],
  ['keren_pct', 'קרן השתלמות', 'pct'], ['credit_points', 'נקודות זיכוי'], ['children', 'ילדים עד 23'],
  ['current', 'היום'], ['current_participation', 'השתתפות היום', 'money'],
]

const ROWS = [
  ['budget', 'תקציב הקבוצה'], ['car_cost', 'עלות לחברה'], ['participation', 'השתתפות'],
  ['value_of_use', 'שווי שימוש'], ['electric_refund_net', 'החזר חשמל (נטו)'],
  ['maintenance', 'אחזקת רכב'], ['family_share', 'חלק בפער המשפחתי'],
  ['tax', 'מס הכנסה'], ['social', 'ביטוח לאומי ובריאות'], ['net', 'נטו משוער', 'strong'],
]

const FLASH_MS = 1600
const fmtMoney = (v) => `${v.toLocaleString('he-IL')} ₪`

function fmt(v, kind = 'money') {
  if (v === null || v === undefined) return '—'
  if (typeof v !== 'number') return String(v) // e.g. "⏳ ממתין לנציג"
  if (kind === 'pct') return `${v}%`
  if (kind === 'money') return fmtMoney(v)
  return v.toLocaleString('he-IL')
}

function fmtDiff(v) {
  if (typeof v !== 'number') return ''
  if (v === 0) return '—'
  return `${v > 0 ? '+' : '−'}${fmtMoney(Math.abs(v))}`
}

const isWaiting = (v) => typeof v === 'string' && v.includes('⏳')

function Value({ v, kind }) {
  if (isWaiting(v)) return <span className="wait">{v}</span>
  if (typeof v === 'number') return <bdi dir="ltr" className="num">{fmt(v, kind)}</bdi>
  return <bdi>{fmt(v, kind)}</bdi>
}

function Source({ s }) {
  return s ? <span className="source">{s}</span> : null
}

// keys of the alternative whose value changed since the last render (e.g. a rep answer)
function useChanged(alt) {
  const prev = useRef(alt)
  const [changed, setChanged] = useState(() => new Set())
  useEffect(() => {
    const before = prev.current
    prev.current = alt
    if (before === alt) return
    const keys = new Set(Object.keys(alt.values).filter((k) => before.values[k]?.value !== alt.values[k]?.value))
    if (!keys.size) return
    setChanged(keys)
    const t = setTimeout(() => setChanged(new Set()), FLASH_MS)
    return () => clearTimeout(t)
  }, [alt])
  return changed
}

// importerLink: the employee's card has it; the rep screen passes false (the rep does not need it)
export default function CompareCard({ result, importerLink = true }) {
  const { card, status } = result
  const { your_data: yours, today, alternative: alt, diff, explanation } = card
  // the rep is asked to confirm the catalog's amount: calculated by it meanwhile, those fields marked
  const awaiting = card.awaiting_confirmation
  const changed = useChanged(alt)
  const facts = YOUR_DATA.filter(([key]) => yours[key])
  const sources = new Set(facts.map(([key]) => yours[key].source))
  const oneSource = sources.size === 1 ? [...sources][0] : null
  const net = diff.net
  const direction = typeof net !== 'number' || net === 0 ? 'flat' : net > 0 ? 'up' : 'down'
  const lines = [...new Set(explanation)]

  return (
    <article className={`card ${status === 'waiting_rep' ? 'card--waiting' : ''}`}>
      <section aria-label="הנתונים שלך" className="card__yours">
        <h3>הנתונים שלך <Source s={oneSource} /></h3>
        <dl>
          {facts.map(([key, label, kind]) => (
            <div key={key} className="card__fact">
              <dt>{label}</dt>
              <dd><Value v={yours[key].value} kind={kind ?? 'plain'} /></dd>
              {!oneSource && <dd><Source s={yours[key].source} /></dd>}
            </div>
          ))}
        </dl>
        <p className="hint">טעות באחד הנתונים? כתבו את הנכון בשיחה, והחישוב יתעדכן.</p>
      </section>

      <div className="card__scroll">
        <table className="card__table">
          <thead>
            <tr>
              <th scope="col"><span className="visually-hidden">שדה</span></th>
              <th scope="col">{today.label}</th>
              <th scope="col" className="col--alt">{alt.label}</th>
              <th scope="col">הפרש</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map(([key, label, style]) => {
              const t = today.values[key]
              const a = alt.values[key]
              if (!t && !a) return null
              const cls = [style === 'strong' && 'row--strong', changed.has(key) && 'row--flash'].filter(Boolean).join(' ')
              return (
                <tr key={key} className={cls}>
                  <th scope="row">{label}</th>
                  <td><Value v={t?.value} /><Source s={t?.source} /></td>
                  <td className="col--alt">
                    <Value v={a?.value} /><Source s={a?.source} />
                    {awaiting?.fields.includes(key) && <span className="wait">⏳ {awaiting.label}</span>}
                  </td>
                  <td className="diff"><bdi dir="ltr">{fmtDiff(diff[key])}</bdi></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {/* the importer's page of the new car only - today's car is already known (the server adds it; none outside the catalog) */}
      {importerLink && alt?.importer_url && (
        <p className="card__importers">
          <ImporterLink url={alt.importer_url} car={alt.label} />
        </p>
      )}

      {typeof net === 'number' ? (
        <div role="group" aria-label="הפרש בנטו, לחודש" className={`bigdiff bigdiff--${direction}`}>
          <span className="bigdiff__num">
            {direction !== 'flat' && <span aria-hidden="true" className="bigdiff__arrow">{direction === 'up' ? '▲' : '▼'}</span>}
            <bdi dir="ltr">{net === 0 ? fmtMoney(0) : fmtDiff(net)}</bdi>
          </span>
          <div className="card__explain">
            {lines.map((line) => <p key={line}>{line}</p>)}
            {awaiting && <p className="wait">⏳ {awaiting.note}</p>}
          </div>
        </div>
      ) : (
        <div className="bigdiff bigdiff--waiting">
          <span className="bigdiff__icon" aria-hidden="true">⏳</span>
          <div className="card__explain">
            {lines.map((line) => <p key={line}>{line}</p>)}
          </div>
        </div>
      )}
    </article>
  )
}

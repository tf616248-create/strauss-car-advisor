// Comparison card, built from the `calculate` tool result. Every number here comes
// from the server; the card only formats (rounding was already done for display).

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

export default function CompareCard({ result }) {
  const { card, status } = result
  const { your_data: yours, today, alternative: alt, diff, explanation } = card
  return (
    <article className={`card ${status === 'waiting_rep' ? 'card--waiting' : ''}`}>
      <section aria-label="הנתונים שלך" className="card__yours">
        <h3>הנתונים שלך</h3>
        <dl>
          {YOUR_DATA.filter(([key]) => yours[key]).map(([key, label, kind]) => (
            <div key={key} className="card__fact">
              <dt>{label}</dt>
              <dd>{fmt(yours[key].value, kind ?? 'plain')}</dd>
              <dd className="source">{yours[key].source}</dd>
            </div>
          ))}
        </dl>
        <p className="hint">טעות באחד הנתונים? כתבו את הנכון בשיחה, והחישוב יתעדכן.</p>
      </section>

      <table className="card__table">
        <thead>
          <tr>
            <th scope="col"></th>
            <th scope="col">{today.label}</th>
            <th scope="col">{alt.label}</th>
            <th scope="col">הפרש</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map(([key, label, style]) => {
            const t = today.values[key]
            const a = alt.values[key]
            if (!t && !a) return null
            return (
              <tr key={key} className={style === 'strong' ? 'row--strong' : ''}>
                <th scope="row">{label}</th>
                <td>{fmt(t?.value)}<span className="source">{t?.source}</span></td>
                <td>{fmt(a?.value)}<span className="source">{a?.source}</span></td>
                <td className="diff">{fmtDiff(diff[key])}</td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <div className="card__explain">
        {explanation.map((line) => <p key={line}>{line}</p>)}
      </div>
    </article>
  )
}

// Ranking card, from rank_options (the tool's artifact: it reaches the screen without passing
// through the model). Every number and spec comes from the server; the card only formats.

const fmtMoney = (v) => `${v.toLocaleString('he-IL')} ₪`

function fmtDiff(v) {
  if (typeof v !== 'number' || v === 0) return '—'
  return `${v > 0 ? '+' : '−'}${fmtMoney(Math.abs(v))}`
}

function fmtSpec(item) {
  const unit = item.unit ? ` ${item.unit}` : ''
  if ('value' in item) {
    if (typeof item.value === 'boolean') return item.value ? 'כן' : 'לא'
    return `${typeof item.value === 'number' ? item.value.toLocaleString('he-IL') : item.value}${unit}`
  }
  if ('values' in item) return item.values.join(' / ')
  return `${item.min.toLocaleString('he-IL')}–${item.max.toLocaleString('he-IL')}${unit}`
}

function SortValue({ v }) {
  if (v.category) return <span>{v.label}</span>
  const unit = v.unit ? ` ${v.unit}` : ''
  return <bdi dir="ltr" className="num">{`${v.value.toLocaleString('he-IL')}${unit}`}</bdi>
}

function Option({ o, sortLabel }) {
  return (
    <article className="rank">
      <h4 className="rank__name">{`${o.rank}. ${o.car}`}</h4>
      <dl className="rank__main">
        <div className="card__fact"><dt>נטו משוער</dt><dd><bdi dir="ltr" className="num">{fmtMoney(o.net)}</bdi></dd></div>
        <div className="card__fact"><dt>שינוי מהיום</dt><dd><bdi dir="ltr" className="num">{fmtDiff(o.diff?.net)}</bdi></dd></div>
        <div className="card__fact"><dt>{sortLabel}</dt><dd><SortValue v={o.sort_value} /></dd></div>
      </dl>
      {o.tie_broken_by_net && <p className="hint">{`שווים ב${sortLabel}, סודרו לפי נטו`}</p>}
      <details className="rank__specs">
        <summary>המפרט</summary>
        <dl>
          {Object.entries(o.specs).map(([key, item]) => (
            <div key={key} className="rank__spec">
              <dt>{item.label}</dt>
              <dd>
                {fmtSpec(item)}
                {item.provisional && <span className="source">{item.note || 'נתון ראשוני'}</span>}
                <span className="source">{`${item.source}${item.year ? `, ${item.year}` : ''}`}</span>
              </dd>
            </div>
          ))}
        </dl>
      </details>
      {o.importer_url && <a href={o.importer_url} target="_blank" rel="noreferrer">המפרט אצל היבואן</a>}
    </article>
  )
}

export default function RankingCard({ result }) {
  const { card } = result
  const missing = card.excluded_missing_data || []
  return (
    <section className="card ranking" aria-label="רכבים מסודרים">
      <h3>{`סידרתי לפי ${card.sort_label}`}</h3>
      {card.options.map((o) => <Option key={o.car} o={o} sortLabel={card.sort_label} />)}
      {missing.length > 0 && (
        <p className="hint">
          {`לא נכללו, כי חסר נתון רשמי: ${missing.map((m) => `${m.car} (${m.label})`).join(', ')}`}
        </p>
      )}
    </section>
  )
}

// Ranking card, from rank_options (the tool's artifact: it reaches the screen without passing
// through the model). Every number and spec comes from the server; the card only formats.
// SpecTags, SourceLine, ImporterLink and FullSpecs are shared with SpecsCard (car_specs).

const fmtMoney = (v) => `${v.toLocaleString('he-IL')} ₪`
const fmtNum = (v) => (typeof v === 'number' ? v.toLocaleString('he-IL') : String(v))
// a range in the Ministry of Transport is between trims; in EEA it is between registered versions
const rangeNote = (item) => (item.source?.startsWith('EEA') ? 'טווח גרסאות' : 'משתנה לפי גימור')

function fmtDiff(v) {
  if (typeof v !== 'number' || v === 0) return '—'
  return `${v > 0 ? '+' : '−'}${fmtMoney(Math.abs(v))}`
}

// one value, or a range when it differs between trims or versions
function fmtSpec(item) {
  const unit = item.unit ? ` ${item.unit}` : ''
  if ('value' in item) {
    if (typeof item.value === 'boolean') return item.value ? 'כן' : 'לא'
    return `${fmtNum(item.value)}${unit}`
  }
  if ('values' in item) return item.values.join(' / ')
  return `${fmtNum(item.min)}–${fmtNum(item.max)}${unit}`
}

// the specs worth a tag, with a short name for it
const TAGS = [
  ['mispar_moshavim', 'מושבים'], ['merkav', 'מרכב'], ['nikud_betihut', 'ניקוד בטיחות'],
  ['electric_consumption', 'צריכה'], ['fuel_consumption', 'צריכה (בקירוב)'], ['electric_range', 'טווח'],
  ['koah_sus', 'כוח סוס'],
]

export function SpecTags({ specs }) {
  const tags = TAGS.filter(([key]) => specs[key])
  if (!tags.length) return null
  return (
    <ul className="tags" aria-label="מפרט עיקרי">
      {tags.map(([key, name]) => <li key={key}>{`${name}: ${fmtSpec(specs[key])}`}</li>)}
    </ul>
  )
}

const day = (iso) => new Date(iso).toLocaleDateString('he-IL')

export function SourceLine({ sources }) {
  if (!sources?.length) return null
  return (
    <p className="sources">
      {`מקור: ${sources.map((s) => `${s.name}, עודכן ${day(s.fetched_at)}`).join(' · ')}`}
    </p>
  )
}

// The importer's page (a model page, or the brand's page when there is none): in a new window, and a
// screen reader is told so. car: its name for a screen reader, where a card shows more than one car.
// No url (a car outside the catalog): no link at all, never a broken one.
export function ImporterLink({ url, car }) {
  if (!url) return null
  return (
    <a className="importer" href={url} target="_blank" rel="noopener noreferrer">
      למפרט המלא אצל היבואן ←
      {car && <>{' '}<span className="visually-hidden">{car}</span></>}
      {' '}<span className="visually-hidden">(נפתח בחלון חדש)</span>
    </a>
  )
}

export function FullSpecs({ specs, open = false }) {
  const items = Object.entries(specs)
  if (!items.length) return null
  const list = (
    <dl>
      {items.map(([key, item]) => (
        <div key={key} className="rank__spec">
          <dt>{item.label}</dt>
          <dd>
            {fmtSpec(item)}
            {item.varies_by_trim && <span className="source">{rangeNote(item)}</span>}
            {item.provisional && <span className="source">{item.note || 'נתון ראשוני'}</span>}
            <span className="source">{`${item.source}${item.year ? `, ${item.year}` : ''}`}</span>
          </dd>
        </div>
      ))}
    </dl>
  )
  if (open) return <div className="rank__specs">{list}</div>
  return (
    <details className="rank__specs">
      <summary>כל המפרט</summary>
      {list}
    </details>
  )
}

function SortValue({ v }) {
  if (v.category) return <span>{v.label}</span>
  const unit = v.unit ? ` ${v.unit}` : ''
  return <bdi dir="ltr" className="num">{`${fmtNum(v.value)}${unit}`}</bdi>
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
      <SpecTags specs={o.specs} />
      <SourceLine sources={o.sources} />
      <ImporterLink url={o.importer_url} />
      <FullSpecs specs={o.specs} />
    </article>
  )
}

export default function RankingCard({ result }) {
  const { card } = result
  const missing = card.excluded_missing_data || []
  const waiting = card.needs_rep || []
  return (
    <section className="card ranking" aria-label="רכבים מסודרים">
      <h3>{`סידרתי לפי: ${card.sort_label}`}</h3>
      {card.options.map((o) => <Option key={o.car} o={o} sortLabel={card.sort_label} />)}
      {waiting.length > 0 && (
        <div className="waiting-rep" role="group" aria-label="ממתינים לנציג">
          {waiting.map((w) => (
            <div key={w.car} className="waiting-rep__row">
              <span>{w.car}</span>
              <span className="wait">⏳ ממתין לנציג</span>
            </div>
          ))}
        </div>
      )}
      {missing.length > 0 && (
        <p className="hint">
          {`לא נכללו, כי חסר נתון רשמי: ${missing.map((m) => `${m.car} (${m.label})`).join(', ')}`}
        </p>
      )}
    </section>
  )
}

import { useCallback, useEffect, useState } from 'react'
import * as realApi from '../lib/api'
import CompareCard from '../components/CompareCard'
import { REP_TITLE } from '../lib/notify'
import logo from '../assets/strauss-logo.svg'
import SiteFooter from '../components/SiteFooter'
import { TEST_REP_PASSCODE, TestCodesNote } from '../lib/testCodes'

const POLL_MS = 5000
const SENT_MS = 3000
const FIELD_LABELS = {
  carGroup: 'קבוצת הרכב', companyCost: 'עלות חודשית לחברה', participation: 'השתתפות עובד',
  group: 'קבוצת העובד', car: 'הרכב', base: 'שכר בסיס', commission: 'עמלות', bonus: 'בונוס',
  pension_pct: 'פנסיה %', keren_pct: 'קרן השתלמות %', credit_points: 'נקודות זיכוי',
  children: 'ילדים עד 23', current_participation: 'השתתפות היום',
}
const MONEY_FIELDS = new Set(['companyCost', 'participation', 'base', 'commission', 'bonus', 'current_participation'])
const NUMBER = /^-?\d+(\.\d+)?$/

function errorText(err) {
  if (err?.status === 401) return 'סיסמה שגויה'
  if (err?.status === 503) return 'מסך הנציג סגור: לא הוגדרה סיסמה בשרת'
  return 'אין חיבור לשרת. נסו שוב בעוד דקה.'
}

const fmtMoney = (v) => `${v.toLocaleString('he-IL')} ₪`

function AnswerForm({ request, onSubmit }) {
  const [values, setValues] = useState({})
  const [missing, setMissing] = useState(false)

  function submit(e) {
    e.preventDefault()
    const clean = {}
    for (const f of request.fields) {
      const v = (values[f] ?? '').trim()
      if (!v) { setMissing(true); return }
      clean[f] = NUMBER.test(v) ? Number(v) : v
    }
    setMissing(false)
    onSubmit(clean)
  }

  return (
    <form onSubmit={submit} className="rep__form">
      {request.fields.map((f) => {
        const id = `f-${request.id}-${f}`
        const money = MONEY_FIELDS.has(f)
        return (
          <div key={f} className="fld">
            <label htmlFor={id}>{FIELD_LABELS[f] ?? f}</label>
            <div className={`fld__box ${money ? 'fld__box--money' : ''}`}>
              <input id={id} inputMode={money ? 'numeric' : undefined} value={values[f] ?? ''}
                onChange={(e) => setValues({ ...values, [f]: e.target.value })} />
              {money && <span aria-hidden="true">₪</span>}
            </div>
          </div>
        )
      })}
      <div className="rep__actions">
        <button type="submit">שליחת תשובה</button>
        {missing
          ? <p className="error" role="alert">צריך למלא את כל השדות</p>
          : <p className="hint">כל השדות חובה. העובד יראה את העדכון מיד.</p>}
      </div>
    </form>
  )
}

// the context the rep needs, taken from the employee's card (nothing typed here)
function Context({ request }) {
  const card = request.card
  if (!card) return null
  const yours = card.your_data ?? {}
  const vou = card.alternative?.values?.value_of_use
  const who = [yours.occupation?.value, yours.group?.value && `קבוצה ${yours.group.value}`].filter(Boolean).join(' · ')
  return (
    <dl className="rep__context">
      {who && <div><dt>עובד</dt><dd>{who}</dd></div>}
      {yours.current && <div><dt>רכב היום</dt><dd>{yours.current.value}</dd></div>}
      {card.alternative?.label && <div><dt>רכב מבוקש</dt><dd><bdi>{card.alternative.label}</bdi></dd></div>}
      {typeof vou?.value === 'number' && (
        <div><dt>שווי שימוש</dt><dd><bdi dir="ltr" className="num">{fmtMoney(vou.value)}</bdi> <span className="source">{vou.source}</span></dd></div>
      )}
      {request.car_key && <div><dt>קוד רשות המסים</dt><dd><bdi dir="ltr" className="num">{request.car_key}</bdi></dd></div>}
    </dl>
  )
}

export default function RepScreen({ api = realApi }) {
  useEffect(() => { document.title = REP_TITLE }, [])
  const [input, setInput] = useState('')
  const [passcode, setPasscode] = useState(() => sessionStorage.getItem('repPasscode'))
  const [requests, setRequests] = useState([])
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [sent, setSent] = useState(null) // the request just answered, shown for a moment

  const load = useCallback(async (pw) => {
    try {
      setRequests(await api.repList(pw))
      setError(null)
      return true
    } catch (err) {
      setError(errorText(err))
      if (err?.status === 401) { setPasscode(null); sessionStorage.removeItem('repPasscode') }
      return false
    }
  }, [api])

  useEffect(() => {
    if (!passcode) return
    load(passcode)
    const t = setInterval(() => load(passcode), POLL_MS)
    return () => clearInterval(t)
  }, [passcode, load])

  useEffect(() => {
    if (!sent) return
    const t = setTimeout(() => setSent(null), SENT_MS)
    return () => clearTimeout(t)
  }, [sent])

  async function login(e) {
    e.preventDefault()
    if (await load(input)) {
      sessionStorage.setItem('repPasscode', input)
      setPasscode(input)
    }
  }

  async function answer(r, values) {
    try {
      await api.repAnswer(passcode, r.id, values)
      setSent(r)
      await load(passcode)
    } catch (err) {
      setError(errorText(err))
    }
  }

  if (!passcode) {
    return (
      <main className="rep rep--login">
        <img className="topbar__logo" src={logo} alt="שטראוס" />
        <h1>מסך נציג התחבורה</h1>
        <form onSubmit={login}>
          <label>
            סיסמת נציג
            <input type="password" value={input} onChange={(e) => setInput(e.target.value)} />
          </label>
          <button type="submit">כניסה</button>
        </form>
        {error && <p className="error" role="alert">{error}</p>}
        <TestCodesNote>{`סיסמת נציג: ${TEST_REP_PASSCODE}.`}</TestCodesNote>
        <SiteFooter />
      </main>
    )
  }

  const selected = requests.find((r) => r.id === selectedId) ?? requests[0]
  const queue = sent && !requests.some((r) => r.id === sent.id) ? [...requests, sent] : requests

  return (
    <div className="rep">
      <header className="topbar">
        <img className="topbar__logo" src={logo} alt="שטראוס" />
        <span className="topbar__sep" aria-hidden="true" />
        <h1>מסך נציג התחבורה</h1>
        <p className="topbar__sub">המסך מתעדכן לבד</p>
      </header>

      <nav className="rep__queue" aria-label="תור שאלות">
        <h2>שאלות פתוחות ({requests.length})</h2>
        {error && <p className="error" role="alert">{error}</p>}
        {queue.map((r) => {
          const isSent = sent?.id === r.id
          return (
            <button key={r.id} type="button" disabled={isSent}
              className={`qitem ${isSent ? 'qitem--sent' : ''}`}
              aria-current={!isSent && selected?.id === r.id ? 'true' : undefined}
              onClick={() => setSelectedId(r.id)}>
              <span className="qitem__title"><bdi>{r.card?.alternative?.label ?? 'שאלה לנציג'}</bdi></span>
              <span className="qitem__meta">{r.card?.your_data?.occupation?.value ?? ''} · {r.fields.length} שדות</span>
              {isSent && <span className="qitem__sent">נשלח ✓</span>}
            </button>
          )
        })}
        {requests.length === 0 && <p className="hint">אין כרגע שאלות. המסך מתעדכן לבד.</p>}
        <p className="hint rep__note">הנציג לא מדבר עם העובד. התשובה מעדכנת את כרטיס ההשוואה שלו.</p>
      </nav>

      <main className="rep__detail" aria-label="שאלה נבחרת">
        {sent && (
          <div className="sentbox" role="status">
            <span className="sentbox__check" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
            </span>
            <span>
              <strong>התשובה נשלחה</strong>
              <span>כרטיס ההשוואה של העובד מתעדכן עכשיו.</span>
            </span>
          </div>
        )}
        {selected ? (
          <div key={selected.id} className="rep__request">
            <h2>{selected.question}</h2>
            <Context request={selected} />
            <AnswerForm request={selected} onSubmit={(values) => answer(selected, values)} />
          </div>
        ) : !sent && (
          <div className="rep__empty">
            <svg width="56" height="56" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 13l2.5-7.5A2 2 0 0 1 7.4 4h9.2a2 2 0 0 1 1.9 1.5L21 13" /><path d="M3 13v5a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5h-5l-1.5 2.5h-5L8 13H3z" /></svg>
            <strong>אין שאלות פתוחות</strong>
            <span>שאלה חדשה תופיע כאן.</span>
          </div>
        )}
      </main>

      <aside className="rep__card" aria-label="כרטיס ההשוואה של העובד">
        {selected?.card && (
          <>
            <h2 className="rep__cardtitle">כרטיס ההשוואה של העובד</h2>
            <CompareCard result={{ status: 'waiting_rep', card: selected.card }} importerLink={false} />
          </>
        )}
      </aside>
      <SiteFooter className="rep__footer" />
    </div>
  )
}

import { useCallback, useEffect, useState } from 'react'
import * as realApi from '../lib/api'
import CompareCard from '../components/CompareCard'

const POLL_MS = 5000
const FIELD_LABELS = {
  carGroup: 'קבוצת הרכב', companyCost: 'עלות חודשית לחברה', participation: 'השתתפות עובד',
  group: 'קבוצת העובד', car: 'הרכב', base: 'שכר בסיס', commission: 'עמלות', bonus: 'בונוס',
  pension_pct: 'פנסיה %', keren_pct: 'קרן השתלמות %', credit_points: 'נקודות זיכוי',
  children: 'ילדים עד 23', current_participation: 'השתתפות היום',
}
const NUMBER = /^-?\d+(\.\d+)?$/

function errorText(err) {
  if (err?.status === 401) return 'סיסמה שגויה'
  if (err?.status === 503) return 'מסך הנציג סגור: לא הוגדרה סיסמה בשרת'
  return 'אין חיבור לשרת. נסו שוב בעוד דקה.'
}

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
      {request.fields.map((f) => (
        <label key={f}>
          {FIELD_LABELS[f] ?? f}
          <input value={values[f] ?? ''} onChange={(e) => setValues({ ...values, [f]: e.target.value })} />
        </label>
      ))}
      {missing && <p className="error">צריך למלא את כל השדות</p>}
      <button type="submit">שליחת תשובה</button>
    </form>
  )
}

export default function RepScreen({ api = realApi }) {
  const [input, setInput] = useState('')
  const [passcode, setPasscode] = useState(() => sessionStorage.getItem('repPasscode'))
  const [requests, setRequests] = useState([])
  const [error, setError] = useState(null)

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

  async function login(e) {
    e.preventDefault()
    if (await load(input)) {
      sessionStorage.setItem('repPasscode', input)
      setPasscode(input)
    }
  }

  async function answer(id, values) {
    try {
      await api.repAnswer(passcode, id, values)
      await load(passcode)
    } catch (err) {
      setError(errorText(err))
    }
  }

  if (!passcode) {
    return (
      <main className="rep rep--login">
        <h1>מסך נציג התחבורה</h1>
        <form onSubmit={login}>
          <label>
            סיסמת נציג
            <input type="password" value={input} onChange={(e) => setInput(e.target.value)} />
          </label>
          <button type="submit">כניסה</button>
        </form>
        {error && <p className="error" role="alert">{error}</p>}
      </main>
    )
  }

  return (
    <main className="rep">
      <h1>שאלות פתוחות ({requests.length})</h1>
      {error && <p className="error" role="alert">{error}</p>}
      {requests.length === 0 && <p className="hint">אין כרגע שאלות. המסך מתעדכן לבד.</p>}
      {requests.map((r) => (
        <section key={r.id} className="rep__request">
          <h2>{r.question}</h2>
          <AnswerForm request={r} onSubmit={(values) => answer(r.id, values)} />
          {r.card && <CompareCard result={{ status: 'waiting_rep', card: r.card }} />}
        </section>
      ))}
    </main>
  )
}

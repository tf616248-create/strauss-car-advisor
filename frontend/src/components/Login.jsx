import { useState } from 'react'
import * as realApi from '../lib/api'
import { setToken } from '../lib/session'
import { TEST_EMPLOYEE_CODES, TestCodesNote } from '../lib/testCodes'
import intro from '../config/intro.json'

const T = intro.texts

// errors always say what to do next
function errorText(err) {
  if (err?.status === 401) return 'הקוד לא נכון. נסו שוב.'
  if (err?.status === 429) return 'יותר מדי ניסיונות. נסו שוב בעוד כמה דקות.'
  if (err?.status === 503) return 'הכניסה סגורה כרגע: לא הוגדרו קודים בשרת.'
  return 'כובי לא מצליח להתחבר כרגע. נסו שוב בעוד דקה.'
}

// Demo login: an employee code -> a token for this tab (app/auth.py). A pilot replaces it with SSO.
// It is the card of the opening scene (Intro.jsx), whose h1 is the slogan - so its title is an h2.
// onFocusField: the phone keeps the field above the keyboard (Intro.jsx).
export default function Login({ api = realApi, onLogin, onFocusField }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    const value = code.trim()
    if (!value || busy) return
    setBusy(true)
    setError(null)
    try {
      const { token } = await api.login(value)
      setToken(token)
      onLogin()
    } catch (err) {
      setError(errorText(err))
      setBusy(false)
    }
  }

  return (
    <form className="intro__card" onSubmit={submit}>
      <h2 className="intro__cardtitle">{T.cardTitle}</h2>
      <p className="intro__cardsub">{T.cardSub}</p>
      <label htmlFor="code" className="intro__label">{T.code}</label>
      <div className="intro__row">
        <input id="code" type="password" inputMode="numeric" autoComplete="off" value={code} placeholder={T.code}
          onChange={(e) => setCode(e.target.value)} onFocus={onFocusField}
          aria-invalid={error ? 'true' : undefined} aria-describedby={error ? 'login-error' : undefined} />
        <button type="submit" className="intro__enter" disabled={busy} aria-label={T.enterLabel}>{T.enter}</button>
      </div>
      {error && <p id="login-error" className="error" role="alert">{error}</p>}
      <TestCodesNote>{`קודי עובד: ${TEST_EMPLOYEE_CODES}.`}</TestCodesNote>
    </form>
  )
}

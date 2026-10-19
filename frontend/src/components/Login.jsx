import { useState } from 'react'
import * as realApi from '../lib/api'
import { setToken } from '../lib/session'
import { CarBody } from './Road'
import logo from '../assets/strauss-logo.svg'

// errors always say what to do next
function errorText(err) {
  if (err?.status === 401) return 'הקוד לא נכון. נסו שוב.'
  if (err?.status === 429) return 'יותר מדי ניסיונות. נסו שוב בעוד כמה דקות.'
  if (err?.status === 503) return 'הכניסה סגורה כרגע: לא הוגדרו קודים בשרת.'
  return 'כובי לא מצליח להתחבר כרגע. נסו שוב בעוד דקה.'
}

// Demo login: an employee code -> a token for this tab (app/auth.py). A pilot replaces it with SSO.
export default function Login({ api = realApi, onLogin }) {
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
    <div className="login">
      <form className="login__card" onSubmit={submit}>
        <img className="login__logo" src={logo} alt="שטראוס" />
        <div className="welcome__car" aria-hidden="true"><CarBody /></div>
        <h1 className="login__title">
          <span className="topbar__name">כובי</span>
          <span className="topbar__product">יועץ הרכב של שטראוס</span>
        </h1>
        <p className="login__sub">כדי לראות את השיחות שלכם, הקלידו את קוד העובד שקיבלתם.</p>
        <label htmlFor="code" className="login__label">קוד עובד</label>
        <input id="code" type="password" inputMode="numeric" autoComplete="off" value={code}
          onChange={(e) => setCode(e.target.value)} aria-invalid={error ? 'true' : undefined}
          aria-describedby={error ? 'login-error' : undefined} />
        {error && <p id="login-error" className="error" role="alert">{error}</p>}
        <button type="submit" disabled={busy}>כניסה</button>
      </form>
    </div>
  )
}

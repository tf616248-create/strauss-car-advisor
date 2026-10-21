import { useEffect } from 'react'
import cfg from '../config/accessibility.json'
import logo from '../assets/strauss-logo.svg'

const S = cfg.statement

// The accessibility statement (/accessibility). All its text is in config/accessibility.json.
// It says what was checked and how far ("נבדק והותאם ככל הניתן") - never that the site is fully
// accessible or approved. The phone app is out of its scope.
const fmtDate = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString('he-IL', { day: 'numeric', month: 'long', year: 'numeric' })

export default function AccessibilityStatement() {
  useEffect(() => { document.title = `${S.title} · יועץ הרכב של שטראוס` }, [])

  return (
    <div className="statement">
      <header className="statement__head">
        <img className="statement__logo" src={logo} alt="שטראוס" />
        <a className="statement__back" href="/">{cfg.backHome}</a>
      </header>
      <main className="statement__body">
        <h1>{S.title}</h1>
        <p>{S.intro}</p>
        <h2>{S.scopeTitle}</h2>
        <ul>{S.scope.map((t) => <li key={t}>{t}</li>)}</ul>
        <h2>{S.doneTitle}</h2>
        <ul>{S.done.map((t) => <li key={t}>{t}</li>)}</ul>
        <h2>{S.limitsTitle}</h2>
        <ul>{S.limits.map((t) => <li key={t}>{t}</li>)}</ul>
        <h2>{S.contactTitle}</h2>
        <p>{S.contact}</p>
        <p className="statement__contact">{S.contactDetails}</p>
        <p className="statement__date">
          {S.checkedOnLabel} <time dateTime={S.checkedOn}>{fmtDate(S.checkedOn)}</time>
        </p>
      </main>
    </div>
  )
}

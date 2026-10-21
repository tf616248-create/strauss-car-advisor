import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import cfg from '../config/profile.json'

const T = cfg.texts
const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, k) => values[k])

// a field's value in the form (always a string), and back to what the server takes
const shown = (v) => (v === undefined || v === null ? '' : String(v))
function parsed(field, text) {
  const t = text.trim()
  if (t === '') return null
  if (field.type !== 'number') return t
  const n = Number(t.replace(/,/g, ''))
  return Number.isFinite(n) ? n : t // not a number: the server says what is wrong, next to the field
}

// the server's reason, in words, next to its field
function why(field, problem) {
  if (problem.range) return fill(T.range, { lo: problem.range[0].toLocaleString('he-IL'), hi: problem.range[1].toLocaleString('he-IL') })
  if (problem.suggestions) {
    return problem.suggestions.length ? fill(T.notFound, { suggestions: problem.suggestions.join(', ') }) : T.notFoundNoSuggestions
  }
  if (problem.options) return T.options
  return T.invalid
}

// The employee's profile, over the conversation (a modal window, about 560px on a computer).
// Every field can be edited; saving sends only what changed. Next to each value: where it came
// from (typed here, the chat, a payslip). The group is read only: the server computes it from the
// occupation. Closed by ✕, Esc or a click outside (the parent also closes it on the browser's Back).
// The focus starts on ✕, stays inside, and goes back to the opener (the parent does that).
export default function ProfileDialog({ api, onClose }) {
  const [view, setView] = useState(null) // { fields, sources, group }
  const [form, setForm] = useState({})
  const [state, setState] = useState('loading') // loading | ready | failed
  const [errors, setErrors] = useState({})
  const [notice, setNotice] = useState(null) // { kind: 'saved' | 'alert', text }
  const [saving, setSaving] = useState(false)
  const boxRef = useRef(null)
  const closeRef = useRef(null)
  const downOutside = useRef(false)
  const onCloseRef = useRef(onClose)
  useEffect(() => { onCloseRef.current = onClose }, [onClose])

  function take(v) {
    setView(v)
    setForm(Object.fromEntries(cfg.fields.map((f) => [f.name, shown(v.fields[f.name])])))
  }

  useEffect(() => {
    let live = true
    Promise.resolve(api.profile())
      .then((v) => { if (live) { take(v); setState('ready') } })
      .catch(() => { if (live) setState('failed') })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // the focus: on ✕ at first, then kept inside; Esc closes
  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); onCloseRef.current(); return }
      if (e.key !== 'Tab') return
      const items = [...boxRef.current.querySelectorAll('button, input, select, a[href]')].filter((el) => !el.disabled)
      if (!items.length) return
      const first = items[0]
      const last = items[items.length - 1]
      if (e.shiftKey && (document.activeElement === first || !boxRef.current.contains(document.activeElement))) {
        e.preventDefault(); last.focus()
      } else if (!e.shiftKey && (document.activeElement === last || !boxRef.current.contains(document.activeElement))) {
        e.preventDefault(); first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  async function save(e) {
    e.preventDefault()
    if (saving || !view) return
    const changed = {}
    for (const f of cfg.fields) {
      if (form[f.name] !== shown(view.fields[f.name])) changed[f.name] = parsed(f, form[f.name])
    }
    setNotice(null)
    setErrors({})
    if (!Object.keys(changed).length) { setNotice({ kind: 'saved', text: T.saved }); return }
    setSaving(true)
    try {
      const res = await api.saveProfile(changed)
      if (res.invalid) {
        setErrors(res.invalid)
        setNotice({ kind: 'alert', text: T.fixErrors })
      } else {
        take(res.profile)
        setNotice({ kind: 'saved', text: T.saved })
      }
    } catch {
      setNotice({ kind: 'alert', text: T.saveError })
    } finally {
      setSaving(false)
    }
  }

  const set = (name) => (e) => { setForm((f) => ({ ...f, [name]: e.target.value })); setNotice(null) }

  function control(f) {
    const id = `pf-${f.name}`
    const source = view?.sources?.[f.name]
    const problem = errors[f.name]
    const described = [source && `${id}-src`, problem && `${id}-err`].filter(Boolean).join(' ') || undefined
    const common = { id, value: form[f.name] ?? '', onChange: set(f.name), 'aria-describedby': described,
      'aria-invalid': problem ? 'true' : undefined }
    return (
      <div key={f.name} className={`profile__field ${problem ? 'profile__field--bad' : ''}`}>
        <label htmlFor={id}>{f.label}</label>
        {f.type === 'kind' ? (
          <select {...common}>
            {Object.entries(T.kinds).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
          </select>
        ) : (
          <input {...common} type="text" inputMode={f.type === 'number' ? 'decimal' : undefined}
            autoComplete="off" dir={f.type === 'number' ? 'ltr' : undefined} />
        )}
        {source && <span id={`${id}-src`} className="profile__source">{T.sources[source]}</span>}
        {problem && <span id={`${id}-err`} className="profile__error">{why(f, problem)}</span>}
      </div>
    )
  }

  const group = view?.group ? fill(T.group, { group: view.group }) : T.groupUnknown

  return createPortal(
    // a click on the dark area outside closes it, on the click itself (so the browser's own focus change
    // comes first, and the focus then goes back to the opener) and only if it started outside too
    // (a text selection dragged out of a field does not close it)
    <div className="modal" onMouseDown={(e) => { downOutside.current = e.target === e.currentTarget }}
      onClick={(e) => { if (downOutside.current && e.target === e.currentTarget) onClose() }}>
      <div ref={boxRef} className="profile" role="dialog" aria-modal="true" aria-labelledby="profile-title"
        aria-describedby="profile-intro">
        <div className="profile__head">
          <h2 id="profile-title">{T.title}</h2>
          <button ref={closeRef} type="button" className="profile__close" aria-label={T.close} onClick={onClose}>
            <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
        <p id="profile-intro" className="profile__intro">{T.intro}</p>
        {state === 'loading' && <p className="profile__status" role="status">{T.loading}</p>}
        {state === 'failed' && <p className="profile__status error" role="alert">{T.loadError}</p>}
        {state === 'ready' && (
          <form className="profile__form" onSubmit={save} noValidate>
            {control(cfg.fields[0])}
            <p className="profile__field profile__readonly">
              <span className="profile__label">{T.groupLabel}</span>
              <span className="profile__group">{group}</span>
            </p>
            {cfg.fields.slice(1).map(control)}
            <div className="profile__foot">
              <button type="submit" disabled={saving}>{saving ? T.saving : T.save}</button>
              <span className="profile__notice" role="status">{notice?.kind === 'saved' ? notice.text : ''}</span>
              {notice?.kind === 'alert' && <p className="profile__notice error" role="alert">{notice.text}</p>}
            </div>
          </form>
        )}
      </div>
    </div>,
    document.body,
  )
}

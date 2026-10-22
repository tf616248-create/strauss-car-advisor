import { useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import cfg from '../config/settings.json'
import { useModalFocus, useOutsideClick } from '../lib/dialog'

const T = cfg.texts

// "התאמה אישית": a small window over the conversation with two settings, kept on the server with the
// profile. Light, dark or the computer's (system) applies at once; the tone from Kobi's next message (the server reads it at
// every model call). A change is saved when it is chosen; a save that fails goes back and says so.
// settings: { theme, tone }; onChange(next): the parent applies the theme.
export default function CustomizeDialog({ api, settings, onChange, onClose }) {
  const boxRef = useRef(null)
  const closeRef = useRef(null)
  const [notice, setNotice] = useState(null) // { kind: 'saved' | 'alert', text }
  useModalFocus(boxRef, closeRef, onClose)
  const outside = useOutsideClick(onClose)

  async function choose(field, value) {
    if (settings[field] === value) return
    const before = settings
    onChange({ ...settings, [field]: value })
    setNotice(null)
    try {
      onChange(await api.saveSettings({ [field]: value }))
      setNotice({ kind: 'saved', text: T.saved })
    } catch {
      onChange(before)
      setNotice({ kind: 'alert', text: T.saveError })
    }
  }

  const group = (field, options, hint) => (
    <div className="customize__group" role="radiogroup" aria-labelledby={`cz-${field}`}
      aria-describedby={hint ? `cz-${field}-hint` : undefined}>
      <span id={`cz-${field}`} className="customize__legend">{T[field]}</span>
      {hint && <span id={`cz-${field}-hint`} className="customize__hint">{hint}</span>}
      <div className="customize__options">
        {Object.entries(options).map(([value, label]) => (
          <label key={value} className="customize__option">
            <input type="radio" name={`cz-${field}`} value={value} checked={settings[field] === value}
              onChange={() => choose(field, value)} />
            {label}
          </label>
        ))}
      </div>
    </div>
  )

  return createPortal(
    <div className="modal" {...outside}>
      <div ref={boxRef} className="profile customize" role="dialog" aria-modal="true" aria-labelledby="cz-title">
        <div className="profile__head">
          <h2 id="cz-title">{T.title}</h2>
          <button ref={closeRef} type="button" className="profile__close" aria-label={T.close} onClick={onClose}>
            <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
        {group('theme', T.themes)}
        {group('tone', T.tones, T.toneHint)}
        <span className="profile__notice" role="status">{notice?.kind === 'saved' ? notice.text : ''}</span>
        {notice?.kind === 'alert' && <p className="profile__notice error" role="alert">{notice.text}</p>}
      </div>
    </div>,
    document.body,
  )
}

import { useEffect, useId, useState } from 'react'

// "Talk to a rep": a service email, at the right end of the message row. The bot's rep
// queue only answers predefined fields; a person to write to is this email.
// VITE_SUPPORT_EMAIL (frontend/.env) overrides the service address.
export const SUPPORT_EMAIL = 'support@strauss-in.com'

export default function ContactRep({ email = import.meta.env.VITE_SUPPORT_EMAIL }) {
  const address = email || SUPPORT_EMAIL
  const [open, setOpen] = useState(false)
  const panelId = useId()

  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <div className="contact">
      {open && (
        // floats above the button, so opening it never moves the button
        <div id={panelId} className="contact__panel contact__panel--floating" role="dialog" aria-label="פנייה לשירות">
          <div className="contact__head">
            <strong>פנייה לנציג התחבורה</strong>
            <button type="button" className="contact__close" aria-label="סגירה" onClick={() => setOpen(false)}>
              <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
            </button>
          </div>
          <p>אפשר לכתוב לנו: <a href={`mailto:${address}`}><bdi dir="ltr">{address}</bdi></a></p>
        </div>
      )}
      <button type="button" className="contact__btn" aria-label="שיחה עם נציג" title="שיחה עם נציג"
        aria-expanded={open} aria-controls={open ? panelId : undefined} onClick={() => setOpen((o) => !o)}>
        <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 6h16v10H8l-4 4z" />
        </svg>
      </button>
    </div>
  )
}

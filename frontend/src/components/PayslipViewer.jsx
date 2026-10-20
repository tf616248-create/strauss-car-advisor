import { useEffect, useRef } from 'react'
import cfg from '../config/payslip.json'

const T = cfg.texts

// The payslip, large. A computer: a window over the page, closed by Esc, ✕ or a click outside.
// A phone: full screen with a big ✕ (styles.css). The focus starts on ✕, stays inside while
// it is open, and goes back to the thumbnail that opened it.
// opener: the thumbnail (a tap on a phone does not always focus it, so it is passed, not guessed)
export default function PayslipViewer({ src, opener: openerProp, onClose }) {
  const closeRef = useRef(null)
  const onCloseRef = useRef(onClose)
  useEffect(() => { onCloseRef.current = onClose }, [onClose])

  useEffect(() => {
    const opener = openerProp ?? document.activeElement
    closeRef.current?.focus()
    const onKey = (e) => {
      if (e.key === 'Escape') onCloseRef.current()
      else if (e.key === 'Tab') { e.preventDefault(); closeRef.current?.focus() } // ✕ is the only control
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      opener?.focus?.()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="viewer" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="viewer__box" role="dialog" aria-modal="true" aria-label={T.viewer}
        onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
        <button ref={closeRef} type="button" className="viewer__close" aria-label={T.close} onClick={onClose}>
          <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
        <img className="viewer__img" src={src} alt={T.image} />
      </div>
    </div>
  )
}

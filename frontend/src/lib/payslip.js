import { useEffect, useState } from 'react'
import cfg from '../config/payslip.json'

// The same checks as the server (backend/app/payslip.py), before anything is sent: the employee
// learns at once, next to the message box. The server checks again by the file's bytes.
const IMAGE = ['image/jpeg', 'image/png']
const PDF = 'application/pdf'

// -> { kind: 'image' | 'pdf' } or { error: text }
export function checkFile(file) {
  const name = (file.name || '').toLowerCase()
  const kind = IMAGE.includes(file.type) || /\.(jpe?g|png)$/.test(name) ? 'image'
    : file.type === PDF || name.endsWith('.pdf') ? 'pdf' : null
  if (!kind) return { error: cfg.texts.badType }
  if (file.size > cfg.maxBytes) return { error: cfg.texts.tooLarge }
  return { kind }
}

// a phone (a touch screen as the main pointer): the camera button shows only there
const PHONE = '(pointer: coarse)'

export function usePhone() {
  const query = () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(PHONE) : null)
  const [phone, setPhone] = useState(() => Boolean(query()?.matches))
  useEffect(() => {
    const mq = query()
    if (!mq?.addEventListener) return
    const onChange = (e) => setPhone(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return phone
}

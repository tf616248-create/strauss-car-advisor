// Formatting only: every number comes from the server.
// Numbers with a sign or a ₪ are isolated left-to-right inside Hebrew text (like <bdi dir="ltr">).
export const ltr = (s) => `\u2066${s}\u2069`
export const fmtMoney = (v) => `${v.toLocaleString('he-IL')} ₪`
export const fmtNum = (v) => (typeof v === 'number' ? v.toLocaleString('he-IL') : String(v))
export function fmtSigned(v) {
  if (typeof v !== 'number' || v === 0) return '—'
  return `${v > 0 ? '+' : '−'}${fmtMoney(Math.abs(v))}`
}
export const fmtNet = (v) => `${v > 0 ? '+' : '−'}${Math.abs(v).toLocaleString('he-IL')} ₪`
export const fmtWhen = (iso) => new Date(iso).toLocaleString('he-IL', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' })
export const fmtDay = (iso) => new Date(iso).toLocaleDateString('he-IL')

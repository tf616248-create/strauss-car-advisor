import { createSSEParser } from './sse'
import { getToken, unauthorized } from './session'

// The server's address, for requests and for the events stream (EventSource).
// Production (Netlify) must set VITE_API_URL; localhost is only a development fallback.
export function apiBase(env) {
  return (env.VITE_API_URL || (env.DEV ? 'http://localhost:8000' : '')).replace(/\/$/, '')
}

export const API_URL = apiBase(import.meta.env)
// errors always say what to do next
const NETWORK_ERROR = 'כובי לא מצליח להתחבר כרגע. נסו שוב בעוד דקה.'
const BUSY = 'כובי עמוס כרגע. נסו שוב בעוד רגע.'

// the employee's login token on every request (lib/session.js)
function withToken(headers = {}) {
  const token = getToken()
  return token ? { ...headers, Authorization: `Bearer ${token}` } : headers
}

// a payslip the server refused (too large, wrong type, unreadable): its own text, shown by the message box
const REFUSED = [413, 415, 422]

async function stream(url, init, onEvent, fetchImpl, { refused = [] } = {}) {
  try {
    const res = await fetchImpl(url, { ...init, headers: withToken(init.headers) })
    if (res.status === 401) { unauthorized(); return } // back to the login screen, no error message
    if (res.status === 429) { onEvent('error', { message: BUSY }); return }
    if (refused.includes(res.status)) {
      const body = await res.json().catch(() => ({}))
      if (typeof body.detail === 'string') { onEvent('rejected', { message: body.detail }); return }
    }
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    const parser = createSSEParser(onEvent)
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      parser.feed(decoder.decode(value, { stream: true }))
    }
  } catch {
    onEvent('error', { message: NETWORK_ERROR })
  }
}

export function streamChat({ message, threadId }, onEvent, fetchImpl = fetch) {
  const body = { message }
  if (threadId) body.thread_id = threadId
  return stream(`${API_URL}/chat`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }, onEvent, fetchImpl)
}

export function streamRepAnswered(threadId, onEvent, fetchImpl = fetch) {
  return stream(`${API_URL}/chat/${threadId}/rep-answered`, { method: 'POST' }, onEvent, fetchImpl)
}

// a payslip (JPG/PNG/PDF): the file itself is the body. Events: step, payslip, token, card, done,
// or "rejected" with the server's text when it refuses the file
export function streamPayslip(threadId, file, onEvent, fetchImpl = fetch) {
  return stream(`${API_URL}/chat/${threadId}/payslip`, {
    method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file,
  }, onEvent, fetchImpl, { refused: REFUSED })
}

// the payslip kept with the conversation (a JPEG): a local URL for <img>, since it needs the token; null = none
export async function payslipImage(threadId, fetchImpl = fetch) {
  try {
    const res = await fetchImpl(`${API_URL}/chat/${threadId}/payslip`, { headers: withToken() })
    if (res.status === 401) unauthorized()
    if (!res.ok) return null
    return URL.createObjectURL(await res.blob())
  } catch { return null }
}

async function json(url, init, fetchImpl = fetch) {
  const res = await fetchImpl(url, init)
  if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status })
  return res.json()
}

// employee routes: with the token; a 401 means the login is over
async function employeeJson(url, init = {}, fetchImpl = fetch) {
  try {
    return await json(url, { ...init, headers: withToken(init.headers) }, fetchImpl)
  } catch (err) {
    if (err.status === 401) unauthorized()
    throw err
  }
}

// a demo code -> { token, employee_id }. A wrong code is 401 here, not "logged out".
export const login = (code, fetchImpl = fetch) => json(`${API_URL}/login`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code }),
}, fetchImpl)
// the logged-in employee: { employee_id, name } (name: dummy names, the employees table)
export const me = (fetchImpl = fetch) => employeeJson(`${API_URL}/me`, {}, fetchImpl)
// the employee's profile: { employee_id, fields, sources, group } (group: read only, from the occupation)
export const profile = (fetchImpl = fetch) => employeeJson(`${API_URL}/profile`, {}, fetchImpl)

// some fields (null clears one) -> { profile } once kept, or { invalid: { field: why } } (422: nothing kept)
export async function saveProfile(fields, fetchImpl = fetch) {
  const res = await fetchImpl(`${API_URL}/profile`, {
    method: 'PATCH', headers: withToken({ 'Content-Type': 'application/json' }), body: JSON.stringify({ fields }),
  })
  if (res.status === 401) unauthorized()
  if (res.status === 422) {
    const body = await res.json().catch(() => ({}))
    if (body.detail?.invalid) return { invalid: body.detail.invalid }
  }
  if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status })
  return { profile: await res.json() }
}
// "התאמה אישית": { theme: light | dark, tone: professional | friendly | funny }, kept with the profile
export const settings = (fetchImpl = fetch) => employeeJson(`${API_URL}/settings`, {}, fetchImpl)
export const saveSettings = (values, fetchImpl = fetch) => employeeJson(`${API_URL}/settings`, {
  method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values),
}, fetchImpl)
// my conversations, newest first: [{ thread_id, title, updated_at }]
export const threads = async (fetchImpl = fetch) => (await employeeJson(`${API_URL}/threads`, {}, fetchImpl)).threads
// the conversation's current state: messages, cards, rep { pending, new_answers }
export const restore = (threadId) => employeeJson(`${API_URL}/chat/${threadId}`)
export const repList = (passcode) => json(`${API_URL}/rep/requests`, { headers: { 'X-Rep-Passcode': passcode } })
export const repAnswer = (passcode, id, values) => json(`${API_URL}/rep/requests/${id}/answer`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'X-Rep-Passcode': passcode },
  body: JSON.stringify({ values }),
})

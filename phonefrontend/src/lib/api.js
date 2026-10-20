import { createSSEParser } from './sse'
import { getToken, unauthorized } from './session'

// The server's address. A build must set EXPO_PUBLIC_API_URL (phonefrontend/.env);
// localhost is only a development fallback (on a real phone: the computer's address on the network).
export function apiBase(env, dev) {
  return (env.EXPO_PUBLIC_API_URL || (dev ? 'http://localhost:8000' : '')).replace(/\/$/, '')
}

export const API_URL = apiBase({ EXPO_PUBLIC_API_URL: process.env.EXPO_PUBLIC_API_URL }, __DEV__)
// errors always say what to do next
const NETWORK_ERROR = 'כובי לא מצליח להתחבר כרגע. נסו שוב בעוד דקה.'
const BUSY = 'כובי עמוס כרגע. נסו שוב בעוד רגע.'

// the employee's login token on every request (lib/session.js)
function withToken(headers = {}) {
  const token = getToken()
  return token ? { ...headers, Authorization: `Bearer ${token}` } : headers
}

// the global fetch on Android and iOS is expo/fetch, which streams the body (getReader)
async function stream(url, init, onEvent, fetchImpl) {
  try {
    const res = await fetchImpl(url, { ...init, headers: withToken(init.headers) })
    if (res.status === 401) { unauthorized(); return } // back to the login screen, no error message
    if (res.status === 429) { onEvent('error', { message: BUSY }); return }
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
// my conversations, newest first: [{ thread_id, title, updated_at }]
export const threads = async (fetchImpl = fetch) => (await employeeJson(`${API_URL}/threads`, {}, fetchImpl)).threads
// the conversation's current state: messages, cards, rep { pending, new_answers }
export const restore = (threadId, fetchImpl = fetch) => employeeJson(`${API_URL}/chat/${threadId}`, {}, fetchImpl)

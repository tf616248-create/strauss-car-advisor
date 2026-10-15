import { createSSEParser } from './sse'

export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')
const NETWORK_ERROR = 'אין חיבור לשרת. נסו שוב בעוד דקה.'

async function stream(url, init, onEvent, fetchImpl) {
  try {
    const res = await fetchImpl(url, init)
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

async function json(url, init) {
  const res = await fetch(url, init)
  if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status })
  return res.json()
}

// the conversation's current state: messages, cards, rep { pending, new_answers }
export const restore = (threadId) => json(`${API_URL}/chat/${threadId}`)
export const repList = (passcode) => json(`${API_URL}/rep/requests`, { headers: { 'X-Rep-Passcode': passcode } })
export const repAnswer = (passcode, id, values) => json(`${API_URL}/rep/requests/${id}/answer`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'X-Rep-Passcode': passcode },
  body: JSON.stringify({ values }),
})

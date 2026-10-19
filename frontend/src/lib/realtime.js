// "Something changed in this conversation" from our server (SSE, GET /conversations/{id}/events).
// The event carries nothing: the database is the source of truth, and the screen reads the
// current state again. The browser reconnects by itself; every (re)connect calls onOpen,
// so anything missed while disconnected is picked up by reading the state.
import { API_URL } from './api'
import { getToken } from './session'

export function subscribeChanges(threadId, { onChanged, onOpen }, EventSourceImpl = globalThis.EventSource) {
  if (!EventSourceImpl) return () => {}
  // EventSource can't send headers: the login token goes in the address
  const token = encodeURIComponent(getToken() ?? '')
  const es = new EventSourceImpl(`${API_URL}/conversations/${threadId}/events?token=${token}`)
  es.addEventListener('changed', () => onChanged())
  es.addEventListener('open', () => onOpen())
  return () => es.close()
}

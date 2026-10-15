// "Something changed in this conversation" from our server (SSE, GET /conversations/{id}/events).
// The event carries nothing: the database is the source of truth, and the screen reads the
// current state again. The browser reconnects by itself; every (re)connect calls onOpen,
// so anything missed while disconnected is picked up by reading the state.
import { API_URL } from './api'

export function subscribeChanges(threadId, { onChanged, onOpen }, EventSourceImpl = globalThis.EventSource) {
  if (!EventSourceImpl) return () => {}
  const es = new EventSourceImpl(`${API_URL}/conversations/${threadId}/events`)
  es.addEventListener('changed', () => onChanged())
  es.addEventListener('open', () => onOpen())
  return () => es.close()
}

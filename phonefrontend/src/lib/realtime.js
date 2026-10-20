// "Something changed in this conversation" from our server (SSE, GET /conversations/{id}/events).
// The event carries nothing: the database is the source of truth, and the screen reads the
// current state again. Every (re)connect calls onOpen, so anything missed is picked up.
// React Native has no EventSource: react-native-sse, which reconnects by itself.
import RNEventSource from 'react-native-sse'
import { API_URL } from './api'
import { getToken } from './session'

export function subscribeChanges(threadId, { onChanged, onOpen }, EventSourceImpl = RNEventSource) {
  // the same address as the website: the login token goes in it
  const token = encodeURIComponent(getToken() ?? '')
  const es = new EventSourceImpl(`${API_URL}/conversations/${threadId}/events?token=${token}`)
  es.addEventListener('changed', () => onChanged())
  es.addEventListener('open', () => onOpen())
  return () => es.close()
}

// "The rep answered" for one conversation. Supabase Realtime Broadcast when configured
// (channel = conversation id), polling the server as a fallback.
import { repStatus } from './api'

const POLL_MS = 10000

export function subscribeRepAnswers(threadId, onAnswered) {
  let stopped = false
  const seen = new Set()
  let supabaseCleanup = null

  const url = import.meta.env.VITE_SUPABASE_URL
  const key = import.meta.env.VITE_SUPABASE_ANON_KEY
  if (url && key) {
    import('@supabase/supabase-js').then(({ createClient }) => {
      if (stopped) return
      const client = createClient(url, key)
      const channel = client.channel(`conv:${threadId}`)
        .on('broadcast', { event: 'rep_answered' }, ({ payload }) => {
          if (payload?.request_id && !seen.has(payload.request_id)) {
            seen.add(payload.request_id)
            onAnswered()
          }
        })
        .subscribe()
      supabaseCleanup = () => client.removeChannel(channel)
    })
  }

  const timer = setInterval(async () => {
    try {
      const { answered } = await repStatus(threadId)
      const fresh = answered.filter((id) => !seen.has(id))
      fresh.forEach((id) => seen.add(id))
      if (fresh.length) onAnswered()
    } catch { /* server asleep or offline - try again next tick */ }
  }, POLL_MS)
  // ids answered before this page loaded are not "new"
  repStatus(threadId).then(({ answered }) => answered.forEach((id) => seen.add(id))).catch(() => {})

  return () => { stopped = true; clearInterval(timer); supabaseCleanup?.() }
}

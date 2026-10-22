import { describe, expect, it, vi } from 'vitest'
import { API_URL } from '@/lib/api'
import { subscribeChanges } from '@/lib/realtime'

const TID = '11111111-2222-3333-4444-555555555555'

function fakeEventSource() {
  const made = []
  class FakeES {
    constructor(url) { this.url = url; this.listeners = {}; this.close = vi.fn(); made.push(this) }
    addEventListener(type, fn) { (this.listeners[type] ??= []).push(fn) }
    emit(type) { (this.listeners[type] ?? []).forEach((fn) => fn({ type, data: '{}' })) }
  }
  return { FakeES, made }
}

describe('subscribeChanges', () => {
  it('listens to the conversation events on our server', () => {
    const { FakeES, made } = fakeEventSource()
    subscribeChanges(TID, { onChanged: vi.fn(), onOpen: vi.fn() }, FakeES)
    expect(made[0].url).toBe(`${API_URL}/conversations/${TID}/events?token=`)
  })

  it('sends the login token in the address (EventSource cannot send headers)', async () => {
    const { setToken } = await import('@/lib/session')
    setToken('a b')
    const { FakeES, made } = fakeEventSource()
    subscribeChanges(TID, { onChanged: vi.fn(), onOpen: vi.fn() }, FakeES)
    expect(made[0].url).toBe(`${API_URL}/conversations/${TID}/events?token=a%20b`)
  })

  it('"changed" calls onChanged; every (re)connect calls onOpen', () => {
    const { FakeES, made } = fakeEventSource()
    const onChanged = vi.fn()
    const onOpen = vi.fn()
    subscribeChanges(TID, { onChanged, onOpen }, FakeES)
    made[0].emit('open')
    made[0].emit('changed')
    made[0].emit('open') // the browser reconnected by itself
    expect(onChanged).toHaveBeenCalledTimes(1)
    expect(onOpen).toHaveBeenCalledTimes(2)
  })

  it('closes the connection when the screen leaves the conversation', () => {
    const { FakeES, made } = fakeEventSource()
    const stop = subscribeChanges(TID, { onChanged: vi.fn(), onOpen: vi.fn() }, FakeES)
    stop()
    expect(made[0].close).toHaveBeenCalled()
  })
})

import { describe, expect, it, vi } from 'vitest'
import { streamChat } from './api'

function sseResponse(chunks) {
  const enc = new TextEncoder()
  const body = new ReadableStream({
    start(c) { chunks.forEach((x) => c.enqueue(enc.encode(x))); c.close() },
  })
  return { ok: true, status: 200, body }
}

describe('streamChat', () => {
  it('posts the message and thread id, and delivers events in order', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(sseResponse([
      'event: step\ndata: {"tool":"calculate","label":"כובי מחשב נטו…"}\n\n',
      'event: token\ndata: {"text":"הנטו "}\n\nevent: token\ndata: {"text":"עולה"}\n\n',
      'event: done\ndata: {}\n\n',
    ]))
    const got = []
    await streamChat({ message: 'שלום', threadId: 'abc' }, (e, d) => got.push(e), fetchImpl)
    const [url, init] = fetchImpl.mock.calls[0]
    expect(url).toMatch(/\/chat$/)
    expect(JSON.parse(init.body)).toEqual({ message: 'שלום', thread_id: 'abc' })
    expect(got).toEqual(['step', 'token', 'token', 'done'])
  })

  it('turns a network failure into an error event', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('offline'))
    const got = []
    await streamChat({ message: 'x' }, (e, d) => got.push([e, d]), fetchImpl)
    expect(got).toEqual([['error', { message: 'כובי לא מצליח להתחבר כרגע. נסו שוב בעוד דקה.' }]])
  })

  it('a server that is down (e.g. 502/503) is "cannot connect", with what to do', async () => {
    const got = []
    await streamChat({ message: 'x' }, (e, d) => got.push([e, d]), vi.fn().mockResolvedValue({ ok: false, status: 503 }))
    expect(got).toEqual([['error', { message: 'כובי לא מצליח להתחבר כרגע. נסו שוב בעוד דקה.' }]])
  })

  it('429 (too many requests) is "busy", with what to do', async () => {
    const got = []
    await streamChat({ message: 'x' }, (e, d) => got.push([e, d]), vi.fn().mockResolvedValue({ ok: false, status: 429 }))
    expect(got).toEqual([['error', { message: 'כובי עמוס כרגע. נסו שוב בעוד רגע.' }]])
  })
})

describe('apiBase', () => {
  it('uses VITE_API_URL (without a trailing slash) for requests and the event stream', async () => {
    const { apiBase } = await import('./api')
    expect(apiBase({ VITE_API_URL: 'https://advisor-api.onrender.com/', DEV: false })).toBe('https://advisor-api.onrender.com')
  })

  it('falls back to localhost only in development', async () => {
    const { apiBase } = await import('./api')
    expect(apiBase({ VITE_API_URL: '', DEV: true })).toBe('http://localhost:8000')
    expect(apiBase({ VITE_API_URL: '', DEV: false })).toBe('')
  })
})

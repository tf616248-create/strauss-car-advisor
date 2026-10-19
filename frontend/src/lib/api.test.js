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

describe('employee login', () => {
  const ok = (body) => ({ ok: true, status: 200, json: async () => body })

  it('every request carries the login token', async () => {
    const { setToken } = await import('./session')
    setToken('tok-1')
    const fetchImpl = vi.fn().mockResolvedValue(sseResponse(['event: done\ndata: {}\n\n']))
    await streamChat({ message: 'x' }, () => {}, fetchImpl)
    expect(fetchImpl.mock.calls[0][1].headers.Authorization).toBe('Bearer tok-1')
  })

  it('an expired login (401) sends the employee back to the login screen, with no error message', async () => {
    const { setToken, setUnauthorizedHandler, getToken } = await import('./session')
    const back = vi.fn()
    setUnauthorizedHandler(back)
    setToken('old')
    const got = []
    await streamChat({ message: 'x' }, (e) => got.push(e), vi.fn().mockResolvedValue({ ok: false, status: 401 }))
    expect(back).toHaveBeenCalled()
    expect(getToken()).toBeNull()
    expect(got).toEqual([])
    setUnauthorizedHandler(() => {})
  })

  it('login posts the code and returns the token', async () => {
    const { login } = await import('./api')
    const fetchImpl = vi.fn().mockResolvedValue(ok({ token: 't', employee_id: 'E01' }))
    expect(await login('1111', fetchImpl)).toEqual({ token: 't', employee_id: 'E01' })
    const [url, init] = fetchImpl.mock.calls[0]
    expect(url).toMatch(/\/login$/)
    expect(JSON.parse(init.body)).toEqual({ code: '1111' })
  })

  it('a wrong code is an error with its status (and is not "logged out")', async () => {
    const { login } = await import('./api')
    const { setUnauthorizedHandler } = await import('./session')
    const back = vi.fn()
    setUnauthorizedHandler(back)
    await expect(login('0', vi.fn().mockResolvedValue({ ok: false, status: 401 }))).rejects.toMatchObject({ status: 401 })
    expect(back).not.toHaveBeenCalled()
    setUnauthorizedHandler(() => {})
  })

  it('threads lists my conversations, with the token', async () => {
    const { threads } = await import('./api')
    const { setToken } = await import('./session')
    setToken('tok-2')
    const list = [{ thread_id: 'a', title: 'שאלה', updated_at: '2026-10-20T10:00:00+00:00' }]
    const fetchImpl = vi.fn().mockResolvedValue(ok({ threads: list }))
    expect(await threads(fetchImpl)).toEqual(list)
    expect(fetchImpl.mock.calls[0][1].headers.Authorization).toBe('Bearer tok-2')
  })
})

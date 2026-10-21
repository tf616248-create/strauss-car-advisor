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
    expect(got).toEqual([['error', { message: 'כובי לא מצליח להתחבר כרגע. אפשר לנסות שוב בעוד דקה.' }]])
  })

  it('a server that is down (e.g. 502/503) is "cannot connect", with what to do', async () => {
    const got = []
    await streamChat({ message: 'x' }, (e, d) => got.push([e, d]), vi.fn().mockResolvedValue({ ok: false, status: 503 }))
    expect(got).toEqual([['error', { message: 'כובי לא מצליח להתחבר כרגע. אפשר לנסות שוב בעוד דקה.' }]])
  })

  it('429 (too many requests) is "busy", with what to do', async () => {
    const got = []
    await streamChat({ message: 'x' }, (e, d) => got.push([e, d]), vi.fn().mockResolvedValue({ ok: false, status: 429 }))
    expect(got).toEqual([['error', { message: 'כובי עמוס כרגע. אפשר לנסות שוב בעוד רגע.' }]])
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

  it('profile reads the profile, with the token', async () => {
    const { profile } = await import('./api')
    const { setToken } = await import('./session')
    setToken('tok-4')
    const view = { employee_id: 'E01', fields: { base: 1 }, sources: { base: 'profile' }, group: null }
    const fetchImpl = vi.fn().mockResolvedValue(ok(view))
    expect(await profile(fetchImpl)).toEqual(view)
    expect(fetchImpl.mock.calls[0][0]).toMatch(/\/profile$/)
    expect(fetchImpl.mock.calls[0][1].headers.Authorization).toBe('Bearer tok-4')
  })

  it('saveProfile: PATCH {fields} -> { profile }, or { invalid } on 422', async () => {
    const { saveProfile } = await import('./api')
    const view = { employee_id: 'E01', fields: { base: 2 }, sources: {}, group: null }
    let fetchImpl = vi.fn().mockResolvedValue(ok(view))
    expect(await saveProfile({ base: 2 }, { fetchImpl })).toEqual({ profile: view })
    const [, init] = fetchImpl.mock.calls[0]
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(init.body)).toEqual({ fields: { base: 2 } })
    const invalid = { base: { range: [1, 500000] } }
    fetchImpl = vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: { invalid } }) })
    expect(await saveProfile({ base: 0 }, { fetchImpl })).toEqual({ invalid })
    fetchImpl = vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) })
    await expect(saveProfile({ base: 3 }, { fetchImpl })).rejects.toMatchObject({ status: 500 })
    fetchImpl = vi.fn().mockResolvedValue(ok(view))
    await saveProfile({}, { address: 'female', fetchImpl })
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({ fields: {}, address: 'female' })
  })

  it('settings and saveSettings: GET and PATCH /settings, with the token', async () => {
    const { settings, saveSettings } = await import('./api')
    const { setToken } = await import('./session')
    setToken('tok-5')
    let fetchImpl = vi.fn().mockResolvedValue(ok({ theme: 'light', tone: 'professional' }))
    expect(await settings(fetchImpl)).toEqual({ theme: 'light', tone: 'professional' })
    expect(fetchImpl.mock.calls[0][0]).toMatch(/\/settings$/)
    expect(fetchImpl.mock.calls[0][1].headers.Authorization).toBe('Bearer tok-5')
    fetchImpl = vi.fn().mockResolvedValue(ok({ theme: 'dark', tone: 'professional' }))
    expect(await saveSettings({ theme: 'dark' }, fetchImpl)).toEqual({ theme: 'dark', tone: 'professional' })
    const [, init] = fetchImpl.mock.calls[0]
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(init.body)).toEqual({ theme: 'dark' })
    expect(init.headers.Authorization).toBe('Bearer tok-5')
  })

  it('usage gives this week\'s usage, with the token', async () => {
    const { usage } = await import('./api')
    const { setToken } = await import('./session')
    setToken('tok-6')
    const view = { used: 1, limit: 2, remaining: 1, avg_tokens_per_conversation: 1, conversations_left: 1,
      blocked: false, resets_on: '2026-10-25' }
    const fetchImpl = vi.fn().mockResolvedValue(ok(view))
    expect(await usage(fetchImpl)).toEqual(view)
    expect(fetchImpl.mock.calls[0][0]).toMatch(/\/usage$/)
    expect(fetchImpl.mock.calls[0][1].headers.Authorization).toBe('Bearer tok-6')
  })

  it('me gives the logged-in employee (the name for the sidebar), with the token', async () => {
    const { me } = await import('./api')
    const { setToken } = await import('./session')
    setToken('tok-3')
    const fetchImpl = vi.fn().mockResolvedValue(ok({ employee_id: 'E01', name: 'נועה לוי' }))
    expect(await me(fetchImpl)).toEqual({ employee_id: 'E01', name: 'נועה לוי' })
    expect(fetchImpl.mock.calls[0][0]).toMatch(/\/me$/)
    expect(fetchImpl.mock.calls[0][1].headers.Authorization).toBe('Bearer tok-3')
  })
})

describe('payslip upload', () => {
  it('posts the file itself as the body, with its type and the login token', async () => {
    const { streamPayslip } = await import('./api')
    sessionStorage.setItem('employeeToken', 'tok')
    const fetchImpl = vi.fn().mockResolvedValue(sseResponse([
      'event: payslip\ndata: {"status":"ok","fields":{"base":12000}}\n\n', 'event: done\ndata: {}\n\n',
    ]))
    const file = new File(['png-bytes'], 'tlush.png', { type: 'image/png' })
    const got = []
    await streamPayslip('tid-1', file, (e, d) => got.push([e, d]), fetchImpl)
    const [url, init] = fetchImpl.mock.calls[0]
    expect(url).toMatch(/\/chat\/tid-1\/payslip$/)
    expect(init.method).toBe('POST')
    expect(init.body).toBe(file)
    expect(init.headers['Content-Type']).toBe('image/png')
    expect(init.headers.Authorization).toBe('Bearer tok')
    expect(got).toEqual([['payslip', { status: 'ok', fields: { base: 12000 } }], ['done', {}]])
  })

  it.each([413, 415, 422])('a refused file (%i) comes back as "rejected" with the server\'s text', async (status) => {
    const { streamPayslip } = await import('./api')
    const fetchImpl = vi.fn().mockResolvedValue({ ok: false, status, json: async () => ({ detail: 'אפשר להעלות רק JPG, PNG או PDF.' }) })
    const got = []
    await streamPayslip('t', new File(['x'], 'a.gif', { type: 'image/gif' }), (e, d) => got.push([e, d]), fetchImpl)
    expect(got).toEqual([['rejected', { message: 'אפשר להעלות רק JPG, PNG או PDF.' }]])
  })

  it('the stored image: a local URL for the screen, or null when there is none', async () => {
    const { payslipImage } = await import('./api')
    URL.createObjectURL = vi.fn(() => 'blob:tlush')
    const blob = new Blob(['jpg'], { type: 'image/jpeg' })
    const ok = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => blob })
    expect(await payslipImage('t', ok)).toBe('blob:tlush')
    expect(ok.mock.calls[0][0]).toMatch(/\/chat\/t\/payslip$/)
    expect(await payslipImage('t', vi.fn().mockResolvedValue({ ok: false, status: 404 }))).toBeNull()
  })
})

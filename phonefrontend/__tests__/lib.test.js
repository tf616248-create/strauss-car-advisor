// The connection to the server: the same API as the website (frontend/src/lib), on a phone.
import { apiBase, streamChat, login, threads, restore } from '../src/lib/api'
import { clearSession, getToken, setToken, setUnauthorizedHandler, getCurrentThread, setCurrentThread } from '../src/lib/session'
import { subscribeChanges } from '../src/lib/realtime'

function streamBody(chunks) {
  const enc = new TextEncoder()
  let i = 0
  return { getReader: () => ({ read: async () => (i < chunks.length ? { value: enc.encode(chunks[i++]), done: false } : { done: true }) }) }
}
const fakeFetch = (res) => jest.fn(async () => ({ ok: true, status: 200, ...res }))

beforeEach(() => { clearSession(); setUnauthorizedHandler(() => {}) })

test('the server address: EXPO_PUBLIC_API_URL, without a trailing slash', () => {
  expect(apiBase({ EXPO_PUBLIC_API_URL: 'https://api.example.com/' }, false)).toBe('https://api.example.com')
  expect(apiBase({}, true)).toBe('http://localhost:8000')
  expect(apiBase({}, false)).toBe('')
})

test('the session lives only while the app is open (memory)', () => {
  setToken('t1'); setCurrentThread('th1')
  expect(getToken()).toBe('t1'); expect(getCurrentThread()).toBe('th1')
  clearSession()
  expect(getToken()).toBeNull(); expect(getCurrentThread()).toBeNull()
})

test('streamChat sends the token and the thread, and parses the stream across chunks', async () => {
  setToken('tok')
  const f = fakeFetch({ body: streamBody(['event: token\ndata: {"text":"של', 'ום"}\n\nevent: done\ndata: {}\n\n']) })
  const events = []
  await streamChat({ message: 'היי', threadId: 'th' }, (e, d) => events.push([e, d]), f)
  const [, init] = f.mock.calls[0]
  expect(init.headers.Authorization).toBe('Bearer tok')
  expect(JSON.parse(init.body)).toEqual({ message: 'היי', thread_id: 'th' })
  expect(events).toEqual([['token', { text: 'שלום' }], ['done', {}]])
})

test('401 logs out with no message; 429 and a network error say what to do', async () => {
  setToken('tok')
  const out = jest.fn()
  setUnauthorizedHandler(out)
  const events = []
  await streamChat({ message: 'x' }, (e, d) => events.push(d.message), fakeFetch({ ok: false, status: 401 }))
  expect(out).toHaveBeenCalled(); expect(getToken()).toBeNull(); expect(events).toEqual([])
  await streamChat({ message: 'x' }, (e, d) => events.push(d.message), fakeFetch({ ok: false, status: 429 }))
  await streamChat({ message: 'x' }, (e, d) => events.push(d.message), jest.fn(async () => { throw new Error('offline') }))
  expect(events).toEqual(['כובי עמוס כרגע. נסו שוב בעוד רגע.', 'כובי לא מצליח להתחבר כרגע. נסו שוב בעוד דקה.'])
})

test('login and threads', async () => {
  const f = fakeFetch({ json: async () => ({ token: 't', employee_id: 'E01' }) })
  expect(await login('1111', f)).toEqual({ token: 't', employee_id: 'E01' })
  expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ code: '1111' })
  const wrong = fakeFetch({ ok: false, status: 401 })
  await expect(login('0', wrong)).rejects.toMatchObject({ status: 401 })
  setToken('t')
  const list = fakeFetch({ json: async () => ({ threads: [{ thread_id: 'a' }] }) })
  expect(await threads(list)).toEqual([{ thread_id: 'a' }])
  expect(list.mock.calls[0][1].headers.Authorization).toBe('Bearer t')
  await expect(restore('a', fakeFetch({ ok: false, status: 401 }))).rejects.toMatchObject({ status: 401 })
  expect(getToken()).toBeNull()
})

test('subscribeChanges: the token in the address, "changed" and "open", and close', () => {
  setToken('a b')
  const handlers = {}
  const close = jest.fn()
  let url
  class FakeES { constructor(u) { url = u } addEventListener(n, fn) { handlers[n] = fn } close() { close() } }
  const onChanged = jest.fn(); const onOpen = jest.fn()
  const stop = subscribeChanges('th', { onChanged, onOpen }, FakeES)
  expect(url).toMatch(/\/conversations\/th\/events\?token=a%20b$/)
  handlers.changed(); handlers.open()
  expect(onChanged).toHaveBeenCalled(); expect(onOpen).toHaveBeenCalled()
  stop()
  expect(close).toHaveBeenCalled()
})

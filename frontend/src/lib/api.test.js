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
      'event: step\ndata: {"tool":"calculate","label":"מחשב נטו…"}\n\n',
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
    expect(got[0][0]).toBe('error')
  })
})

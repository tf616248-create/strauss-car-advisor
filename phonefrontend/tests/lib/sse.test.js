import { createSSEParser } from '@/lib/sse'

describe('createSSEParser', () => {
  it('parses whole events', () => {
    const got = []
    const p = createSSEParser((e, d) => got.push([e, d]))
    p.feed('event: token\ndata: {"text":"שלום"}\n\nevent: done\ndata: {}\n\n')
    expect(got).toEqual([['token', { text: 'שלום' }], ['done', {}]])
  })

  it('handles events split across chunks and CRLF', () => {
    const got = []
    const p = createSSEParser((e, d) => got.push([e, d]))
    p.feed('event: ca')
    p.feed('rd\r\ndata: {"status":"ok",')
    p.feed('"card":{}}\r\n\r\n')
    expect(got).toEqual([['card', { status: 'ok', card: {} }]])
  })
})

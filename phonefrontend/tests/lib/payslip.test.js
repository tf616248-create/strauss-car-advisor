// The payslip on a phone: the checks before sending (like the website's lib/payslip.js), the three
// pickers (camera, gallery, file), the upload (the file itself is the body) and the server's image.
import { checkAsset, pickPayslip } from '@/lib/payslip'
import { payslipSource, streamPayslip } from '@/lib/api'
import { clearSession, setToken, setUnauthorizedHandler } from '@/lib/session'
const cfg = require('@/config/payslip.json')

beforeEach(() => { clearSession(); setUnauthorizedHandler(() => {}) })

test('only JPG, PNG or PDF, up to 10MB (by the type, or the name when the type is missing)', () => {
  expect(checkAsset({ name: 'a.jpg', type: 'image/jpeg', size: 1000 })).toEqual({ kind: 'image' })
  expect(checkAsset({ name: 'IMG_1.PNG', size: 1000 })).toEqual({ kind: 'image' })
  expect(checkAsset({ name: 'tlush.pdf', type: 'application/pdf', size: 1000 })).toEqual({ kind: 'pdf' })
  expect(checkAsset({ name: 'a.heic', type: 'image/heic', size: 1000 })).toEqual({ error: cfg.texts.badType })
  expect(checkAsset({ name: 'a.jpg', type: 'image/jpeg', size: cfg.maxBytes + 1 })).toEqual({ error: cfg.texts.tooLarge })
  expect(checkAsset({ name: 'a.jpg', type: 'image/jpeg' })).toEqual({ kind: 'image' }) // size unknown: the server checks
})

const asset = { uri: 'file:///x/IMG_1.jpg', fileName: 'IMG_1.jpg', mimeType: 'image/jpeg', fileSize: 2000 }
function fakePickers(over = {}) {
  return {
    cameraPermission: jest.fn(async () => ({ granted: true })),
    camera: jest.fn(async () => ({ canceled: false, assets: [asset] })),
    gallery: jest.fn(async () => ({ canceled: false, assets: [asset] })),
    file: jest.fn(async () => ({ canceled: false, assets: [{ uri: 'file:///d/tlush.pdf', name: 'tlush.pdf', mimeType: 'application/pdf', size: 5000 }] })),
    ...over,
  }
}

test('each source gives one attachment: its address, name, type and kind', async () => {
  const p = fakePickers()
  expect(await pickPayslip('camera', p)).toEqual({ uri: asset.uri, name: 'IMG_1.jpg', type: 'image/jpeg', kind: 'image' })
  expect(await pickPayslip('gallery', p)).toMatchObject({ kind: 'image' })
  expect(await pickPayslip('file', p)).toEqual({ uri: 'file:///d/tlush.pdf', name: 'tlush.pdf', type: 'application/pdf', kind: 'pdf' })
  expect(p.cameraPermission).toHaveBeenCalledTimes(1)
})

test('a camera photo without a name or type is still a JPEG image', async () => {
  const p = fakePickers({ camera: jest.fn(async () => ({ canceled: false, assets: [{ uri: 'file:///c/photo' }] })) })
  expect(await pickPayslip('camera', p)).toEqual({ uri: 'file:///c/photo', name: 'photo.jpg', type: 'image/jpeg', kind: 'image' })
})

test('cancelled: nothing; no camera permission or a bad file: an error to show', async () => {
  expect(await pickPayslip('gallery', fakePickers({ gallery: jest.fn(async () => ({ canceled: true, assets: null })) }))).toBeNull()
  const denied = fakePickers({ cameraPermission: jest.fn(async () => ({ granted: false })) })
  expect(await pickPayslip('camera', denied)).toEqual({ error: cfg.texts.noCamera })
  expect(denied.camera).not.toHaveBeenCalled()
  const big = fakePickers({ gallery: jest.fn(async () => ({ canceled: false, assets: [{ ...asset, fileSize: cfg.maxBytes + 1 }] })) })
  expect(await pickPayslip('gallery', big)).toEqual({ error: cfg.texts.tooLarge })
})

function streamBody(chunks) {
  const enc = new TextEncoder()
  let i = 0
  return { getReader: () => ({ read: async () => (i < chunks.length ? { value: enc.encode(chunks[i++]), done: false } : { done: true }) }) }
}

test('the upload: the file itself is the body, with its type and the token; the events stream back', async () => {
  setToken('tok')
  const body = { file: 'the bytes' }
  const makeBody = jest.fn(() => body)
  const f = jest.fn(async () => ({ ok: true, status: 200, body: streamBody(['event: payslip\ndata: {"status":"ok"}\n\nevent: done\ndata: {}\n\n']) }))
  const events = []
  await streamPayslip('th1', { uri: 'file:///x.jpg', type: 'image/jpeg' }, (e, d) => events.push([e, d]), f, makeBody)
  const [url, init] = f.mock.calls[0]
  expect(url).toMatch(/\/chat\/th1\/payslip$/)
  expect(makeBody).toHaveBeenCalledWith('file:///x.jpg')
  expect(init).toMatchObject({ method: 'POST', body })
  expect(init.headers).toEqual({ 'Content-Type': 'image/jpeg', Authorization: 'Bearer tok' })
  expect(events).toEqual([['payslip', { status: 'ok' }], ['done', {}]])
})

test('a file the server refuses (413, 415, 422): its own text, as "rejected"', async () => {
  setToken('tok')
  for (const status of [413, 415, 422]) {
    const f = jest.fn(async () => ({ ok: false, status, json: async () => ({ detail: `נדחה ${status}` }) }))
    const events = []
    await streamPayslip('th1', { uri: 'file:///x.pdf', type: 'application/pdf' }, (e, d) => events.push([e, d]), f, () => ({}))
    expect(events).toEqual([['rejected', { message: `נדחה ${status}` }]])
  }
})

test('the image kept with the conversation: an image source with the token (no download of our own)', () => {
  setToken('tok')
  expect(payslipSource('th9')).toEqual({ uri: expect.stringMatching(/\/chat\/th9\/payslip$/), headers: { Authorization: 'Bearer tok' } })
})

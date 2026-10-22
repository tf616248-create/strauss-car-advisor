// The employee's own routes, like the website's lib/api.js: me, the profile (and saving it), the settings, the usage.
import { me, profile, saveProfile, settings, saveSettings, usage } from '@/lib/api'
import { clearSession, setToken, setUnauthorizedHandler } from '@/lib/session'

beforeEach(() => { clearSession(); setUnauthorizedHandler(() => {}); setToken('tok') })
const ok = (body) => jest.fn(async () => ({ ok: true, status: 200, json: async () => body }))

test('me, profile, settings and usage: with the token', async () => {
  for (const [call, path] of [[me, '/me'], [profile, '/profile'], [settings, '/settings'], [usage, '/usage']]) {
    const f = ok({ x: 1 })
    expect(await call(f)).toEqual({ x: 1 })
    expect(f.mock.calls[0][0]).toMatch(new RegExp(`${path}$`))
    expect(f.mock.calls[0][1].headers.Authorization).toBe('Bearer tok')
  }
})

test('saving the profile: only the fields, or with the form of address; 422 gives the reasons per field', async () => {
  const f = ok({ fields: { base: 15000 } })
  expect(await saveProfile({ base: 15000 }, { fetchImpl: f })).toEqual({ profile: { fields: { base: 15000 } } })
  expect(f.mock.calls[0][1]).toMatchObject({ method: 'PATCH' })
  expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ fields: { base: 15000 } })
  const g = ok({})
  await saveProfile({}, { address: 'female', fetchImpl: g })
  expect(JSON.parse(g.mock.calls[0][1].body)).toEqual({ fields: {}, address: 'female' })
  const bad = jest.fn(async () => ({ ok: false, status: 422, json: async () => ({ detail: { invalid: { base: { range: [0, 100000] } } } }) }))
  expect(await saveProfile({ base: -5 }, { fetchImpl: bad })).toEqual({ invalid: { base: { range: [0, 100000] } } })
})

test('saving the settings: PATCH with the values', async () => {
  const f = ok({ theme: 'dark', tone: 'professional' })
  expect(await saveSettings({ theme: 'dark' }, f)).toEqual({ theme: 'dark', tone: 'professional' })
  expect(f.mock.calls[0][1]).toMatchObject({ method: 'PATCH', body: JSON.stringify({ theme: 'dark' }) })
})

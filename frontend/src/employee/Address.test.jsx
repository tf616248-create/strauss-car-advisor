// The employee's name and form of address: the welcome greets by first name (the template in config),
// and "פנייה" (male / female / plural, plural until chosen) is a field in the profile dialog.
import { readFileSync } from 'node:fs'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import chatCfg from '../config/chat.json'
import profileCfg from '../config/profile.json'
import EmployeeScreen from './EmployeeScreen'

const P = profileCfg.texts
const VIEW = { employee_id: 'E01', fields: { base: 14200 }, sources: { base: 'profile' }, group: null, address: 'plural' }

function setup({ name = 'נועה לוי', view = VIEW, save } = {}) {
  const api = {
    streamChat: vi.fn(),
    streamRepAnswered: vi.fn(),
    restore: vi.fn().mockRejectedValue(new Error('none')),
    threads: vi.fn().mockResolvedValue([]),
    me: vi.fn().mockResolvedValue({ employee_id: 'E01', name }),
    profile: vi.fn().mockResolvedValue(view),
    saveProfile: save ?? vi.fn(async (fields, { address } = {}) => ({ profile: { ...view, address: address ?? view.address } })),
  }
  render(<EmployeeScreen api={api} subscribe={() => () => {}} notifier={{ beep: vi.fn(), setUnread: vi.fn() }} />)
  return api
}

beforeEach(() => { window.history.replaceState(null, '', '/'); sessionStorage.clear() })
afterEach(() => vi.restoreAllMocks())

describe('the welcome', () => {
  it('greets by first name, from the template in the config', async () => {
    setup()
    const title = chatCfg.welcomeNamed.replace('{name}', 'נועה')
    expect(await screen.findByRole('heading', { name: title })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: title })).toBeInTheDocument()
  })

  it('without a name, the welcome as it was', async () => {
    const api = setup({ name: null })
    await waitFor(() => expect(api.me).toHaveBeenCalled())
    expect(screen.getByRole('heading', { name: chatCfg.welcome })).toBeInTheDocument()
  })

  it('before the name arrives, the welcome without it (no empty "שלום ,")', () => {
    setup()
    expect(screen.getByRole('heading', { name: chatCfg.welcome })).toBeInTheDocument()
  })
})

describe('"פנייה" in the profile', () => {
  const open = async (user) => {
    await user.click(screen.getByRole('button', { name: 'פרופיל' }))
    return screen.findByRole('dialog', { name: P.title })
  }

  it('three options with clear labels; plural until chosen', async () => {
    setup()
    const dialog = await open(userEvent.setup())
    const group = await within(dialog).findByRole('radiogroup', { name: P.address })
    for (const [value, label] of Object.entries(P.addresses)) {
      const radio = within(group).getByRole('radio', { name: label })
      expect(radio).toHaveAttribute('value', value)
    }
    expect(within(group).getByRole('radio', { name: P.addresses.plural })).toBeChecked()
    expect(group).toHaveAccessibleDescription(P.addressHint)
  })

  it('the kept choice is shown', async () => {
    setup({ view: { ...VIEW, address: 'female' } })
    const dialog = await open(userEvent.setup())
    expect(await within(dialog).findByRole('radio', { name: P.addresses.female })).toBeChecked()
  })

  it('saved with the profile: only the form of address when only it changed', async () => {
    const api = setup()
    const user = userEvent.setup()
    const dialog = await open(user)
    await user.click(await within(dialog).findByRole('radio', { name: P.addresses.male }))
    await user.click(within(dialog).getByRole('button', { name: P.save }))
    expect(api.saveProfile).toHaveBeenCalledWith({}, { address: 'male' })
    expect(await within(dialog).findByText(P.saved)).toBeInTheDocument()
  })

  it('a field and the form of address together, in one save', async () => {
    const api = setup()
    const user = userEvent.setup()
    const dialog = await open(user)
    const bonus = await within(dialog).findByLabelText(profileCfg.fields.find((f) => f.name === 'bonus').label)
    await user.type(bonus, '500')
    await user.click(within(dialog).getByRole('radio', { name: P.addresses.female }))
    await user.click(within(dialog).getByRole('button', { name: P.save }))
    expect(api.saveProfile).toHaveBeenCalledWith({ bonus: 500 }, { address: 'female' })
  })

  it('a refused form of address shows its error next to it', async () => {
    const save = vi.fn().mockResolvedValue({ invalid: { address: { options: ['male', 'female', 'plural'] } } })
    setup({ save })
    const user = userEvent.setup()
    const dialog = await open(user)
    await user.click(await within(dialog).findByRole('radio', { name: P.addresses.male }))
    await user.click(within(dialog).getByRole('button', { name: P.save }))
    const group = within(dialog).getByRole('radiogroup', { name: P.address })
    await waitFor(() => expect(group).toHaveAccessibleDescription(expect.stringContaining(P.options)))
  })
})

describe('the fixed texts that speak to the employee are neutral', () => {
  // one wording for a man, a woman or many: "אפשר לנסות שוב", not "נסו שוב"
  const NOT_NEUTRAL = /(נסו |נסו\.|שלכם|תוכלו|רוצים|תרצו)/
  it.each([
    ['src/lib/api.js', /const (NETWORK_ERROR|BUSY) = '([^']+)'/g],
    ['src/components/Login.jsx', /return '([^']+)'/g],
  ])('%s', (file, pattern) => {
    const texts = [...readFileSync(file, 'utf8').matchAll(pattern)].map((m) => m.at(-1))
    expect(texts.length).toBeGreaterThan(1)
    expect(texts.filter((t) => NOT_NEUTRAL.test(t))).toEqual([])
  })

  it('the error texts in the profile and settings windows', async () => {
    const settings = (await import('../config/settings.json')).default
    for (const t of [P.loadError, P.saveError, settings.texts.saveError]) expect(t).not.toMatch(NOT_NEUTRAL)
  })
})

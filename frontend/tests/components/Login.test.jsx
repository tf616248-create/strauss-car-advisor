import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { getToken } from '@/lib/session'
import Login from '@/components/Login'
import intro from '@/config/intro.json'

const fail = (status) => vi.fn().mockRejectedValue(Object.assign(new Error('x'), { status }))

async function enter(code, api) {
  const onLogin = vi.fn()
  render(<Login api={api} onLogin={onLogin} />)
  const user = userEvent.setup()
  if (code) await user.type(screen.getByLabelText('קוד עובד'), code)
  await user.click(screen.getByRole('button', { name: intro.texts.enterLabel }))
  return onLogin
}

describe('Login', () => {
  it('a right code keeps the token for this tab and lets the employee in', async () => {
    const api = { login: vi.fn().mockResolvedValue({ token: 'tok', employee_id: 'E01' }) }
    const onLogin = await enter('1111', api)
    expect(api.login).toHaveBeenCalledWith('1111')
    expect(getToken()).toBe('tok')
    expect(onLogin).toHaveBeenCalled()
  })

  it('the code field is hidden like a password and asks for digits', () => {
    render(<Login api={{ login: vi.fn() }} onLogin={vi.fn()} />)
    const field = screen.getByLabelText('קוד עובד')
    expect(field).toHaveAttribute('type', 'password')
    expect(field).toHaveAttribute('inputmode', 'numeric')
  })

  it('an empty code is not sent', async () => {
    const api = { login: vi.fn() }
    await enter('', api)
    expect(api.login).not.toHaveBeenCalled()
  })

  it.each([
    [401, 'הקוד לא נכון. אפשר לנסות שוב.'],
    [429, 'יותר מדי ניסיונות. אפשר לנסות שוב בעוד כמה דקות.'],
    [503, 'הכניסה סגורה כרגע: לא הוגדרו קודים בשרת.'],
    [undefined, 'כובי לא מצליח להתחבר כרגע. אפשר לנסות שוב בעוד דקה.'],
  ])('error %s says what to do', async (status, text) => {
    const onLogin = await enter('9999', { login: fail(status) })
    expect(await screen.findByRole('alert')).toHaveTextContent(text)
    expect(onLogin).not.toHaveBeenCalled()
    expect(getToken()).toBeNull()
  })

  it('says it is Kobi (the h1 is the slogan above it, in the intro)', () => {
    render(<Login api={{ login: vi.fn() }} onLogin={vi.fn()} />)
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('כובי')
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull()
  })
})

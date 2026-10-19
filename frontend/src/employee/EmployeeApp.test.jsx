import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { getToken, setCurrentThread, setToken, unauthorized } from '../lib/session'
import EmployeeApp from './EmployeeApp'

const api = {
  login: vi.fn().mockResolvedValue({ token: 'tok', employee_id: 'E01' }),
  threads: vi.fn().mockResolvedValue([]),
  restore: vi.fn().mockRejectedValue(new Error('none')),
  streamChat: vi.fn(),
  streamRepAnswered: vi.fn(),
}
const props = { api, subscribe: () => () => {}, notifier: { beep: vi.fn(), setUnread: vi.fn() } }

describe('EmployeeApp', () => {
  it('without a login: the login screen', () => {
    render(<EmployeeApp {...props} />)
    expect(screen.getByLabelText('קוד עובד')).toBeInTheDocument()
    expect(screen.queryByLabelText('הודעה')).toBeNull()
  })

  it('after the code: the chat', async () => {
    render(<EmployeeApp {...props} />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('קוד עובד'), '1111')
    await user.click(screen.getByRole('button', { name: 'כניסה' }))
    expect(await screen.findByLabelText('הודעה')).toBeInTheDocument()
  })

  it('"logout" forgets the login and the open conversation in this tab', async () => {
    setToken('tok')
    setCurrentThread('11111111-2222-3333-4444-555555555555')
    render(<EmployeeApp {...props} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'יציאה' }))
    expect(screen.getByLabelText('קוד עובד')).toBeInTheDocument()
    expect(getToken()).toBeNull()
    expect(sessionStorage.getItem('threadId')).toBeNull()
  })

  it('an expired login (401 from the server) goes back to the login screen', async () => {
    setToken('tok')
    render(<EmployeeApp {...props} />)
    expect(screen.getByLabelText('הודעה')).toBeInTheDocument()
    act(() => unauthorized())
    expect(screen.getByLabelText('קוד עובד')).toBeInTheDocument()
  })
})

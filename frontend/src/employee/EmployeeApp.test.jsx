import { readFileSync } from 'node:fs'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import intro from '../config/intro.json'
import { getToken, setCurrentThread, setToken, unauthorized } from '../lib/session'
import EmployeeApp from './EmployeeApp'

const T = intro.texts
const api = {
  login: vi.fn().mockResolvedValue({ token: 'tok', employee_id: 'E01' }),
  threads: vi.fn().mockResolvedValue([]),
  restore: vi.fn().mockRejectedValue(new Error('none')),
  streamChat: vi.fn(),
  streamRepAnswered: vi.fn(),
}
const props = { api, subscribe: () => () => {}, notifier: { beep: vi.fn(), setUnread: vi.fn() } }
const skip = (user) => user.click(screen.getByRole('button', { name: T.skipLabel }))
const enter = () => screen.getByRole('button', { name: T.enterLabel })

describe('EmployeeApp', () => {
  it('every visit opens with the intro; without a login, its card asks for the code', async () => {
    render(<EmployeeApp {...props} />)
    expect(document.querySelector('video')).toBeInTheDocument()
    expect(screen.queryByLabelText('הודעה')).toBeNull()
    await skip(userEvent.setup())
    expect(screen.getByLabelText(T.code)).toBeInTheDocument()
  })

  it('after the code: the picture shrinks to a banner, the chat comes in below, the focus is in the box', async () => {
    render(<EmployeeApp {...props} />)
    const user = userEvent.setup()
    await skip(user)
    await user.type(screen.getByLabelText(T.code), '1111')
    await user.click(enter())
    const box = await screen.findByLabelText('הודעה')
    expect(box).toHaveFocus()
    expect(document.querySelector('.intro')).toHaveClass('intro--banner')
    expect(document.querySelector('.intro__slogan')).toHaveTextContent(T.slogan) // the slogan stays, small
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('כובי') // one h1: the chat's
  })

  it('under the banner the chat keeps its full height; the page scrolls instead', () => {
    const css = readFileSync('src/styles.css', 'utf8')
    expect(css).toMatch(/\.employee \{[^}]*height:\s*100vh/)
    expect(css).not.toMatch(/\.shell--inside \.employee \{[^}]*height/)
  })

  it('with a login already: the same intro, only the button, then the chat', async () => {
    setToken('tok')
    render(<EmployeeApp {...props} />)
    const user = userEvent.setup()
    await skip(user)
    expect(screen.queryByLabelText(T.code)).toBeNull()
    await user.click(enter())
    expect(await screen.findByLabelText('הודעה')).toHaveFocus()
  })

  it('"logout" (in the sidebar) forgets the login and the open conversation, and replays the intro with the video', async () => {
    setToken('tok')
    setCurrentThread('11111111-2222-3333-4444-555555555555')
    render(<EmployeeApp {...props} />)
    const user = userEvent.setup()
    await skip(user)
    await user.click(enter())
    await user.click(await screen.findByRole('button', { name: 'יציאה' }))
    expect(document.querySelector('video')).toBeInTheDocument()
    expect(screen.queryByLabelText('הודעה')).toBeNull()
    await skip(user)
    expect(screen.getByLabelText(T.code)).toBeInTheDocument()
    expect(getToken()).toBeNull()
    expect(sessionStorage.getItem('threadId')).toBeNull()
  })

  it('an expired login (401 from the server) goes back to the card, without the video', async () => {
    setToken('tok')
    render(<EmployeeApp {...props} />)
    const user = userEvent.setup()
    await skip(user)
    await user.click(enter())
    expect(await screen.findByLabelText('הודעה')).toBeInTheDocument()
    act(() => unauthorized())
    expect(screen.getByLabelText(T.code)).toBeInTheDocument()
    expect(document.querySelector('video')).toBeNull()
    expect(screen.queryByLabelText('הודעה')).toBeNull()
  })
})

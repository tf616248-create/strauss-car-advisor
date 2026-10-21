// A screen reader hears Kobi's answer once, when it is ready - not letter by letter while it
// streams - and hears "כובי מקליד…" when the answer starts.
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import a11y from '../config/accessibility.json'
import EmployeeScreen from './EmployeeScreen'

const quiet = { subscribe: () => () => {}, notifier: { beep: vi.fn(), setUnread: vi.fn() } }

// a stream we hold open: the test lets it go on step by step
function heldStream() {
  let push, finish
  const done = new Promise((r) => { finish = r })
  const streamChat = vi.fn(async (p, onEvent) => { push = onEvent; await done })
  return { streamChat, push: (e, d) => act(() => push(e, d)), finish: () => act(async () => { finish() }) }
}

function setup(streamChat) {
  const api = { streamChat, streamRepAnswered: vi.fn(), restore: vi.fn().mockRejectedValue(new Error('x')), threads: vi.fn().mockResolvedValue([]) }
  render(<EmployeeScreen api={api} {...quiet} />)
}

async function ask(text = 'שאלה') {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('הודעה'), text)
  await user.click(screen.getByRole('button', { name: 'שליחה' }))
}

const live = () => screen.getByRole('status', { name: a11y.live.name })

describe('the live region', () => {
  it('"כובי מקליד…" when the answer starts; then the whole answer once, as plain text', async () => {
    const s = heldStream()
    setup(s.streamChat)
    await ask()
    await waitFor(() => expect(live()).toHaveTextContent(a11y.live.typing))
    s.push('token', { text: 'הנטו ' })
    s.push('token', { text: '**עולה** ' })
    expect(live()).not.toHaveTextContent('הנטו') // nothing while it streams
    s.push('token', { text: 'ב-661 ₪.' })
    s.push('done', {})
    await s.finish()
    await waitFor(() => expect(live()).toHaveTextContent(`${a11y.live.answered} הנטו עולה ב-661 ₪.`))
    expect(live().textContent).not.toContain('*')
    expect(live()).toHaveAttribute('aria-live', 'polite')
    expect(live()).toHaveAttribute('aria-atomic', 'true')
  })

  it('an error is announced too', async () => {
    setup(vi.fn(async (p, onEvent) => onEvent('error', { message: 'כובי עמוס כרגע. אפשר לנסות שוב בעוד רגע.' })))
    await ask()
    await waitFor(() => expect(live()).toHaveTextContent('כובי עמוס כרגע. אפשר לנסות שוב בעוד רגע.'))
  })

  it('the conversation itself is not a live region (no letter-by-letter reading)', () => {
    setup(vi.fn())
    const list = screen.getByRole('list', { name: 'השיחה' })
    expect(list).not.toHaveAttribute('aria-live')
  })

  it('the conversation can be scrolled from the keyboard', () => {
    setup(vi.fn())
    expect(screen.getByRole('list', { name: 'השיחה' })).toHaveAttribute('tabindex', '0')
  })

  it('"כובי מקליד…" is shown in the bubble until the first word', async () => {
    const s = heldStream()
    setup(s.streamChat)
    await ask()
    const list = screen.getByRole('list', { name: 'השיחה' })
    await waitFor(() => expect(within(list).getByText(a11y.live.typing)).toBeInTheDocument())
    s.push('token', { text: 'שלום' })
    expect(within(list).queryByText(a11y.live.typing)).toBeNull()
    await s.finish()
  })
})

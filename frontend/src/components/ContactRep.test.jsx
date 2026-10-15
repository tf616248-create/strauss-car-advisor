import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import ContactRep from './ContactRep'

const EMAIL = 'transport@example.com'

describe('ContactRep', () => {
  it('is closed until the employee clicks it', () => {
    render(<ContactRep email={EMAIL} />)
    const button = screen.getByRole('button', { name: 'שיחה עם נציג' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText(EMAIL)).toBeNull()
  })

  it('shows the service email as a link', async () => {
    const user = userEvent.setup()
    render(<ContactRep email={EMAIL} />)
    await user.click(screen.getByRole('button', { name: 'שיחה עם נציג' }))
    expect(screen.getByRole('button', { name: 'שיחה עם נציג' })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('link', { name: EMAIL })).toHaveAttribute('href', `mailto:${EMAIL}`)
  })

  it('closes with Escape and with the close button', async () => {
    const user = userEvent.setup()
    render(<ContactRep email={EMAIL} />)
    await user.click(screen.getByRole('button', { name: 'שיחה עם נציג' }))
    await user.keyboard('{Escape}')
    expect(screen.queryByText(EMAIL)).toBeNull()
    await user.click(screen.getByRole('button', { name: 'שיחה עם נציג' }))
    await user.click(screen.getByRole('button', { name: 'סגירה' }))
    expect(screen.queryByText(EMAIL)).toBeNull()
  })

  it('says so when no email is configured, instead of inventing one', async () => {
    const user = userEvent.setup()
    render(<ContactRep email="" />)
    await user.click(screen.getByRole('button', { name: 'שיחה עם נציג' }))
    expect(screen.getByText('כתובת המייל של השירות עוד לא הוגדרה.')).toBeInTheDocument()
    expect(screen.queryByRole('link')).toBeNull()
  })
})

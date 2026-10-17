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

  it('without VITE_SUPPORT_EMAIL it shows the service address support@strauss-in.com', async () => {
    const user = userEvent.setup()
    render(<ContactRep email="" />)
    await user.click(screen.getByRole('button', { name: 'שיחה עם נציג' }))
    expect(screen.getByRole('link', { name: 'support@strauss-in.com' })).toHaveAttribute('href', 'mailto:support@strauss-in.com')
    expect(screen.queryByText('כתובת המייל של השירות עוד לא הוגדרה.')).toBeNull()
  })

  it('opening the panel does not move the button: the panel floats above it', async () => {
    const user = userEvent.setup()
    const { container } = render(<ContactRep email={EMAIL} />)
    const button = screen.getByRole('button', { name: 'שיחה עם נציג' })
    await user.click(button)
    expect(screen.getByRole('button', { name: 'שיחה עם נציג' })).toBe(button) // same element, same place
    expect(container.querySelector('.contact__panel')).toHaveClass('contact__panel--floating')
  })
})

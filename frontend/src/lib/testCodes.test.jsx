// The test codes shown on the login screens - temporary, for testing only. To remove them:
// delete lib/testCodes.js, this file, and the <TestCodesNote> in Login.jsx and RepScreen.jsx.
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import Login from '../components/Login'
import RepScreen from '../rep/RepScreen'
import { TEST_EMPLOYEE_CODES, TEST_REP_PASSCODE } from './testCodes'

describe('test codes on the login screens (temporary)', () => {
  it('the employee login says which codes work, and that it is only for testing', () => {
    render(<Login api={{ login: vi.fn() }} onLogin={vi.fn()} />)
    const note = screen.getByRole('note', { name: 'קודים לבדיקות' })
    expect(note).toHaveTextContent('לבדיקות בלבד')
    expect(note).toHaveTextContent(TEST_EMPLOYEE_CODES)
    expect(TEST_EMPLOYEE_CODES).toBe('1111, 2222, 3333 … 9999')
  })

  it('the rep login says the passcode, and that it is only for testing', () => {
    sessionStorage.clear()
    render(<RepScreen api={{ repRequests: vi.fn(), repAnswer: vi.fn() }} />)
    const note = screen.getByRole('note', { name: 'קודים לבדיקות' })
    expect(note).toHaveTextContent('לבדיקות בלבד')
    expect(note).toHaveTextContent(TEST_REP_PASSCODE)
    expect(TEST_REP_PASSCODE).toBe('2222')
  })
})

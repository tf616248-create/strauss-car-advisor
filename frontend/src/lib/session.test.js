import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  clearSession, getCurrentThread, getToken, setCurrentThread, setToken, setUnauthorizedHandler, unauthorized,
} from './session'

afterEach(() => vi.restoreAllMocks())

describe('session (sessionStorage: gone when the tab closes - a shared computer)', () => {
  it('keeps the login token and the open conversation in this tab only', () => {
    setToken('tok')
    setCurrentThread('tid')
    expect(sessionStorage.getItem('employeeToken')).toBe('tok')
    expect(localStorage.length).toBe(0)
    expect(getToken()).toBe('tok')
    expect(getCurrentThread()).toBe('tid')
    setCurrentThread(null)
    expect(getCurrentThread()).toBeNull()
  })

  it('logging out forgets both', () => {
    setToken('tok')
    setCurrentThread('tid')
    clearSession()
    expect(getToken()).toBeNull()
    expect(getCurrentThread()).toBeNull()
  })

  it('a blocked storage (private mode, previews) does not break the screen', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    expect(() => setToken('tok')).not.toThrow()
    expect(getToken()).toBeNull()
  })

  it('an expired login (401) forgets the token and tells the screen', () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    setToken('tok')
    unauthorized()
    expect(getToken()).toBeNull()
    expect(handler).toHaveBeenCalledTimes(1)
    setUnauthorizedHandler(() => {})
  })
})

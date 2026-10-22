import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { EMPLOYEE_TITLE, REP_TITLE, setUnread } from '@/lib/notify'

describe('tab titles', () => {
  it('employee tab: Kobi, then the product', () => {
    expect(EMPLOYEE_TITLE).toBe('כובי · יועץ הרכב של שטראוס')
    expect(readFileSync('index.html', 'utf8')).toContain(`<title>${EMPLOYEE_TITLE}</title>`)
  })

  it('a new answer puts (1) in front; reading it takes it away', () => {
    setUnread(1)
    expect(document.title).toBe('(1) כובי · יועץ הרכב של שטראוס')
    setUnread(0)
    expect(document.title).toBe('כובי · יועץ הרכב של שטראוס')
  })

  it('rep tab: no Kobi', () => {
    expect(REP_TITLE).toBe('תור הנציג · יועץ הרכב של שטראוס')
    expect(REP_TITLE).not.toContain('כובי')
  })
})

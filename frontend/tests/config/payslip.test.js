import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import payslip from '@/config/payslip.json'

// The texts the server also says (the note in the history, the refusals) are one text, not two
describe('payslip settings', () => {
  const agent = JSON.parse(readFileSync('../backend/config/agent.json', 'utf8'))

  it('says the same as the server', () => {
    for (const key of ['shown', 'shownText', 'tooLarge', 'badType']) {
      expect(payslip.texts[key], key).toBe(agent.texts.payslip[key])
    }
    expect(payslip.maxBytes).toBe(agent.payslip.maxBytes)
  })
})

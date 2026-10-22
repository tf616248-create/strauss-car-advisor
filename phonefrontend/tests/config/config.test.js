// The app's settings files (src/config): the texts the server also says are the same as backend/config/agent.json
const payslip = require('@/config/payslip.json')
const agent = require('../../../backend/config/agent.json')

test('payslip: the same texts and size limit as the server', () => {
  expect(payslip.maxBytes).toBe(agent.payslip.maxBytes)
  for (const key of ['shown', 'tooLarge', 'badType']) expect(payslip.texts[key]).toBe(agent.texts.payslip[key])
})

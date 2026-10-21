// The app's texts (src/config/texts.json)
const texts = require('../src/config/texts.json')

test('the payslip line is short, and has a label for screen readers', () => {
  expect(texts.payslipLine).toBe('📄 תלוש שכר')
  expect(texts.payslipLabel).toBeTruthy()
})

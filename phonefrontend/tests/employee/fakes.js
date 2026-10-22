// A fake server (api) and no real-time connection, shared by the screen tests (not a test file itself).
import noa from '../fixtures/card-noa.json'

export function fakeApi(over = {}) {
  return {
    login: jest.fn(),
    threads: jest.fn(async () => []),
    restore: jest.fn(async () => ({ messages: [], cards: [], rep: { pending: 0, new_answers: 0 } })),
    streamChat: jest.fn(async (_body, onEvent) => {
      onEvent('thread', { thread_id: 'th1' })
      onEvent('step', { tool: 'calculate', label: 'כובי מחשב נטו…' })
      onEvent('card', noa)
      onEvent('token', { text: 'הנטו ' })
      onEvent('token', { text: 'עולה.' })
      onEvent('done', {})
    }),
    streamRepAnswered: jest.fn(async () => {}),
    streamPayslip: jest.fn(async (_tid, _att, onEvent) => {
      onEvent('step', { tool: 'payslip', label: 'כובי קורא את התלוש…' })
      onEvent('payslip', { status: 'ok', fields: { base: 15000 } })
      onEvent('token', { text: 'לקחתי מהתלוש: שכר בסיס.' })
      onEvent('done', {})
    }),
    payslipSource: jest.fn((tid) => ({ uri: `https://api.test/chat/${tid}/payslip`, headers: { Authorization: 'Bearer t' } })),
    me: jest.fn(async () => ({ employee_id: 'E01', name: 'נועה לוי' })),
    profile: jest.fn(async () => ({ employee_id: 'E01', fields: {}, sources: {}, group: null, address: 'plural' })),
    saveProfile: jest.fn(async () => ({ profile: { employee_id: 'E01', fields: {}, sources: {}, group: null, address: 'plural' } })),
    settings: jest.fn(async () => ({ theme: 'light', tone: 'professional', address: 'plural' })),
    saveSettings: jest.fn(async (v) => ({ theme: 'light', tone: 'professional', address: 'plural', ...v })),
    usage: jest.fn(async () => ({ used: 0, limit: 100, remaining: 100, avg_tokens_per_conversation: 10, conversations_left: 10, blocked: false, resets_on: '2026-10-25' })),
    ...over,
  }
}

export const quiet = () => ({ subscribe: () => () => {}, notifier: { beep: jest.fn(), setUnread: jest.fn() } })

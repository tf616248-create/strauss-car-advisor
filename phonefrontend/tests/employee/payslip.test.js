// The payslip on the employee screen: 📎 once there is a conversation, three sources, a preview before
// sending, the employee's bubble with a thumbnail, the large view, a refused file, and the image kept
// with a conversation that is opened again.
import { render, screen, fireEvent, waitFor } from '@testing-library/react-native'
import EmployeeScreen from '@/employee/EmployeeScreen'
import { clearSession, setToken } from '@/lib/session'
import { fakeApi, quiet } from './fakes'
const PT = require('@/config/payslip.json').texts

beforeEach(() => { clearSession(); setToken('t') })

const photo = { uri: 'file:///x/IMG_1.jpg', name: 'IMG_1.jpg', type: 'image/jpeg', kind: 'image' }

async function withConversation(api, pick) {
  await render(<EmployeeScreen api={api} pickPayslip={pick} {...quiet()} />)
  expect(screen.queryByLabelText(PT.attach)).toBeNull() // no conversation yet: the server takes a payslip only for one
  await fireEvent.changeText(screen.getByLabelText('הודעה'), 'שאלה')
  await fireEvent.press(screen.getByText('שליחה'))
  await screen.findByText('הנטו עולה.')
}

test('📎 opens the three sources; a photo is shown before sending, with ✕', async () => {
  const pick = jest.fn(async () => photo)
  await withConversation(fakeApi(), pick)
  await fireEvent.press(screen.getByLabelText(PT.attach))
  for (const s of [PT.camera, PT.gallery, PT.file]) expect(screen.getByLabelText(s)).toBeTruthy()
  await fireEvent.press(screen.getByLabelText(PT.gallery))
  expect(pick).toHaveBeenCalledWith('gallery')
  expect(await screen.findByTestId('payslip-preview')).toBeTruthy()
  await fireEvent.press(screen.getByLabelText(PT.remove))
  expect(screen.queryByTestId('payslip-preview')).toBeNull()
})

test('send: the file goes up, the bubble has its thumbnail, and it opens large', async () => {
  const api = fakeApi()
  await withConversation(api, jest.fn(async () => photo))
  await fireEvent.press(screen.getByLabelText(PT.attach))
  await fireEvent.press(screen.getByLabelText(PT.camera))
  await screen.findByTestId('payslip-preview')
  await fireEvent.press(screen.getByText('שליחה'))
  await screen.findByText('לקחתי מהתלוש: שכר בסיס.')
  expect(api.streamPayslip).toHaveBeenCalledWith('th1', photo, expect.any(Function))
  expect(screen.getByText(PT.shown)).toBeTruthy()
  expect(screen.queryByTestId('payslip-preview')).toBeNull()
  expect(screen.getByTestId('payslip-thumb').props.source).toEqual({ uri: photo.uri })
  await fireEvent.press(screen.getByLabelText(PT.open))
  expect(screen.getByTestId('payslip-large').props.source).toEqual({ uri: photo.uri })
  await fireEvent.press(screen.getByLabelText(PT.close))
  await waitFor(() => expect(screen.queryByTestId('payslip-large')).toBeNull())
})

test('a PDF: its name before sending; after it, the first page the server kept', async () => {
  const api = fakeApi()
  const pdf = { uri: 'file:///d/tlush.pdf', name: 'tlush.pdf', type: 'application/pdf', kind: 'pdf' }
  await withConversation(api, jest.fn(async () => pdf))
  await fireEvent.press(screen.getByLabelText(PT.attach))
  await fireEvent.press(screen.getByLabelText(PT.file))
  expect(await screen.findByText('tlush.pdf')).toBeTruthy()
  await fireEvent.press(screen.getByText('שליחה'))
  await screen.findByText('לקחתי מהתלוש: שכר בסיס.')
  expect(screen.getByTestId('payslip-thumb').props.source).toEqual(api.payslipSource('th1'))
})

test('a file the server refuses: its text next to the box, the preview stays, no bubble', async () => {
  const api = fakeApi({ streamPayslip: jest.fn(async (_t, _a, onEvent) => onEvent('rejected', { message: 'לא הצלחתי לקרוא את הקובץ.' })) })
  await withConversation(api, jest.fn(async () => photo))
  await fireEvent.press(screen.getByLabelText(PT.attach))
  await fireEvent.press(screen.getByLabelText(PT.gallery))
  await screen.findByTestId('payslip-preview')
  await fireEvent.press(screen.getByText('שליחה'))
  expect(await screen.findByText('לא הצלחתי לקרוא את הקובץ.')).toBeTruthy()
  expect(screen.getByTestId('payslip-preview')).toBeTruthy()
  expect(screen.queryByText(PT.shown)).toBeNull()
})

test('a check that fails before sending (e.g. too large) is said at once, nothing is attached', async () => {
  await withConversation(fakeApi(), jest.fn(async () => ({ error: PT.tooLarge })))
  await fireEvent.press(screen.getByLabelText(PT.attach))
  await fireEvent.press(screen.getByLabelText(PT.gallery))
  expect(await screen.findByText(PT.tooLarge)).toBeTruthy()
  expect(screen.queryByTestId('payslip-preview')).toBeNull()
})

test('a conversation opened again: the payslip line shows the image the server kept (with the token)', async () => {
  const api = fakeApi({
    threads: jest.fn(async () => [{ thread_id: 'a', title: 'שיחה', updated_at: '2026-10-20T10:00:00Z' }]),
    restore: jest.fn(async () => ({
      messages: [{ role: 'user', text: 'שאלה' }, { role: 'payslip', text: PT.shown }],
      cards: [], rep: { pending: 0, new_answers: 0 }, payslip: { source: 'image', fields: {}, image: '/chat/a/payslip' },
    })),
  })
  await render(<EmployeeScreen api={api} {...quiet()} />)
  expect(await screen.findByText(PT.shown)).toBeTruthy()
  expect(screen.getByTestId('payslip-thumb').props.source).toEqual({ uri: 'https://api.test/chat/a/payslip', headers: { Authorization: 'Bearer t' } })
  expect(screen.queryByText('כובי · בוט')).toBeNull() // the employee's bubble, never Kobi's
})

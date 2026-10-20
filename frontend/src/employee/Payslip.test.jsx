import { readFileSync } from 'node:fs'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import cfg from '../config/payslip.json'
import EmployeeScreen from './EmployeeScreen'

// Payslip upload on the employee screen: 📎, drag and drop, paste, the phone camera, the preview
// before sending, the thumbnail after, the large view, and the payslip coming back from the server.
const T = cfg.texts
const TID = '11111111-2222-3333-4444-555555555555'

const png = () => new File(['png-bytes'], 'tlush.png', { type: 'image/png' })
const pdf = () => new File(['%PDF-1.4'], 'tlush-october.pdf', { type: 'application/pdf' })

function phone(isPhone) {
  window.matchMedia = vi.fn((q) => ({
    matches: isPhone && q.includes('coarse'), media: q, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  }))
}

function setup({ payslipEvents, restore, payslipImage, withThread = true } = {}) {
  if (withThread) sessionStorage.setItem('threadId', TID)
  const api = {
    streamChat: vi.fn(async (p, onEvent) => { onEvent('token', { text: 'בסדר' }); onEvent('done', {}) }),
    streamRepAnswered: vi.fn(),
    streamPayslip: vi.fn(async (tid, file, onEvent) => {
      for (const [e, d] of payslipEvents ?? [['payslip', { status: 'ok', fields: { base: 12000 } }],
        ['token', { text: 'לקחתי מהתלוש: שכר בסיס 12,000' }], ['done', {}]]) onEvent(e, d)
    }),
    payslipImage: payslipImage ?? vi.fn().mockResolvedValue('blob:server-tlush'),
    restore: restore ?? vi.fn().mockResolvedValue({ thread_id: TID, messages: [{ role: 'user', text: 'שאלה' }], cards: [], rep: { pending: 0, new_answers: 0 }, payslip: null }),
    threads: vi.fn().mockResolvedValue([]),
  }
  render(<EmployeeScreen api={api} subscribe={() => () => {}} notifier={{ beep: vi.fn(), setUnread: vi.fn() }} />)
  return { api }
}

const fileInput = () => document.getElementById('payslip-file')
const preview = () => screen.queryByRole('group', { name: T.attach })

beforeEach(() => {
  phone(false)
  URL.createObjectURL = vi.fn(() => 'blob:local-tlush')
  URL.revokeObjectURL = vi.fn()
})
afterEach(() => { vi.restoreAllMocks(); delete window.matchMedia })

describe('choosing a payslip', () => {
  it('📎 opens the file picker for JPG, PNG and PDF', async () => {
    setup()
    const attach = await screen.findByRole('button', { name: T.attach })
    const input = fileInput()
    const click = vi.spyOn(input, 'click')
    await userEvent.setup().click(attach)
    expect(click).toHaveBeenCalled()
    expect(input).toHaveAttribute('accept', cfg.accept)
    expect(input).not.toHaveAttribute('capture')
  })

  it('shows a preview with ✕ before sending; ✕ removes it and the focus goes back to the message box', async () => {
    setup()
    const user = userEvent.setup()
    await user.upload(fileInput(), png())
    const box = preview()
    expect(within(box).getByRole('img', { name: T.image })).toHaveAttribute('src', 'blob:local-tlush')
    await user.click(within(box).getByRole('button', { name: T.remove }))
    expect(preview()).toBeNull()
    expect(screen.getByLabelText('הודעה')).toHaveFocus()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:local-tlush')
  })

  it('a PDF is shown as an icon with its file name', async () => {
    setup()
    await userEvent.setup().upload(fileInput(), pdf())
    expect(within(preview()).getByText('tlush-october.pdf')).toBeInTheDocument()
    expect(within(preview()).getByRole('img', { name: T.pdf })).toBeInTheDocument()
  })

  it.each([
    ['too large', new File([new Uint8Array(cfg.maxBytes + 1)], 'big.png', { type: 'image/png' }), T.tooLarge],
    ['another type', new File(['GIF89a'], 'a.gif', { type: 'image/gif' }), T.badType],
  ])('%s: a clear message next to the message box, nothing to send', async (_, file, text) => {
    const { api } = setup()
    // applyAccept: false - the employee can still pick "all files" in the picker
    await userEvent.setup({ applyAccept: false }).upload(fileInput(), file)
    expect(screen.getByRole('alert')).toHaveTextContent(text)
    expect(screen.getByLabelText('הודעה')).toHaveAttribute('aria-describedby', screen.getByRole('alert').id)
    expect(preview()).toBeNull()
    expect(api.streamPayslip).not.toHaveBeenCalled()
  })

  it('dragging a file over the chat highlights it; dropping it gives the preview', async () => {
    setup()
    const chat = screen.getByRole('main')
    const dataTransfer = { types: ['Files'], files: [png()] }
    fireEvent.dragEnter(chat, { dataTransfer })
    expect(chat).toHaveClass('chat--drop')
    expect(screen.getByText(T.drop)).toBeInTheDocument()
    fireEvent.drop(chat, { dataTransfer })
    expect(chat).not.toHaveClass('chat--drop')
    expect(preview()).not.toBeNull()
  })

  it('dragging out again removes the highlight', () => {
    setup()
    const chat = screen.getByRole('main')
    fireEvent.dragEnter(chat, { dataTransfer: { types: ['Files'], files: [] } })
    fireEvent.dragLeave(chat, { dataTransfer: { types: ['Files'] }, relatedTarget: document.body })
    expect(chat).not.toHaveClass('chat--drop')
  })

  it('pasting an image (Ctrl+V, or paste from a long press) gives the preview', async () => {
    setup()
    const box = screen.getByLabelText('הודעה')
    const pasted = fireEvent.paste(box, { clipboardData: { files: [png()], types: ['Files'], getData: () => '' } })
    expect(pasted).toBe(false) // the image does not go into the text
    expect(preview()).not.toBeNull()
  })

  it('pasting text stays as it was', async () => {
    setup()
    const box = screen.getByLabelText('הודעה')
    const pasted = fireEvent.paste(box, { clipboardData: { files: [], types: ['text/plain'], getData: () => 'שכר בסיס 12,000' } })
    expect(pasted).toBe(true)
    await userEvent.setup().click(box)
    await userEvent.setup().paste('שכר בסיס 12,000')
    expect(box).toHaveValue('שכר בסיס 12,000')
    expect(preview()).toBeNull()
  })

  it('before a conversation starts there is nothing to attach to: no 📎, and a dropped file says why', () => {
    setup({ withThread: false })
    expect(screen.queryByRole('button', { name: T.attach })).toBeNull()
    fireEvent.drop(screen.getByRole('main'), { dataTransfer: { types: ['Files'], files: [png()] } })
    expect(screen.getByRole('alert')).toHaveTextContent(T.needsConversation)
  })
})

describe('phone camera', () => {
  it('"צלם תלוש" is there only on a phone, and opens the back camera', async () => {
    phone(true)
    setup()
    const camera = await screen.findByRole('button', { name: T.camera })
    expect(camera).toHaveTextContent(T.cameraLabel)
    const input = document.getElementById('payslip-camera')
    expect(input).toHaveAttribute('capture', 'environment')
    expect(input).toHaveAttribute('accept', 'image/*')
    const click = vi.spyOn(input, 'click')
    await userEvent.setup().click(camera)
    expect(click).toHaveBeenCalled()
    await userEvent.setup().upload(input, png())
    expect(preview()).not.toBeNull()
  })

  it('not on a computer', async () => {
    setup()
    await screen.findByRole('button', { name: T.attach })
    expect(screen.queryByRole('button', { name: T.camera })).toBeNull()
    expect(document.getElementById('payslip-camera')).toBeNull()
  })

  it('every new button is at least 44×44, and the preview is 120px high', () => {
    const css = readFileSync('src/styles.css', 'utf8')
    for (const sel of ['\\.attach__btn', '\\.preview__remove', '\\.msg__thumb', '\\.viewer__close']) {
      const rule = css.match(new RegExp(`${sel}[^{]*\\{([^}]*)\\}`))[1]
      expect(rule, sel).toMatch(/min-width:\s*(4[4-9]|[5-9]\d)px/)
      expect(rule, sel).toMatch(/min-height:\s*(4[4-9]|[5-9]\d)px/)
    }
    expect(css).toMatch(/\.preview \{[^}]*height:\s*120px/)
  })
})

describe('sending', () => {
  it('sends the file, then shows a 48px thumbnail in the bubble', async () => {
    const { api } = setup()
    const user = userEvent.setup()
    await user.upload(fileInput(), png())
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    expect(api.streamPayslip).toHaveBeenCalledWith(TID, expect.any(File), expect.any(Function))
    expect(await screen.findByText('לקחתי מהתלוש: שכר בסיס 12,000')).toBeInTheDocument()
    expect(preview()).toBeNull()
    const thumb = screen.getByRole('button', { name: T.open })
    const img = within(thumb).getByRole('presentation')
    expect(img).toHaveAttribute('width', '48')
    expect(img).toHaveAttribute('height', '48')
    expect(thumb.closest('li')).toHaveTextContent(T.shown)
    expect(api.streamChat).not.toHaveBeenCalled()
  })

  it('text written next to the file goes after it, as a question', async () => {
    const { api } = setup()
    const user = userEvent.setup()
    await user.upload(fileInput(), png())
    await user.type(screen.getByLabelText('הודעה'), 'ומה עם חשמלי?')
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    await waitFor(() => expect(api.streamChat).toHaveBeenCalled())
    expect(api.streamChat.mock.calls[0][0]).toEqual({ message: 'ומה עם חשמלי?', threadId: TID })
  })

  it('a PDF: an icon until the server has its first page, then the thumbnail', async () => {
    const { api } = setup()
    const user = userEvent.setup()
    await user.upload(fileInput(), pdf())
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    await waitFor(() => expect(api.payslipImage).toHaveBeenCalledWith(TID))
    const thumb = await screen.findByRole('button', { name: T.open })
    expect(within(thumb).getByRole('presentation')).toHaveAttribute('src', 'blob:server-tlush')
  })

  it('refused by the server: its text next to the message box, and no bubble', async () => {
    setup({ payslipEvents: [['rejected', { message: T.tooLarge }]] })
    const user = userEvent.setup()
    await user.upload(fileInput(), png())
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(T.tooLarge)
    expect(screen.queryByText(T.shown)).toBeNull()
  })
})

describe('the large view', () => {
  async function openIt() {
    setup()
    const user = userEvent.setup()
    await user.upload(fileInput(), png())
    await user.click(screen.getByRole('button', { name: 'שליחה' }))
    const thumb = await screen.findByRole('button', { name: T.open })
    await user.click(thumb)
    return { user, thumb, dialog: screen.getByRole('dialog', { name: T.viewer }) }
  }

  it('opens as a dialog, with the focus on ✕; Esc closes it and the focus goes back', async () => {
    const { user, thumb, dialog } = await openIt()
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(within(dialog).getByRole('img', { name: T.image })).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: T.close })).toHaveFocus()
    await user.tab() // the focus stays inside
    expect(within(dialog).getByRole('button', { name: T.close })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(thumb).toHaveFocus()
  })

  it('a click outside the image closes it; a click on the image does not', async () => {
    const { user, dialog } = await openIt()
    await user.click(within(dialog).getByRole('img', { name: T.image }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await user.click(document.querySelector('.viewer'))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('✕ closes it (on a phone it is full screen with a big ✕)', async () => {
    const { user, thumb, dialog } = await openIt()
    await user.click(within(dialog).getByRole('button', { name: T.close }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(thumb).toHaveFocus()
    const css = readFileSync('src/styles.css', 'utf8')
    const phoneCss = css.slice(css.indexOf('@media (max-width: 767px)'))
    expect(phoneCss).toMatch(/\.viewer__box \{[^}]*width:\s*100vw[^}]*height:\s*100dvh/)
  })
})

it('a tap that does not focus the thumbnail (a phone) still brings the focus back to it', async () => {
  setup()
  const user = userEvent.setup()
  await user.upload(fileInput(), png())
  await user.click(screen.getByRole('button', { name: 'שליחה' }))
  const thumb = await screen.findByRole('button', { name: T.open })
  document.body.focus()
  act(() => { thumb.dispatchEvent(new MouseEvent('click', { bubbles: true })) }) // no focus, like iOS
  await user.keyboard('{Escape}')
  expect(thumb).toHaveFocus()
})

describe('after a reload or back to the conversation', () => {
  it('the payslip comes back from the server, with its thumbnail', async () => {
    const restore = vi.fn().mockResolvedValue({
      thread_id: TID, cards: [], rep: { pending: 0, new_answers: 0 },
      messages: [{ role: 'user', text: 'שאלה' }, { role: 'payslip', text: T.shown }, { role: 'assistant', text: 'לקחתי מהתלוש' }],
      payslip: { source: 'image', fields: { base: 12000 }, image: `/chat/${TID}/payslip` },
    })
    const { api } = setup({ restore })
    const thumb = await screen.findByRole('button', { name: T.open })
    expect(within(thumb).getByRole('presentation')).toHaveAttribute('src', 'blob:server-tlush')
    expect(api.payslipImage).toHaveBeenCalledWith(TID)
  })

  it('pasted payslip text comes back as a line, without a thumbnail', async () => {
    const restore = vi.fn().mockResolvedValue({
      thread_id: TID, cards: [], rep: { pending: 0, new_answers: 0 },
      messages: [{ role: 'payslip', text: T.shownText }],
      payslip: { source: 'text', fields: { base: 12000 }, image: null },
    })
    const { api } = setup({ restore })
    expect(await screen.findByText(T.shownText)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: T.open })).toBeNull()
    expect(api.payslipImage).not.toHaveBeenCalled()
  })

  it('reads the image once per conversation, not on every refresh', async () => {
    const restore = vi.fn().mockResolvedValue({
      thread_id: TID, cards: [], rep: { pending: 0, new_answers: 0 },
      messages: [{ role: 'payslip', text: T.shown }],
      payslip: { source: 'image', fields: {}, image: `/chat/${TID}/payslip` },
    })
    const { api } = setup({ restore })
    await screen.findByRole('button', { name: T.open })
    // a reload refreshes several times at once: one request for all of them
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'))
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await waitFor(() => expect(restore).toHaveBeenCalledTimes(3))
    expect(api.payslipImage).toHaveBeenCalledTimes(1)
  })
})

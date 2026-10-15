import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import rachel from '../test-fixtures/card-rachel-waiting.json'
import RepScreen from './RepScreen'

const request = {
  id: '1', thread_id: 't', fields: ['carGroup', 'companyCost', 'participation'],
  question: 'מהי הקבוצה, העלות וההשתתפות של BYD ATTO 2?', car_key: '01014/00045/2025', card: rachel.card,
}

function fakeApi() {
  return {
    repList: vi.fn().mockResolvedValue([request]),
    repAnswer: vi.fn().mockResolvedValue({ status: 'ok' }),
  }
}

describe('RepScreen', () => {
  it('asks for the passcode first', () => {
    render(<RepScreen api={fakeApi()} />)
    expect(screen.getByLabelText('סיסמת נציג')).toBeInTheDocument()
  })

  it('lists open questions with the employee card, and sends typed answers', async () => {
    const api = fakeApi()
    const user = userEvent.setup()
    render(<RepScreen api={api} />)
    await user.type(screen.getByLabelText('סיסמת נציג'), 'pw')
    await user.click(screen.getByRole('button', { name: 'כניסה' }))

    expect(await screen.findByText(request.question)).toBeInTheDocument()
    expect(api.repList).toHaveBeenCalledWith('pw')
    expect(screen.getByRole('region', { name: 'הנתונים שלך' })).toBeInTheDocument()

    await user.type(screen.getByLabelText('קבוצת הרכב'), 'ב')
    await user.type(screen.getByLabelText('עלות חודשית לחברה'), '3500')
    await user.type(screen.getByLabelText('השתתפות עובד'), '250')
    await user.click(screen.getByRole('button', { name: 'שליחת תשובה' }))

    await waitFor(() => expect(api.repAnswer).toHaveBeenCalledWith('pw', '1',
      { carGroup: 'ב', companyCost: 3500, participation: 250 }))
  })

  it('confirms the sent answer, then shows the empty queue', async () => {
    const api = fakeApi()
    const user = userEvent.setup()
    render(<RepScreen api={api} />)
    await user.type(screen.getByLabelText('סיסמת נציג'), 'pw')
    await user.click(screen.getByRole('button', { name: 'כניסה' }))
    await screen.findByText(request.question, { selector: 'h2' })
    await user.type(screen.getByLabelText('קבוצת הרכב'), 'ב')
    await user.type(screen.getByLabelText('עלות חודשית לחברה'), '3500')
    await user.type(screen.getByLabelText('השתתפות עובד'), '250')
    api.repList.mockResolvedValue([]) // the answered question leaves the queue
    await user.click(screen.getByRole('button', { name: 'שליחת תשובה' }))

    expect(await screen.findByText('התשובה נשלחה')).toBeInTheDocument()
    expect(screen.getByText('נשלח ✓')).toBeInTheDocument()
    expect(screen.getByText('אין כרגע שאלות. המסך מתעדכן לבד.')).toBeInTheDocument()
  })

  it('does not send an incomplete answer', async () => {
    const api = fakeApi()
    const user = userEvent.setup()
    render(<RepScreen api={api} />)
    await user.type(screen.getByLabelText('סיסמת נציג'), 'pw')
    await user.click(screen.getByRole('button', { name: 'כניסה' }))
    await screen.findByText(request.question)
    await user.type(screen.getByLabelText('קבוצת הרכב'), 'ב')
    await user.click(screen.getByRole('button', { name: 'שליחת תשובה' }))
    expect(api.repAnswer).not.toHaveBeenCalled()
  })

  it('shows a clear message on a wrong passcode', async () => {
    const api = { repList: vi.fn().mockRejectedValue(Object.assign(new Error('401'), { status: 401 })), repAnswer: vi.fn() }
    const user = userEvent.setup()
    render(<RepScreen api={api} />)
    await user.type(screen.getByLabelText('סיסמת נציג'), 'bad')
    await user.click(screen.getByRole('button', { name: 'כניסה' }))
    expect(await screen.findByText('סיסמה שגויה')).toBeInTheDocument()
  })
})

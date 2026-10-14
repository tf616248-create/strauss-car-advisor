import { useEffect, useRef, useState } from 'react'
import * as realApi from '../lib/api'
import { notifier as realNotifier } from '../lib/notify'
import { subscribeRepAnswers } from '../lib/realtime'
import CompareCard from '../components/CompareCard'

const REP_ANSWERED = 'הנציג ענה, והחלופה מתעדכנת'
let nextId = 1

export default function EmployeeScreen({ api = realApi, subscribe = subscribeRepAnswers, notifier = realNotifier }) {
  const [threadId, setThreadId] = useState(() => localStorage.getItem('threadId'))
  const [messages, setMessages] = useState([])
  const [cards, setCards] = useState([])
  const [step, setStep] = useState(null)
  const [busy, setBusy] = useState(false)
  const [input, setInput] = useState('')
  const endRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView?.({ block: 'end' }) }, [messages])

  // restore after a reload
  useEffect(() => {
    const tid = localStorage.getItem('threadId')
    if (!tid) return
    api.restore(tid).then((s) => {
      setMessages(s.messages.map((m) => ({ ...m, id: nextId++ })))
      if (s.cards.length) setCards([s.cards[s.cards.length - 1]])
    }).catch(() => {})
  }, [api])

  function append(msg) {
    const m = { ...msg, id: nextId++ }
    setMessages((ms) => [...ms, m])
    return m.id
  }

  function handler(assistantId) {
    let turnCards = []
    return (event, data) => {
      if (event === 'thread') {
        localStorage.setItem('threadId', data.thread_id)
        setThreadId(data.thread_id)
      } else if (event === 'step') {
        setStep(data.label)
      } else if (event === 'card') {
        turnCards = [...turnCards, data]
        setCards(turnCards)
      } else if (event === 'token') {
        setStep(null)
        setMessages((ms) => ms.map((m) => (m.id === assistantId ? { ...m, text: m.text + data.text } : m)))
      } else if (event === 'error') {
        setMessages((ms) => ms.map((m) => (m.id === assistantId ? { ...m, role: 'error', text: data.message } : m)))
      }
    }
  }

  async function run(start) {
    setBusy(true)
    const assistantId = append({ role: 'assistant', text: '' })
    await start(handler(assistantId))
    setStep(null)
    setBusy(false)
  }

  async function send(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    notifier.setUnread(0)
    append({ role: 'user', text })
    await run((onEvent) => api.streamChat({ message: text, threadId }, onEvent))
  }

  // the rep answered: tell the employee, and let the bot recalculate
  useEffect(() => {
    if (!threadId) return
    return subscribe(threadId, () => {
      notifier.beep()
      notifier.setUnread(1)
      if (!document.hidden) setTimeout(() => notifier.setUnread(0), 4000)
      append({ role: 'system', text: REP_ANSWERED })
      run((onEvent) => api.streamRepAnswered(threadId, onEvent))
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId])

  return (
    <div className="employee">
      <main className="chat">
        <header className="chat__header">
          <h1>יועץ הרכב</h1>
          <p>מה יקרה לנטו שלך אם תעבור לרכב אחר, לרכב חשמלי, למסלול המשפחתי, או תוותר על הרכב?</p>
        </header>
        <ol className="chat__messages" aria-live="polite">
          {messages.length === 0 && (
            <li className="msg msg--hint">למשל: "אם אעבור מהקורולה קרוס ל-BYD Atto 3, כמה זה ישנה לי בנטו?"</li>
          )}
          {messages.map((m) => (
            <li key={m.id} className={`msg msg--${m.role}`}>
              {m.role === 'system' ? REP_ANSWERED : m.text}
            </li>
          ))}
          <li ref={endRef} aria-hidden="true" />
        </ol>
        {busy && (
          <div className="working" role="status">
            <span className="car" aria-hidden="true">🚗</span>
            <span>{step ?? 'חושב…'}</span>
          </div>
        )}
        <form className="chat__form" onSubmit={send}>
          <label htmlFor="msg" className="visually-hidden">הודעה</label>
          <textarea id="msg" rows={2} value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) send(e) }}
            placeholder="כתבו כאן…" />
          <button type="submit" disabled={busy}>שליחה</button>
        </form>
      </main>
      <aside className="cards" aria-label="כרטיס השוואה">
        {cards.length === 0
          ? <p className="hint">כרטיס ההשוואה יופיע כאן אחרי החישוב.</p>
          : cards.map((c, i) => <CompareCard key={i} result={c} />)}
      </aside>
    </div>
  )
}

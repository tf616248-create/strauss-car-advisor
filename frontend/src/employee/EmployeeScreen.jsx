import { useEffect, useRef, useState } from 'react'
import * as realApi from '../lib/api'
import { notifier as realNotifier } from '../lib/notify'
import { subscribeRepAnswers } from '../lib/realtime'
import CompareCard from '../components/CompareCard'
import Road, { stationIndex } from '../components/Road'
import logo from '../assets/strauss-logo.svg'

const REP_ANSWERED = 'הנציג ענה, והחלופה מתעדכנת'
const PARKED_MS = 2500
let nextId = 1

const fmtNet = (v) => `${v > 0 ? '+' : '−'}${Math.abs(v).toLocaleString('he-IL')} ₪`

export default function EmployeeScreen({ api = realApi, subscribe = subscribeRepAnswers, notifier = realNotifier }) {
  const [threadId, setThreadId] = useState(() => localStorage.getItem('threadId'))
  const [messages, setMessages] = useState([])
  const [cards, setCards] = useState([])
  const [step, setStep] = useState(null)
  const [busy, setBusy] = useState(false)
  const [input, setInput] = useState('')
  const [panelOpen, setPanelOpen] = useState(true)
  const [reached, setReached] = useState(-1)
  const [parked, setParked] = useState(false)
  const [currentId, setCurrentId] = useState(null)
  const endRef = useRef(null)
  const wasBusy = useRef(false)

  useEffect(() => { endRef.current?.scrollIntoView?.({ block: 'end' }) }, [messages])

  // a new comparison (or a rep answer) opens the panel by itself
  useEffect(() => { if (cards.length) setPanelOpen(true) }, [cards])

  // road: the car reaches a station only when the server really moves to that step
  useEffect(() => {
    const i = stationIndex(step)
    if (i >= 0) setReached((r) => Math.max(r, i))
  }, [step])

  useEffect(() => {
    if (busy) { setReached(-1); setParked(false) }
    if (wasBusy.current && !busy) {
      setParked(true)
      const t = setTimeout(() => setParked(false), PARKED_MS)
      wasBusy.current = busy
      return () => clearTimeout(t)
    }
    wasBusy.current = busy
  }, [busy])

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
    setCurrentId(assistantId)
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

  const waiting = cards.some((c) => c.status === 'waiting_rep')
  const answering = busy && step === null && messages.some((m) => m.id === currentId && m.text)
  // waiting for the rep: the car drives straight to the light (it never parks and backs up)
  const roadPhase = busy
    ? (answering ? (waiting ? 'waiting' : 'arrived') : 'driving')
    : waiting ? 'waiting' : parked ? 'arrived' : null
  const nets = cards.map((c) => c.card?.diff?.net).filter((v) => typeof v === 'number' && v !== 0)
  const togglePanel = () => setPanelOpen((o) => !o)

  return (
    <div className={`employee ${panelOpen ? '' : 'employee--closed'}`}>
      <header className="topbar">
        <img className="topbar__logo" src={logo} alt="שטראוס" />
        <span className="topbar__sep" aria-hidden="true" />
        <h1>יועץ הרכב</h1>
        <p className="topbar__sub">מה יקרה לנטו שלך אם תעבור לרכב אחר, לרכב חשמלי, למסלול המשפחתי, או תוותר על הרכב?</p>
      </header>

      <main className="chat">
        <ol className="chat__messages" aria-live="polite">
          {messages.length === 0 && (
            <li className="msg msg--hint">למשל: "אם אעבור מהקורולה קרוס ל-BYD Atto 3, כמה זה ישנה לי בנטו?"</li>
          )}
          {messages.map((m) => (
            <li key={m.id} className={`msg msg--${m.role}`}>
              {m.role === 'assistant' && m.text && <span className="msg__who">יועץ הרכב</span>}
              {m.role === 'system' ? REP_ANSWERED : m.text}
            </li>
          ))}
          <li ref={endRef} aria-hidden="true" />
        </ol>
        {/* a new key per answer: the car starts each trip from the start line */}
        {roadPhase && <Road key={currentId ?? 'idle'} phase={roadPhase} reached={reached} label={step} />}
        <form className="chat__form" onSubmit={send}>
          <label htmlFor="msg" className="visually-hidden">הודעה</label>
          <textarea id="msg" rows={1} value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) send(e) }}
            placeholder="כתבו שאלה…" />
          <button type="submit" disabled={busy}>שליחה</button>
        </form>
      </main>

      <div className="divider">
        {panelOpen && (
          <button type="button" className="divider__btn" onClick={togglePanel}
            aria-expanded="true" aria-controls="cmp-panel" aria-label="סגירת פאנל ההשוואה">
            <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>
          </button>
        )}
      </div>

      <section className="panel">
        <button type="button" className="panel__head" onClick={togglePanel}
          aria-expanded={panelOpen} aria-controls="cmp-panel">
          <span className="panel__title">
            השוואה
            {waiting && <span aria-label="ממתין לנציג">⏳</span>}
            {nets.map((v, i) => (
              <span key={i} className={`chip chip--${v > 0 ? 'up' : 'down'}`}>
                <span aria-hidden="true">{v > 0 ? '▲' : '▼'}</span> <bdi dir="ltr">{fmtNet(v)}</bdi>
              </span>
            ))}
          </span>
          <span className="panel__toggle">
            {panelOpen ? 'הסתרה' : 'הצגה'}
            <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
          </span>
        </button>
        <aside id="cmp-panel" className="cards" aria-label="כרטיס השוואה" inert={!panelOpen}>
          {cards.length === 0
            ? <p className="hint">כרטיס ההשוואה יופיע כאן אחרי החישוב.</p>
            : cards.map((c, i) => <CompareCard key={i} result={c} />)}
        </aside>
      </section>

      {!panelOpen && (
        <button type="button" className="sidetab" onClick={togglePanel}
          aria-expanded="false" aria-controls="cmp-panel" aria-label="פתיחת פאנל ההשוואה">
          <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
          <span className="sidetab__text">השוואה</span>
          {waiting && <span aria-hidden="true">⏳</span>}
        </button>
      )}
    </div>
  )
}

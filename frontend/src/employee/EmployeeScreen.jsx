import { useEffect, useRef, useState } from 'react'
import * as realApi from '../lib/api'
import { notifier as realNotifier } from '../lib/notify'
import { subscribeChanges } from '../lib/realtime'
import CompareCard from '../components/CompareCard'
import Road from '../components/Road'
import ContactRep from '../components/ContactRep'
import logo from '../assets/strauss-logo.svg'

const REP_ANSWERED = 'הנציג ענה, והחלופה מתעדכנת'
const PARKED_MS = 2500
let nextId = 1

const fmtNet = (v) => `${v > 0 ? '+' : '−'}${Math.abs(v).toLocaleString('he-IL')} ₪`

export default function EmployeeScreen({ api = realApi, subscribe = subscribeChanges, notifier = realNotifier }) {
  const [threadId, setThreadId] = useState(() => localStorage.getItem('threadId'))
  const [messages, setMessages] = useState([])
  const [cards, setCards] = useState([])
  const [step, setStep] = useState(null)
  const [busy, setBusy] = useState(false)
  const [input, setInput] = useState('')
  const [panelOpen, setPanelOpen] = useState(true)
  const [stops, setStops] = useState([]) // tools really called in this answer, in order
  const [parked, setParked] = useState(false)
  const [currentId, setCurrentId] = useState(null)
  const endRef = useRef(null)
  const wasBusy = useRef(false)
  const busyRef = useRef(false) // set at once, so two reads of the state cannot both start the bot
  const turnStartCards = useRef(cards) // the cards before this answer began

  useEffect(() => { endRef.current?.scrollIntoView?.({ block: 'end' }) }, [messages])

  // a new comparison (or a rep answer) opens the panel by itself
  useEffect(() => { if (cards.length) setPanelOpen(true) }, [cards])

  useEffect(() => {
    if (busy) { turnStartCards.current = cards; setStops([]); setParked(false) }
    if (wasBusy.current && !busy) {
      setParked(true)
      const t = setTimeout(() => setParked(false), PARKED_MS)
      wasBusy.current = busy
      return () => clearTimeout(t)
    }
    wasBusy.current = busy
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy])

  // The server (database) is the source of truth: read the conversation's current state.
  // Called on page load, on "changed", when the employee returns to the tab, and after
  // the events stream reconnects. A rep answer not yet used by the bot starts a recalculation.
  async function refresh(tid) {
    if (!tid || busyRef.current) return
    let s
    try { s = await api.restore(tid) } catch { return }
    if (busyRef.current) return
    setMessages((ms) => {
      const errors = []
      for (let i = ms.length - 1; i >= 0 && ms[i].role === 'error'; i--) errors.unshift(ms[i])
      return [...s.messages.map((m) => ({ ...m, id: nextId++ })), ...errors]
    })
    if (s.cards.length) setCards((cs) => (cs.length ? cs : [s.cards[s.cards.length - 1]]))
    if (s.rep?.new_answers > 0) {
      append({ role: 'system', text: REP_ANSWERED })
      run((onEvent) => api.streamRepAnswered(tid, onEvent))
    }
  }

  // after a reload
  useEffect(() => {
    refresh(localStorage.getItem('threadId'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        // the road gets a stop per tool call (a repeat of the same tool in a row is one stop)
        setStops((ss) => (ss.at(-1)?.tool === data.tool ? ss : [...ss, { tool: data.tool, label: data.label }]))
      } else if (event === 'card') {
        turnCards = [...turnCards, data]
        setCards(turnCards)
      } else if (event === 'token') {
        setStep(null)
        setMessages((ms) => ms.map((m) => (m.id === assistantId ? { ...m, text: m.text + data.text } : m)))
      } else if (event === 'error') {
        // keep what was already written; the error goes below it as its own message
        setMessages((ms) => {
          const current = ms.find((m) => m.id === assistantId)
          if (current?.text) return [...ms, { role: 'error', text: data.message, id: nextId++ }]
          return ms.map((m) => (m.id === assistantId ? { ...m, role: 'error', text: data.message } : m))
        })
      }
    }
  }

  async function run(start) {
    busyRef.current = true
    setBusy(true)
    const assistantId = append({ role: 'assistant', text: '' })
    setCurrentId(assistantId)
    await start(handler(assistantId))
    setStep(null)
    busyRef.current = false
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

  // the server rang ("changed", e.g. the rep answered): beep, mark the tab, read the state
  useEffect(() => {
    if (!threadId) return
    return subscribe(threadId, {
      onChanged: () => {
        notifier.beep()
        notifier.setUnread(1)
        if (!document.hidden) setTimeout(() => notifier.setUnread(0), 4000)
        refresh(threadId)
      },
      onOpen: () => { refresh(threadId) }, // (re)connected: catch up on anything missed
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId])

  // back to the tab: the browser may have paused the connection
  useEffect(() => {
    if (!threadId) return
    const onVisible = () => { if (!document.hidden) refresh(threadId) }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId])

  const waiting = cards.some((c) => c.status === 'waiting_rep')
  // The car arrives only with a real result: a card from `calculate` in this answer.
  // Tool calls add stops; the bot writing (e.g. a follow-up question) does not move it on.
  const gotCard = cards !== turnStartCards.current
  const roadPhase = busy
    ? (gotCard ? (waiting ? 'waiting' : 'arrived') : 'driving')
    : waiting ? 'waiting' : (parked && gotCard) ? 'arrived' : null
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
        {roadPhase && <Road key={currentId ?? 'idle'} phase={roadPhase} stops={stops} label={step} />}
        <form className="chat__form" onSubmit={send}>
          <ContactRep />
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

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import * as realApi from '../lib/api'
import { EMPLOYEE_TITLE, notifier as realNotifier } from '../lib/notify'
import { subscribeChanges } from '../lib/realtime'
import { getCurrentThread, setCurrentThread } from '../lib/session'
import CompareCard from '../components/CompareCard'
import RankingCard from '../components/RankingCard'
import SpecsCard from '../components/SpecsCard'
import Road, { CarBody } from '../components/Road'
import ContactRep from '../components/ContactRep'
import Answer from '../components/Answer'
import EmptyPanel from '../components/EmptyPanel'
import logo from '../assets/strauss-logo.svg'

const REP_ANSWERED = 'הנציג ענה, והחלופה מתעדכנת'
const PARKED_MS = 2500
let nextId = 1

// the welcome screen: four equal choices (the bot compares, it does not recommend)
const CHOICES = [
  ['לעבור לרכב חשמלי', 'מה יקרה לנטו שלי אם אעבור לרכב חשמלי?'],
  ['להחליף לרכב אחר', 'מה יקרה לנטו שלי אם אחליף לרכב אחר?'],
  ['מסלול משפחתי', 'מה יקרה לנטו שלי אם אעבור למסלול המשפחתי?'],
  ['לוותר על הרכב', 'מה יקרה לנטו שלי אם אוותר על הרכב?'],
]
const WELCOME = 'שלום, אני כובי'

const fmtNet = (v) => `${v > 0 ? '+' : '−'}${Math.abs(v).toLocaleString('he-IL')} ₪`
const fmtWhen = (iso) => new Date(iso).toLocaleString('he-IL', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' })

export default function EmployeeScreen({ api = realApi, subscribe = subscribeChanges, notifier = realNotifier, onLogout }) {
  // the open conversation, kept for this tab (a reload stays on it); the list is on the server
  const [threadId, setThreadId] = useState(() => getCurrentThread())
  const [history, setHistory] = useState([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const [messages, setMessages] = useState([])
  const [cards, setCards] = useState([])
  const [step, setStep] = useState(null)
  const [busy, setBusy] = useState(false)
  const [input, setInput] = useState('')
  const boxRef = useRef(null)

  // the message box grows with its text, like other chats (CSS caps it at ~7 lines, then it scrolls)
  useLayoutEffect(() => {
    const box = boxRef.current
    if (!box) return
    box.style.height = 'auto'
    box.style.height = `${box.scrollHeight + box.offsetHeight - box.clientHeight}px` // + the borders
  }, [input])
  const [panelOpen, setPanelOpen] = useState(true)
  const [stops, setStops] = useState([]) // tools really called in this answer, in order
  const [parked, setParked] = useState(false)
  const [currentId, setCurrentId] = useState(null)
  const endRef = useRef(null)
  const wasBusy = useRef(false)
  const busyRef = useRef(false) // set at once, so two reads of the state cannot both start the bot
  const turnStartCards = useRef(cards) // the cards before this answer began

  useEffect(() => { document.title = EMPLOYEE_TITLE }, [])

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

  // my conversations, newest first (GET /threads): read on load and after every answer
  async function loadHistory() {
    try {
      const list = await api.threads()
      setHistory(list)
      return list
    } catch { return [] }
  }

  // after a reload: the conversation open in this tab; right after login: the newest one
  useEffect(() => {
    const tid = getCurrentThread()
    if (tid) refresh(tid)
    loadHistory().then((list) => {
      if (!getCurrentThread() && !busyRef.current && list[0]) openThread(list[0].thread_id)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api])

  function clearScreen() {
    setMessages([])
    setCards([])
    setStops([])
    setStep(null)
    setParked(false)
    setHistoryOpen(false)
    notifier.setUnread(0)
  }

  // a conversation from the list: its messages and cards come from the server
  function openThread(tid) {
    if (busyRef.current) return
    setCurrentThread(tid)
    setThreadId(tid)
    clearScreen()
    refresh(tid)
  }

  function append(msg) {
    const m = { ...msg, id: nextId++ }
    setMessages((ms) => [...ms, m])
    return m.id
  }

  function handler(assistantId) {
    let turnCards = []
    return (event, data) => {
      if (event === 'thread') {
        setCurrentThread(data.thread_id)
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
    loadHistory() // a new conversation, or a new title from the card
  }

  async function send(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    await ask(text)
  }

  async function ask(text) {
    if (busyRef.current) return
    notifier.setUnread(0)
    append({ role: 'user', text })
    await run((onEvent) => api.streamChat({ message: text, threadId }, onEvent))
  }

  // A fresh start. The previous conversation stays in "my conversations".
  function newConversation() {
    setCurrentThread(null)
    setThreadId(null)
    clearScreen()
  }

  // Escape closes the list
  useEffect(() => {
    if (!historyOpen) return
    const onKey = (e) => { if (e.key === 'Escape') setHistoryOpen(false) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [historyOpen])

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
        <h1 className="topbar__title">
          <span className="topbar__name">כובי</span>
          <span className="topbar__product">יועץ הרכב של שטראוס</span>
        </h1>
        <button type="button" className="topbar__logout" onClick={() => onLogout?.()}>יציאה</button>
        <p className="topbar__sub"><strong>רק בדיקה, שום דבר לא משתנה בשכר או ברכב שלכם</strong> · לפי כללי שטראוס ורשות המסים</p>
      </header>

      <main className="chat">
        <div className="chat__top">
          <button type="button" className="chat__new" onClick={() => setHistoryOpen((o) => !o)}
            aria-expanded={historyOpen} aria-controls="history" disabled={busy}>
            <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10" /></svg>
            השיחות שלי
          </button>
          {(threadId || messages.length > 0) && (
            <button type="button" className="chat__new" onClick={newConversation} disabled={busy}>
              <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
              שיחה חדשה
            </button>
          )}
        </div>
        {historyOpen && (
          <nav id="history" className="history" aria-label="השיחות שלי">
            {history.length === 0
              ? <p className="history__empty">עוד אין שיחות קודמות.</p>
              : (
                <ul className="history__list">
                  {history.map((t) => (
                    <li key={t.thread_id}>
                      <button type="button" className="history__item" data-thread={t.thread_id}
                        aria-current={t.thread_id === threadId ? 'true' : undefined}
                        onClick={() => openThread(t.thread_id)}>
                        <span className="history__title">{t.title || 'שיחה חדשה'}</span>
                        <span className="history__when">{fmtWhen(t.updated_at)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
          </nav>
        )}
        {messages.length === 0 && (
          <section className="welcome" aria-labelledby="welcome-title">
            <div className="welcome__car" aria-hidden="true"><CarBody /></div>
            <h2 id="welcome-title" className="welcome__title">{WELCOME}</h2>
            <p className="welcome__sub">רכב חברה משפיע על המשכורת שלכם, גם אם לא שמתם לב.</p>
            <p className="welcome__sub">אני מראה בדיוק כמה כסף יישאר לכם בכל חודש, היום ואחרי שינוי ברכב.</p>
            <p id="welcome-ask" className="welcome__ask">מה תרצו לבדוק?</p>
            <div className="welcome__choices" role="group" aria-labelledby="welcome-ask">
              {CHOICES.map(([label, question]) => (
                <button key={label} type="button" className="welcome__choice" onClick={() => ask(question)}>{label}</button>
              ))}
            </div>
            <p className="welcome__more">לא בטוחים מה זה "שווי שימוש" או "השתתפות עצמית"? פשוט שאלו אותי.</p>
          </section>
        )}
        <ol className={`chat__messages ${messages.length ? '' : 'chat__messages--empty'}`} aria-live="polite">
          {messages.map((m) => (
            <li key={m.id} className={`msg msg--${m.role}`}>
              {m.role === 'assistant' && m.text && <span className="msg__who">כובי · בוט</span>}
              {m.role === 'system' ? REP_ANSWERED : m.role === 'assistant' ? <Answer text={m.text} /> : m.text}
            </li>
          ))}
          <li ref={endRef} aria-hidden="true" />
        </ol>
        {/* a new key per answer: the car starts each trip from the start line */}
        {roadPhase && <Road key={currentId ?? 'idle'} phase={roadPhase} stops={stops} label={step} />}
        <form className="chat__form" onSubmit={send}>
          <ContactRep />
          <label htmlFor="msg" className="visually-hidden">הודעה</label>
          <textarea id="msg" ref={boxRef} rows={1} value={input} onChange={(e) => setInput(e.target.value)}
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
            ? <EmptyPanel />
            : cards.map((c, i) => {
              if (c.kind === 'ranking') return <RankingCard key={i} result={c} />
              if (c.kind === 'specs') return <SpecsCard key={i} result={c} />
              return <CompareCard key={i} result={c} />
            })}
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

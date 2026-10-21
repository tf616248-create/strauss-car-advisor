// The employee screen on a phone: the same flow as frontend/src/employee/EmployeeScreen.jsx
// (the same server events, the same state rules). Only the layout differs: the chat and the
// comparison are two tabs instead of two side-by-side panels.
import { useEffect, useRef, useState } from 'react'
import { AppState, KeyboardAvoidingView, Platform, Pressable, ScrollView, TextInput, View } from 'react-native'
import { SvgXml } from 'react-native-svg'
import * as realApi from '../lib/api'
import { notifier as realNotifier } from '../lib/notify'
import { subscribeChanges } from '../lib/realtime'
import { getCurrentThread, setCurrentThread } from '../lib/session'
import { fmtNet, fmtWhen, ltr } from '../lib/format'
import CompareCard from '../components/CompareCard'
import RankingCard from '../components/RankingCard'
import SpecsCard from '../components/SpecsCard'
import Road, { CarBody } from '../components/Road'
import ContactRep from '../components/ContactRep'
import Answer from '../components/Answer'
import EmptyPanel from '../components/EmptyPanel'
import logo from '../assets/logo'
import { FONTS, useColors } from '../theme'
import { Btn, T } from '../components/ui'
import TEXTS from '../config/texts.json'

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

export default function EmployeeScreen({ api = realApi, subscribe = subscribeChanges, notifier = realNotifier, onLogout }) {
  const c = useColors()
  // the open conversation, kept while the app is open; the list is on the server
  const [threadId, setThreadId] = useState(() => getCurrentThread())
  const [history, setHistory] = useState([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const [messages, setMessages] = useState([])
  const [cards, setCards] = useState([])
  const [step, setStep] = useState(null)
  const [busy, setBusy] = useState(false)
  const [input, setInput] = useState('')
  const [tab, setTab] = useState('chat')
  const [unseenCard, setUnseenCard] = useState(false)
  const [stops, setStops] = useState([]) // tools really called in this answer, in order
  const [parked, setParked] = useState(false)
  const [currentId, setCurrentId] = useState(null)
  const scrollRef = useRef(null)
  const wasBusy = useRef(false)
  const busyRef = useRef(false) // set at once, so two reads of the state cannot both start the bot
  const turnStartCards = useRef(cards) // the cards before this answer began

  // a new comparison (or a rep answer) marks the comparison tab, unless it is open
  useEffect(() => { if (cards.length && tab !== 'cards') setUnseenCard(true) }, [cards]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (tab === 'cards') setUnseenCard(false) }, [tab])

  useEffect(() => {
    if (busy) { turnStartCards.current = cards; setStops([]); setParked(false) }
    if (wasBusy.current && !busy) {
      setParked(true)
      const t = setTimeout(() => setParked(false), PARKED_MS)
      wasBusy.current = busy
      return () => clearTimeout(t)
    }
    wasBusy.current = busy
  }, [busy]) // eslint-disable-line react-hooks/exhaustive-deps

  // The server (database) is the source of truth: read the conversation's current state.
  // Called on start, on "changed", when the app comes back to the front, and after the
  // events stream reconnects. A rep answer not yet used by the bot starts a recalculation.
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

  // my conversations, newest first (GET /threads): read on start and after every answer
  async function loadHistory() {
    try {
      const list = await api.threads()
      setHistory(list)
      return list
    } catch { return [] }
  }

  // the conversation open before; right after login: the newest one
  useEffect(() => {
    const tid = getCurrentThread()
    if (tid) refresh(tid)
    loadHistory().then((list) => {
      if (!getCurrentThread() && !busyRef.current && list[0]) openThread(list[0].thread_id)
    })
  }, [api]) // eslint-disable-line react-hooks/exhaustive-deps

  function clearScreen() {
    setMessages([])
    setCards([])
    setStops([])
    setStep(null)
    setParked(false)
    setHistoryOpen(false)
    setUnseenCard(false)
    notifier.setUnread(0)
  }

  // a conversation from the list: its messages and cards come from the server
  function openThread(tid) {
    if (busyRef.current) return
    setCurrentThread(tid)
    setThreadId(tid)
    clearScreen()
    setTab('chat')
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

  async function send() {
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    await ask(text)
  }

  async function ask(text) {
    if (busyRef.current) return
    notifier.setUnread(0)
    setTab('chat')
    append({ role: 'user', text })
    await run((onEvent) => api.streamChat({ message: text, threadId }, onEvent))
  }

  // A fresh start. The previous conversation stays in "my conversations".
  function newConversation() {
    setCurrentThread(null)
    setThreadId(null)
    clearScreen()
    setTab('chat')
  }

  // the server rang ("changed", e.g. the rep answered): vibrate, read the state
  useEffect(() => {
    if (!threadId) return
    return subscribe(threadId, {
      onChanged: () => {
        notifier.beep()
        refresh(threadId)
      },
      onOpen: () => { refresh(threadId) }, // (re)connected: catch up on anything missed
    })
  }, [threadId]) // eslint-disable-line react-hooks/exhaustive-deps

  // back to the app: the phone may have paused the connection
  useEffect(() => {
    if (!threadId) return
    const sub = AppState.addEventListener('change', (state) => { if (state === 'active') refresh(threadId) })
    return () => sub.remove()
  }, [threadId]) // eslint-disable-line react-hooks/exhaustive-deps

  const waiting = cards.some((card) => card.status === 'waiting_rep')
  // The car arrives only with a real result: a card from `calculate` in this answer.
  const gotCard = cards !== turnStartCards.current
  const roadPhase = busy
    ? (gotCard ? (waiting ? 'waiting' : 'arrived') : 'driving')
    : waiting ? 'waiting' : (parked && gotCard) ? 'arrived' : null
  const nets = cards.map((card) => card.card?.diff?.net).filter((v) => typeof v === 'number' && v !== 0)

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <View style={{ paddingHorizontal: 16, paddingTop: 8, paddingBottom: 6, borderBottomWidth: 1, borderColor: c.line, gap: 2 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View accessibilityLabel="שטראוס" accessibilityRole="image"><SvgXml xml={logo} width={44} height={30} /></View>
          <View style={{ width: 1, height: 28, backgroundColor: c.line }} />
          <View style={{ flex: 1 }} accessibilityRole="header">
            <T weight={800} size={22} style={{ lineHeight: 26 }}>כובי</T>
            <T muted size={12} style={{ lineHeight: 16 }}>יועץ הרכב של שטראוס</T>
          </View>
          <Btn quiet title="יציאה" onPress={() => onLogout?.()} />
        </View>
        <T size={12} muted><T size={12} weight={700}>רק בדיקה, שום דבר לא משתנה בשכר או ברכב שלכם</T> · לפי כללי שטראוס ורשות המסים</T>
      </View>

      <View accessibilityRole="tablist" style={{ flexDirection: 'row', borderBottomWidth: 1, borderColor: c.line }}>
        <TabButton active={tab === 'chat'} label="שיחה" onPress={() => setTab('chat')} />
        <TabButton active={tab === 'cards'} label="השוואה" onPress={() => setTab('cards')}>
          {waiting && <T size={13}>⏳</T>}
          {nets.map((v, i) => (
            <View key={i} style={{ borderRadius: 999, paddingHorizontal: 8, backgroundColor: v > 0 ? 'rgba(140,187,33,0.18)' : 'rgba(180,35,24,0.12)' }}>
              <T size={12} weight={800} color={v > 0 ? c.up : c.down}>{`${v > 0 ? '▲' : '▼'} ${ltr(fmtNet(v))}`}</T>
            </View>
          ))}
          {unseenCard && <View accessibilityLabel="השוואה חדשה" style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: c.orange }} />}
        </TabButton>
      </View>

      {tab === 'cards' ? (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 16 }} accessibilityLabel="כרטיס השוואה">
          {cards.length === 0
            ? <EmptyPanel />
            : cards.map((card, i) => {
              if (card.kind === 'ranking') return <RankingCard key={i} result={card} />
              if (card.kind === 'specs') return <SpecsCard key={i} result={card} />
              return <CompareCard key={i} result={card} />
            })}
        </ScrollView>
      ) : (
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={Platform.OS === 'ios' ? 110 : 0}>
          <View style={{ flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingVertical: 8 }}>
            <Btn quiet title="השיחות שלי" onPress={() => setHistoryOpen((o) => !o)} disabled={busy} />
            {(threadId || messages.length > 0) && <Btn quiet title="+ שיחה חדשה" label="שיחה חדשה" onPress={newConversation} disabled={busy} />}
          </View>
          {historyOpen && (
            <View accessibilityLabel="השיחות שלי" style={{ marginHorizontal: 16, marginBottom: 8, borderWidth: 1, borderColor: c.line, borderRadius: 12, backgroundColor: c.surface2, maxHeight: 280 }}>
              {history.length === 0
                ? <T muted style={{ padding: 12 }}>עוד אין שיחות קודמות.</T>
                : (
                  <ScrollView>
                    {history.map((t) => (
                      <Pressable key={t.thread_id} accessibilityRole="button" accessibilityState={{ selected: t.thread_id === threadId }}
                        onPress={() => openThread(t.thread_id)}
                        style={{ padding: 12, borderBottomWidth: 1, borderColor: c.line, backgroundColor: t.thread_id === threadId ? c.surface : 'transparent' }}>
                        <T weight={700}>{t.title || 'שיחה חדשה'}</T>
                        <T size={12} muted>{fmtWhen(t.updated_at)}</T>
                      </Pressable>
                    ))}
                  </ScrollView>
                )}
            </View>
          )}
          <ScrollView ref={scrollRef} style={{ flex: 1 }} contentContainerStyle={{ padding: 16, gap: 12 }} keyboardShouldPersistTaps="handled"
            onContentSizeChange={() => scrollRef.current?.scrollToEnd?.({ animated: true })}>
            {messages.length === 0 && (
              <View style={{ alignItems: 'center', gap: 8, paddingTop: 12 }}>
                <CarBody />
                <T weight={800} size={24} style={{ textAlign: 'center' }} accessibilityRole="header">{WELCOME}</T>
                <T muted style={{ textAlign: 'center' }}>רכב חברה משפיע על המשכורת שלכם, גם אם לא שמתם לב.</T>
                <T muted style={{ textAlign: 'center' }}>אני מראה בדיוק כמה כסף יישאר לכם בכל חודש, היום ואחרי שינוי ברכב.</T>
                <T weight={700} style={{ textAlign: 'center', marginTop: 8 }}>מה תרצו לבדוק?</T>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
                  {CHOICES.map(([label, question]) => (
                    <Pressable key={label} accessibilityRole="button" onPress={() => ask(question)}
                      style={({ pressed }) => ({ width: '47%', minHeight: 56, borderWidth: 1, borderColor: c.line, borderRadius: 14, backgroundColor: c.surface2, alignItems: 'center', justifyContent: 'center', padding: 8, opacity: pressed ? 0.7 : 1 })}>
                      <T weight={700} style={{ textAlign: 'center' }}>{label}</T>
                    </Pressable>
                  ))}
                </View>
                <T size={13} muted style={{ textAlign: 'center' }}>לא בטוחים מה זה "שווי שימוש" או "השתתפות עצמית"? פשוט שאלו אותי.</T>
              </View>
            )}
            {messages.map((m) => <Message key={m.id} m={m} />)}
          </ScrollView>
          {/* a new key per answer: the car starts each trip from the start line */}
          {roadPhase && <Road key={currentId ?? 'idle'} phase={roadPhase} stops={stops} label={step} />}
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8, padding: 12, borderTopWidth: 1, borderColor: c.line, backgroundColor: c.bg }}>
            <ContactRep />
            <TextInput accessibilityLabel="הודעה" value={input} onChangeText={setInput} placeholder="כתבו שאלה…" placeholderTextColor={c.muted}
              multiline style={{ flex: 1, minHeight: 44, maxHeight: 160, borderWidth: 1, borderColor: c.line, borderRadius: 22, paddingHorizontal: 14, paddingTop: 10, paddingBottom: 10, fontFamily: FONTS[400], fontSize: 16, color: c.text, backgroundColor: c.surface2, textAlign: 'right' }} />
            <Btn title="שליחה" onPress={send} disabled={busy} />
          </View>
        </KeyboardAvoidingView>
      )}
    </View>
  )
}

function TabButton({ active, label, onPress, children }) {
  const c = useColors()
  return (
    <Pressable accessibilityRole="tab" accessibilityLabel={label} accessibilityState={{ selected: active }} onPress={onPress}
      style={{ flex: 1, minHeight: 46, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, borderBottomWidth: 3, borderColor: active ? c.cyan : 'transparent' }}>
      <T weight={active ? 800 : 600} muted={!active}>{label}</T>
      {children}
    </Pressable>
  )
}

function Message({ m }) {
  const c = useColors()
  if (m.role === 'system') return <T size={14} weight={700} color={c.cyanText} style={{ textAlign: 'center' }}>{REP_ANSWERED}</T>
  if (m.role === 'error') return <T weight={600} color={c.error} accessibilityRole="alert">{m.text}</T>
  // a payslip uploaded on the website: the employee's bubble, the app's own short text, no image
  if (m.role === 'user' || m.role === 'payslip') {
    const payslip = m.role === 'payslip'
    return (
      <View accessibilityLabel={payslip ? TEXTS.payslipLabel : undefined}
        style={{ alignSelf: 'flex-start', maxWidth: '85%', backgroundColor: c.surface, borderRadius: 16, paddingHorizontal: 14, paddingVertical: 8 }}>
        <T>{payslip ? TEXTS.payslipLine : m.text}</T>
      </View>
    )
  }
  if (!m.text) return null
  if (m.role === 'assistant') {
    return (
      <View style={{ alignSelf: 'stretch', gap: 2 }}>
        <T size={12} weight={700} muted>כובי · בוט</T>
        <Answer text={m.text} />
      </View>
    )
  }
  // a kind of line the app does not know yet: a neutral line, never as if Kobi wrote it
  return <T size={14} muted style={{ textAlign: 'center' }}>{m.text}</T>
}

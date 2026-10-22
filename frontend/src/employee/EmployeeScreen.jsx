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
import PayslipViewer from '../components/PayslipViewer'
import { checkFile, usePhone } from '../lib/payslip'
import payslipCfg from '../config/payslip.json'
import A11Y from '../config/accessibility.json'
import chatCfg from '../config/chat.json'
import SiteFooter from '../components/SiteFooter'
import Sidebar, { useSidebar } from './Sidebar'
import ProfileDialog from './ProfileDialog'
import CustomizeDialog from './CustomizeDialog'
import settingsCfg from '../config/settings.json'
import profileCfg from '../config/profile.json'
import sidebarCfg from '../config/sidebar.json'
import logo from '../assets/strauss-logo.svg'

const REP_ANSWERED = 'הנציג ענה, והחלופה מתעדכנת'
const PT = payslipCfg.texts
const PARKED_MS = 2500
let nextId = 1

// the welcome screen: four equal choices (the bot compares, it does not recommend)
const CHOICES = [
  ['לעבור לרכב חשמלי', 'מה יקרה לנטו שלי אם אעבור לרכב חשמלי?'],
  ['להחליף לרכב אחר', 'מה יקרה לנטו שלי אם אחליף לרכב אחר?'],
  ['מסלול משפחתי', 'מה יקרה לנטו שלי אם אעבור למסלול המשפחתי?'],
  ['לוותר על הרכב', 'מה יקרה לנטו שלי אם אוותר על הרכב?'],
]

const fmtNet = (v) => `${v > 0 ? '+' : '−'}${Math.abs(v).toLocaleString('he-IL')} ₪`
// the answer as a screen reader should hear it: no Markdown marks (it would read "כוכבית")
const plainText = (md) => md.replace(/[*_`#>]+/g, '').replace(/^\s*[-+]\s+/gm, '').replace(/\s+/g, ' ').trim()

// autoFocus: coming in from the intro, the focus goes straight to the message box
export default function EmployeeScreen({ api = realApi, subscribe = subscribeChanges, notifier = realNotifier, onLogout, autoFocus = false }) {
  // the open conversation, kept for this tab (a reload stays on it); the list is on the server
  const [threadId, setThreadId] = useState(() => getCurrentThread())
  const [history, setHistory] = useState([])
  const [me, setMe] = useState(null) // { employee_id, name } (GET /me), for the sidebar
  const [usage, setUsage] = useState(null) // this week's usage (GET /usage), for the sidebar
  // "שלום נועה, אני כובי": the first name from GET /me; without one, the welcome as it was
  const firstName = me?.name?.trim().split(/\s+/)[0]
  const welcome = firstName ? chatCfg.welcomeNamed.replace('{name}', firstName) : chatCfg.welcome
  const [messages, setMessages] = useState([])
  const [cards, setCards] = useState([])
  const [step, setStep] = useState(null)
  const [busy, setBusy] = useState(false)
  const [input, setInput] = useState('')
  const boxRef = useRef(null)
  // a payslip chosen but not sent yet: { file, kind: 'image' | 'pdf', url, name }
  const [attachment, setAttachment] = useState(null)
  const [attachError, setAttachError] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [viewing, setViewing] = useState(null) // the large view: { src, opener } (focus goes back to opener)
  const fileRef = useRef(null)
  const cameraRef = useRef(null)
  const payslipUrl = useRef({ tid: null, url: null }) // the server's image (a promise), read once per conversation
  const isPhone = usePhone()
  const reduceMotion = Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches)
  const chatRef = useRef(null)
  const side = useSidebar(chatRef)
  // the profile dialog has an address (/profile): a direct link opens it too, and Back closes it
  const [profileOpen, setProfileOpen] = useState(() => window.location.pathname === profileCfg.path)
  const profileOpener = useRef(null) // where the focus goes back; none = the message box
  // "התאמה אישית" (kept on the server): light or dark on the page, the tone on the server's side
  const [settings, setSettings] = useState(settingsCfg.defaults)
  const [customizer, setCustomizer] = useState(null) // the button that opened the window, while it is open

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
  const listRef = useRef(null)
  const rootRef = useRef(null)
  const wasBusy = useRef(false)
  const busyRef = useRef(false) // set at once, so two reads of the state cannot both start the bot
  const turnStartCards = useRef(cards) // the cards before this answer began

  useEffect(() => { document.title = EMPLOYEE_TITLE }, [])
  // Coming in from the intro: the focus in the message box - without scrolling (the banner is still
  // shrinking, and a scroll now lands anywhere) - and once the banner has shrunk (the end of its height
  // transition, .intro in styles.css; afterBannerMs only if that never comes), one scroll so the chat fills
  // the screen, the banner scrolled out above it. Reduced motion: no transition, at once.
  // (Not when the profile opened over it from a direct link: the focus stays in the dialog.)
  useEffect(() => {
    if (!autoFocus || window.location.pathname === profileCfg.path) return
    boxRef.current?.focus({ preventScroll: true })
    let done = false
    const align = () => {
      if (done) return
      done = true
      const top = rootRef.current?.getBoundingClientRect().top
      if (top) window.scrollBy?.({ top, behavior: reduceMotion ? 'auto' : 'smooth' })
    }
    const banner = document.querySelector('.intro--banner')
    const onEnd = (e) => { if (e.target === banner && e.propertyName === 'height') align() }
    banner?.addEventListener('transitionend', onEnd)
    const t = setTimeout(align, reduceMotion ? 0 : chatCfg.afterBannerMs)
    return () => { clearTimeout(t); banner?.removeEventListener('transitionend', onEnd) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // the list starts (and stays) at its last message - scrolled itself: scrollIntoView would scroll the page too.
  // "Sticky bottom": it follows the answer only while the employee is at the end; scrolled up, it stays put and
  // "↓ תשובה חדשה" shows. A new question or conversation sticks it again.
  const stickRef = useRef(true)
  const [newBelow, setNewBelow] = useState(false)
  useLayoutEffect(() => {
    const list = listRef.current
    if (!list) return
    if (stickRef.current) list.scrollTop = list.scrollHeight
    else if (messages.length) setNewBelow(true)
  }, [messages])
  function onListScroll() {
    const list = listRef.current
    stickRef.current = list.scrollHeight - list.scrollTop - list.clientHeight < 40
    if (stickRef.current) setNewBelow(false)
  }
  function toBottom() {
    const list = listRef.current
    stickRef.current = true
    setNewBelow(false)
    list?.scrollTo?.({ top: list.scrollHeight, behavior: reduceMotion ? 'auto' : 'smooth' })
  }

  // the screen's visible height (above a phone keyboard): the fixed layout's height (styles.css --app-h)
  useEffect(() => {
    const vv = window.visualViewport
    if (!vv) return
    const update = () => document.documentElement.style.setProperty('--app-h', `${Math.round(vv.height)}px`)
    update()
    vv.addEventListener('resize', update)
    return () => {
      vv.removeEventListener('resize', update)
      document.documentElement.style.removeProperty('--app-h')
    }
  }, [])

  // the header's height: on a phone the chat is the rest of the screen under it (styles.css --topbar-h)
  const topbarRef = useRef(null)
  useEffect(() => {
    const top = topbarRef.current
    if (!top || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => {
      top.parentElement?.style.setProperty('--topbar-h', `${Math.round(top.getBoundingClientRect().height)}px`)
    })
    ro.observe(top)
    return () => ro.disconnect()
  }, [])

  // the focus goes to the message box without scrolling the page; in a layout effect, so it comes before
  // anything that would take it afterwards (the sidebar giving it back to its button)
  const [focusBox, setFocusBox] = useState(0)
  useLayoutEffect(() => { if (focusBox) boxRef.current?.focus({ preventScroll: true }) }, [focusBox])

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
    if (!tid || busyRef.current || loadingRef.current) return
    let s
    try { s = await api.restore(tid) } catch { return }
    if (busyRef.current || loadingRef.current) return
    applyState(tid, s)
  }

  function applyState(tid, s) {
    const restored = s.messages.map((m) => ({ ...m, id: nextId++ }))
    setMessages((ms) => {
      const errors = []
      for (let i = ms.length - 1; i >= 0 && ms[i].role === 'error'; i--) errors.unshift(ms[i])
      return [...restored, ...errors]
    })
    // the payslip kept on the server: its thumbnail on the latest payslip line (one per conversation)
    const last = restored.findLast((m) => m.role === 'payslip')
    if (last && s.payslip?.image) showServerPayslip(tid, last.id)
    if (s.cards.length) setCards((cs) => (cs.length ? cs : [s.cards[s.cards.length - 1]]))
    if (s.rep?.new_answers > 0) {
      append({ role: 'system', text: REP_ANSWERED })
      run((onEvent) => api.streamRepAnswered(tid, onEvent))
    }
  }

  // Opening a conversation (the history, a reload, after login): its state from the server, with a loading
  // state - shown only after loadingDelayMs, so a quick load does not flicker. Writing waits for it.
  // A conversation that is gone (404) is a new one; any other failure offers to try again.
  const [loading, setLoading] = useState(null) // null | { tid, shown, failed }
  const loadSeq = useRef(0)
  const loadingRef = useRef(false)
  // focus: move the focus to the message box once loaded - when the employee opened it, not on the
  // page's first load (the focus may be elsewhere by then: never taken from where the employee is)
  async function loadThread(tid, { focus = false } = {}) {
    const seq = ++loadSeq.current
    loadingRef.current = true
    setLoading({ tid, shown: false, failed: false })
    const timer = setTimeout(() => {
      if (loadSeq.current === seq) setLoading((l) => (l && !l.failed ? { ...l, shown: true } : l))
    }, chatCfg.loadingDelayMs)
    let s
    try {
      s = await api.restore(tid)
    } catch (err) {
      clearTimeout(timer)
      if (loadSeq.current !== seq) return
      loadingRef.current = false
      if (err?.status === 404) { setLoading(null); newConversation(); return }
      loadingRef.current = true // still not loaded: no other read, and writing waits
      setLoading({ tid, shown: true, failed: true })
      return
    }
    clearTimeout(timer)
    if (loadSeq.current !== seq) return
    loadingRef.current = false
    setLoading(null)
    applyState(tid, s)
    if (focus) setFocusBox((n) => n + 1)
  }

  function cancelLoading() {
    loadSeq.current++
    loadingRef.current = false
    setLoading(null)
  }

  // the weekly usage: read on load and after every answer (the server counts it)
  function loadUsage() {
    Promise.resolve(api.usage?.()).then((u) => { if (u) setUsage(u) }).catch(() => {})
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
    Promise.resolve(api.me?.()).then((m) => setMe(m ?? null)).catch(() => {})
    Promise.resolve(api.settings?.()).then((s) => { if (s) setSettings(s) }).catch(() => {})
    loadUsage()
    const tid = getCurrentThread()
    if (tid) loadThread(tid)
    loadHistory().then((list) => {
      if (!getCurrentThread() && !busyRef.current && list[0]) openThread(list[0].thread_id)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api])

  // the thumbnail of the payslip kept on the server; fetched once per conversation (it needs the token)
  // (the request itself is kept: a reload refreshes several times at once, and they share it)
  async function showServerPayslip(tid, messageId, fresh = false) {
    if (fresh || payslipUrl.current.tid !== tid) {
      payslipUrl.current = { tid, url: Promise.resolve(api.payslipImage?.(tid)).catch(() => null) }
    }
    const url = await payslipUrl.current.url
    if (!url) { if (payslipUrl.current.tid === tid) payslipUrl.current = { tid: null, url: null }; return }
    setMessages((ms) => ms.map((m) => (m.id === messageId ? { ...m, thumb: url } : m)))
  }

  function dropAttachment() {
    if (attachment?.url) URL.revokeObjectURL?.(attachment.url)
    setAttachment(null)
  }

  // a file from 📎, the camera, a drop or a paste: checked here first, then shown before sending
  function pick(file) {
    if (!file) return
    if (!threadId) { setAttachError(PT.needsConversation); return }
    const checked = checkFile(file)
    if (checked.error) { setAttachError(checked.error); return }
    dropAttachment()
    setAttachError(null)
    setAttachment({ file, kind: checked.kind, name: file.name,
      url: checked.kind === 'image' ? URL.createObjectURL?.(file) ?? null : null })
  }

  function onFileChosen(e) {
    pick(e.target.files?.[0])
    e.target.value = '' // choosing the same file again still counts
  }

  function removeAttachment() {
    dropAttachment()
    setAttachError(null)
    boxRef.current?.focus({ preventScroll: true })
  }

  // Ctrl+V (or paste from a long press on a phone): an image becomes the payslip; text stays text
  function onPaste(e) {
    const file = [...(e.clipboardData?.files ?? [])].find((f) => f.type.startsWith('image/'))
    if (!file) return
    e.preventDefault()
    pick(file)
  }

  const hasFiles = (e) => [...(e.dataTransfer?.types ?? [])].includes('Files')
  const drag = {
    onDragEnter: (e) => { if (hasFiles(e)) { e.preventDefault(); setDragging(true) } },
    onDragOver: (e) => { if (hasFiles(e)) e.preventDefault() },
    onDragLeave: (e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDragging(false) },
    onDrop: (e) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      setDragging(false)
      pick(e.dataTransfer.files?.[0])
    },
  }

  // returns false when the server refused the file (its text goes next to the message box)
  async function sendPayslip(att) {
    setAttachError(null)
    const bubbleId = append({ role: 'payslip', text: PT.shown, thumb: att.url, pdfName: att.kind === 'pdf' ? att.name : null })
    let refused = null
    const assistantId = await run((onEvent) => api.streamPayslip(threadId, att.file, (event, data) => {
      if (event === 'rejected') refused = data.message
      else onEvent(event, data)
    }))
    if (refused) {
      setMessages((ms) => ms.filter((m) => m.id !== bubbleId && m.id !== assistantId))
      setAttachError(refused)
      return false
    }
    // a PDF has no picture here: the server's first page (as kept) becomes its thumbnail
    if (att.kind === 'pdf') await showServerPayslip(threadId, bubbleId, true)
    else payslipUrl.current = { tid: threadId, url: Promise.resolve(att.url) }
    return true
  }

  function clearScreen() {
    dropAttachment()
    setAttachError(null)
    setMessages([])
    setCards([])
    setStops([])
    setStep(null)
    setParked(false)
    notifier.setUnread(0)
  }

  // a conversation from the list: its messages and cards come from the server
  function openThread(tid) {
    if (busyRef.current) return
    setCurrentThread(tid)
    setThreadId(tid)
    clearScreen()
    loadThread(tid, { focus: true })
  }

  function append(msg) {
    const m = { ...msg, id: nextId++ }
    setMessages((ms) => [...ms, m])
    return m.id
  }

  // what a screen reader hears (the hidden role="status" region): "כובי מקליד…" when an answer
  // starts, then the whole answer once it is done - never the letters as they stream in.
  // Cleared first, so the same words twice in a row are still read.
  const [announcement, setAnnouncement] = useState('')
  function announce(text) {
    setAnnouncement('')
    setTimeout(() => setAnnouncement(text), 50)
  }

  function handler(assistantId, said) {
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
        said.text += data.text
        setMessages((ms) => ms.map((m) => (m.id === assistantId ? { ...m, text: m.text + data.text } : m)))
      } else if (event === 'limit') {
        // the weekly limit is used up: no answer from Kobi, the server's fixed message with a mailto link
        said.limit = data.message
        setMessages((ms) => ms.map((m) => (m.id === assistantId
          ? { ...m, role: 'limit', text: data.message, email: data.email } : m)))
      } else if (event === 'error') {
        said.error = data.message
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
    announce(A11Y.live.typing)
    const said = { text: '', error: null }
    await start(handler(assistantId, said))
    const spoken = plainText(said.text)
    announce([spoken && `${A11Y.live.answered} ${spoken}`, said.limit, said.error].filter(Boolean).join(' '))
    setStep(null)
    busyRef.current = false
    setBusy(false)
    loadHistory() // a new conversation, or a new title from the card
    loadUsage()
    return assistantId
  }

  async function send(e) {
    e.preventDefault()
    const text = input.trim()
    if ((!text && !attachment) || busy || loadingRef.current) return
    setInput('')
    if (attachment) {
      const att = attachment
      setAttachment(null) // the bubble keeps its local picture
      if (!(await sendPayslip(att))) { setAttachment(att); setInput(text); return }
    }
    if (text) await ask(text)
  }

  async function ask(text) {
    if (busyRef.current) return
    notifier.setUnread(0)
    stickRef.current = true
    setNewBelow(false)
    // a welcome choice unmounts the button that had the focus: back to the box, without scrolling the page
    boxRef.current?.focus({ preventScroll: true })
    append({ role: 'user', text })
    await run((onEvent) => api.streamChat({ message: text, threadId }, onEvent))
  }

  // A fresh start. The previous conversation stays in "my conversations".
  function newConversation() {
    cancelLoading()
    setCurrentThread(null)
    setThreadId(null)
    clearScreen()
    setFocusBox((n) => n + 1)
  }

  // opened here (the sidebar, Kobi's link): a new history entry, so Back closes it
  function openProfile(opener) {
    profileOpener.current = opener ?? null
    if (window.location.pathname !== profileCfg.path) {
      window.history.pushState({ kobiProfile: true }, '', profileCfg.path)
    }
    setProfileOpen(true)
  }

  // ✕, Esc, a click outside: back to the address before it. Opened by a direct link there is no
  // entry of ours to go back to, so the address becomes the conversation's.
  function closeProfile() {
    if (window.history.state?.kobiProfile) window.history.back() // popstate closes it
    else {
      window.history.replaceState(null, '', '/')
      setProfileOpen(false)
    }
  }

  useEffect(() => {
    const onPop = () => setProfileOpen(window.location.pathname === profileCfg.path)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  // closed: the focus goes back to what opened it (or the message box, after a direct link)
  const profileWasOpen = useRef(profileOpen)
  useEffect(() => {
    if (profileWasOpen.current && !profileOpen) {
      const opener = profileOpener.current
      ;(opener?.isConnected ? opener : boxRef.current)?.focus()
      profileOpener.current = null
    }
    profileWasOpen.current = profileOpen
  }, [profileOpen])

  // light or dark: on <html>, where the color tokens are (styles.css). Light again when the employee
  // screen goes (logout): the opening scene and the statement are light
  useEffect(() => { document.documentElement.dataset.theme = settings.theme }, [settings.theme])
  useEffect(() => () => { document.documentElement.dataset.theme = settingsCfg.defaults.theme }, [])

  function closeCustomize() {
    const opener = customizer
    setCustomizer(null)
    ;(opener?.isConnected ? opener : boxRef.current)?.focus()
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

  // the sidebar over the chat (a phone, or no room): the rest of the page waits behind it
  const behind = side.floating || undefined

  return (
    <div ref={rootRef} className={`employee ${panelOpen ? '' : 'employee--closed'} ${side.expanded && !side.floating ? 'employee--side' : ''}`}
      style={{ '--side-w': `${sidebarCfg.width}px`, '--rail-w': `${sidebarCfg.railWidth}px` }}>
      <div className="side">
        <Sidebar state={side} busy={busy} onNew={newConversation} onProfile={openProfile}
          onCustomize={(opener) => setCustomizer(opener ?? true)} usage={usage} history={history} threadId={threadId}
          onOpenThread={openThread} name={me?.name} onLogout={onLogout} />
      </div>
      <header ref={topbarRef} className="topbar" inert={behind}>
        <img className="topbar__logo" src={logo} alt="שטראוס" />
        <span className="topbar__sep" aria-hidden="true" />
        <h1 className="topbar__title">
          <span className="topbar__name">כובי</span>
          <span className="topbar__product">יועץ הרכב של שטראוס</span>
        </h1>
        {side.phone && (
          <button type="button" className="topbar__menu" aria-label={sidebarCfg.texts.toggle}
            aria-expanded={side.expanded} aria-controls="sidebar" onClick={() => side.open()}>
            <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
          </button>
        )}
        <p className="topbar__sub"><strong>רק בדיקה, שום דבר לא משתנה בשכר או ברכב שלכם</strong> · לפי כללי שטראוס ורשות המסים</p>
      </header>

      <main ref={chatRef} className={`chat ${dragging ? 'chat--drop' : ''}`} inert={behind} {...drag}>
        {dragging && <div className="chat__dropzone" aria-hidden="true">{PT.drop}</div>}
        {loading?.shown && (loading.failed ? (
          <div className="chat__loading" role="alert">
            <p>{chatCfg.texts.loadFailed}</p>
            <button type="button" className="chat__retry" onClick={() => loadThread(loading.tid, { focus: true })}>{chatCfg.texts.retry}</button>
          </div>
        ) : (
          <div className="chat__loading" role="status" aria-label={chatCfg.texts.loading}>
            {/* reduced motion: the text alone, no moving bubbles */}
            {!reduceMotion && (
              <div className="loading__bubbles" aria-hidden="true">
                <span className="loading__bubble loading__bubble--user" />
                <span className="loading__bubble" />
                <span className="loading__bubble loading__bubble--short" />
              </div>
            )}
            <p className="loading__text">{chatCfg.texts.loading}</p>
          </div>
        ))}
        {messages.length === 0 && !loading && (
          <section className="welcome" aria-labelledby="welcome-title">
            <div className="welcome__car" aria-hidden="true"><CarBody /></div>
            <h2 id="welcome-title" className="welcome__title">{welcome}</h2>
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
        {/* not a live region (it would read the answer letter by letter): the status line below speaks.
            Focusable, so the keyboard can scroll it */}
        <ol ref={listRef} className={`chat__messages ${messages.length ? '' : 'chat__messages--empty'}`} aria-label="השיחה"
          tabIndex={0} aria-busy={loading ? 'true' : undefined} onScroll={onListScroll}>
          {messages.map((m) => m.role === 'limit' ? (
            <li key={m.id} className="msg msg--limit"><LimitText text={m.text} email={m.email} /></li>
          ) : m.role === 'payslip' ? (
            <li key={m.id} className="msg msg--user msg--payslip">
              {m.thumb ? (
                <button type="button" className="msg__thumb" aria-label={PT.open}
                  onClick={(e) => setViewing({ src: m.thumb, opener: e.currentTarget })}>
                  <img src={m.thumb} alt="" width="48" height="48" />
                </button>
              ) : m.pdfName ? (
                <span className="msg__pdf"><PdfIcon /><bdi>{m.pdfName}</bdi></span>
              ) : null}
              <span>{m.text}</span>
            </li>
          ) : (
            <li key={m.id} className={`msg msg--${m.role}`}>
              {m.role === 'assistant' && m.text && <span className="msg__who">כובי · בוט</span>}
              {m.role === 'assistant' && !m.text && busy && m.id === currentId
                ? <span className="msg__typing">{A11Y.live.typing}</span>
                : m.role === 'system' ? REP_ANSWERED : m.role === 'assistant' ? <Answer text={m.text} onProfile={openProfile} /> : m.text}
            </li>
          ))}
        </ol>
        {newBelow && <button type="button" className="chat__new-below" onClick={toBottom}>{chatCfg.texts.newBelow}</button>}
        <p className="visually-hidden" role="status" aria-live="polite" aria-atomic="true" aria-label={A11Y.live.name}>{announcement}</p>
        {/* a new key per answer: the car starts each trip from the start line */}
        {roadPhase && <Road key={currentId ?? 'idle'} phase={roadPhase} stops={stops} label={step} />}
        {attachment && (
          // above the message box, in the page's flow: on a phone it never covers the box or the keyboard
          <div className="preview" role="group" aria-label={PT.attach}>
            {attachment.kind === 'image'
              ? <img className="preview__img" src={attachment.url} alt={PT.image} />
              : <span className="preview__pdf"><PdfIcon label={PT.pdf} /><bdi>{attachment.name}</bdi></span>}
            <button type="button" className="preview__remove" aria-label={PT.remove} onClick={removeAttachment}>
              <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
            </button>
          </div>
        )}
        {attachError && <p id="attach-error" className="composer__error" role="alert">{attachError}</p>}
        <form className="chat__form" onSubmit={send}>
          <ContactRep />
          {threadId && (
            <div className="attach">
              <input id="payslip-file" ref={fileRef} type="file" accept={payslipCfg.accept} className="visually-hidden"
                tabIndex={-1} aria-hidden="true" onChange={onFileChosen} />
              <button type="button" className="attach__btn" aria-label={PT.attach} title={PT.attach}
                disabled={busy || Boolean(loading)} onClick={() => fileRef.current?.click()}>
                <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M20 11.5l-8.2 8.2a5 5 0 01-7.1-7.1l8.5-8.5a3.3 3.3 0 014.7 4.7l-8.5 8.5a1.7 1.7 0 01-2.4-2.4l7.8-7.8" />
                </svg>
              </button>
              {isPhone && (
                <>
                  <input id="payslip-camera" ref={cameraRef} type="file" accept="image/*" capture="environment"
                    className="visually-hidden" tabIndex={-1} aria-hidden="true" onChange={onFileChosen} />
                  <button type="button" className="attach__btn attach__btn--camera" aria-label={PT.camera}
                    disabled={busy || Boolean(loading)} onClick={() => cameraRef.current?.click()}>
                    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" />
                    </svg>
                    <span>{PT.cameraLabel}</span>
                  </button>
                </>
              )}
            </div>
          )}
          <label htmlFor="msg" className="visually-hidden">הודעה</label>
          {/* while a conversation loads: read only (it keeps the focus), and nothing can be sent */}
          <textarea id="msg" ref={boxRef} rows={1} value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) send(e) }} onPaste={onPaste}
            aria-describedby={attachError ? 'attach-error' : undefined}
            readOnly={Boolean(loading)} aria-disabled={loading ? 'true' : undefined}
            placeholder="כתבו שאלה…" />
          <button type="submit" disabled={busy || Boolean(loading)}>שליחה</button>
        </form>
        <SiteFooter />
        {viewing && <PayslipViewer src={viewing.src} opener={viewing.opener} onClose={() => setViewing(null)} />}
        {profileOpen && <ProfileDialog api={api} onClose={closeProfile} />}
        {customizer && <CustomizeDialog api={api} settings={settings} onChange={setSettings} onClose={closeCustomize} />}
      </main>

      <div className="divider" inert={behind}>
        {panelOpen && (
          <button type="button" className="divider__btn" onClick={togglePanel}
            aria-expanded="true" aria-controls="cmp-panel" aria-label="סגירת פאנל ההשוואה">
            <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>
          </button>
        )}
      </div>

      <section className="panel" inert={behind}>
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
          {/* the cards' headings are h3: this h2 keeps the outline in order (the visible title is a button) */}
          <h2 className="visually-hidden">השוואה</h2>
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
        <button type="button" className="sidetab" onClick={togglePanel} inert={behind}
          aria-expanded="false" aria-controls="cmp-panel" aria-label="פתיחת פאנל השוואה">
          <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
          <span className="sidetab__text">השוואה</span>
          {waiting && <span aria-hidden="true">⏳</span>}
        </button>
      )}

    </div>
  )
}

// the weekly limit's message from the server, its address as a mailto link
function LimitText({ text, email }) {
  const at = email ? text.indexOf(email) : -1
  if (at < 0) return text
  return <>{text.slice(0, at)}<a href={`mailto:${email}`}><bdi>{email}</bdi></a>{text.slice(at + email.length)}</>
}

// a PDF payslip: an icon (with a name for screen readers when it stands alone)
function PdfIcon({ label }) {
  return (
    <svg className="pdf-icon" width="28" height="28" viewBox="0 0 24 24" role={label ? 'img' : undefined}
      aria-label={label} aria-hidden={label ? undefined : 'true'}>
      <path d="M6 2h8l5 5v15H6z" /><path d="M14 2v5h5" /><text x="12.5" y="17.5" textAnchor="middle">PDF</text>
    </svg>
  )
}

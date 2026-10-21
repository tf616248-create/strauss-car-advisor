import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import cfg from '../config/sidebar.json'

const T = cfg.texts
const fmtWhen = (iso) => new Date(iso).toLocaleString('he-IL', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' })

// is the chat too narrow for the sidebar open beside it? chatWidth is its width now; while the
// sidebar is closed (a strip), opening it would take the difference between the two widths
export function isCramped(chatWidth, open) {
  const ifOpen = open ? chatWidth : chatWidth - (cfg.width - cfg.railWidth)
  return ifOpen < cfg.minChatWidth
}

function readOpen() {
  try { return localStorage.getItem(cfg.storageKey) === '1' } catch { return false }
}
function saveOpen(open) {
  try { localStorage.setItem(cfg.storageKey, open ? '1' : '0') } catch { /* blocked storage: not kept */ }
}

function useMedia(query) {
  const mq = () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query) : null)
  const [matches, setMatches] = useState(() => Boolean(mq()?.matches))
  useEffect(() => {
    const m = mq()
    if (!m?.addEventListener) return
    const onChange = (e) => setMatches(e.matches)
    m.addEventListener('change', onChange)
    return () => m.removeEventListener('change', onChange)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query])
  return matches
}

// The sidebar's state. On a computer: open (pushes the chat, kept in the browser) or a strip.
// When the chat would be narrower than minChatWidth it folds back to the strip; opening it then,
// or on a phone, puts it over the chat ("floating"), and Escape or a pick closes it.
// chatRef: the chat, whose width is watched.
export function useSidebar(chatRef) {
  const phone = useMedia(cfg.phoneQuery)
  const [pref, setPref] = useState(readOpen)
  const [floating, setFloating] = useState(false)
  const [cramped, setCramped] = useState(false)
  const focusTo = useRef(null) // what gets the focus once it is open: 'top' or 'list'
  const pushed = !phone && pref && !cramped
  const expanded = pushed || floating

  useEffect(() => {
    const chat = chatRef.current
    if (phone || !chat || typeof ResizeObserver === 'undefined') return
    // the chat's whole column (with its padding), as the employee sees it
    const ro = new ResizeObserver(([entry]) => setCramped(isCramped(entry.target.getBoundingClientRect().width, pushed)))
    ro.observe(chat)
    return () => ro.disconnect()
  }, [chatRef, phone, pushed])

  function open(target = 'top') {
    focusTo.current = target
    if (phone || cramped) {
      setFloating(true)
    } else {
      setPref(true)
      saveOpen(true)
    }
  }

  function close() {
    if (floating) {
      setFloating(false)
      // back to the button that opens it: in the header on a phone, on the strip on a computer
      // (not "the element that had the focus": a tap on a phone does not always focus a button)
      setTimeout(() => document.querySelector(phone ? '.topbar__menu' : '.sidebar__toggle')?.focus(), 0)
    } else {
      setPref(false)
      saveOpen(false)
    }
  }

  // Escape closes the one over the chat
  useEffect(() => {
    if (!floating) return
    const onKey = (e) => { if (e.key === 'Escape') close() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [floating])

  return { phone, expanded, floating, focusTo, toggle: () => (expanded ? close() : open()), open, close }
}

// the sidebar itself: new conversation, three items for later, my conversations, the name and logout
export default function Sidebar({ state, busy, onNew, onProfile, history, threadId, onOpenThread, name, onLogout }) {
  const { phone, expanded, floating, focusTo } = state
  const topRef = useRef(null)
  const listRef = useRef(null)

  // the focus goes into the sidebar when it opens
  useEffect(() => {
    if (!expanded || !focusTo.current) return
    const target = focusTo.current
    focusTo.current = null
    if (target === 'list') {
      const list = listRef.current
      const item = list?.querySelector('[aria-current="true"]') ?? list?.querySelector('button')
      ;(item ?? topRef.current)?.focus()
    } else topRef.current?.focus()
  }, [expanded, focusTo, history])

  if (phone && !floating) return null // a phone has no strip: the header button opens it

  const pick = (fn) => () => { fn(); if (floating) state.close() }
  const cls = `sidebar ${expanded ? 'sidebar--open' : ''} ${floating ? 'sidebar--floating' : ''}`

  const sidebar = (
    <>
      {floating && <div className="sidebar__backdrop" aria-hidden="true" onClick={state.close} />}
      <aside id="sidebar" className={cls} aria-label={T.label}
        style={{ '--side-w': `${cfg.width}px`, '--rail-w': `${cfg.railWidth}px` }}>
        {floating ? (
          <button ref={topRef} type="button" className="sidebar__item sidebar__toggle" aria-label={T.close}
            onClick={state.close}>
            <Icon d="M6 6l12 12M18 6L6 18" />
          </button>
        ) : (
          <button ref={topRef} type="button" className="sidebar__item sidebar__toggle" aria-label={T.toggle}
            aria-expanded={expanded} aria-controls="sidebar" onClick={() => state.toggle()}>
            <Icon d="M4 6h16M4 12h16M4 18h16" />
          </button>
        )}

        <button type="button" className="sidebar__item" data-item="new" onClick={pick(onNew)} disabled={busy}>
          <Icon d="M12 5v14M5 12h14" />
          <span className="sidebar__label">{T.newConversation}</span>
        </button>
        {/* the profile opens over the conversation (ProfileDialog.jsx); the focus comes back here */}
        <button type="button" className="sidebar__item" data-item="profile"
          onClick={(e) => { const opener = e.currentTarget; onProfile?.(opener); if (floating) state.close() }}>
          <Icon><circle cx="12" cy="8" r="4" /><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" /></Icon>
          <span className="sidebar__label">{T.profile}</span>
        </button>
        {/* not built yet: focusable (so the keyboard finds them), aria-disabled, "soon" */}
        {[['customize', <path d="M4 7h10M18 7h2M4 17h4M12 17h8M14 5v4M8 15v4" />],
          ['usage', <path d="M5 20V12M12 20V5M19 20v-9" />]].map(([key, shape]) => (
          <button key={key} type="button" className="sidebar__item" data-item={key} aria-disabled="true"
            title={`${T[key]} · ${T.soon}`}>
            <Icon>{shape}</Icon>
            <span className="sidebar__label">{T[key]}</span>{' '}
            <span className="sidebar__soon">{T.soon}</span>
          </button>
        ))}

        <div className="sidebar__gap" aria-hidden="true" />

        {expanded ? (
          <nav className="sidebar__history" aria-labelledby="sidebar-history">
            <h2 id="sidebar-history" className="sidebar__heading">{T.history}</h2>
            {history.length === 0
              ? <p className="history__empty">{T.historyEmpty}</p>
              : (
                <ul ref={listRef} className="history__list">
                  {history.map((t) => (
                    <li key={t.thread_id}>
                      <button type="button" className="history__item" data-item="thread" data-thread={t.thread_id}
                        aria-current={t.thread_id === threadId ? 'true' : undefined}
                        onClick={pick(() => onOpenThread(t.thread_id))} disabled={busy}>
                        <span className="history__title">{t.title || T.untitled}</span>
                        <span className="history__when">{fmtWhen(t.updated_at)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
          </nav>
        ) : (
          <button type="button" className="sidebar__item" aria-label={T.history}
            aria-expanded="false" aria-controls="sidebar" onClick={() => state.open('list')}>
            <Icon d="M12 7v5l3 2M3.5 12a8.5 8.5 0 1 0 2.5-6M3 4v4h4" />
          </button>
        )}

        <div className="sidebar__spacer" />

        <div className="sidebar__user">
          {name && (
            <>
              <span className="sidebar__avatar" aria-hidden="true">{name.trim()[0]}</span>
              <span className="sidebar__name sidebar__label">{name}</span>
            </>
          )}
          <button type="button" className="sidebar__item sidebar__logout" data-item="logout" onClick={() => onLogout?.()}>
            <Icon d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10" />
            <span className="sidebar__label">{T.logout}</span>
          </button>
        </div>
      </aside>
    </>
  )
  // over the chat: straight in <body>, so no ancestor (the chat's entrance animation moves it with
  // a transform) can hold a position: fixed element inside itself
  return floating ? createPortal(sidebar, document.body) : sidebar
}

function Icon({ d, children }) {
  return (
    <svg className="sidebar__icon" width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
      {d ? <path d={d} /> : children}
    </svg>
  )
}

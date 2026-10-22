// The little road under the chat. It is built while the answer runs: every tool the
// model really calls adds a stop, and the finish lights only with a real result (a card).
// View only - it never decides anything and never guesses the next step.
//
// While a step runs the car drives on its own, slowly, toward the next stop and slows down as it
// gets closer, but it never goes past SHARE of the way: it reaches a stop only when that step
// really ended (a tool was called), so what it shows is never ahead of what happened. Then it
// catches up to the stop, and drives on slowly. Reduced motion: no animation, the car stands at
// the stop of the current step. The scene is aria-hidden; the status line says what is going on.
import { useEffect, useState } from 'react'
import logo from '../assets/strauss-logo.svg'

// short stop names for the known tools (backend/app/agent/graph.py)
const NAMES = {
  lookup_vehicle: 'איתור רכב',
  check_eligibility: 'זכאות',
  calculate: 'חישוב נטו',
  ask_rep: 'שאלה לנציג',
}
const MAX_STOPS = 3
const WAITING = 'כובי שלח שאלה לנציג התחבורה ⏳'
// distance from the right edge (RTL: the car drives right to left), in %
export const SLOTS = [12, 34, 56]
export const START = 2
export const FINISH = 84
const PARK = 96
const WAIT_AT = 62 // stopped at the light, before the finish
export const SHARE = 0.8 // how far toward the next stop the car may drive before its step really ends
const CRUISE_S = 4 // the slow drive on: its time constant, in seconds (slower and slower near the cap)
const CATCH_UP = 15 // % a second: a step really ended, so the car speeds up to its stop (under 1.5s)
const MOVING = 0.05 // % a second: below it the car counts as standing (no wheels, no bobbing)
const REDUCE = '(prefers-reduced-motion: reduce)'
const reducedMotion = () => Boolean(window.matchMedia?.(REDUCE)?.matches)

export function stopName({ tool, label }) {
  return NAMES[tool] ?? (label ?? '').replace(/…$/, '')
}

// where the car may be: "at" is the stop the answer really reached, "upTo" the furthest it may drive
export function legOf(phase, count) {
  if (phase === 'arrived') return { at: PARK, upTo: PARK }
  if (phase === 'waiting') return { at: WAIT_AT, upTo: WAIT_AT }
  const at = count === 0 ? START : SLOTS[count - 1]
  const next = count < SLOTS.length ? SLOTS[count] : FINISH
  return { at, upTo: at + SHARE * (next - at) }
}

// one frame of dt seconds: catch up to the stop really reached, then on toward upTo, never past it.
// A car already past upTo (e.g. stopped at the light) stays where it is: it never drives back
export function drive(pos, { at, upTo }, dt) {
  if (pos < at) return Math.min(at, pos + CATCH_UP * dt)
  if (pos >= upTo) return pos
  return Math.min(upTo, pos + (upTo - pos) * (1 - Math.exp(-dt / CRUISE_S)))
}

// the white car with the Strauss logo is Kobi, the bot (also parked on the welcome screen).
// No face and no eyes, on purpose
export function CarBody() {
  return (
  <div className="road__body">
    <svg viewBox="0 0 100 46" width="92" height="42">
      <ellipse cx="50" cy="42" rx="42" ry="3.5" fill="#000" opacity="0.16" />
      <path d="M5 31 Q5 23 13 22 L27 20 L38 10 Q41 8 46 8 L69 8 Q75 8 79 12 L88 21 Q96 22 96 29 L96 34 L5 34 Z" fill="#FFFFFF" stroke="#8E959E" strokeWidth="1.3" />
      <path d="M32 20 L41 11.5 L55 11.5 L55 20 Z" fill="#D4E4EF" />
      <path d="M58 11.5 L69 11.5 Q73 11.5 76 14.5 L81 20 L58 20 Z" fill="#D4E4EF" />
      <rect x="6" y="25" width="5" height="3" rx="1.5" fill="#F2C94C" />
      {[24, 78].map((cx) => (
        <g key={cx} className="road__wheel">
          <circle cx={cx} cy="34" r="7.5" fill="#2B2F36" />
          <circle cx={cx} cy="34" r="3.2" fill="#C9CED4" />
          <path d={`M${cx - 5.5} 34 H${cx + 5.5} M${cx} 28.5 V39.5`} stroke="#2B2F36" strokeWidth="1.4" />
        </g>
      ))}
    </svg>
    <img className="road__logo" src={logo} alt="" />
  </div>
  )
}

export default function Road({ phase, stops = [], label }) {
  const shown = stops.slice(-MAX_STOPS)
  const [reduce] = useState(reducedMotion)
  const { at, upTo } = legOf(phase, shown.length)
  const [car, setCar] = useState({ pos: at, speed: 0 })
  useEffect(() => {
    if (reduce) return undefined
    let frame
    let last
    const tick = (now) => {
      const dt = last === undefined ? 0 : Math.min((now - last) / 1000, 0.25) // a background tab: no jump
      last = now
      if (dt > 0) setCar(({ pos }) => { const next = drive(pos, { at, upTo }, dt); return { pos: next, speed: (next - pos) / dt } })
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [reduce, at, upTo])
  const pos = reduce ? at : car.pos
  const moving = !reduce && car.speed > MOVING
  const note = phase === 'waiting' ? WAITING : phase === 'arrived' ? 'התשובה מוכנה' : (label || 'כובי חושב…')
  const stopState = (i) => (phase === 'driving' && i === shown.length - 1 ? 'active' : 'done')
  return (
    <div className={`road road--${phase}`}>
      <span role="status" className="visually-hidden">{note}</span>
      <div className="road__scene" aria-hidden="true">
        <div className="road__lane" />
        {shown.map((s, i) => (
          <div key={`${stops.length - shown.length + i}-${s.tool}`} className={`stop stop--${stopState(i)}`} style={{ right: `${SLOTS[i]}%` }}>
            <span className="stop__label">{stopName(s)}</span>
            <span className="stop__dot" />
          </div>
        ))}
        <div className={`finish ${phase === 'arrived' ? 'finish--done' : ''}`} style={{ right: `${FINISH}%` }}>
          <span className="finish__label">תוצאה</span>
          <span className="finish__flag" />
        </div>
        {phase === 'waiting' && (
          <div className="road__light" style={{ right: `calc(${WAIT_AT}% + 42px)` }}>
            <span /><span className="road__lamp" /><span />
          </div>
        )}
        {/* at the start line the whole car (and its note) stays inside the road, not half past the edge */}
        <div className={`road__car${phase === 'driving' && !shown.length ? ' road__car--start' : ''}${moving ? ' road__car--moving' : ''}`}
          style={{ right: `${pos}%` }}>
          {/* the stop itself names the running step; above the car only "thinking" or "waiting" */}
          {(phase === 'waiting' || (phase === 'driving' && !shown.length)) && <span className="road__note">{note}</span>}
          <CarBody />
        </div>
      </div>
    </div>
  )
}

// The little road under the chat: the car drives between stations that match the
// real steps the server reports. View only - it never decides anything.
import logo from '../assets/strauss-logo.svg'

// Server step labels (backend/config/agent.json, "steps"), in the order the tools run.
const STATIONS = [
  { step: 'מחפש את הרכב…', label: 'שווי שימוש' },
  { step: 'בודק זכאות…', label: 'זכאות' },
  { step: 'מחשב נטו…', label: 'חישוב נטו' },
]
// distance from the right edge (RTL: the car drives right to left), in %
const AT = [12, 50, 88]
const START = 2
const PARK = 96
const WAIT_AT = 64 // between the last two stations, stopped at the light

export function stationIndex(stepLabel) {
  return STATIONS.findIndex((s) => s.step === stepLabel)
}

function carPosition(phase, reached) {
  if (phase === 'arrived') return PARK
  if (phase === 'waiting') return WAIT_AT
  // driving: creep most of the way to the next station, never reach it on its own
  const from = reached < 0 ? START : AT[reached]
  const to = reached + 1 < AT.length ? AT[reached + 1] : PARK
  return from + (to - from) * 0.75
}

function stationState(i, phase, reached) {
  if (phase === 'arrived' || i <= reached) return 'done'
  if (phase === 'waiting') return i < STATIONS.length - 1 ? 'done' : 'idle'
  if (phase === 'driving' && i === reached + 1) return 'active'
  return 'idle'
}

export default function Road({ phase, reached = -1, label }) {
  const note = phase === 'waiting' ? '⏳ ממתין לנציג' : phase === 'arrived' ? 'התשובה מוכנה' : (label || 'חושב…')
  return (
    <div className={`road road--${phase}`}>
      <span role="status" className="visually-hidden">{note}</span>
      <div className="road__scene" aria-hidden="true">
        <div className="road__lane" />
        {STATIONS.map((s, i) => (
          <div key={s.step} className={`station station--${stationState(i, phase, reached)}`} style={{ right: `${AT[i]}%` }}>
            <span className="station__label">{s.label}</span>
            <span className="station__dot" />
          </div>
        ))}
        {phase === 'waiting' && (
          <div className="road__light" style={{ right: `calc(${WAIT_AT}% + 48px)` }}>
            <span /><span className="road__lamp" /><span />
          </div>
        )}
        <div className="road__car" style={{ right: `${carPosition(phase, reached)}%` }}>
          {phase !== 'arrived' && <span className="road__note">{note}</span>}
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
        </div>
      </div>
    </div>
  )
}

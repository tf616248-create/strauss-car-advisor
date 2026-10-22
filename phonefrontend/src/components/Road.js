// The little road under the chat. It is built while the answer runs: every tool the
// model really calls adds a stop, and the finish lights only with a real result (a card).
// View only - it never decides anything and never guesses the next step.
// The car drives right to left, on its own while a step runs: slowly toward the next stop, slower and
// slower, but at most SHARE (80%) of the way - it reaches a stop only when that step really ended (a
// tool was called), so what it shows is never ahead of what happened. Then it catches up and drives on
// (like the website's Road). With "reduce motion" on it stands at the stop of the current step.
import { useEffect, useState } from 'react'
import { AccessibilityInfo, View } from 'react-native'
import Svg, { Circle, Ellipse, G, Path, Rect, SvgXml } from 'react-native-svg'
import logo from '../assets/logo'
import { useColors } from '../theme'
import { T } from './ui'

// short stop names for the known tools (backend/app/agent/graph.py)
const NAMES = {
  lookup_vehicle: 'איתור רכב',
  check_eligibility: 'זכאות',
  calculate: 'חישוב נטו',
  ask_rep: 'שאלה לנציג',
}
const MAX_STOPS = 3
const WAITING = 'כובי שלח שאלה לנציג התחבורה ⏳'
// distance from the right edge, in % of the road
export const SLOTS = [12, 34, 56]
export const START = 2
export const FINISH = 84
const PARK = 90
const WAIT_AT = 62 // stopped at the light, before the finish
const CAR_W = 72
export const SHARE = 0.8 // how far toward the next stop the car may drive before its step really ends
const CRUISE_S = 4 // the slow drive on: its time constant, in seconds
const CATCH_UP = 15 // % a second: a step really ended, so the car speeds up to its stop

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
export function CarBody({ width = 92 }) {
  const height = (width * 46) / 100
  return (
    <View style={{ width, height }}>
      <Svg viewBox="0 0 100 46" width={width} height={height}>
        <Ellipse cx="50" cy="42" rx="42" ry="3.5" fill="#000" opacity={0.16} />
        <Path d="M5 31 Q5 23 13 22 L27 20 L38 10 Q41 8 46 8 L69 8 Q75 8 79 12 L88 21 Q96 22 96 29 L96 34 L5 34 Z" fill="#FFFFFF" stroke="#8E959E" strokeWidth={1.3} />
        <Path d="M32 20 L41 11.5 L55 11.5 L55 20 Z" fill="#D4E4EF" />
        <Path d="M58 11.5 L69 11.5 Q73 11.5 76 14.5 L81 20 L58 20 Z" fill="#D4E4EF" />
        <Rect x="6" y="25" width="5" height="3" rx="1.5" fill="#F2C94C" />
        {[24, 78].map((cx) => (
          <G key={cx}>
            <Circle cx={cx} cy="34" r="7.5" fill="#2B2F36" />
            <Circle cx={cx} cy="34" r="3.2" fill="#C9CED4" />
          </G>
        ))}
      </Svg>
      <View style={{ position: 'absolute', left: width * 0.47, top: height * 0.47, width: width * 0.2, height: height * 0.3 }}>
        <SvgXml xml={logo} width="100%" height="100%" />
      </View>
    </View>
  )
}

export default function Road({ phase, stops = [], label }) {
  const c = useColors()
  const shown = stops.slice(-MAX_STOPS)
  const note = phase === 'waiting' ? WAITING : phase === 'arrived' ? 'התשובה מוכנה' : (label || 'כובי חושב…')
  const [width, setWidth] = useState(0)
  const [reduce, setReduce] = useState(false)
  const { at: legAt, upTo } = legOf(phase, shown.length)
  const [carPos, setCarPos] = useState(legAt)

  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled?.().then((on) => setReduce(Boolean(on))).catch(() => {})
  }, [])
  // frame by frame (requestAnimationFrame): the leg changes when a step really ends
  useEffect(() => {
    if (reduce) return undefined
    let frame
    let last
    const tick = (now) => {
      const dt = last === undefined ? 0 : Math.min((now - last) / 1000, 0.25) // a paused app: no jump
      last = now
      if (dt > 0) setCarPos((p) => drive(p, { at: legAt, upTo }, dt))
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [reduce, legAt, upTo])
  const pos = reduce ? legAt : carPos

  // the car's right edge at pos% of the road; it moves left (negative x) from the right side
  const x = -Math.max(width - CAR_W, 0) * (pos / 100)
  const at = (pct) => ({ position: 'absolute', right: `${pct}%` })

  return (
    <View style={{ paddingHorizontal: 12, paddingVertical: 4 }}>
      <View accessibilityRole="text" accessibilityLiveRegion="polite" accessibilityLabel={note}>
        {(phase === 'waiting' || (phase === 'driving' && !shown.length)) && <T size={13} muted>{note}</T>}
      </View>
      <View onLayout={(e) => setWidth(e.nativeEvent.layout.width)} style={{ height: 70 }} importantForAccessibility="no-hide-descendants">
        <View style={{ position: 'absolute', left: 0, right: 0, bottom: 10, height: 4, borderRadius: 2, backgroundColor: c.line }} />
        {shown.map((s, i) => {
          const active = phase === 'driving' && i === shown.length - 1
          return (
            <View key={`${stops.length - shown.length + i}-${s.tool}`} style={[at(SLOTS[i]), { bottom: 6, alignItems: 'center' }]}>
              <T size={11} weight={active ? 800 : 600} color={active ? c.cyanText : c.muted}>{stopName(s)}</T>
              <View style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: active ? c.cyan : c.green }} />
            </View>
          )
        })}
        <View style={[at(FINISH), { bottom: 6, alignItems: 'center' }]}>
          <T size={11} weight={700} color={phase === 'arrived' ? c.cyanText : c.muted}>תוצאה</T>
          <View style={{ width: 14, height: 14, borderRadius: 3, backgroundColor: phase === 'arrived' ? c.green : c.line }} />
        </View>
        {phase === 'waiting' && (
          <View style={[at(WAIT_AT - 6), { bottom: 18, width: 10, height: 26, borderRadius: 4, backgroundColor: '#2B2F36', alignItems: 'center', justifyContent: 'center' }]}>
            <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: c.orange }} />
          </View>
        )}
        <View testID="road-car" position={pos} style={{ position: 'absolute', right: 0, bottom: 6, transform: [{ translateX: x }] }}>
          <CarBody width={CAR_W} />
        </View>
      </View>
    </View>
  )
}

// Comparison card, built from the `calculate` tool result. Every number here comes
// from the server; the card only formats. On a phone the table is a row per field:
// the name, then today | the alternative | the difference.
import { useEffect, useRef, useState } from 'react'
import { View } from 'react-native'
import { useColors } from '../theme'
import { fmtMoney, fmtSigned, ltr } from '../lib/format'
import { Card, Source, T } from './ui'
import { ImporterLink } from './RankingCard'

const YOUR_DATA = [
  ['occupation', 'עיסוק'], ['group', 'קבוצה'], ['base', 'שכר בסיס', 'money'],
  ['commission', 'עמלות', 'money'], ['bonus', 'בונוס', 'money'], ['pension_pct', 'פנסיה', 'pct'],
  ['keren_pct', 'קרן השתלמות', 'pct'], ['credit_points', 'נקודות זיכוי'], ['children', 'ילדים עד 23'],
  ['current', 'היום'], ['current_participation', 'השתתפות היום', 'money'],
]

const ROWS = [
  ['budget', 'תקציב הקבוצה'], ['car_cost', 'עלות לחברה'], ['participation', 'השתתפות'],
  ['value_of_use', 'שווי שימוש'], ['electric_refund_net', 'החזר חשמל (נטו)'],
  ['maintenance', 'אחזקת רכב'], ['family_share', 'חלק בפער המשפחתי'],
  ['tax', 'מס הכנסה'], ['social', 'ביטוח לאומי ובריאות'], ['net', 'נטו משוער', 'strong'],
]

const FLASH_MS = 1600
const isWaiting = (v) => typeof v === 'string' && v.includes('⏳')

function fmt(v, kind = 'money') {
  if (v === null || v === undefined) return '—'
  if (typeof v !== 'number') return String(v) // e.g. "⏳ ממתין לנציג"
  if (kind === 'pct') return ltr(`${v}%`)
  if (kind === 'money') return ltr(fmtMoney(v))
  return v.toLocaleString('he-IL')
}

function Value({ v, kind, weight = 700 }) {
  const c = useColors()
  if (isWaiting(v)) return <T size={14} weight={700} color={c.orange}>{v}</T>
  return <T size={14} weight={typeof v === 'number' ? weight : 400}>{fmt(v, kind)}</T>
}

// keys of the alternative whose value changed since the last render (e.g. a rep answer)
function useChanged(alt) {
  const prev = useRef(alt)
  const [changed, setChanged] = useState(() => new Set())
  useEffect(() => {
    const before = prev.current
    prev.current = alt
    if (before === alt) return
    const keys = new Set(Object.keys(alt.values).filter((k) => before.values[k]?.value !== alt.values[k]?.value))
    if (!keys.size) return
    setChanged(keys)
    const t = setTimeout(() => setChanged(new Set()), FLASH_MS)
    return () => clearTimeout(t)
  }, [alt])
  return changed
}

// importerLink: the employee's card has it (like the website, where the rep screen passes false)
export default function CompareCard({ result, importerLink = true }) {
  const c = useColors()
  const { card, status } = result
  const { your_data: yours, today, alternative: alt, diff, explanation } = card
  // the rep is asked to confirm the catalog's amount: calculated by it meanwhile, those fields marked
  const awaiting = card.awaiting_confirmation
  const changed = useChanged(alt)
  const facts = YOUR_DATA.filter(([key]) => yours[key])
  const sources = new Set(facts.map(([key]) => yours[key].source))
  const oneSource = sources.size === 1 ? [...sources][0] : null
  const net = diff.net
  const direction = typeof net !== 'number' || net === 0 ? 'flat' : net > 0 ? 'up' : 'down'
  const lines = [...new Set(explanation)]
  const tone = direction === 'up' ? c.up : direction === 'down' ? c.down : c.text

  return (
    <Card waiting={status === 'waiting_rep'} label="כרטיס השוואה">
      <View accessibilityLabel="הנתונים שלך" style={{ backgroundColor: c.surface, borderRadius: 10, padding: 12, gap: 6 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <T weight={800}>הנתונים שלך</T>
          <Source s={oneSource} />
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {facts.map(([key, label, kind]) => (
            <View key={key} style={{ minWidth: '45%', flexGrow: 1 }}>
              <T size={12} muted>{!oneSource && yours[key].source ? `${label} · ${yours[key].source}` : label}</T>
              <Value v={yours[key].value} kind={kind ?? 'plain'} />
            </View>
          ))}
        </View>
        <T size={13} muted>טעות באחד הנתונים? כתבו את הנכון בשיחה, והחישוב יתעדכן.</T>
      </View>

      <View style={{ flexDirection: 'row', gap: 8, borderBottomWidth: 1, borderColor: c.line, paddingBottom: 6 }}>
        <T size={13} weight={700} style={{ flex: 1 }}>{today.label}</T>
        <T size={13} weight={800} color={c.cyanText} style={{ flex: 1 }}>{alt.label}</T>
        <T size={13} weight={700} style={{ flex: 1 }}>הפרש</T>
      </View>
      {ROWS.map(([key, label, style]) => {
        const t = today.values[key]
        const a = alt.values[key]
        if (!t && !a) return null
        const strong = style === 'strong'
        return (
          <View key={key} style={{ gap: 2, paddingVertical: 4, borderRadius: 6, backgroundColor: changed.has(key) ? 'rgba(22,189,230,0.15)' : 'transparent' }}>
            <T size={13} weight={strong ? 800 : 600} muted={!strong}>{label}</T>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <View style={{ flex: 1 }}><Value v={t?.value} weight={strong ? 800 : 700} /><Source s={t?.source} /></View>
              <View style={{ flex: 1 }}>
                <Value v={a?.value} weight={strong ? 800 : 700} /><Source s={a?.source} />
                {awaiting?.fields.includes(key) && <T size={12} weight={700} color={c.orange}>{`⏳ ${awaiting.label}`}</T>}
              </View>
              <View style={{ flex: 1 }}><T size={14}>{ltr(fmtSigned(diff[key]))}</T></View>
            </View>
          </View>
        )
      })}

      {/* the importer's page of the new car only - today's car is already known */}
      {importerLink && <ImporterLink url={alt.importer_url} car={alt.label} />}

      <View accessibilityLabel={typeof net === 'number' ? 'הפרש בנטו, לחודש' : 'ממתין לנציג'}
        style={{ borderRadius: 12, padding: 14, gap: 6, backgroundColor: c.surface }}>
        {typeof net === 'number'
          ? <T size={28} weight={800} color={tone}>{`${direction === 'up' ? '▲ ' : direction === 'down' ? '▼ ' : ''}${ltr(net === 0 ? fmtMoney(0) : fmtSigned(net))}`}</T>
          : <T size={28}>⏳</T>}
        {lines.map((line) => <T key={line} size={14}>{line}</T>)}
        {awaiting && <T size={14} color={c.orange}>{`⏳ ${awaiting.note}`}</T>}
      </View>
    </Card>
  )
}

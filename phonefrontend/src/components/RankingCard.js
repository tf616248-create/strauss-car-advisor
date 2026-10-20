// Ranking card, from rank_options (the tool's artifact: it reaches the screen without passing
// through the model). Every number and spec comes from the server; the card only formats.
// SpecTags, SourceLine, ImporterLink and FullSpecs are shared with SpecsCard (car_specs).
import { useState } from 'react'
import { Linking, Pressable, View } from 'react-native'
import { useColors } from '../theme'
import { fmtDay, fmtMoney, fmtNum, fmtSigned, ltr } from '../lib/format'
import { Card, T } from './ui'

// a range in the Ministry of Transport is between trims; in EEA it is between registered versions
const rangeNote = (item) => (item.source?.startsWith('EEA') ? 'טווח גרסאות' : 'משתנה לפי גימור')

// one value, or a range when it differs between trims or versions
function fmtSpec(item) {
  const unit = item.unit ? ` ${item.unit}` : ''
  if ('value' in item) {
    if (typeof item.value === 'boolean') return item.value ? 'כן' : 'לא'
    return `${fmtNum(item.value)}${unit}`
  }
  if ('values' in item) return item.values.join(' / ')
  return `${fmtNum(item.min)}–${fmtNum(item.max)}${unit}`
}

// the specs worth a tag, with a short name for it
const TAGS = [
  ['mispar_moshavim', 'מושבים'], ['merkav', 'מרכב'], ['nikud_betihut', 'ניקוד בטיחות'],
  ['electric_consumption', 'צריכה'], ['fuel_consumption', 'צריכה (בקירוב)'], ['electric_range', 'טווח'],
  ['koah_sus', 'כוח סוס'],
]

export function SpecTags({ specs }) {
  const c = useColors()
  const tags = TAGS.filter(([key]) => specs[key])
  if (!tags.length) return null
  return (
    <View accessibilityLabel="מפרט עיקרי" style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
      {tags.map(([key, name]) => (
        <View key={key} style={{ backgroundColor: c.surface, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 2 }}>
          <T size={13}>{`${name}: ${fmtSpec(specs[key])}`}</T>
        </View>
      ))}
    </View>
  )
}

export function SourceLine({ sources }) {
  if (!sources?.length) return null
  return <T size={12} muted>{`מקור: ${sources.map((s) => `${s.name}, עודכן ${fmtDay(s.fetched_at)}`).join(' · ')}`}</T>
}

export function ImporterLink({ url }) {
  const c = useColors()
  if (!url) return null
  return (
    <Pressable accessibilityRole="link" onPress={() => Linking.openURL(url)} hitSlop={8}>
      <T weight={700} size={14} color={c.cyanText}>למפרט המלא אצל היבואן ←</T>
    </Pressable>
  )
}

export function FullSpecs({ specs, open: alwaysOpen = false }) {
  const c = useColors()
  const [open, setOpen] = useState(alwaysOpen)
  const items = Object.entries(specs)
  if (!items.length) return null
  return (
    <View style={{ gap: 6 }}>
      {!alwaysOpen && (
        <Pressable accessibilityRole="button" accessibilityState={{ expanded: open }} onPress={() => setOpen((o) => !o)} hitSlop={8}>
          <T weight={700} size={14} color={c.cyanText}>כל המפרט</T>
        </Pressable>
      )}
      {open && items.map(([key, item]) => (
        <View key={key} style={{ borderTopWidth: 1, borderColor: c.line, paddingTop: 4 }}>
          <T size={13} muted>{item.label}</T>
          <T size={14} weight={600}>{fmtSpec(item)}</T>
          <T size={12} muted>
            {[item.varies_by_trim && rangeNote(item), item.provisional && (item.note || 'נתון ראשוני'),
              `${item.source}${item.year ? `, ${item.year}` : ''}`].filter(Boolean).join(' · ')}
          </T>
        </View>
      ))}
    </View>
  )
}

function sortValue(v) {
  if (v.category) return v.label
  return ltr(`${fmtNum(v.value)}${v.unit ? ` ${v.unit}` : ''}`)
}

function Fact({ label, value }) {
  return (
    <View style={{ flex: 1 }}>
      <T size={12} muted>{label}</T>
      <T size={15} weight={700}>{value}</T>
    </View>
  )
}

function Option({ o, sortLabel }) {
  const c = useColors()
  return (
    <View style={{ gap: 8, borderTopWidth: 1, borderColor: c.line, paddingTop: 12 }}>
      <T weight={800} size={17}>{`${o.rank}. ${o.car}`}</T>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Fact label="נטו משוער" value={ltr(fmtMoney(o.net))} />
        <Fact label="שינוי מהיום" value={ltr(fmtSigned(o.diff?.net))} />
        <Fact label={sortLabel} value={sortValue(o.sort_value)} />
      </View>
      {o.tie_broken_by_net && <T size={13} muted>{`שווים ב${sortLabel}, סודרו לפי נטו`}</T>}
      <SpecTags specs={o.specs} />
      <SourceLine sources={o.sources} />
      <ImporterLink url={o.importer_url} />
      <FullSpecs specs={o.specs} />
    </View>
  )
}

export default function RankingCard({ result }) {
  const c = useColors()
  const { card } = result
  const missing = card.excluded_missing_data || []
  const waiting = card.needs_rep || []
  return (
    <Card label="רכבים מסודרים">
      <T weight={800} size={18}>{`סידרתי לפי: ${card.sort_label}`}</T>
      {card.options.map((o) => <Option key={o.car} o={o} sortLabel={card.sort_label} />)}
      {waiting.map((w) => (
        <View key={w.car} style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <T>{w.car}</T>
          <T weight={700} color={c.orange}>⏳ ממתין לנציג</T>
        </View>
      ))}
      {missing.length > 0 && (
        <T size={13} muted>{`לא נכללו, כי חסר נתון רשמי: ${missing.map((m) => `${m.car} (${m.label})`).join(', ')}`}</T>
      )}
    </Card>
  )
}

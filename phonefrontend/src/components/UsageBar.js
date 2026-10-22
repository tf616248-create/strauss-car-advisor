// This week's usage in the side menu (like the website's sidebar): how much is used, as a progress bar,
// and "נשארו לך כ-X שיחות השבוע". A screen reader hears the bar with its sentence (accessibilityValue),
// so the sentence below it is hidden from it, not read twice.
import { View } from 'react-native'
import { useColors } from '../theme'
import { T } from './ui'
import cfg from '../config/usage.json'

const U = cfg.texts

// X = what is left / the average conversation, rounded down (by the server)
export function usageSentence(usage) {
  if (!usage) return U.loading
  if (usage.blocked) return U.none
  const n = usage.conversations_left
  if (n < 1) return U.lessThanOne
  return n === 1 ? U.leftOne : U.left.replace('{n}', n)
}

export default function UsageBar({ usage }) {
  const c = useColors()
  const used = usage ? Math.min(100, Math.round((usage.used / usage.limit) * 100)) : 0
  const sentence = usageSentence(usage)
  return (
    <View style={{ paddingHorizontal: 16, paddingVertical: 8, gap: 4 }}>
      <T weight={800} size={14} muted>{U.label}</T>
      <View accessible accessibilityRole="progressbar" accessibilityLabel={U.barLabel}
        accessibilityValue={{ min: 0, max: 100, now: used, text: sentence }}
        style={{ height: 8, borderRadius: 4, backgroundColor: c.surface, overflow: 'hidden', borderWidth: 1, borderColor: c.line }}>
        <View style={{ width: `${used}%`, height: '100%', backgroundColor: usage?.blocked ? c.orange : c.cyan }} />
      </View>
      <T size={14} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">{sentence}</T>
      <T size={12} muted>{U.resets}</T>
    </View>
  )
}

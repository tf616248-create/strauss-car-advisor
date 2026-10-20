// "Talk to a rep": a service email, at the edge of the message row. The bot's rep queue only
// answers predefined fields; a person to write to is this email. The panel floats above the
// button, so opening it never moves the button. EXPO_PUBLIC_SUPPORT_EMAIL overrides the address.
import { useState } from 'react'
import { Linking, Pressable, View } from 'react-native'
import Svg, { Path } from 'react-native-svg'
import { useColors } from '../theme'
import { T } from './ui'

export const SUPPORT_EMAIL = 'support@strauss-in.com'

export default function ContactRep({ email = process.env.EXPO_PUBLIC_SUPPORT_EMAIL }) {
  const c = useColors()
  const address = email || SUPPORT_EMAIL
  const [open, setOpen] = useState(false)
  return (
    <View>
      {open && (
        <View accessibilityLabel="פנייה לשירות"
          style={{ position: 'absolute', bottom: 52, end: 0, width: 260, backgroundColor: c.surface2, borderWidth: 1, borderColor: c.line, borderRadius: 12, padding: 12, gap: 6, elevation: 4, shadowColor: '#000', shadowOpacity: 0.15, shadowRadius: 8, zIndex: 10 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <T weight={800}>פנייה לנציג התחבורה</T>
            <Pressable accessibilityRole="button" accessibilityLabel="סגירה" onPress={() => setOpen(false)} hitSlop={10}>
              <T size={18} muted>✕</T>
            </Pressable>
          </View>
          <T size={14}>אפשר לכתוב לנו:</T>
          <Pressable accessibilityRole="link" onPress={() => Linking.openURL(`mailto:${address}`)}>
            <T weight={700} size={14} color={c.cyanText}>{`⁦${address}⁩`}</T>
          </Pressable>
        </View>
      )}
      <Pressable accessibilityRole="button" accessibilityLabel="שיחה עם נציג" accessibilityState={{ expanded: open }}
        onPress={() => setOpen((o) => !o)}
        style={{ width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: c.line, alignItems: 'center', justifyContent: 'center' }}>
        <Svg width={22} height={22} viewBox="0 0 24 24">
          <Path d="M4 6h16v10H8l-4 4z" fill="none" stroke={c.muted} strokeWidth={2} strokeLinejoin="round" />
        </Svg>
      </Pressable>
    </View>
  )
}

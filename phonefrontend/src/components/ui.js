// Small building blocks: text in Rubik, right-aligned (the app's root is direction: rtl), and buttons.
import { Pressable, Text, View } from 'react-native'
import { FONTS, useColors } from '../theme'

export function T({ weight = 400, muted, size = 16, color, style, ...props }) {
  const c = useColors()
  return (
    <Text {...props} style={[{
      fontFamily: FONTS[weight], fontSize: size, lineHeight: Math.round(size * 1.5),
      color: color ?? (muted ? c.muted : c.text), textAlign: 'right', writingDirection: 'rtl',
    }, style]} />
  )
}

// primary: the cyan pill (dark text on it); quiet: a thin border and secondary text
export function Btn({ title, onPress, disabled, quiet, style, label, children }) {
  const c = useColors()
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label ?? title} accessibilityState={{ disabled: !!disabled }}
      onPress={disabled ? undefined : onPress}
      style={({ pressed }) => [{
        minHeight: quiet ? 36 : 44, paddingHorizontal: quiet ? 14 : 22, borderRadius: 999,
        alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 6,
        backgroundColor: quiet ? 'transparent' : c.cyan, borderWidth: quiet ? 1 : 0, borderColor: c.line,
        opacity: disabled ? 0.5 : pressed ? 0.8 : 1,
      }, style]}>
      {children}
      {title ? <T weight={quiet ? 600 : 800} size={quiet ? 14 : 16} color={quiet ? c.muted : c.onBrand}>{title}</T> : null}
    </Pressable>
  )
}

export function Card({ waiting, children, label }) {
  const c = useColors()
  return (
    <View accessibilityLabel={label}
      style={{ backgroundColor: c.surface2, borderWidth: 1, borderColor: waiting ? c.orange : c.line, borderRadius: 14, padding: 16, gap: 12 }}>
      {children}
    </View>
  )
}

// a short source tag ("עובד", "קטלוג", "רשות המסים", "נציג")
export function Source({ s }) {
  return s ? <T size={12} muted>{s}</T> : null
}

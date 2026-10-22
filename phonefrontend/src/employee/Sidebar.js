// The side menu on a phone: ☰ in the header opens it over the screen, from the right (like the
// website's sidebar on a narrow screen). New conversation, profile, customize, usage, my conversations,
// and at the bottom the employee's name and logout. ✕, a tap on the dark backdrop, Android's Back or a
// choice close it. A screen reader stays inside it while it is open.
import { Modal, Pressable, ScrollView, View } from 'react-native'
import { useColors } from '../theme'
import { fmtWhen } from '../lib/format'
import { T } from '../components/ui'
import cfg from '../config/sidebar.json'

const S = cfg.texts

function Item({ icon, label, onPress, disabled }) {
  const c = useColors()
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled: !!disabled }}
      onPress={disabled ? undefined : onPress}
      style={({ pressed }) => ({ minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16,
        borderRadius: 10, backgroundColor: pressed ? c.surface : 'transparent', opacity: disabled ? 0.5 : 1 })}>
      <T size={20} accessibilityElementsHidden importantForAccessibility="no">{icon}</T>
      <T weight={600}>{label}</T>
    </Pressable>
  )
}

export default function Sidebar({ open, onClose, busy, threadId, history, name, usage,
  onNewConversation, onProfile, onCustomize, onOpenThread, onLogout }) {
  const c = useColors()
  if (!open) return null
  const then = (fn) => () => { onClose(); fn?.() }
  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose} statusBarTranslucent>
      <View style={{ flex: 1, flexDirection: 'row', direction: 'rtl' }}>
        <View accessibilityViewIsModal accessibilityLabel={S.label}
          style={{ width: '82%', maxWidth: 340, backgroundColor: c.bg, paddingTop: 36, paddingBottom: 16, gap: 4, borderLeftWidth: 1, borderColor: c.line }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 8 }}>
            <T weight={800} size={20} style={{ flex: 1, paddingHorizontal: 8 }} accessibilityRole="header">כובי</T>
            <Pressable accessibilityRole="button" accessibilityLabel={S.close} onPress={onClose}
              style={{ width: 44, height: 44, alignItems: 'center', justifyContent: 'center' }}>
              <T size={22} weight={800}>✕</T>
            </Pressable>
          </View>
          <Item icon="＋" label={S.newConversation} onPress={then(onNewConversation)} disabled={busy} />
          <Item icon="👤" label={S.profile} onPress={then(onProfile)} />
          <Item icon="⚙" label={S.customize} onPress={then(onCustomize)} />
          {usage}
          <T weight={800} size={14} muted style={{ paddingHorizontal: 16, marginTop: 12 }} accessibilityRole="header">{S.history}</T>
          <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingHorizontal: 8 }}>
            {history.length === 0
              ? <T muted style={{ padding: 8 }}>{S.historyEmpty}</T>
              : history.map((t) => {
                const title = t.title || S.untitled
                const current = t.thread_id === threadId
                return (
                  <Pressable key={t.thread_id} accessibilityRole="button" accessibilityLabel={`${title}, ${fmtWhen(t.updated_at)}`}
                    accessibilityState={{ selected: current, disabled: !!busy }} onPress={busy ? undefined : then(() => onOpenThread(t.thread_id))}
                    style={{ minHeight: 48, paddingHorizontal: 8, paddingVertical: 6, borderRadius: 10, backgroundColor: current ? c.surface : 'transparent' }}>
                    <T weight={700} numberOfLines={1}>{title}</T>
                    <T size={12} muted>{fmtWhen(t.updated_at)}</T>
                  </Pressable>
                )
              })}
          </ScrollView>
          <View style={{ borderTopWidth: 1, borderColor: c.line, paddingTop: 8, paddingHorizontal: 8, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <T weight={700} style={{ flex: 1, paddingHorizontal: 8 }} numberOfLines={1}>{name ?? ''}</T>
            <Pressable accessibilityRole="button" accessibilityLabel={S.logout} onPress={then(onLogout)}
              style={{ minHeight: 44, paddingHorizontal: 14, borderRadius: 999, borderWidth: 1, borderColor: c.line, justifyContent: 'center' }}>
              <T weight={600} muted>{S.logout}</T>
            </Pressable>
          </View>
        </View>
        {/* the backdrop: a tap closes it; for a screen reader ✕ is the way out */}
        <Pressable accessible={false} importantForAccessibility="no" onPress={onClose} style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)' }} />
      </View>
    </Modal>
  )
}

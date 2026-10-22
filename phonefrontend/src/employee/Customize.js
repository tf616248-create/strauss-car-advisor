// "התאמה אישית" (like frontend/src/employee/CustomizeDialog.jsx): the design and Kobi's tone. Each choice
// is shown at once and saved on the server; "נשמר" says so, and a save that fails goes back and says so.
import { useState } from 'react'
import { Modal, Pressable, ScrollView, View } from 'react-native'
import { useColors } from '../theme'
import { T } from '../components/ui'
import { Choice } from './ProfileScreen'
import cfg from '../config/settings.json'

const TX = cfg.texts

export default function Customize({ api, settings, onChange, onClose }) {
  const c = useColors()
  const [notice, setNotice] = useState(null) // { kind: 'saved' | 'alert', text }

  async function choose(field, value) {
    if (settings[field] === value) return
    const before = settings
    onChange({ ...settings, [field]: value })
    setNotice(null)
    try {
      const saved = await api.saveSettings({ [field]: value })
      onChange({ ...before, [field]: value, ...saved })
      setNotice({ kind: 'saved', text: TX.saved })
    } catch {
      onChange(before)
      setNotice({ kind: 'alert', text: TX.saveError })
    }
  }

  const group = (field, options, hint) => (
    <View style={{ gap: 6 }}>
      <T weight={800} accessibilityRole="header">{TX[field]}</T>
      {hint && <T size={13} muted>{hint}</T>}
      <View accessibilityRole="radiogroup" accessibilityLabel={TX[field]} style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {Object.entries(options).map(([value, label]) => (
          <Choice key={value} label={label} checked={settings[field] === value} onPress={() => choose(field, value)} />
        ))}
      </View>
    </View>
  )

  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose} statusBarTranslucent>
      <View style={{ flex: 1, justifyContent: 'center', padding: 16, backgroundColor: 'rgba(0,0,0,0.45)', direction: 'rtl' }}>
        <View accessibilityViewIsModal style={{ backgroundColor: c.bg, borderRadius: 16, maxHeight: '90%' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', padding: 12, borderBottomWidth: 1, borderColor: c.line }}>
            <T weight={800} size={20} accessibilityRole="header" style={{ flex: 1, paddingHorizontal: 4 }}>{TX.title}</T>
            <Pressable accessibilityRole="button" accessibilityLabel={TX.close} onPress={onClose}
              style={{ width: 44, height: 44, alignItems: 'center', justifyContent: 'center' }}>
              <T size={22} weight={800}>✕</T>
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={{ padding: 16, gap: 18 }}>
            {group('theme', TX.themes)}
            {group('tone', TX.tones, TX.toneHint)}
            {notice?.kind === 'saved' && <T accessibilityLiveRegion="polite" weight={700} color={c.up}>{notice.text}</T>}
            {notice?.kind === 'alert' && <T accessibilityRole="alert" accessibilityLiveRegion="assertive" weight={700} color={c.error}>{notice.text}</T>}
          </ScrollView>
        </View>
      </View>
    </Modal>
  )
}

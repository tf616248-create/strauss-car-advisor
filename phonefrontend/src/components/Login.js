import { useState } from 'react'
import { KeyboardAvoidingView, Platform, ScrollView, TextInput, View } from 'react-native'
import { SvgXml } from 'react-native-svg'
import * as realApi from '../lib/api'
import { setToken } from '../lib/session'
import { TEST_EMPLOYEE_CODES } from '../lib/testCodes'
import logo from '../assets/logo'
import { FONTS, useColors } from '../theme'
import { CarBody } from './Road'
import { Btn, T } from './ui'

// errors always say what to do next
function errorText(err) {
  if (err?.status === 401) return 'הקוד לא נכון. אפשר לנסות שוב.'
  if (err?.status === 429) return 'יותר מדי ניסיונות. אפשר לנסות שוב בעוד כמה דקות.'
  if (err?.status === 503) return 'הכניסה סגורה כרגע: לא הוגדרו קודים בשרת.'
  return 'כובי לא מצליח להתחבר כרגע. אפשר לנסות שוב בעוד דקה.'
}

// Demo login: an employee code -> a token for while the app is open (app/auth.py). A pilot replaces it with SSO.
// embedded: the card of the opening scene (Intro.js), not a screen of its own
export default function Login({ api = realApi, onLogin, embedded = false }) {
  const c = useColors()
  const [code, setCode] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit() {
    const value = code.trim()
    if (!value || busy) return
    setBusy(true)
    setError(null)
    try {
      const { token } = await api.login(value)
      setToken(token)
      onLogin()
    } catch (err) {
      setError(errorText(err))
      setBusy(false)
    }
  }

  const card = (
        <View style={{ backgroundColor: c.surface, borderRadius: 18, padding: 24, gap: 12, alignItems: 'stretch' }}>
          <View accessibilityLabel="שטראוס" accessibilityRole="image" style={{ alignSelf: 'center' }}>
            <SvgXml xml={logo} width={88} height={60} />
          </View>
          <View style={{ alignSelf: 'center' }}><CarBody /></View>
          <T weight={800} size={30} style={{ textAlign: 'center' }} accessibilityRole="header">כובי</T>
          <T muted size={15} style={{ textAlign: 'center', marginTop: -8 }}>יועץ הרכב של שטראוס</T>
          <T muted>כדי לראות את השיחות שלכם, הקלידו את קוד העובד שקיבלתם.</T>
          <T weight={700} size={14} nativeID="code-label">קוד עובד</T>
          <TextInput accessibilityLabel="קוד עובד" accessibilityLabelledBy="code-label" value={code} onChangeText={setCode}
            secureTextEntry keyboardType="number-pad" autoComplete="off" onSubmitEditing={submit} returnKeyType="go"
            style={{ minHeight: 48, borderWidth: 1, borderColor: error ? c.error : c.line, borderRadius: 12, paddingHorizontal: 14, fontFamily: FONTS[600], fontSize: 18, color: c.text, backgroundColor: c.surface2, textAlign: 'right' }} />
          {error && <T weight={600} color={c.error} accessibilityRole="alert" accessibilityLiveRegion="assertive">{error}</T>}
          <Btn title="כניסה" onPress={submit} disabled={busy} />
          <View accessibilityLabel="קודים לבדיקות" style={{ borderWidth: 1, borderStyle: 'dashed', borderColor: c.line, borderRadius: 10, padding: 10 }}>
            <T size={13}><T size={13} weight={800}>לבדיקות בלבד: </T>{`קודי עובד: ${TEST_EMPLOYEE_CODES}.`}</T>
            <T size={12} muted>הקודים יימחקו לפני השימוש האמיתי.</T>
          </View>
        </View>
  )
  if (embedded) return card
  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1, backgroundColor: c.bg }}>
      <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', padding: 24 }} keyboardShouldPersistTaps="handled">
        {card}
      </ScrollView>
    </KeyboardAvoidingView>
  )
}

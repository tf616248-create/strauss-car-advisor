// The employee's profile, full screen over the conversation (like frontend/src/employee/ProfileDialog.jsx).
// Every field can be edited; saving sends only what changed. Next to each value: where it came from
// (typed here, the chat, a payslip). The group is read only: the server computes it from the occupation.
// "פנייה" (male / female / plural) is saved with it. ✕ and Android's Back close it.
import { useEffect, useState } from 'react'
import { KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, TextInput, View } from 'react-native'
import { FONTS, useColors } from '../theme'
import { Btn, T } from '../components/ui'
import cfg from '../config/profile.json'

const TX = cfg.texts
const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, k) => values[k])
const shown = (v) => (v === undefined || v === null ? '' : String(v))

// a field's text back to what the server takes: empty -> null, a number without commas
function parsed(field, text) {
  const t = text.trim()
  if (t === '') return null
  if (field.type !== 'number') return t
  const n = Number(t.replace(/,/g, ''))
  return Number.isFinite(n) ? n : t // not a number: the server says what is wrong, next to the field
}

// the server's reason, in words, next to its field
function why(problem) {
  if (problem.range) return fill(TX.range, { lo: problem.range[0].toLocaleString('he-IL'), hi: problem.range[1].toLocaleString('he-IL') })
  if (problem.suggestions) return problem.suggestions.length ? fill(TX.notFound, { suggestions: problem.suggestions.join(', ') }) : TX.notFoundNoSuggestions
  if (problem.options) return TX.options
  return TX.invalid
}

// one choice of a radio group (accessibilityRole radio, 44 high)
export function Choice({ label, checked, onPress }) {
  const c = useColors()
  return (
    <Pressable accessibilityRole="radio" accessibilityLabel={label} accessibilityState={{ checked }} onPress={onPress}
      style={{ minHeight: 44, paddingHorizontal: 14, borderRadius: 999, borderWidth: checked ? 2 : 1, borderColor: checked ? c.cyan : c.line,
        backgroundColor: checked ? c.surface : 'transparent', alignItems: 'center', justifyContent: 'center' }}>
      <T weight={checked ? 700 : 400}>{label}</T>
    </Pressable>
  )
}

export default function ProfileScreen({ api, onClose }) {
  const c = useColors()
  const [view, setView] = useState(null)
  const [form, setForm] = useState({})
  const [state, setState] = useState('loading') // loading | ready | failed
  const [errors, setErrors] = useState({})
  const [notice, setNotice] = useState(null) // { kind: 'saved' | 'alert', text }
  const [saving, setSaving] = useState(false)
  const [address, setAddress] = useState('plural')

  function take(v) {
    setView(v)
    setAddress(v.address ?? 'plural')
    setForm(Object.fromEntries(cfg.fields.map((f) => [f.name, shown(v.fields[f.name])])))
  }

  useEffect(() => {
    let live = true
    Promise.resolve(api.profile())
      .then((v) => { if (live) { take(v); setState('ready') } })
      .catch(() => { if (live) setState('failed') })
    return () => { live = false }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function save() {
    if (saving || !view) return
    const changed = {}
    for (const f of cfg.fields) {
      if (form[f.name] !== shown(view.fields[f.name])) changed[f.name] = parsed(f, form[f.name])
    }
    const newAddress = address !== (view.address ?? 'plural') ? address : null
    setNotice(null)
    setErrors({})
    if (!Object.keys(changed).length && !newAddress) { setNotice({ kind: 'saved', text: TX.saved }); return }
    setSaving(true)
    try {
      const res = await (newAddress ? api.saveProfile(changed, { address: newAddress }) : api.saveProfile(changed))
      if (res.invalid) {
        setErrors(res.invalid)
        setNotice({ kind: 'alert', text: TX.fixErrors })
      } else {
        take(res.profile)
        setNotice({ kind: 'saved', text: TX.saved })
      }
    } catch {
      setNotice({ kind: 'alert', text: TX.saveError })
    } finally {
      setSaving(false)
    }
  }

  const set = (name) => (text) => { setForm((f) => ({ ...f, [name]: text })); setNotice(null) }

  function control(f) {
    const source = view?.sources?.[f.name]
    const problem = errors[f.name]
    const hint = [source && TX.sources[source], problem && why(problem)].filter(Boolean).join('. ')
    return (
      <View key={f.name} style={{ gap: 4 }}>
        <T weight={700} size={14}>{f.label}</T>
        {f.type === 'kind' ? (
          <View accessibilityRole="radiogroup" accessibilityLabel={f.label} style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {Object.entries(TX.kinds).map(([value, text]) => (
              <Choice key={value} label={text} checked={form[f.name] === value} onPress={set(f.name).bind(null, value)} />
            ))}
          </View>
        ) : (
          <TextInput accessibilityLabel={f.label} accessibilityHint={hint || undefined} value={form[f.name] ?? ''} onChangeText={set(f.name)}
            keyboardType={f.type === 'number' ? 'decimal-pad' : 'default'} autoComplete="off"
            style={{ minHeight: 44, borderWidth: problem ? 2 : 1, borderColor: problem ? c.error : c.line, borderRadius: 10, paddingHorizontal: 12,
              fontFamily: FONTS[400], fontSize: 16, color: c.text, backgroundColor: c.surface2, textAlign: f.type === 'number' ? 'left' : 'right' }} />
        )}
        {source && <T size={12} muted>{TX.sources[source]}</T>}
        {problem && <T size={13} weight={600} color={c.error}>{why(problem)}</T>}
      </View>
    )
  }

  const group = view?.group ? fill(TX.group, { group: view.group }) : TX.groupUnknown

  return (
    <Modal visible animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1, backgroundColor: c.bg, direction: 'rtl' }}>
        <View accessibilityViewIsModal style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', padding: 16, borderBottomWidth: 1, borderColor: c.line }}>
            <T weight={800} size={22} accessibilityRole="header" style={{ flex: 1 }}>{TX.title}</T>
            <Pressable accessibilityRole="button" accessibilityLabel={TX.close} onPress={onClose}
              style={{ width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' }}>
              <T size={22} weight={800}>✕</T>
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={{ padding: 16, gap: 14 }} keyboardShouldPersistTaps="handled">
            <T muted>{TX.intro}</T>
            {state === 'loading' && <T accessibilityLiveRegion="polite">{TX.loading}</T>}
            {state === 'failed' && <T color={c.error} accessibilityRole="alert">{TX.loadError}</T>}
            {state === 'ready' && (
              <>
                {control(cfg.fields[0])}
                <View style={{ gap: 2 }}>
                  <T weight={700} size={14}>{TX.groupLabel}</T>
                  <T>{group}</T>
                </View>
                <View style={{ gap: 4 }}>
                  <T weight={700} size={14}>{TX.address}</T>
                  <T size={12} muted>{TX.addressHint}</T>
                  <View accessibilityRole="radiogroup" accessibilityLabel={TX.address} style={{ flexDirection: 'row', gap: 8 }}>
                    {Object.entries(TX.addresses).map(([value, label]) => (
                      <Choice key={value} label={label} checked={address === value} onPress={() => { setAddress(value); setNotice(null) }} />
                    ))}
                  </View>
                  {errors.address && <T size={13} weight={600} color={c.error}>{why(errors.address)}</T>}
                </View>
                {cfg.fields.slice(1).map(control)}
                <Btn title={saving ? TX.saving : TX.save} label={TX.save} onPress={save} disabled={saving} />
                {notice?.kind === 'saved' && <T accessibilityLiveRegion="polite" weight={700} color={c.up}>{notice.text}</T>}
                {notice?.kind === 'alert' && <T accessibilityRole="alert" accessibilityLiveRegion="assertive" weight={700} color={c.error}>{notice.text}</T>}
              </>
            )}
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  )
}

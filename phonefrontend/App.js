// Kobi on a phone: the employee side only. The rep screen stays on the website (/rep).
// The whole app is right-to-left by its root style (direction: rtl), whatever the phone's language.
import { StatusBar } from 'expo-status-bar'
import { View } from 'react-native'
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context'
import { useFonts, Assistant_400Regular, Assistant_600SemiBold, Assistant_700Bold, Assistant_800ExtraBold } from '@expo-google-fonts/assistant'
import EmployeeApp from './src/employee/EmployeeApp'
import { useColors } from './src/theme'

export default function App() {
  const c = useColors()
  const [fontsLoaded] = useFonts({ Assistant_400Regular, Assistant_600SemiBold, Assistant_700Bold, Assistant_800ExtraBold })
  return (
    <SafeAreaProvider>
      <SafeAreaView style={{ flex: 1, backgroundColor: c.bg }}>
        <StatusBar style="auto" />
        <View style={{ flex: 1, direction: 'rtl' }}>
          {fontsLoaded ? <EmployeeApp /> : null}
        </View>
      </SafeAreaView>
    </SafeAreaProvider>
  )
}

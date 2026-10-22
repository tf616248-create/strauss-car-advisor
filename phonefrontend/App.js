// Kobi on a phone: the employee side only. The rep screen stays on the website (/rep).
// The whole app is right-to-left by its root style (direction: rtl), whatever the phone's language.
import { StatusBar } from 'expo-status-bar'
import { View } from 'react-native'
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context'
import { useFonts } from 'expo-font'
// each weight from its own path: only these three files go into the app, not all 18 of the family
import { Rubik_400Regular } from '@expo-google-fonts/rubik/400Regular'
import { Rubik_500Medium } from '@expo-google-fonts/rubik/500Medium'
import { Rubik_700Bold } from '@expo-google-fonts/rubik/700Bold'
import EmployeeApp from './src/employee/EmployeeApp'
import { useColors } from './src/theme'

export default function App() {
  const c = useColors()
  // one font, like the website: Rubik 400, 500 and 700 (theme.js FONTS)
  const [fontsLoaded] = useFonts({ Rubik_400Regular, Rubik_500Medium, Rubik_700Bold })
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

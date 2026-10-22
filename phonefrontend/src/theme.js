// The website's colors (frontend/src/styles.css :root and :root[data-theme="dark"], checked in
// tests/theme.test.js). Strauss brand colors are the same in both; #16BDE6 (cyan) is never a text color.
// The design is the employee's choice ("התאמה אישית", kept on the server): light (the default, even
// when the phone is dark), dark, or system (follows the phone). Outside the chat (login): light.
import { createContext, useContext } from 'react'
import { useColorScheme } from 'react-native'

const brand = { green: '#8CBB21', cyan: '#16BDE6', orange: '#FF5700', onBrand: '#1A1A1A' }
const light = { ...brand, cyanText: '#0A7896', bg: '#FFFFFF', surface: '#F5F6F7', surface2: '#FFFFFF', text: '#1A1A1A', muted: '#575E68', line: '#E3E6EA', error: '#B42318', readingText: '#2B2F36', up: '#3B6B0A', down: '#B42318' }
const dark = { ...brand, cyanText: '#4CCBEB', bg: '#121417', surface: '#1B1E23', surface2: '#22262C', text: '#F2F3F5', muted: '#AAB1BB', line: '#30353D', error: '#FF8A80', readingText: '#DADDE2', up: '#A8D65A', down: '#FF8A80' }
export const PALETTES = { light, dark }

// 'light' | 'dark' | 'system'
export const ThemeMode = createContext('light')

export function useColors() {
  const mode = useContext(ThemeMode)
  const phone = useColorScheme()
  return mode === 'dark' || (mode === 'system' && phone === 'dark') ? dark : light
}

// the employee's form of address ('male' | 'female' | 'plural'), for the texts that speak to them
export const Address = createContext('plural')
export const useAddress = () => useContext(Address)

// one font on every screen: Rubik (loaded in App.js), only the weights the website loads - 400, 500
// and 700. A component asking for 600 gets 500, for 800 gets 700 (the website did the same)
export const FONTS = { 400: 'Rubik_400Regular', 500: 'Rubik_500Medium', 600: 'Rubik_500Medium', 700: 'Rubik_700Bold', 800: 'Rubik_700Bold' }

// long reading text (Kobi's answers), like the website's --reading-* tokens: 16, line height 1.7,
// 0.6em between paragraphs and list items
export const READING = { size: 16, lineHeight: 27, gap: 10 }

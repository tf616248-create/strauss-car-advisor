// The website's colors (frontend/src/styles.css :root), light and dark.
// Strauss brand colors are the same in both; #16BDE6 (cyan) is never a text color.
import { useColorScheme } from 'react-native'

const brand = { green: '#8CBB21', cyan: '#16BDE6', orange: '#FF5700', onBrand: '#1A1A1A' }
const light = { ...brand, cyanText: '#0B7F9E', bg: '#FFFFFF', surface: '#F5F6F7', surface2: '#FFFFFF', text: '#1A1A1A', muted: '#575E68', line: '#E3E6EA', error: '#B42318', up: '#3B6B0A', down: '#B42318' }
const dark = { ...brand, cyanText: '#4CCBEB', bg: '#121417', surface: '#1B1E23', surface2: '#22262C', text: '#F2F3F5', muted: '#AAB1BB', line: '#30353D', error: '#FF8A80', up: '#A8D65A', down: '#FF8A80' }

export const useColors = () => (useColorScheme() === 'dark' ? dark : light)

// one font on every screen: Assistant (loaded in App.js)
export const FONTS = { 400: 'Assistant_400Regular', 600: 'Assistant_600SemiBold', 700: 'Assistant_700Bold', 800: 'Assistant_800ExtraBold' }

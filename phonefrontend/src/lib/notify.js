// A rep answer while the app is open: a short vibration (the website beeps and marks the tab).
// A phone has no tab title, so setUnread does nothing; it keeps the website's interface.
import { Vibration } from 'react-native'

export function beep() {
  try { Vibration.vibrate(200) } catch { /* no vibration - fine */ }
}

export function setUnread() {}

export const notifier = { beep, setUnread }

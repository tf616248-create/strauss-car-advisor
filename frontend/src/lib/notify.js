// tab titles: the employee talks to Kobi; the rep screen is the queue (no Kobi)
export const EMPLOYEE_TITLE = 'כובי · יועץ הרכב של שטראוס'
export const REP_TITLE = 'תור הנציג · יועץ הרכב של שטראוס'

export function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.frequency.value = 880
    gain.gain.value = 0.1
    osc.connect(gain).connect(ctx.destination)
    osc.start()
    osc.stop(ctx.currentTime + 0.15)
  } catch { /* no audio - fine */ }
}

export function setUnread(n) {
  document.title = n > 0 ? `(${n}) ${EMPLOYEE_TITLE}` : EMPLOYEE_TITLE
}

export const notifier = { beep, setUnread }

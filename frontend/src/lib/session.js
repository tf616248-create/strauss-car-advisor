// The employee's login and open conversation, for this tab only (sessionStorage): closing the
// tab logs out, which suits a shared computer. The history itself is on the server (GET /threads).
// Storage can be blocked (private mode, previews): then the employee just logs in again.
const TOKEN = 'employeeToken'
const THREAD = 'threadId'

function read(key) {
  try { return sessionStorage.getItem(key) } catch { return null }
}

function write(key, value) {
  try {
    if (value == null) sessionStorage.removeItem(key)
    else sessionStorage.setItem(key, value)
  } catch { /* blocked storage: nothing to keep */ }
}

export const getToken = () => read(TOKEN)
export const setToken = (token) => write(TOKEN, token)
export const getCurrentThread = () => read(THREAD)
export const setCurrentThread = (threadId) => write(THREAD, threadId)

export function clearSession() {
  write(TOKEN, null)
  write(THREAD, null)
}

// a 401 from the server (the login expired, or the server's secret changed): back to the login screen
let onUnauthorized = () => {}
export function setUnauthorizedHandler(fn) { onUnauthorized = fn }
export function unauthorized() {
  clearSession()
  onUnauthorized()
}

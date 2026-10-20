// The employee's login and open conversation, in memory only: closing the app logs out,
// like closing the tab on the website. The history itself is on the server (GET /threads).
let token = null
let thread = null

export const getToken = () => token
export const setToken = (value) => { token = value ?? null }
export const getCurrentThread = () => thread
export const setCurrentThread = (value) => { thread = value ?? null }

export function clearSession() {
  token = null
  thread = null
}

// a 401 from the server (the login expired, or the server's secret changed): back to the login screen
let onUnauthorized = () => {}
export function setUnauthorizedHandler(fn) { onUnauthorized = fn }
export function unauthorized() {
  clearSession()
  onUnauthorized()
}

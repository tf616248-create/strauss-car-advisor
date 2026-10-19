import { useEffect, useState } from 'react'
import * as realApi from '../lib/api'
import { clearSession, getToken, setUnauthorizedHandler } from '../lib/session'
import Login from '../components/Login'
import EmployeeScreen from './EmployeeScreen'

// The employee side: the login screen until there is a token for this tab, then the chat.
// A 401 from the server (expired login) and "logout" both come back here.
export default function EmployeeApp({ api = realApi, ...screenProps }) {
  const [loggedIn, setLoggedIn] = useState(() => Boolean(getToken()))

  useEffect(() => {
    setUnauthorizedHandler(() => setLoggedIn(false))
    return () => setUnauthorizedHandler(() => {})
  }, [])

  function logout() {
    clearSession()
    setLoggedIn(false)
  }

  if (!loggedIn) return <Login api={api} onLogin={() => setLoggedIn(true)} />
  return <EmployeeScreen api={api} onLogout={logout} {...screenProps} />
}

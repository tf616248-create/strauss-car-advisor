import { useEffect, useState } from 'react'
import * as realApi from '../lib/api'
import { clearSession, getToken, setUnauthorizedHandler } from '../lib/session'
import Intro from '../components/Intro'
import EmployeeScreen from './EmployeeScreen'

// The employee side: the opening scene (with the login card) until there is a token, then the chat.
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

  if (!loggedIn) return <Intro api={api} onEnter={() => setLoggedIn(true)} />
  return <EmployeeScreen api={api} onLogout={logout} {...screenProps} />
}

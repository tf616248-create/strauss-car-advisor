import { useEffect, useState } from 'react'
import * as realApi from '../lib/api'
import { clearSession, getToken, setUnauthorizedHandler } from '../lib/session'
import Intro from '../components/Intro'
import EmployeeScreen from './EmployeeScreen'

// The employee side. Every visit opens with the intro scene (components/Intro.jsx): its card logs in,
// or, with a token for this tab already, only its button goes on. Then the picture shrinks to a
// banner and the chat comes in below it, with the focus in the message box.
// A 401 from the server (expired login) and "logout" come back to the card - without the video again.
export default function EmployeeApp({ api = realApi, ...screenProps }) {
  const [loggedIn, setLoggedIn] = useState(() => Boolean(getToken()))
  const [inside, setInside] = useState(false)
  const [backAgain, setBackAgain] = useState(false) // returned from inside: no replay

  function backToCard() {
    setLoggedIn(false)
    setInside(false)
    setBackAgain(true)
  }

  useEffect(() => {
    setUnauthorizedHandler(backToCard)
    return () => setUnauthorizedHandler(() => {})
  }, [])

  function enter() {
    setLoggedIn(true)
    setInside(true)
  }

  function logout() {
    clearSession()
    backToCard()
  }

  return (
    <div className={`shell ${inside ? 'shell--inside' : ''}`}>
      {/* a new key on the way back: the scene starts at its end, without the video */}
      <Intro key={backAgain ? 'back' : 'first'} api={api} hasToken={loggedIn} onEnter={enter}
        banner={inside} startFinal={backAgain} />
      {inside && (
        <div className="shell__app">
          <EmployeeScreen api={api} onLogout={logout} autoFocus {...screenProps} />
        </div>
      )}
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import cfg from '../config/intro.json'
import Login from './Login'

// The opening scene, on every visit before the chat. The hero video plays once, muted: at
// times.slogan the slogan breaks in, at times.answer the answer rises, after it the card (the login,
// or with a token only the button), and at times.end it stops on the frame. "Skip" jumps to the end.
// Reduced motion, a broken file, a refused play() or nothing playing by loadTimeoutSeconds: the
// poster at once, and everything else works the same.
// After going in it becomes the banner above the chat (banner): the picture and a small slogan.
// startFinal: back here from inside (logout, expired login) - the end, without the video again.
const T = cfg.texts
const P = cfg.media.poster
const REDUCE = '(prefers-reduced-motion: reduce)'
const reducedMotion = () => Boolean(window.matchMedia?.(REDUCE)?.matches)

function Poster() {
  return (
    <picture className="intro__poster" aria-hidden="true">
      <source type="image/webp" srcSet={`${P.webp['640']} 640w, ${P.webp['1280']} 1280w`} sizes="100vw" />
      <img src={P.jpg['1280']} srcSet={`${P.jpg['640']} 640w, ${P.jpg['1280']} 1280w`} sizes="100vw" alt="" />
    </picture>
  )
}

export default function Intro({ api, hasToken, onEnter, banner = false, startFinal = false }) {
  const [reduce] = useState(reducedMotion)
  const [withVideo] = useState(() => !reduce && !banner && !startFinal)
  const [time, setTime] = useState(0) // the video's time, which drives the scene
  const [final, setFinal] = useState(() => !withVideo)
  const [playing, setPlaying] = useState(false)
  const [muted, setMuted] = useState(true)
  const sectionRef = useRef(null)
  const videoRef = useRef(null)

  const at = (seconds) => final || time >= seconds
  const video = withVideo && !banner

  function finish() {
    videoRef.current?.pause()
    setFinal(true)
  }

  // "skip" disappears with the scene: the focus goes on to the card, not to the page
  const [skipped, setSkipped] = useState(false)
  function skip() {
    finish()
    setSkipped(true)
  }
  useEffect(() => {
    if (skipped) sectionRef.current?.querySelector('.intro__dock input, .intro__dock button')?.focus()
  }, [skipped])

  // play once (autoplay alone is not enough everywhere); a refusal is the final picture
  useEffect(() => {
    if (!withVideo) return
    Promise.resolve(videoRef.current?.play()).catch(() => setFinal(true))
  }, [withVideo])

  // a slow or stuck file: the picture, instead of a black screen
  useEffect(() => {
    if (final || playing || !withVideo) return
    const id = setTimeout(() => setFinal(true), cfg.loadTimeoutSeconds * 1000)
    return () => clearTimeout(id)
  }, [final, playing, withVideo])

  // a phone keyboard covers the bottom of the screen: the card rises above it (--kb)
  useEffect(() => {
    const vv = window.visualViewport
    const el = sectionRef.current
    if (!vv || !el) return
    const update = () => el.style.setProperty('--kb', `${Math.max(0, window.innerHeight - vv.height - vv.offsetTop)}px`)
    vv.addEventListener('resize', update)
    vv.addEventListener('scroll', update)
    return () => { vv.removeEventListener('resize', update); vv.removeEventListener('scroll', update) }
  }, [])

  function onTime(e) {
    const now = e.currentTarget.currentTime
    setTime(now)
    if (now >= cfg.times.end) finish()
  }

  function toggleSound() {
    const next = !muted
    if (videoRef.current) videoRef.current.muted = next
    setMuted(next)
  }

  // iOS does not move the page for the keyboard by itself every time
  const keepFieldInView = (e) => {
    const field = e.currentTarget
    setTimeout(() => field.scrollIntoView?.({ block: 'nearest' }), 300)
  }

  const classes = ['intro', final && 'intro--final', banner && 'intro--banner', reduce && 'intro--still']
  const Slogan = banner ? 'p' : 'h1'
  return (
    <section ref={sectionRef} className={classes.filter(Boolean).join(' ')} aria-label={T.cardTitle}>
      {video && !final && (
        <div className="intro__controls">
          <button type="button" className="intro__skip" aria-label={T.skipLabel} onClick={skip}>{T.skip}</button>
          <button type="button" className="intro__sound" aria-label={muted ? T.soundOn : T.soundOff}
            aria-pressed={!muted} onClick={toggleSound}>{muted ? '🔇' : '🔊'}</button>
        </div>
      )}
      {video && (
        <video ref={videoRef} className="intro__video" muted autoPlay playsInline preload="auto"
          poster={P.jpg['1280']} aria-hidden="true" tabIndex={-1}
          onTimeUpdate={onTime} onEnded={finish} onPlaying={() => setPlaying(true)}>
          <source src={cfg.media.webm} type="video/webm" />
          <source src={cfg.media.mp4} type="video/mp4" onError={() => setFinal(true)} />
        </video>
      )}
      {final && <Poster />}
      <div className="intro__shade" aria-hidden="true" />
      {/* the page's h1 while it is the scene; in the banner the chat's header is the h1, so a <p> */}
      <Slogan className="intro__slogan">
        <span className={`intro__line ${!reduce && !banner ? 'intro__slogan--break' : ''} ${at(cfg.times.slogan) ? 'is-shown' : ''}`}>
          {T.slogan}
        </span>{' '}
        <span className={`intro__line intro__line--answer ${at(cfg.times.answer) ? 'is-shown' : ''}`}>{T.answer}</span>
      </Slogan>
      {!banner && at(cfg.times.card) && (
        <div className="intro__dock">
          {hasToken
            ? <button type="button" className="intro__enter intro__go" aria-label={T.enterLabel} onClick={onEnter}>{T.enter}</button>
            : <Login api={api} onLogin={onEnter} onFocusField={keepFieldInView} />}
        </div>
      )}
    </section>
  )
}

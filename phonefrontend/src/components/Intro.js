// The opening scene before the chat (like frontend/src/components/Intro.jsx). The hero video plays
// once, muted (🔇 by default, 🔊 turns the sound on): at times.slogan the slogan appears, at times.answer
// the answer, at times.card the login card, and at times.end it stops on the last frame (the picture).
// "דלג" jumps to the end. Reduced motion on the phone, a video that fails, or one that does not start
// by loadTimeoutSeconds: the picture at once, and everything else works the same.
// The slogan is the screen's heading all along; its lines are only hidden until their time.
import { useEffect, useState } from 'react'
import { AccessibilityInfo, Image, KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native'
import { useVideoPlayer, VideoView } from 'expo-video'
import { T } from './ui'
import Login from './Login'
import cfg from '../config/intro.json'

const TX = cfg.texts
const VIDEO = require('../../assets/media/hero.mp4')
const POSTER = require('../../assets/media/hero-poster-1280.jpg')

export default function Intro({ api, onEnter }) {
  const [reduce, setReduce] = useState(null) // null until the phone's setting is read
  const [time, setTime] = useState(0)
  const [final, setFinal] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [muted, setMuted] = useState(true)
  const player = useVideoPlayer(VIDEO, (p) => {
    p.muted = true
    p.loop = false
    p.timeUpdateEventInterval = 0.25
  })
  const video = reduce === false && !final
  const at = (seconds) => final || time >= seconds

  function finish() {
    player.pause()
    setFinal(true)
  }

  useEffect(() => {
    let live = true
    Promise.resolve(AccessibilityInfo.isReduceMotionEnabled?.()).then((on) => {
      if (!live) return
      setReduce(Boolean(on))
      if (on) setFinal(true)
    }).catch(() => { if (live) { setReduce(false) } })
    return () => { live = false }
  }, [])

  // the video's time drives the scene; the end, or an error, is the picture
  useEffect(() => {
    if (reduce !== false) return undefined
    const subs = [
      player.addListener('timeUpdate', ({ currentTime }) => {
        setPlaying(true)
        setTime(currentTime)
        if (currentTime >= cfg.times.end) finish()
      }),
      player.addListener('playToEnd', finish),
      player.addListener('statusChange', ({ status }) => { if (status === 'error') setFinal(true) }),
    ]
    player.play()
    return () => subs.forEach((s) => s.remove())
  }, [reduce]) // eslint-disable-line react-hooks/exhaustive-deps

  // a slow or stuck file: the picture, instead of a black screen
  useEffect(() => {
    if (final || playing || reduce !== false) return undefined
    const id = setTimeout(() => setFinal(true), cfg.loadTimeoutSeconds * 1000)
    return () => clearTimeout(id)
  }, [final, playing, reduce])

  function toggleSound() {
    player.muted = !muted
    setMuted(!muted)
  }

  const line = (text, seconds, big) => (
    <T weight={700} size={big ? 34 : 26} color="#FFFFFF"
      style={{ opacity: at(seconds) ? 1 : 0, textAlign: 'center', textShadowColor: 'rgba(0,0,0,0.6)', textShadowRadius: 8 }}>{text}</T>
  )

  return (
    <View style={{ flex: 1, backgroundColor: '#000' }}>
      {video
        ? <VideoView testID="intro-video" player={player} contentFit="cover" nativeControls={false} style={{ position: 'absolute', top: 0, right: 0, bottom: 0, left: 0 }}
            accessibilityElementsHidden importantForAccessibility="no-hide-descendants" />
        : reduce !== null && <Image testID="intro-poster" source={POSTER} resizeMode="cover" accessibilityElementsHidden importantForAccessibility="no"
            style={{ position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, width: '100%', height: '100%' }} />}
      <View style={{ position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, backgroundColor: 'rgba(0,0,0,0.25)' }} />
      {video && (
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', padding: 12, direction: 'rtl' }}>
          <Pressable accessibilityRole="button" accessibilityLabel={TX.skipLabel} onPress={finish}
            style={{ minHeight: 44, paddingHorizontal: 18, borderRadius: 999, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'center' }}>
            <T weight={700} color="#FFFFFF">{TX.skip}</T>
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel={muted ? TX.soundOn : TX.soundOff} accessibilityState={{ selected: !muted }}
            onPress={toggleSound} style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: 'rgba(0,0,0,0.55)', alignItems: 'center', justifyContent: 'center' }}>
            <T size={20}>{muted ? '🔇' : '🔊'}</T>
          </Pressable>
        </View>
      )}
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'flex-end', padding: 20, gap: 16 }} keyboardShouldPersistTaps="handled">
          <View accessibilityRole="header" accessible accessibilityLabel={`${TX.slogan} ${TX.answer}`} style={{ gap: 4, marginBottom: 'auto', marginTop: 48 }}>
            {line(TX.slogan, cfg.times.slogan, true)}
            {line(TX.answer, cfg.times.answer)}
          </View>
          {at(cfg.times.card) && <Login api={api} onLogin={onEnter} embedded />}
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  )
}

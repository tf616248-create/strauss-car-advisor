// fonts are not loaded in tests
jest.mock('expo-font', () => ({ useFonts: () => [true], isLoaded: () => true, loadAsync: async () => {} }))
// native modules: the tests pass fakes (pickPayslip, the upload body); only the imports must load
jest.mock('expo-image-picker', () => ({
  requestCameraPermissionsAsync: jest.fn(async () => ({ granted: true })),
  launchCameraAsync: jest.fn(async () => ({ canceled: true, assets: null })),
  launchImageLibraryAsync: jest.fn(async () => ({ canceled: true, assets: null })),
}))
jest.mock('expo-document-picker', () => ({ getDocumentAsync: jest.fn(async () => ({ canceled: true, assets: null })) }))
jest.mock('expo-file-system', () => ({ File: class File { constructor(uri) { this.uri = uri } } }))
// expo-video: a fake player the tests drive (__emit a time, __reset between tests)
jest.mock('expo-video', () => {
  const { View } = require('react-native')
  const listeners = {}
  const player = { muted: false, loop: true, play: jest.fn(), pause: jest.fn(), timeUpdateEventInterval: 0,
    addListener: (name, fn) => { (listeners[name] ??= []).push(fn); return { remove: () => { listeners[name] = listeners[name].filter((f) => f !== fn) } } } }
  return {
    // like the real one: the setup runs once, when the player is created
    useVideoPlayer: (_source, setup) => { if (!player.created) { player.created = true; setup?.(player) } return player },
    VideoView: (props) => <View testID="intro-video" {...props} />,
    __player: player,
    __emit: (name, payload) => (listeners[name] ?? []).forEach((fn) => fn(payload)),
    __reset: () => { for (const k of Object.keys(listeners)) delete listeners[k]; player.created = false; player.muted = false; player.loop = true; player.play.mockClear(); player.pause.mockClear() },
  }
})

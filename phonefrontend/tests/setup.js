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

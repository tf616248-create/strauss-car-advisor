// fonts are not loaded in tests
jest.mock('expo-font', () => ({ useFonts: () => [true], isLoaded: () => true, loadAsync: async () => {} }))

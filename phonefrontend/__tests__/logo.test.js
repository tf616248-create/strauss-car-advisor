// The Strauss logo (from frontend/src/assets/strauss-logo.svg, an Inkscape file) is cleaned for
// react-native-svg: a viewBox so it scales to its box (without one it is cut off), and no Inkscape metadata.
import logo from '../src/assets/logo'

test('the logo scales to its box: a viewBox, no fixed width or height', () => {
  expect(logo).toMatch(/<svg[^>]*viewBox="0 0 219\.91246 151\.40248"/)
  expect(logo).not.toMatch(/<svg[^>]*\swidth=/)
})

test('no Inkscape or Sodipodi metadata left (React warns about every such attribute)', () => {
  expect(logo).not.toMatch(/inkscape|sodipodi|xmlns:|<metadata|rdf:/i)
  expect(logo).toMatch(/#ee2622/i) // the drawing itself is still there
})

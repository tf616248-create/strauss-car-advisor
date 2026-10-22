// The payslip on a phone: the same checks as the server (backend/app/payslip.py) and the website
// (frontend/src/lib/payslip.js) before anything is sent, and three sources: the camera, the
// gallery, a file (PDF too). The server checks again by the file's bytes.
import * as ImagePicker from 'expo-image-picker'
import * as DocumentPicker from 'expo-document-picker'
import cfg from '../config/payslip.json'

const IMAGE = ['image/jpeg', 'image/png']
const PDF = 'application/pdf'

// { name, type, size } -> { kind: 'image' | 'pdf' } or { error: text }. An unknown size: the server checks.
export function checkAsset({ name = '', type = '', size }) {
  const n = name.toLowerCase()
  const kind = IMAGE.includes(type) || /\.(jpe?g|png)$/.test(n) ? 'image'
    : type === PDF || n.endsWith('.pdf') ? 'pdf' : null
  if (!kind) return { error: cfg.texts.badType }
  if (typeof size === 'number' && size > cfg.maxBytes) return { error: cfg.texts.tooLarge }
  return { kind }
}

const IMAGES = { mediaTypes: ['images'], quality: 0.8 }
export const realPickers = {
  cameraPermission: () => ImagePicker.requestCameraPermissionsAsync(),
  camera: () => ImagePicker.launchCameraAsync(IMAGES),
  gallery: () => ImagePicker.launchImageLibraryAsync(IMAGES),
  file: () => DocumentPicker.getDocumentAsync({ type: [PDF, ...IMAGE], copyToCacheDirectory: true }),
}

// one picked asset (image picker or document picker) -> { uri, name, type }
function normalize(a) {
  const name = a.fileName ?? a.name ?? `${a.uri.split('/').pop() || 'photo'}`
  const type = a.mimeType ?? (/\.png$/i.test(name) ? 'image/png' : /\.pdf$/i.test(name) ? PDF : 'image/jpeg')
  const withExt = /\.(jpe?g|png|pdf)$/i.test(name) ? name : `${name}.${type === PDF ? 'pdf' : type === 'image/png' ? 'png' : 'jpg'}`
  return { uri: a.uri, name: withExt, type, size: a.fileSize ?? a.size }
}

// source: 'camera' | 'gallery' | 'file' -> { uri, name, type, kind }, null when cancelled, or { error }
export async function pickPayslip(source, pickers = realPickers) {
  if (source === 'camera') {
    const permission = await pickers.cameraPermission()
    if (!permission?.granted) return { error: cfg.texts.noCamera }
  }
  const res = await pickers[source]()
  if (!res || res.canceled || !res.assets?.length) return null
  const { size, ...att } = normalize(res.assets[0])
  const checked = checkAsset({ ...att, size })
  return checked.error ? { error: checked.error } : { ...att, kind: checked.kind }
}

// Builds the opening (hero) video and its poster images, from the source in media-src/ (not in git).
// Run again after replacing the source video:
//
//   cd scripts && npm install && npm run build-hero-media          (or: node build-hero-media.mjs [video])
//
// Output, in frontend/public/media/:
//   hero.mp4    H.264 + AAC, 720p, faststart (playback starts before the whole file is down)
//   hero.webm   VP9 + Opus, 720p
//   hero-poster-1280.jpg / .webp, hero-poster-640.jpg / .webp   the frame at POSTER_AT (banner,
//               reduced motion, and what shows until the video loads)
//
// Both videos: seconds START..END of the source, two-pass to TARGET_MB, audio AUDIO_GAIN_DB down with
// a limiter at LIMIT_DBFS so it cannot clip. The script checks the results and fails loudly if a file
// is outside SIZE_RANGE_MB, the audio peaks above LIMIT_DBFS, or the MP4 is not faststart.
// ffmpeg comes from ffmpeg-static (scripts/package.json), not from the system.
import { execFileSync, spawnSync } from 'node:child_process'
import { mkdtempSync, readdirSync, readFileSync, rmSync, statSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ffmpeg from 'ffmpeg-static'

const START = 0
const END = 9
const POSTER_AT = 9
const HEIGHT = 720
const POSTER_WIDTHS = [1280, 640]
const TARGET_MB = 2.5
const SIZE_RANGE_MB = [2, 3]
const AUDIO_GAIN_DB = -6
const LIMIT_DBFS = -1
const AUDIO_KBPS = { mp4: 128, webm: 96 }
const CONTAINER_OVERHEAD = 0.03

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const SRC_DIR = join(ROOT, 'media-src')
const OUT = join(ROOT, 'frontend', 'public', 'media')
const MB = 1024 * 1024

function run(args) {
  execFileSync(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', ...args], { stdio: 'inherit' })
}

// what ffmpeg says about a file (duration, volumedetect) - it writes that to stderr
const info = (args) => spawnSync(ffmpeg, ['-hide_banner', ...args], { encoding: 'utf8' }).stderr

function source() {
  const given = process.argv[2]
  if (given) return resolve(given)
  const videos = readdirSync(SRC_DIR).filter((f) => /\.(mp4|mov|webm|mkv)$/i.test(f))
  if (videos.length !== 1) throw new Error(`expected one video in ${SRC_DIR}, found ${videos.length}: ${videos.join(', ')}`)
  return join(SRC_DIR, videos[0])
}

const duration = END - START
const audio = `volume=${AUDIO_GAIN_DB}dB,alimiter=limit=${10 ** (LIMIT_DBFS / 20)}:level=0`
const scale = `scale=-2:${HEIGHT}:flags=lanczos`
const videoKbps = (kind) => Math.floor((TARGET_MB * MB * 8 * (1 - CONTAINER_OVERHEAD)) / duration / 1000) - AUDIO_KBPS[kind]

function twoPass(src, out, kind, codecArgs, audioArgs, extra = []) {
  const logDir = mkdtempSync(join(tmpdir(), 'hero-'))
  const log = join(logDir, 'pass')
  const input = ['-ss', String(START), '-to', String(END), '-i', src]
  const v = ['-vf', scale, ...codecArgs, '-b:v', `${videoKbps(kind)}k`, '-passlogfile', log]
  try {
    run([...input, ...v, '-pass', '1', '-an', '-f', 'null', '-'])
    run([...input, ...v, '-pass', '2', '-af', audio, ...audioArgs, ...extra, out])
  } finally {
    rmSync(logDir, { recursive: true, force: true })
  }
}

function peakDb(file, input = []) {
  const m = info([...input, '-i', file, '-vn', '-af', 'volumedetect', '-f', 'null', '-']).match(/max_volume: (-?[\d.]+) dB/)
  if (!m) throw new Error(`no audio level for ${file}`)
  return Number(m[1])
}

function durationOf(file) {
  const m = info(['-i', file]).match(/Duration: (\d+):(\d+):([\d.]+)/)
  return m ? Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]) : NaN
}

// faststart: the index (moov) comes before the media data (mdat)
function isFaststart(file) {
  const buf = readFileSync(file)
  const moov = buf.indexOf('moov')
  const mdat = buf.indexOf('mdat')
  return moov !== -1 && mdat !== -1 && moov < mdat
}

const src = source()
mkdirSync(OUT, { recursive: true })
console.log(`source: ${src}`)

const mp4 = join(OUT, 'hero.mp4')
twoPass(src, mp4, 'mp4',
  ['-c:v', 'libx264', '-preset', 'slow', '-profile:v', 'high', '-pix_fmt', 'yuv420p'],
  ['-c:a', 'aac', '-b:a', `${AUDIO_KBPS.mp4}k`],
  ['-movflags', '+faststart'])

const webm = join(OUT, 'hero.webm')
twoPass(src, webm, 'webm',
  ['-c:v', 'libvpx-vp9', '-deadline', 'good', '-cpu-used', '2', '-row-mt', '1', '-pix_fmt', 'yuv420p'],
  ['-c:a', 'libopus', '-b:a', `${AUDIO_KBPS.webm}k`])

const posters = []
for (const width of POSTER_WIDTHS) {
  const frame = ['-ss', String(POSTER_AT), '-i', src, '-frames:v', '1', '-vf', `scale=${width}:-2:flags=lanczos`]
  const jpg = join(OUT, `hero-poster-${width}.jpg`)
  const webp = join(OUT, `hero-poster-${width}.webp`)
  run([...frame, '-q:v', '3', jpg])
  run([...frame, '-c:v', 'libwebp', '-quality', '82', webp])
  posters.push(jpg, webp)
}

// --- checks ---------------------------------------------------------------------------------------
const problems = []
const report = []
for (const file of [mp4, webm]) {
  const size = statSync(file).size / MB
  const peak = peakDb(file)
  const secs = durationOf(file)
  report.push(`${file.slice(ROOT.length + 1)}  ${size.toFixed(2)} MB  ${secs.toFixed(2)} s  peak ${peak} dB`)
  if (size < SIZE_RANGE_MB[0] || size > SIZE_RANGE_MB[1]) problems.push(`${file}: ${size.toFixed(2)} MB, outside ${SIZE_RANGE_MB.join('-')} MB`)
  if (peak > LIMIT_DBFS) problems.push(`${file}: audio peak ${peak} dB, above ${LIMIT_DBFS} dB`)
  if (Math.abs(secs - duration) > 0.1) problems.push(`${file}: ${secs} s, not ${duration} s`)
}
if (!isFaststart(mp4)) problems.push(`${mp4}: not faststart (moov after mdat)`)
for (const file of posters) report.push(`${file.slice(ROOT.length + 1)}  ${(statSync(file).size / 1024).toFixed(0)} KB`)

console.log(`source audio peak (seconds ${START}-${END}): ${peakDb(src, ['-ss', String(START), '-to', String(END)])} dB, gain ${AUDIO_GAIN_DB} dB`)
console.log(report.join('\n'))
if (problems.length) {
  console.error(`\nPROBLEMS:\n${problems.join('\n')}`)
  process.exit(1)
}
console.log('\nall checks passed (size, audio peak, duration, faststart)')

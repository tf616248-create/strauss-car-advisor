import { readFileSync } from 'node:fs'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import cfg from '../config/intro.json'
import { getToken } from '../lib/session'
import Intro from './Intro'

// The opening scene: the video plays once, the slogan comes in at 2 s and 6 s, the card after it,
// and at 9 s the picture stays. "Skip" jumps to the end. jsdom plays nothing: the tests drive the
// video's time themselves (test-setup.js stubs play/pause).
const T = cfg.texts

function motion(reduce) {
  window.matchMedia = vi.fn((q) => ({
    matches: reduce && q.includes('reduce'), media: q, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  }))
}

function setup(props = {}) {
  const onEnter = vi.fn()
  const api = { login: vi.fn().mockResolvedValue({ token: 'tok', employee_id: 'E01' }) }
  render(<Intro api={api} hasToken={false} onEnter={onEnter} {...props} />)
  return { onEnter, api, video: document.querySelector('video') }
}

function at(video, seconds) {
  Object.defineProperty(video, 'currentTime', { value: seconds, configurable: true, writable: true })
  act(() => { fireEvent.timeUpdate(video) })
}

const slogan = () => screen.getByRole('heading', { level: 1 })
const line = (text) => within(slogan()).getByText(text)
const codeField = () => screen.queryByLabelText(T.code)
const enterButton = () => screen.queryByRole('button', { name: T.enterLabel })

beforeEach(() => motion(false))
afterEach(() => { vi.useRealTimers(); delete window.matchMedia })

describe('the video', () => {
  it('full screen, muted, plays once inline, hidden from screen readers, with the poster', () => {
    const { video } = setup()
    expect(video.muted).toBe(true)
    expect(video).toHaveAttribute('autoplay')
    expect(video).toHaveAttribute('playsinline')
    expect(video).not.toHaveAttribute('loop')
    expect(video).toHaveAttribute('aria-hidden', 'true')
    expect(video).toHaveAttribute('poster', cfg.media.poster.jpg['1280'])
    const sources = [...video.querySelectorAll('source')].map((s) => s.getAttribute('src'))
    expect(sources).toEqual([cfg.media.webm, cfg.media.mp4])
    const css = readFileSync('src/styles.css', 'utf8')
    expect(css).toMatch(/\.intro \{[^}]*height:\s*100svh/)
    expect(css).toMatch(/\.intro__video[^{]*\{[^}]*object-fit:\s*cover/)
  })

  it('the slogan is real text in an h1; it comes in at 2 s ("breaking") and 6 s, the card after it', () => {
    const { video } = setup()
    expect(slogan()).toHaveTextContent(T.slogan)
    expect(slogan()).toHaveTextContent(T.answer)
    expect(line(T.slogan)).not.toHaveClass('is-shown')
    at(video, cfg.times.slogan)
    expect(line(T.slogan)).toHaveClass('is-shown')
    expect(line(T.slogan)).toHaveClass('intro__slogan--break')
    expect(line(T.answer)).not.toHaveClass('is-shown')
    expect(codeField()).toBeNull()
    at(video, cfg.times.answer)
    expect(line(T.answer)).toHaveClass('is-shown')
    expect(codeField()).toBeNull()
    at(video, cfg.times.card)
    expect(codeField()).toBeInTheDocument()
  })

  it('at 9 s it stops on the frame: the picture stays', () => {
    const { video } = setup()
    const pause = vi.spyOn(video, 'pause')
    at(video, cfg.times.end)
    expect(pause).toHaveBeenCalled()
    expect(document.querySelector('.intro')).toHaveClass('intro--final')
    expect(document.querySelector('.intro__poster img')).toBeInTheDocument()
  })

  it('the end of the file also ends the scene (one play, no loop)', () => {
    const { video } = setup()
    act(() => { fireEvent.ended(video) })
    expect(document.querySelector('.intro')).toHaveClass('intro--final')
    expect(codeField()).toBeInTheDocument()
  })

  it('🔇 by default; the button turns the sound on and off, and says what it does', async () => {
    const { video } = setup()
    const user = userEvent.setup()
    const on = screen.getByRole('button', { name: T.soundOn })
    expect(on).toHaveTextContent('🔇')
    await user.click(on)
    expect(video.muted).toBe(false)
    const off = screen.getByRole('button', { name: T.soundOff })
    expect(off).toHaveTextContent('🔊')
    await user.click(off)
    expect(video.muted).toBe(true)
  })
})

describe('skip', () => {
  it('is the first stop for the keyboard, from the first second', async () => {
    setup()
    await userEvent.setup().tab()
    expect(screen.getByRole('button', { name: T.skipLabel })).toHaveFocus()
    expect(screen.getByRole('button', { name: T.skipLabel })).toHaveTextContent(T.skip)
  })

  it('jumps straight to the end: the whole slogan and the card', async () => {
    const { video } = setup()
    const pause = vi.spyOn(video, 'pause')
    await userEvent.setup().click(screen.getByRole('button', { name: T.skipLabel }))
    expect(line(T.slogan)).toHaveClass('is-shown')
    expect(line(T.answer)).toHaveClass('is-shown')
    expect(codeField()).toBeInTheDocument()
    expect(pause).toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: T.skipLabel })).toBeNull() // nothing left to skip
  })

  it('the focus does not get lost with the button: it goes to the card', async () => {
    setup()
    const user = userEvent.setup()
    await user.tab()
    await user.keyboard('{Enter}')
    expect(codeField()).toHaveFocus()
  })

  it('with a token, to the button', async () => {
    setup({ hasToken: true })
    await userEvent.setup().click(screen.getByRole('button', { name: T.skipLabel }))
    expect(enterButton()).toHaveFocus()
  })
})

describe('without a token: the login card', () => {
  it('a right code keeps the token and goes in', async () => {
    const { onEnter, api } = setup()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: T.skipLabel }))
    await user.type(codeField(), '1111')
    await user.click(enterButton())
    expect(api.login).toHaveBeenCalledWith('1111')
    expect(getToken()).toBe('tok')
    expect(onEnter).toHaveBeenCalled()
  })

  it('a wrong code says so, and stays', async () => {
    const api = { login: vi.fn().mockRejectedValue(Object.assign(new Error('x'), { status: 401 })) }
    const onEnter = vi.fn()
    render(<Intro api={api} hasToken={false} onEnter={onEnter} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: T.skipLabel }))
    await user.type(codeField(), '9')
    await user.click(enterButton())
    expect(await screen.findByRole('alert')).toHaveTextContent('הקוד לא נכון. אפשר לנסות שוב.')
    expect(onEnter).not.toHaveBeenCalled()
  })
})

describe('with a token', () => {
  it('the same video, then only the button (no code field)', async () => {
    const { video, onEnter } = setup({ hasToken: true })
    expect(video).toBeInTheDocument()
    at(video, cfg.times.card)
    expect(codeField()).toBeNull()
    await userEvent.setup().click(enterButton())
    expect(onEnter).toHaveBeenCalled()
  })
})

describe('reduced motion', () => {
  it('no video and no animation: the poster, the whole slogan and the card at once', () => {
    motion(true)
    setup()
    expect(document.querySelector('video')).toBeNull()
    expect(document.querySelector('.intro__poster img')).toBeInTheDocument()
    expect(line(T.slogan)).toHaveClass('is-shown')
    expect(line(T.answer)).toHaveClass('is-shown')
    expect(line(T.slogan)).not.toHaveClass('intro__slogan--break')
    expect(codeField()).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: T.skipLabel })).toBeNull()
    expect(screen.queryByRole('button', { name: T.soundOn })).toBeNull()
  })

  it('the CSS turns every intro animation off too', () => {
    const css = readFileSync('src/styles.css', 'utf8')
    const reduce = css.slice(css.indexOf('/* intro: reduced motion */'))
    expect(reduce).toMatch(/@media \(prefers-reduced-motion: reduce\)/)
    expect(reduce).toMatch(/\.intro[^{]*\{[^}]*(animation|transition):\s*none/)
  })
})

describe('when the video does not load', () => {
  it('a broken file: the poster at once, and everything else works', async () => {
    const { video, onEnter } = setup()
    const sources = video.querySelectorAll('source')
    act(() => { fireEvent.error(sources[sources.length - 1]) })
    expect(document.querySelector('.intro__poster img')).toBeInTheDocument()
    expect(line(T.answer)).toHaveClass('is-shown')
    const user = userEvent.setup()
    await user.type(codeField(), '1111')
    await user.click(enterButton())
    expect(onEnter).toHaveBeenCalled()
  })

  it('play() refused (e.g. data saver): the poster at once', async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockRejectedValue(new Error('NotAllowedError'))
    setup()
    await act(async () => {})
    expect(document.querySelector('.intro')).toHaveClass('intro--final')
    expect(codeField()).toBeInTheDocument()
    play.mockRestore()
  })

  it(`nothing played after ${cfg.loadTimeoutSeconds} s (slow network): the poster`, () => {
    vi.useFakeTimers()
    setup()
    act(() => { vi.advanceTimersByTime(cfg.loadTimeoutSeconds * 1000) })
    expect(document.querySelector('.intro')).toHaveClass('intro--final')
    expect(codeField()).toBeInTheDocument()
  })

  it('once it plays, a slow second does not cut it short', () => {
    vi.useFakeTimers()
    const { video } = setup()
    act(() => { fireEvent.playing(video) })
    act(() => { vi.advanceTimersByTime(cfg.loadTimeoutSeconds * 1000) })
    expect(document.querySelector('.intro')).not.toHaveClass('intro--final')
  })
})

describe('the banner (after going in)', () => {
  it('the picture and a small slogan; no video, card or buttons', () => {
    render(<Intro api={{ login: vi.fn() }} hasToken onEnter={vi.fn()} banner />)
    expect(document.querySelector('.intro')).toHaveClass('intro--banner')
    expect(document.querySelector('video')).toBeNull()
    expect(document.querySelector('.intro__poster img')).toBeInTheDocument()
    // still real text, but the chat's header is the page's h1 now
    expect(document.querySelector('.intro__slogan')).toHaveTextContent(T.slogan)
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('about a third of the screen on a computer, 120px on a phone', () => {
    const css = readFileSync('src/styles.css', 'utf8')
    expect(css).toMatch(/\.intro--banner \{[^}]*height:\s*33vh/)
    const phone = css.slice(css.indexOf('/* intro: phone */'))
    expect(phone).toMatch(/\.intro--banner \{[^}]*height:\s*120px/)
  })
})

describe('accessibility', () => {
  it('every button has a label, and is at least 44×44', () => {
    setup()
    for (const b of screen.getAllByRole('button')) expect(b).toHaveAccessibleName()
    const css = readFileSync('src/styles.css', 'utf8')
    for (const sel of ['\\.intro__skip', '\\.intro__sound', '\\.intro__enter']) {
      const rule = css.match(new RegExp(`${sel}[^{]*\\{([^}]*)\\}`))[1]
      expect(rule, sel).toMatch(/min-height:\s*(4[4-9]|[5-9]\d)px/)
      expect(rule, sel).toMatch(/min-width:\s*(4[4-9]|[5-9]\d)px/)
    }
  })

  it('a dark gradient under the text, so white text keeps AA contrast', () => {
    const css = readFileSync('src/styles.css', 'utf8')
    expect(css).toMatch(/\.intro__shade \{[^}]*linear-gradient/)
  })
})

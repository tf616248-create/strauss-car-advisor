// The bot's answer: Markdown shown formatted (bold, headings, lists), like other chats.
// No tables (the comparison is the card beside the chat), no raw HTML, no images, and no links but
// one: the employee's own profile (/profile), which opens the profile dialog over the conversation.
// Anything else is shown as its plain text. No remark-gfm, so a table is never even parsed.
// The profile link always reads as a Hebrew word: a bare "/profile", or a link whose text is the
// path itself, reads "כאן" (texts.linkText). Its accessible name starts with the words shown.
import { useMemo, useRef } from 'react'
import Markdown from 'react-markdown'
import profileCfg from '../config/profile.json'

const ALLOWED = ['p', 'strong', 'em', 'ul', 'ol', 'li', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']
const PATH = profileCfg.path
const { linkText: LINK_TEXT, linkLabel: LINK_LABEL } = profileCfg.texts
// "/profile" written as it is: a link to the same place
const BARE = new RegExp(`(^|[\\s:,])${PATH.replace('/', '\\/')}(?![\\w/\\]])`, 'g')

const textOf = (children) => [children].flat().filter((c) => typeof c === 'string').join('').trim()

export default function Answer({ text, onProfile }) {
  // one component for every render (a new one each time would remount the link under the pointer);
  // it reads the latest onProfile from the ref
  const onProfileRef = useRef(onProfile)
  onProfileRef.current = onProfile
  const components = useMemo(() => ({
    a: ({ href, children }) => {
      if (href !== PATH) return <>{children}</> // any other link: its text only
      const own = textOf(children)
      const shown = !own || own === PATH ? LINK_TEXT : children
      return (
        <a href={PATH} aria-label={LINK_LABEL.replace('{text}', textOf(shown) || LINK_TEXT)}
          onClick={(e) => { e.preventDefault(); onProfileRef.current?.(e.currentTarget) }}>{shown}</a>
      )
    },
  }), [])
  if (!onProfile) {
    return (
      <div className="answer">
        <Markdown allowedElements={ALLOWED} unwrapDisallowed skipHtml>{text}</Markdown>
      </div>
    )
  }
  const withLinks = text.replace(BARE, `$1[${LINK_TEXT}](${PATH})`)
  return (
    <div className="answer">
      <Markdown allowedElements={[...ALLOWED, 'a']} unwrapDisallowed skipHtml components={components}>
        {withLinks}
      </Markdown>
    </div>
  )
}

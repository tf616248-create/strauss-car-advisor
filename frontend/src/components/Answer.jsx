// The bot's answer: Markdown shown formatted (bold, headings, lists), like other chats.
// No tables (the comparison is the card beside the chat), no raw HTML, no links or images:
// anything else is shown as its plain text. No remark-gfm, so a table is never even parsed.
import Markdown from 'react-markdown'

const ALLOWED = ['p', 'strong', 'em', 'ul', 'ol', 'li', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']

export default function Answer({ text }) {
  return (
    <div className="answer">
      <Markdown allowedElements={ALLOWED} unwrapDisallowed skipHtml>{text}</Markdown>
    </div>
  )
}

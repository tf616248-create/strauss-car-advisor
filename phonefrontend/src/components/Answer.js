// The bot's answer: Markdown shown formatted (bold, headings, lists), like the website.
// No tables (the comparison is its own tab), no raw HTML, no links or images, no code:
// those rules are turned off in the parser, so they stay plain text.
import Markdown, { MarkdownIt } from 'react-native-markdown-display'
import { FONTS, useColors } from '../theme'

const parser = MarkdownIt({ html: false, linkify: false, typographer: false })
  .disable(['table', 'link', 'image', 'html_block', 'html_inline', 'code', 'fence', 'backticks', 'blockquote', 'hr', 'strikethrough'])

export default function Answer({ text }) {
  const c = useColors()
  const base = { fontFamily: FONTS[400], fontSize: 16, lineHeight: 24, color: c.text, textAlign: 'right', writingDirection: 'rtl' }
  const heading = { ...base, fontFamily: FONTS[800], fontSize: 17, borderBottomWidth: 3, borderColor: c.cyan, alignSelf: 'flex-start', marginTop: 6, marginBottom: 4 }
  const styles = {
    body: base,
    paragraph: { ...base, marginTop: 0, marginBottom: 8 },
    strong: { fontFamily: FONTS[700], color: c.cyanText },
    em: { fontStyle: 'italic' },
    heading1: heading, heading2: heading, heading3: heading, heading4: heading, heading5: heading, heading6: heading,
    bullet_list: { marginBottom: 8 },
    ordered_list: { marginBottom: 8 },
    list_item: { flexDirection: 'row' },
    bullet_list_icon: { ...base, marginHorizontal: 8, color: c.cyanText },
    ordered_list_icon: { ...base, marginHorizontal: 8, color: c.cyanText, fontFamily: FONTS[800] },
    text: { fontFamily: undefined },
  }
  return <Markdown markdownit={parser} style={styles} mergeStyle>{text}</Markdown>
}

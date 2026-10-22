// The bot's answer: Markdown shown formatted (bold, headings, lists), like the website.
// No tables (the comparison is its own tab), no raw HTML, no images, no code: those rules are turned
// off in the parser, so they stay plain text. One link only: the employee's own profile (/profile),
// which opens the profile screen. Any other link is shown as its text. The profile link always reads
// as a Hebrew word: a bare "/profile", or a link whose text is the path, reads "כאן" (profile.json).
import { Text, View } from 'react-native'
import Markdown, { MarkdownIt, hasParents, renderRules } from 'react-native-markdown-display'
import { FONTS, READING, useColors } from '../theme'
import profileCfg from '../config/profile.json'

const PATH = profileCfg.path
const { linkText: LINK_TEXT, linkLabel: LINK_LABEL } = profileCfg.texts
// "/profile" written as it is: a link to the same place
const BARE = new RegExp(`(^|[\\s:,])${PATH.replace('/', '\\/')}(?![\\w/\\]])`, 'g')

const parser = MarkdownIt({ html: false, linkify: false, typographer: false })
  .disable(['table', 'image', 'html_block', 'html_inline', 'code', 'fence', 'backticks', 'blockquote', 'hr', 'strikethrough'])

const textOf = (node) => (node.children ?? []).map((n) => n.content ?? textOf(n)).join('').trim()

export default function Answer({ text, onProfile }) {
  const c = useColors()
  // the website's reading tokens: 16, line height 1.7, a very dark gray (not black), 0.6em between blocks
  const base = { fontFamily: FONTS[400], fontSize: READING.size, lineHeight: READING.lineHeight, color: c.readingText, textAlign: 'right', writingDirection: 'rtl' }
  const heading = { ...base, fontFamily: FONTS[700], fontSize: 17, color: c.text, borderBottomWidth: 3, borderColor: c.cyan, alignSelf: 'flex-start', marginTop: 6, marginBottom: 4 }
  const styles = {
    body: base,
    paragraph: { ...base, marginTop: 0, marginBottom: READING.gap },
    strong: { fontFamily: FONTS[700], color: c.cyanText },
    em: { fontStyle: 'italic' },
    heading1: heading, heading2: heading, heading3: heading, heading4: heading, heading5: heading, heading6: heading,
    bullet_list: { marginBottom: READING.gap },
    ordered_list: { marginBottom: READING.gap },
    // the bullet outside the text: a second line starts under the text, not under the bullet
    list_item: { flexDirection: 'row', marginBottom: READING.gap },
    bullet_list_icon: { ...base, marginHorizontal: 8, color: c.muted },
    ordered_list_icon: { ...base, marginHorizontal: 8, color: c.muted },
  }
  const rules = {
    // a bullet: the website's soft hollow circle (◦), in the muted color; numbered items as the library does
    list_item: (node, children, parent, st, inherited) => (hasParents(parent, 'bullet_list') ? (
      <View key={node.key} style={st._VIEW_SAFE_list_item}>
        <Text style={st.bullet_list_icon} accessible={false}>◦</Text>
        <View style={st._VIEW_SAFE_bullet_list_content}>{children}</View>
      </View>
    ) : renderRules.list_item(node, children, parent, st, inherited)),
    link: (node, children) => {
      const own = textOf(node)
      if (node.attributes?.href !== PATH || !onProfile) return <Text key={node.key}>{own === PATH ? LINK_TEXT : children}</Text>
      const shown = !own || own === PATH ? LINK_TEXT : own
      return (
        <Text key={node.key} accessibilityRole="link" accessibilityLabel={LINK_LABEL.replace('{text}', shown)} onPress={() => onProfile()}
          style={{ color: c.cyanText, fontFamily: FONTS[700], textDecorationLine: 'underline' }}>{shown}</Text>
      )
    },
  }
  const source = onProfile ? text.replace(BARE, `$1[${LINK_TEXT}](${PATH})`) : text
  return <Markdown markdownit={parser} style={styles} rules={rules} mergeStyle>{source}</Markdown>
}

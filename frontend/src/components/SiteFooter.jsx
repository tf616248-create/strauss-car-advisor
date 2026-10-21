import cfg from '../config/accessibility.json'

// "הצהרת נגישות" at the bottom of every screen (the intro, the chat, the rep screen). A plain link:
// reachable from the keyboard, and it opens the statement page (/accessibility).
export default function SiteFooter({ className = '' }) {
  return (
    <footer className={`site-footer ${className}`.trim()}>
      <a href="/accessibility">{cfg.link}</a>
    </footer>
  )
}

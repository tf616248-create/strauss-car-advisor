// The comparison panel before the first comparison: why a car changes the salary,
// how it works, and a grey preview (skeleton) of the card. No numbers: the audience is new to this.
const STEPS = [
  'מספרים לכובי בקצרה על השכר והרכב שלכם',
  'בוחרים מה לבדוק',
  'מקבלים כאן השוואה: היום מול החלופה, וכמה יישאר לכם בכל חודש',
]
const GHOST_ROWS = 5

export default function EmptyPanel() {
  return (
    <div className="intro">
      <h2 className="intro__title">למה רכב משנה את המשכורת?</h2>
      <p className="intro__text">
        כשהחברה נותנת לכם רכב, המדינה רואה בו חלק מהשכר שלכם. הסכום הזה נקרא "שווי שימוש",
        ומשלמים עליו מס, גם בלי לקבל אותו בכסף. לכל רכב יש שווי שימוש אחר, ולכן כל החלפה משנה כמה יישאר לכם בנטו.
      </p>
      <h2 className="intro__title">איך זה עובד?</h2>
      <ol className="intro__steps">
        {STEPS.map((s) => <li key={s}>{s}</li>)}
      </ol>
      {/* the shape of the comparison, in grey: today vs the alternative, rows, and the net at the bottom */}
      <div className="ghost-card" aria-hidden="true">
        <div className="ghost-card__bar ghost-card__bar--title" />
        <div className="ghost-card__row ghost-card__row--head">
          <span className="ghost-card__bar" /><span className="ghost-card__bar" /><span className="ghost-card__bar" />
        </div>
        {Array.from({ length: GHOST_ROWS }, (_, i) => (
          <div key={i} className="ghost-card__row">
            <span className="ghost-card__bar" /><span className="ghost-card__bar" /><span className="ghost-card__bar" />
          </div>
        ))}
        <div className="ghost-card__row ghost-card__row--net">
          <span className="ghost-card__bar" /><span className="ghost-card__bar" /><span className="ghost-card__bar" />
        </div>
      </div>
    </div>
  )
}

// The comparison panel before the first comparison: why a car changes the salary,
// and how it works. No numbers: the audience is new to this.
const STEPS = [
  'מספרים לכובי בקצרה על השכר והרכב שלכם',
  'בוחרים מה לבדוק',
  'מקבלים כאן השוואה: היום מול החלופה, וכמה יישאר לכם בכל חודש',
]

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
    </div>
  )
}

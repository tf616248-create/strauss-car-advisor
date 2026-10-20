// The comparison tab before the first comparison: why a car changes the salary,
// and how it works. No numbers: the audience is new to this.
import { View } from 'react-native'
import { useColors } from '../theme'
import { T } from './ui'

const STEPS = [
  'מספרים לכובי בקצרה על השכר והרכב שלכם',
  'בוחרים מה לבדוק',
  'מקבלים כאן השוואה: היום מול החלופה, וכמה יישאר לכם בכל חודש',
]

export default function EmptyPanel() {
  const c = useColors()
  return (
    <View style={{ gap: 10 }}>
      <T weight={800} size={17}>למה רכב משנה את המשכורת?</T>
      <T muted>
        כשהחברה נותנת לכם רכב, המדינה רואה בו חלק מהשכר שלכם. הסכום הזה נקרא "שווי שימוש",
        ומשלמים עליו מס, גם בלי לקבל אותו בכסף. לכל רכב יש שווי שימוש אחר, ולכן כל החלפה משנה כמה יישאר לכם בנטו.
      </T>
      <T weight={800} size={17} style={{ marginTop: 8 }}>איך זה עובד?</T>
      {STEPS.map((s, i) => (
        <View key={s} style={{ flexDirection: 'row', gap: 8 }}>
          <T weight={800} color={c.cyanText}>{`${i + 1}.`}</T>
          <T style={{ flex: 1 }}>{s}</T>
        </View>
      ))}
    </View>
  )
}

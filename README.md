# יועץ הרכב של שטראוס

בוט בעברית שעונה לעובד תוך דקה: מה יקרה לנטו שלי אם אעבור לרכב חשמלי, לרכב אחר, למסלול ברוכת ילדים, או אוותר על הרכב?

הבוט משווה ולא ממליץ. כל מספר מחושב בקוד, אף פעם לא במודל השפה. מידע חסר נשאל מהעובד, ומידע של החברה עובר לנציג התחבורה.

> האקתון AI קוד פתוח 2026.

## שימוש

לא צריך להתקין כלום. פותחים את האתר בדפדפן, במחשב או בטלפון:

- **עובד:** https://strauss-car-advisor-y1x6.onrender.com – מקלידים קוד כניסה, וכותבים לכובי.
- **נציג התחבורה:** https://strauss-car-advisor-y1x6.onrender.com/rep – סיסמת הנציג.

קודי הכניסה והסיסמה נמסרים בנפרד, ולא נשמרים בגיט. אחרי זמן בלי שימוש השרת החינמי נרדם, ולכן התשובה הראשונה עשויה לקחת כחצי דקה.

## נגישות

האתר נבדק והותאם ככל הניתן לפי WCAG 2.1 ברמה AA (ת"י 5568). הצהרת הנגישות נמצאת ב-[/accessibility](https://strauss-car-advisor-y1x6.onrender.com/accessibility).

- **בכל הרצה של הבדיקות:** `axe-core` בודק כל מסך ברוחב 375 וברוחב 1280 (`frontend/tests/a11y.test.jsx`). כל ממצא, בכל רמה, מכשיל את הבדיקה. הניגודיות נבדקת במצב בהיר ובמצב כהה.
- **Lighthouse ב-Chrome, 21/10/2026:**

  | מסך | תוצאת Accessibility |
  |---|---|
  | מסך הפתיחה | 100 |
  | הצ'אט | 25/25 בדיקות עברו (מצב Snapshot) |

  <img src="docs/images/lighthouse-intro.png" alt="Lighthouse, מסך הפתיחה: Accessibility 100" width="120">

- **מה זה לא אומר:** בדיקה אוטומטית מוצאת רק חלק מבעיות הנגישות, כמו ש-Lighthouse עצמו כותב. היא לא מבטיחה שהאתר נגיש. קורא מסך אמיתי לא נבדק בכל המכשירים. בכרטיסי ההשוואה הקריאה בקורא מסך ארוכה, ולסרטון הפתיחה (בלי דיבור) אין כתוביות. אפליקציית הטלפון (`phonefrontend/`) לא נבדקה.

## הפעלה מקומית מאפס (למפתחים)

**מה צריך:** git, Python 3.12, Node 22 (נבדק עם 22.19), ומפתח למודל אחד לפחות (Gemini, Groq או OpenRouter). הבדיקות לא צריכות מפתח.

הפקודות כתובות ל-Git Bash ב-Windows. ב-Linux וב-Mac מחליפים `.venv/Scripts/python` ב-`.venv/bin/python`.

### 1. השרת (backend)

```bash
git clone <כתובת הריפו> strauss-car-advisor
cd strauss-car-advisor/backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env
```

ממלאים ב-`backend/.env` את הערכים האלה. הרשימה המלאה, עם הסבר לכל משתנה, ב-`.env.example`:

| משתנה | למה | דוגמה |
|---|---|---|
| `GOOGLE_API_KEY` | מודל ראשי. בלי אף מפתח של מודל השרת לא עולה | מפתח מ-aistudio.google.com |
| `EMPLOYEE_CODES` | קודי הכניסה לעובדים. ריק: מסך העובד סגור (503) | `E01:1111,E02:2222` |
| `REP_PASSCODE` | הסיסמה למסך הנציג. ריק: מסך הנציג סגור | כל מחרוזת |
| `JWT_SECRET` | לא חובה מקומית. בלעדיו כל הכניסות נגמרות כשהשרת עולה מחדש | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `DATABASE_URL` | לא חובה. ריק: הכול בזיכרון, ונמחק כשהשרת עולה מחדש | כתובת מ-Neon |

מפעילים:

```bash
.venv/Scripts/python -m uvicorn app.api.server:app --reload --port 8000
```

- **בדיקה שהשרת עלה:** `http://localhost:8000/health` מחזיר 200.
- **בעלייה:** קובץ רשות המסים נטען לזיכרון, וזה לוקח שנייה. המפרט של הרכבים נטען מהאינטרנט ברקע, ובלי רשת נטען מהגיבוי שבגיט (`backend/cache/specs-snapshot.json`).

### 2. הממשק (frontend)

בחלון נוסף:

```bash
cd strauss-car-advisor/frontend
npm ci
cp .env.example .env
npm run dev
```

- **`VITE_API_URL`:** כתובת השרת. ריק בפיתוח פירושו `http://localhost:8000`. ב-build לפרודקשן (Render) חובה למלא אותו, אחרת הממשק לא מוצא את השרת.
- **הכתובות:** עובד ב-`http://localhost:5173` (מקלידים קוד מ-`EMPLOYEE_CODES`), נציג ב-`http://localhost:5173/rep` (`REP_PASSCODE`).
- **בדיקת הזרימה עם נציג:** שואלים כעובד על הסדר השתתפות אישי ("יש לי הסדר השתתפות אישי ל-EV3"). השאלה מופיעה בתור הנציג. עונים בלשונית אחרת, והכרטיס אצל העובד מתעדכן בלי לרענן.

### 3. בדיקות

```bash
cd backend && .venv/Scripts/python -m pytest -q     # השרת, בלי מפתחות: המודל מזויף
cd frontend && npm test                             # הממשק (vitest)
cd frontend && npm run build                        # בנייה לפרודקשן
cd phonefrontend && npm install && npm test         # אפליקציית הטלפון (jest)
```

- **מספרי הייחוס** נקראים מגיליון "חישובים" ב-`backend/data/strauss-data.xlsx`, ולא כתובים בקוד.
- **אבלואציות מול המודל האמיתי** (`backend/evals/`) עולות כסף ולכן לא חלק מ-pytest: `.venv/Scripts/python -m evals.run_off_topic main_flow`. התוצאות נכתבות ל-`backend/evals/results/`.
- **בדיקות מול האתרים החיצוניים** (קישורי היבואנים ו-EEA): `pytest -m network`. לא רצות בהרצה הרגילה.

### 4. שיחה בקונסול (בלי ממשק)

```bash
cd backend
.venv/Scripts/python -m app.agent.chat
```

כותבים בתור העובד. פקודות הנציג:

| פקודה | מה היא עושה |
|---|---|
| `/rep` | מציגה שאלות פתוחות לנציג |
| `/rep 1 carGroup=ב companyCost=3500 participation=250` | עונה על שאלה 1, והבוט מחשב מחדש |
| `/card` | מציגה את כרטיס ההשוואה האחרון |
| `/exit` | יציאה |

### 5. אפליקציית הטלפון ופריסה לאוויר

- **טלפון:** [phonefrontend/README.md](phonefrontend/README.md).
- **Render ו-Neon:** [docs/deploy.md](docs/deploy.md).

## סיכום: מה עובד, מגבלות, מה נדרש לפיילוט

[docs/summary.md](docs/summary.md)

## החלטות ארכיטקטורה

שרטוטים של השכבות, של המסלול של שאלה ושל מסלול הנציג: [docs/architecture.md](docs/architecture.md)

### מסד נתונים: Neon, ועדכונים ב-SSE מהשרת
- **הצורך:** כשהנציג עונה, החלופה מתעדכנת אצל העובד מיד, בלי לרענן את הדף.
- **Neon:** Postgres נקי (`DATABASE_URL`). בלי `DATABASE_URL` הכול בזיכרון, לפיתוח ולבדיקות.
- **זמן אמת:** זרם SSE מהשרת שלנו (`GET /conversations/{id}/events`). המסד הוא מקור האמת, וה-SSE רק מצלצל: תשובת הנציג נשמרת קודם, ואז יוצא אירוע `changed` בלי נתונים, והדפדפן קורא את המצב מהשרת. הדפדפן קורא את המצב גם בטעינה, בחזרה ללשונית ואחרי חיבור מחדש.
- **תהליך אחד:** רשימת המחוברים נשמרת בזיכרון של התהליך, ולכן השרת רץ עם `--workers 1` (`render.yaml`).
- **`/health` לא פונה למסד:** UptimeRobot מעיר רק את Render. Neon מתעורר לבד, ופנייה קבועה הייתה מונעת ממנו להיכבות ושורפת את מכסת החינם.
- **מתי נשנה:** יותר מתהליך אחד דורש מנגנון משותף (למשל LISTEN/NOTIFY), ו-Neon בתשלום.

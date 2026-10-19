# העלאה לאוויר

שלושה שירותים: **Neon** (מסד נתונים), **Render** (השרת, `render.yaml`), **Netlify** (הממשק, `frontend/`, לפי `netlify.toml`). הממשק הוא אתר סטטי, ולכן הוא עולה לבד ולא נרדם.
סודות לא נכנסים ל-Git. ממלאים אותם רק באתרים עצמם.

## הסדר

כל שירות צריך את הכתובת של השירות הקודם, ולכן הסדר חשוב:

1. **Neon** (כבר קיים): מעתיקים את כתובת ה-pooler (עם `-pooler` בשם השרת).
2. **Render** קודם, כדי לקבל את כתובת השרת. בשלב הזה `FRONTEND_ORIGIN` נשאר ריק.
3. **Netlify**, עם כתובת השרת מ-Render. מקבלים את כתובת הממשק.
4. **חזרה ל-Render:** ממלאים את `FRONTEND_ORIGIN` בכתובת מ-Netlify, ו-Render מעלה את השרת מחדש.
5. **UptimeRobot:** בודק כל 10 דקות את `https://<השרת>/health`, כדי ש-Render לא יירדם. הנתיב הזה לא פונה למסד, ולכן Neon נכבה ומתעורר לבד.

## Render (השרת)

New → **Blueprint** → בוחרים את הריפו. Render קורא את `render.yaml`: אזור frankfurt, תוכנית free, `rootDir=backend`, ותהליך אחד (`--workers 1`, בגלל SSE). אחר כך הוא מבקש למלא את המשתנים:

| משתנה | מה ממלאים | חובה |
|---|---|---|
| `DATABASE_URL` | כתובת ה-pooler מ-Neon | כן |
| `GEMINI_API_KEY` | מפתח Gemini | כן (או לפחות אחד ממפתחות המודל) |
| `GROQ_API_KEY` | מפתח Groq, גיבוי | לא |
| `OPENROUTER_API_KEY` | מפתח OpenRouter, גיבוי | לא |
| `FRONTEND_ORIGIN` | כתובת הממשק מ-Netlify, למשל `https://strauss-car-advisor.netlify.app` (בלי `/` בסוף) | כן, אחרי שלב 3 |
| `REP_PASSCODE` | סיסמה למסך הנציג. ריק = מסך הנציג סגור | כן, להדגמה |
| `EMPLOYEE_CODES` | קודי כניסה לעובדים: `E01:1111,E02:2222,...`. ריק = מסך העובד סגור | כן |
| `JWT_SECRET` | מחרוזת אקראית ארוכה: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. בלעדיה כל עובד מתנתק כש-Render נרדם | כן |

- `PYTHON_VERSION` (3.12.4) כבר מוגדר ב-`render.yaml`.
- אפשר להוסיף ידנית `GOOGLE_API_KEY_2` ו-`GOOGLE_API_KEY_3`: מפתחות Gemini נוספים, שננסים לפי הסדר.
- בעליית השרת נוצרות הטבלאות, ו-PostgresSaver מכין את הטבלאות שלו. שתי הפעולות בטוחות להרצה בכל הפעלה מחדש.
- **בדיקה:** `https://<השרת>/health` מחזיר `{"status":"ok"}`.

## Netlify (הממשק)

Add new site → Import an existing project → הריפו. Netlify קורא את `netlify.toml` שבשורש, ולא צריך למלא הגדרות בנייה: `base = frontend`, `command = npm run build`, `publish = dist`. כלל ההפניה שולח כל נתיב (גם `/rep`) ל-`index.html`.

את המשתנים ממלאים ב-Site configuration → Environment variables:

| משתנה | מה ממלאים | חובה |
|---|---|---|
| `VITE_API_URL` | כתובת השרת מ-Render, למשל `https://strauss-car-advisor-api.onrender.com` | כן. בלעדיו הממשק לא יודע לאן לפנות |
| `VITE_SUPPORT_EMAIL` | מייל לכפתור "שיחה עם נציג". ריק = `support@strauss-in.com` | לא |

- משתני `VITE_` נכנסים לממשק בזמן הבנייה. אחרי שינוי משתנה צריך לבנות מחדש (Deploys → Trigger deploy).
- **בדיקה:** פותחים את הכתובת, שולחים הודעה, ובודקים שהתשובה זורמת. אם מופיעה "אין חיבור לשרת", בודקים את `VITE_API_URL` ואת `FRONTEND_ORIGIN`.

## אחרי ההעלאה

- הבקשה הראשונה אחרי שינה של Render לוקחת בערך דקה.
- לבדוק את הזרימה של רחל עם הנציג: לשאול על Atto 2 בלשונית אחת, ובלשונית אחרת להיכנס ל-`/rep` עם הסיסמה ולענות. בלשונית של העובד צריך להישמע צפצוף, ולהופיע חישוב מחדש.

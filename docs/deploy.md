# העלאה לאוויר

שלושה שירותים: **Neon** (מסד נתונים), **Render** (השרת, `render.yaml`), **Render Static Site** (הממשק, `frontend/`). הממשק הוא אתר סטטי, ולכן הוא עולה בנפרד מהשרת ולא נרדם.
סודות לא נכנסים ל-Git. ממלאים אותם רק באתרים עצמם.

## הסדר

כל שירות צריך את הכתובת של השירות הקודם, ולכן הסדר חשוב:

1. **Neon** (כבר קיים): מעתיקים את כתובת ה-pooler (עם `-pooler` בשם השרת).
2. **Render** קודם, כדי לקבל את כתובת השרת. בשלב הזה `FRONTEND_ORIGIN` נשאר ריק.
3. **Render Static Site** (הממשק), עם כתובת השרת. מקבלים את כתובת הממשק.
4. **חזרה ל-Render:** ממלאים את `FRONTEND_ORIGIN` בכתובת של הממשק, ו-Render מעלה את השרת מחדש.
5. **UptimeRobot:** בודק כל 10 דקות את `https://<השרת>/health`, כדי ש-Render לא יירדם. הנתיב הזה לא פונה למסד, ולכן Neon נכבה ומתעורר לבד.

## Render (השרת)

New → **Blueprint** → בוחרים את הריפו. Render קורא את `render.yaml`: אזור frankfurt, תוכנית free, `rootDir=backend`, ותהליך אחד (`--workers 1`, בגלל SSE). אחר כך הוא מבקש למלא את המשתנים:

| משתנה | מה ממלאים | חובה |
|---|---|---|
| `DATABASE_URL` | כתובת ה-pooler מ-Neon | כן |
| `GEMINI_API_KEY` | מפתח Gemini | כן (או לפחות אחד ממפתחות המודל) |
| `GROQ_API_KEY` | מפתח Groq, גיבוי | לא |
| `OPENROUTER_API_KEY` | מפתח OpenRouter, גיבוי | לא |
| `FRONTEND_ORIGIN` | כתובת הממשק (ה-Static Site ב-Render), בצורה `https://<הממשק>.onrender.com` (בלי `/` בסוף) | כן, אחרי שלב 3 |
| `REP_PASSCODE` | סיסמה למסך הנציג. ריק = מסך הנציג סגור | כן, להדגמה |
| `EMPLOYEE_CODES` | קודי כניסה לעובדים: `E01:1111,E02:2222,...`. ריק = מסך העובד סגור | כן |
| `JWT_SECRET` | מחרוזת אקראית ארוכה: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. בלעדיה כל עובד מתנתק כש-Render נרדם | כן |

- `PYTHON_VERSION` (3.12.4) כבר מוגדר ב-`render.yaml`.
- אפשר להוסיף ידנית `GOOGLE_API_KEY_2` ו-`GOOGLE_API_KEY_3`: מפתחות Gemini נוספים, שננסים לפי הסדר.
- בעליית השרת נוצרות הטבלאות, ו-PostgresSaver מכין את הטבלאות שלו. שתי הפעולות בטוחות להרצה בכל הפעלה מחדש.
- **בדיקה:** `https://<השרת>/health` מחזיר `{"status":"ok"}`.

### מעקב ב-LangSmith (לא חובה)

בלי המשתנים האלה המעקב כבוי, לא נשלח שום דבר, והשרת עובד כרגיל.

| משתנה | מה ממלאים |
|---|---|
| `LANGSMITH_TRACING` | `true` |
| `LANGSMITH_API_KEY` | מפתח מ-smith.langchain.com, תחת Settings ← API Keys |
| `LANGSMITH_PROJECT` | שם הפרויקט, למשל `kobi-render`. ריק = `default` |

**איך מוסיפים:**
1. ב-Render: השירות ← **Environment** ← **Add Environment Variable**.
2. מוסיפים את שלושת המשתנים.
3. **Save Changes**. השרת עולה מחדש.

- **בדיקה:** ביומן השרת מופיעה השורה `LangSmith: tracing on (project ...)`.
- `true` בלי מפתח נשאר כבוי, וביומן יש אזהרה.
- **כיבוי:** מוחקים את `LANGSMITH_TRACING` או משנים אותו ל-`false`.

**מה רואים בכל trace:**
- **מזהה השיחה:** `thread_id`. ב-LangSmith, תחת Threads, השאלות של שיחה אחת מופיעות יחד.
- **בכל קריאה למודל:**
  - `kobi_model`: איזה מפתח או מודל ענה.
  - `ls_model_name`: שם המודל.
  - `kobi_fallback`: האם זה מודל גיבוי. לגיבוי יש גם תגית `fallback`, ולכן אפשר לסנן לפיה.
- **הרצה מאבלואציה:** תגית `eval`, ו-`eval_set` ו-`eval_case` במטא-דאטה.

> **שימו לב:** ה-trace שומר את כל השיחה, כולל נתוני השכר שהעובד הקליד, בשרת של LangSmith. להפעיל רק עם נתוני דמה.

## Render Static Site (הממשק)

New → **Static Site** → הריפו. ההגדרות לא בקובץ (`render.yaml` מגדיר רק את השרת), וממלאים אותן באתר:

| הגדרה | ערך |
|---|---|
| Root Directory | `frontend` |
| Build Command | `npm install && npm run build` |
| Publish Directory | `dist` |
| Redirects/Rewrites | Source `/*`, Destination `/index.html`, Action **Rewrite**. כך כל נתיב (`/rep`, `/profile`, `/accessibility`) מקבל את `index.html`, כי זו אפליקציית עמוד יחיד |

את המשתנים ממלאים ב-**Environment**:

| משתנה | מה ממלאים | חובה |
|---|---|---|
| `VITE_API_URL` | כתובת השרת מ-Render, למשל `https://strauss-car-advisor-api.onrender.com` | כן. בלעדיו הממשק לא יודע לאן לפנות |
| `VITE_SUPPORT_EMAIL` | מייל לכפתור "שיחה עם נציג". ריק = `support@strauss-in.com` | לא |

- משתני `VITE_` נכנסים לממשק בזמן הבנייה. אחרי שינוי משתנה צריך לבנות מחדש (Manual Deploy → Deploy latest commit).
- **בדיקה:** פותחים את הכתובת, שולחים הודעה, ובודקים שהתשובה זורמת. אם מופיעה "אין חיבור לשרת", בודקים את `VITE_API_URL` ואת `FRONTEND_ORIGIN`.

## אחרי ההעלאה

- הבקשה הראשונה אחרי שינה של Render לוקחת בערך דקה.
- לבדוק את הזרימה של רחל עם הנציג: לשאול על Atto 2 בלשונית אחת, ובלשונית אחרת להיכנס ל-`/rep` עם הסיסמה ולענות. בלשונית של העובד צריך להישמע צפצוף, ולהופיע חישוב מחדש.

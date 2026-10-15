# ארכיטקטורה

שלוש דיאגרמות: השכבות, המסלול של שאלה, ומסלול הנציג. הן מתארות את הקוד כמו שהוא היום.
ההחלטות וההקשר: [CLAUDE.md](../CLAUDE.md).

## 1. שכבות

```mermaid
flowchart TB
    subgraph FE["ממשק: React על Vercel (frontend/)"]
        EMP["מסך העובד /<br/>צ'אט + כרטיס השוואה"]
        REP["מסך הנציג /rep<br/>תור שאלות + טופס תשובה"]
    end

    subgraph BE["שרת: FastAPI על Render (backend/app/), תהליך אחד"]
        API_E["api/employee.py<br/>צ'אט, מצב שיחה, אירועי SSE"]
        API_R["api/rep.py<br/>הכול מאחורי סיסמה"]
        AGENT["איג'נט LangGraph (agent/graph.py)<br/>create_react_agent + פרומפט"]
        TOOLS["4 כלים (agent/advisor.py)<br/>lookup_vehicle · check_eligibility<br/>calculate · ask_rep"]
        EVENTS["api/events.py<br/>publish / subscribe בזיכרון"]
    end

    LLM["מודלי שפה (agent/models.py)<br/>Gemini → Groq → OpenRouter"]

    subgraph ENG["מנוע חישוב Python (backend/app/engine/)"]
        NET["net.py: מס, ביטוח לאומי, פנסיה, נטו"]
        SCEN["scenario.py: זכאות ובניית החלופה"]
    end

    subgraph DATA["backend/data/ (קריאה בלבד)"]
        RULES[("strauss-rules.json")]
        XLSX[("strauss-data.xlsx")]
        CSV[("vehicle-values-2026.csv")]
    end

    DB[("Neon Postgres<br/>שיחות (PostgresSaver) + rep_requests")]

    EMP -- "POST /chat (SSE)" --> API_E
    EMP -. "EventSource: changed" .-> API_E
    REP -- "X-Rep-Passcode" --> API_R
    API_E --> AGENT
    AGENT <--> LLM
    AGENT --> TOOLS
    TOOLS --> SCEN
    TOOLS --> NET
    SCEN --> NET
    TOOLS --> DB
    API_R --> DB
    API_R --> EVENTS
    EVENTS -.-> API_E
    AGENT -- "checkpoint" --> DB
    DATA -- "נטען פעם אחת בעליית השרת (data/loader.py)" --> TOOLS
```

| שכבה | מה היא עושה | מה היא לא עושה |
|---|---|---|
| ממשק (React) | מציג את השיחה ואת הכרטיס, ומעצב מספרים לתצוגה | לא מחשב. ההפרשים מגיעים מוכנים מהשרת |
| איג'נט + מודל שפה | מחליט מה לשאול ואיזה כלי להפעיל, ומנסח בעברית | לא מחשב ולא כותב למסד. כל מספר מועתק מתוצאת כלי, וזה נאכף בפרומפט בלבד |
| כלים (`advisor.py`) | בודקים שהקלט שלם ותקין, מחזירים "חסר" או "צריך נציג" במקום לנחש, ושומרים שאלות לנציג | לא מנסחים טקסט לעובד, ולא קוראים למודל |
| מנוע חישוב | חישוב טהור של זכאות ונטו, לפי הכללים מהקובץ | לא יודע על מודל, שיחה או מסד |
| נתונים | כללים, קטלוג, עיסוקים, שווי שימוש | קריאה בלבד. הקוד לא משנה אותם |
| Neon | שומר את השיחות ואת תור הנציג, ומשמש מקור האמת | לא נבדק ב-`/health`, כדי ש-Neon יוכל להיכבות |

השרת רץ בתהליך אחד, כי רשימת הדפדפנים שמחוברים ל-SSE נשמרת בזיכרון של התהליך.
קבצי הנתונים נטענים לזיכרון פעם אחת בעליית השרת. אם הכללים לא תואמים לקטלוג, השרת לא עולה.

## 2. המסלול של שאלה

```mermaid
sequenceDiagram
    autonumber
    actor W as עובד
    participant UI as מסך העובד
    participant API as api/employee.py
    participant AG as איג'נט + מודל שפה
    participant T as כלים (advisor.py)
    participant E as מנוע חישוב

    W->>UI: "אם אעבור ל-BYD Atto 3, מה יקרה לנטו?"
    UI->>API: POST /chat
    API->>AG: הודעת העובד + היסטוריית השיחה

    loop עד שיש את כל הנתונים
        AG->>T: check_eligibility / calculate עם מה שידוע
        alt חסר שדה
            T-->>AG: status=missing, fields
            AG-->>UI: שאלה לעובד (token)
            W->>UI: תשובה
            UI->>API: POST /chat
        else ערך לא תקין, פעם ראשונה
            T-->>AG: status=invalid
            AG-->>UI: שואל שוב את העובד
        else ערך לא תקין או רכב לא זוהה, פעם שנייה
            T-->>AG: status=needs_rep
            AG->>T: ask_rep (ראו דיאגרמה 3)
        end
    end

    AG->>T: lookup_vehicle (שווי שימוש מהקטלוג או מרשות המסים)
    T-->>AG: הרכב + שווי שימוש + מקור
    AG->>T: check_eligibility
    T->>E: build_scenario
    E-->>T: זכאי / לא זכאי + סיבה
    AG->>T: calculate
    T->>E: build_scenario + compute_net (היום מול החלופה)
    E-->>T: נטו, רכיבים, הפרשים
    T-->>AG: status=ok + כרטיס השוואה
    API-->>UI: אירוע card (הכרטיס, בצד שמאל)
    AG-->>UI: הסבר בשפה חופשית (token אחר token)
    API-->>UI: done
```

המודל מחליט על סדר הקריאות. הסדר שבדיאגרמה הוא הסדר הרגיל, לא סדר שהקוד אוכף. `calculate` מזהה את הרכב בעצמו, גם בלי קריאה קודמת ל-`lookup_vehicle`.
ניסיונות כושלים נספרים מתוך תוצאות הכלים הקודמות בשיחה, ולכן הכלים עצמם בלי מצב. הספירה חלה על ערך לא תקין ועל רכב שלא זוהה. שדה שפשוט חסר נשאל שוב ושוב, ולא עובר לנציג.
כשכל מודלי השפה נכשלים, השרת שולח אירוע `error` עם "המערכת עמוסה". מה שכבר נכתב לעובד נשאר על המסך.

## 3. מסלול הנציג

```mermaid
sequenceDiagram
    autonumber
    participant AG as איג'נט
    participant T as כלים (advisor.py)
    participant DB as Neon
    actor R as נציג
    participant RUI as מסך הנציג
    participant RAPI as api/rep.py
    participant N as Notifier (events.py)
    participant UI as מסך העובד
    participant API as api/employee.py

    AG->>T: ask_rep(fields, question)
    T->>DB: INSERT rep_requests
    AG-->>UI: "שלחתי שאלה לנציג התחבורה, והחלופה תתעדכן"
    Note over UI: השדה מסומן "⏳ ממתין לנציג"

    loop כל 5 שניות
        RUI->>RAPI: GET /rep/requests
        RAPI->>DB: שאלות פתוחות
        RAPI-->>RUI: שאלות + כרטיס העובד
    end
    R->>RUI: ממלא תשובה
    RUI->>RAPI: POST /rep/requests/{id}/answer
    RAPI->>DB: UPDATE answer
    alt השמירה נכשלה
        RAPI-->>RUI: 503, ואין צלצול
    else נשמר
        RAPI->>N: publish(conversation_id)
        RAPI-->>RUI: 200
    end

    alt העובד מחובר
        N-->>API: changed
        API-->>UI: SSE event: changed (בלי נתונים)
        UI->>UI: צפצוף + "(1)" בכותרת הלשונית
        UI->>API: GET /chat/{id}
    else העובד לא מחובר
        Note over UI,API: אין למי לצלצל. התשובה מחכה במסד
        UI->>API: חוזר לדף / ללשונית / חיבור מחדש של SSE ← GET /chat/{id}
    end

    API->>DB: מצב השיחה + new_answers
    API-->>UI: הודעות, כרטיסים, rep.new_answers=1
    UI->>API: POST /chat/{id}/rep-answered
    API->>DB: take_new_answers (מסמן delivered_at, פעם אחת בלבד)
    API->>AG: "[עדכון מהמערכת: הנציג ענה על השאלה]"
    AG->>T: calculate (עם תשובת הנציג, מקור: נציג)
    T-->>AG: כרטיס מעודכן
    API-->>UI: card + token + done
```

המסד הוא מקור האמת, וה-SSE רק מצלצל: האירוע `changed` לא נושא נתונים, והדפדפן קורא את המצב מהשרת. הצלצול מגיע רק לדפדפנים שמחוברים לאותה שיחה.
עובד שלא היה מחובר מקבל את התשובה כשהוא חוזר, כי הדף קורא את השיחה מהמסד בטעינה, בחזרה ללשונית ואחרי חיבור מחדש. במקרה הזה אין צפצוף.
הבוט מחשב מחדש פעם אחת לכל תשובת נציג (`delivered_at`), גם אם פתוחות שתי לשוניות. מסך הנציג עצמו לא משתמש ב-SSE: הוא בודק אם יש שאלות חדשות כל 5 שניות.

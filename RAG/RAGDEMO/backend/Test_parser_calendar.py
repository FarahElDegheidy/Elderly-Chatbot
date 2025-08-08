import asyncio
import os
from langchain_groq import ChatGroq # Not used in this snippet, but kept for context
from groq import Groq
from datetime import datetime, timedelta
import json 

async def user_intent_calendar_parser(user_input: str) -> dict:
    client = Groq(api_key= os.getenv("GROQ_API_KEY"))

    # Your system_prompt definition remains the same (it's well-structured!)
    system_prompt = """
📌 فهم المهمة:
أنت مساعد متخصص في فهم رسائل المستخدم المتعلقة بتقويم جوجل. هدفك هو:
1. تحديد نية المستخدم بدقة: هل يريد عرض أحداث، أم إنشاء حدث جديد، أم تعديل، أو حذف حدث؟
2. استخراج التفاصيل الضرورية لتنفيذ الطلب.

📌 صيغة الإخراج المطلوبة:
أعد الإخراج كـ JSON فقط، بدون أي شرح، ويحتوي على:
- "action": أحد القيم التالية:
    - "list_events"
    - "create_event"
    - "edit_event"
    - "delete_event"
    - "unknown_calendar_intent"
- "details": كائن يحتوي على تفاصيل إضافية بناءً على نوع الإجراء. 

📌 الحقول المطلوبة لكل نوع:

1️⃣ إذا كان action = "list_events":
- "time_frame": (اختياري)
    - "today"
    - "tomorrow"
    - "this week"
    - "next week"
    - "this month"
    - "next month"
- "max_results": (اختياري) عدد النتائج المطلوبة، افتراضيًا 10.

2️⃣ إذا كان action = "create_event":
- "summary": (مطلوب) عنوان الحدث.
- "start_time": (مطلوب) بصيغة ISO 8601 (YYYY-MM-DDTHH:MM:SS+03:00).
- "end_time": (مطلوب) بصيغة ISO 8601.
- "description": (اختياري)
- "location": (اختياري)

3️⃣ إذا كان action = "edit_event": 
- "summary": (مطلوب) معرّف الحدث أو وصفه بشكل يمكن التعرف عليه.
- "updates": كائن يحتوي على أي من الحقول التالية لتحديثها:
    - "summary"
    - "start_time"
    - "end_time"
    - "description"
    - "location"

4️⃣ إذا كان action = "delete_event": 🆕
- "summary": (مطلوب) معرّف الحدث أو وصفه بشكل يمكن التعرف عليه.
امثلة:

🟢امسح معادي مع دكتور القلب
```json
{{ 
    "action": "delete_event",
    "summary": {{
        "دكتور القلب"
    }}
}}

-------
📌 تلميحات لاستخراج المعلومات:
- افترض أن وقت البدء هو 9:00 صباحًا إذا لم يُذكر.
- اجعل مدة الحدث ساعة واحدة إذا لم يُذكر خلاف ذلك.
- استخرج التواريخ النسبية مثل: "بكرة"، "الأسبوع الجاي"، "الجمعة الجاية".
- حوّلها إلى تنسيق ISO 8601 باستخدام المنطقة الزمنية: +03:00 (القاهرة).

📌 معلومات حالية:
- التاريخ الحالي: {current_date}
- الوقت الحالي: {current_time}

📌 كلمات دالة على نية تتعلق بالتقويم:
"موعد"، "حدث"، "اجتماع"، "تذكير"، "تقويم"، "مواعيد"، "أحداث"، "الجدول"، "سجللي"، "احجزلي"، "اعرضلي"، "احذف"، "امسح"، "عدل"، "غيّر"، "تحديث"

📌 أمثلة:

🟢 مثال: "إيه اللي عندي النهاردة في الجدول؟"
```json
{{ 
    "action": "list_events",
    "details": {{
        "time_frame": "today",
        "max_results": 10
    }}
}}

:قاعدة أخيرة مهمة

لا تصنف الرسالة على أنها "unknown_calendar_intent" إلا إذا كانت غير مفهومة تمامًا أو لا تتعلق بالتقويم.

إذا كانت هناك أي إشارات زمنية أو نية واضحة، فاستخرج أفضل تخمين منطقي بناءً على المعطيات.

لا تشرح، لا تتفاعل، فقط أخرج الـ JSON النهائي.
"""

    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M:%S")

    # Calculate tomorrow's date
    tomorrow = now + timedelta(days=1)
    tomorrow_date = tomorrow.strftime("%Y-%m-%d")

    # Calculate next Monday's date
    # weekday() returns 0 for Monday, 6 for Sunday
    days_until_next_monday = (0 - now.weekday() + 7) % 7 
    # If today is Monday, and we want next Monday, add 7 days
    if days_until_next_monday == 0 and now.weekday() == 0:
        days_until_next_monday = 7
    next_monday_date = (now + timedelta(days=days_until_next_monday)).strftime("%Y-%m-%d")

    # --- IMPORTANT: Include calculated dates in the prompt formatting ---
    formatted_prompt = system_prompt.format(
        current_date=current_date,
        current_time=current_time,
        tomorrow_date=tomorrow_date,        # <--- ADDED
        next_monday_date=next_monday_date  # <--- ADDED
    )

    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-4-maverick-17b-128e-instruct",
            messages=[
                {"role": "system", "content": formatted_prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=0,
            response_format={"type": "json_object"} # Crucial for strict JSON output
        )

        content = response.choices[0].message.content.strip()
        print(f"\n🧠 Raw Groq Calendar Intent Response:\n{content}\n")

        return json.loads(content) # Use json.loads for safety and correctness

    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing error in calendar intent: {e}. Raw content was: {content}")
        return {
            "action": "unknown_calendar_intent",
            "details": {},
            "error": f"JSON parsing failed: {str(e)}"
        }
    except Exception as e:
        print(f"❌ General error in calendar intent parser: {e}")
        return {
            "action": "unknown_calendar_intent",
            "details": {},
            "error": str(e)
        }
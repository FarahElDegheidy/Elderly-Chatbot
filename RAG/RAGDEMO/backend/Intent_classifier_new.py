import os
import json
from groq import Groq, APIStatusError, APIConnectionError
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import asyncio
from langchain_groq import ChatGroq
from datetime import datetime, timedelta
import pytz
import calendar
from services.google_calendar_service import refresh_and_get_service
from services.google_calendar_service import list_upcoming_events, create_calendar_event
from Intent_prompts import ENHANCER_PROMPT_PROD, Video_Search_Prompt, Web_Search_Prompt, GET_CLEANED_QUERY_PROMPT, GOOGLE_CALENDAR_INTENT_PARSER_PROMPT


def classify_query_groq(query: str, chat_context: str = "", verbose: bool = False) -> str:
    """
    Classifies a query using LLaMA-4 via Groq API based on context.
    Returns raw output from Groq without validation.
    """
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    system_prompt = ENHANCER_PROMPT_PROD  # Swap with DEBUG if needed

    full_input = f"""سياق المحادثة السابق:
{chat_context}

رسالة المستخدم الحالية:
{query}"""

    if verbose or os.getenv("VERBOSE_LOGS") == "true":
        print("\n[Intent Classifier Input]\n", full_input)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": full_input},
    ]

    try:
        chat_completion = client.chat.completions.create(
            messages=messages,
            model="meta-llama/llama-4-maverick-17b-128e-instruct",
            temperature=0.0,
        )
        result = chat_completion.choices[0].message.content.strip()
        return result

    except APIStatusError as e:
        if e.status_code == 413:
            return "⚠️ input too long"
        elif e.status_code == 429:
            raise APIStatusError("Rate limit hit", status_code=429)
        else:
            print(f"🔥 Unhandled Groq Error: {e}")
            raise

    except APIConnectionError as e:
        print(f"🌐 APIConnectionError: {e}")
        raise

def extract_video_search(user_input: str, selected_title: str = "") -> str:
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    system_prompt = Video_Search_Prompt

    if selected_title:
        system_prompt += f"""

الوصفة المؤكدة المطلوب البحث عنها هي:
"{selected_title}"
"""

    prompt = f"رسالة المستخدم: {user_input}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]

    response = client.chat.completions.create(
        messages=messages,
        model="meta-llama/llama-4-maverick-17b-128e-instruct",
        temperature=0.0,
    )

    return response.choices[0].message.content.strip()


def get_chat_context_string(chat_context, n_turns: int = 3) -> str:

    """
    Returns the last n_turns of conversation as a string, to give relevant context.
    """
    if hasattr(chat_context, "load_memory_variables"):
        try:
            history = chat_context.load_memory_variables({}).get("chat_history", [])
            formatted = []
            # Only take the last n_turns (a turn = human + ai message)
            for msg in history[-n_turns*2:]:
                role = "User" if msg.type == "human" else "Bot"
                formatted.append(f"{role}: {msg.content}")
            return "\n".join(formatted)
        except Exception as e:
            print(f"⚠️ Failed to extract memory: {e}")
            return ""
    return str(chat_context)




def extract_web_search(user_input: str, chat_context: str = "", verbose: bool = False) -> str:
    """
    Extracts a Google-style web search query from the user's message.
    Optionally uses chat history for follow-up queries.
    """
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    system_prompt = Web_Search_Prompt

    prompt = f"""سياق المحادثة السابق:
{chat_context}

رسالة المستخدم:
{user_input}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]

    if verbose or os.getenv("VERBOSE_LOGS") == "true":
        print("\n[Web Search Extractor Input]\n", prompt)

    try:
        response = client.chat.completions.create(
            messages=messages,
            model="meta-llama/llama-4-maverick-17b-128e-instruct",
            temperature=0.0,
        )
        return response.choices[0].message.content.strip()

    except APIStatusError as e:
        print(f"🔥 Groq API Error: {e}")
        raise

    except APIConnectionError as e:
        print(f"🌐 Connection Error: {e}")
        raise

def format_web_results_for_memory(results):
    formatted = ""
    for i, item in enumerate(results, 1):
        title = item.get("title", "No title")
        link = item.get("link", "")
        formatted += f"{i}. {title}\n{link}\n\n"
    return formatted.strip()


def extract_cleaned_query_for_search(user_input: str, last_bot_response: str = "", query_classification: str = "", verbose: bool = False) -> dict:
    """
    Uses Groq LLM to extract whether a user is requesting a video/web search
    and returns cleaned search keywords if applicable.

    Returns:
        {
            "type": "video" | "web" | "none",
            "query": "search keywords or empty string"
        }
    """
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    # 🧠 Construct the user prompt from LLM's last response and user's follow-up
    full_input = f"""آخر رد من المساعد: {last_bot_response}
رسالة المستخدم: {user_input}"""

    if verbose or os.getenv("VERBOSE_LOGS") == "true":
        print("\n[Search Intent Extractor Input]\n", full_input)

    messages = [
        {"role": "system", "content": GET_CLEANED_QUERY_PROMPT},
        {"role": "user", "content": full_input}
    ]

    try:
        # Only invoke the LLM if the classification is eligible for possible search
        if query_classification in ["not food related", "food generalized", "respond based on chat history"]:
            response = client.chat.completions.create(
                messages=messages,
                model="meta-llama/llama-4-maverick-17b-128e-instruct",
                temperature=0.0,
            )
            print(f"🧾 LLM raw output for cleaned query:\n{response}\n")
            content = response.choices[0].message.content.strip()

            # Extract JSON payload from markdown block if present
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            else:
                json_str = content

            result = json.loads(json_str)

            if result.get("type") in ["video", "web", "none"] and "query" in result:
                return result
            else:
                return {"type": "none", "query": ""}
        else:
            # 🛑 Skip search detection for irrelevant categories like direct dish name
            return {"type": "none", "query": ""}

    except APIStatusError as e:
        print(f"🔥 Groq API Error: {e}")
        raise

    except APIConnectionError as e:
        print(f"🌐 Connection Error: {e}")
        raise

    except Exception as e:
        print(f"❌ Unexpected parsing error: {e}")
        return {"type": "none", "query": ""}


async def user_intent_calendar_parser(user_input: str, user_id: str, last_bot_response: str = ""):
    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        cairo_tz = pytz.timezone("Africa/Cairo")
        current_datetime_cairo = datetime.now(cairo_tz)

        # Format the prompt using your existing template
        formatted_prompt = GOOGLE_CALENDAR_INTENT_PARSER_PROMPT.format_messages(
            user_input=user_input,
            user_id=user_id,
            current_date=current_datetime_cairo.strftime("%Y-%m-%d"),
            current_time=current_datetime_cairo.strftime("%H:%M"),
            last_bot_response=last_bot_response or ""
        )

        # Convert LangChain messages to Groq-compatible role/content format
        messages = []
        for msg in formatted_prompt:
            if isinstance(msg, SystemMessage):
                role = "system"
            elif isinstance(msg, HumanMessage):
                role = "user"
            elif isinstance(msg, AIMessage):
                role = "assistant"
            else:
                role = "user"
            messages.append({
                "role": role,
                "content": msg.content
            })

        print("🔍 Prompt sent to LLM:")
        for m in messages:
            print(f"{m['role'].capitalize()}: {m['content']}")

        # Call Groq LLM
        response = client.chat.completions.create(
            model="meta-llama/llama-4-maverick-17b-128e-instruct",
            messages=messages,
            temperature=0.0,
        )

        raw_output = response.choices[0].message.content.strip()
        print(f"📅 Calendar LLM raw output:\n{raw_output}")

        # Extract JSON string from content
        if "```json" in raw_output:
            json_str = raw_output.split("```json")[1].split("```")[0].strip()
        else:
            json_str = raw_output

        # Parse the JSON
        try:
            calendar_tool_groq_response = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error: {e}")
            return "عذراً، لم أستطع فهم طلبك الخاص بالتقويم بدقة. هل يمكنك التوضيح أكثر؟"

        action = calendar_tool_groq_response.get("action")
        if not action:
            return "عذراً، لم أستطع تحديد الإجراء المطلوب للتقويم."

        # === LIST EVENTS ===
        if action == "list_events":
            time_range = calendar_tool_groq_response.get("time_frame", "upcoming")
            max_results = calendar_tool_groq_response.get("max_results", 10)
            events_message = ""

            service = await refresh_and_get_service(user_id)
            if not service:
                return "تقويم جوجل غير متصل. يرجى توصيله أولاً."

            start_time = current_datetime_cairo
            end_time = None

            if time_range == "today":
                start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
                end_time = start_time.replace(hour=23, minute=59, second=59, microsecond=999999)
                events_message = "مواعيدك لليوم:"
            elif time_range == "tomorrow":
                start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                end_time = start_time.replace(hour=23, minute=59, second=59, microsecond=999999)
                events_message = "مواعيدك لبكرة:"
            elif time_range == "this week":
                end_time = start_time + timedelta(days=7)
                events_message = "مواعيدك لهذا الأسبوع:"
            elif time_range == "next week":
                start_time = start_time + timedelta(days=7)
                end_time = start_time + timedelta(days=7)
                events_message = "مواعيدك للأسبوع القادم:"
            elif time_range == "this month":
                _, last_day = calendar.monthrange(start_time.year, start_time.month)
                end_time = start_time.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
                events_message = "مواعيدك لهذا الشهر:"
            elif time_range == "next month":
                next_month_start = (start_time.replace(day=1) + timedelta(days=32)).replace(day=1)
                _, last_day_next_month = calendar.monthrange(next_month_start.year, next_month_start.month)
                start_time = next_month_start
                end_time = next_month_start.replace(day=last_day_next_month, hour=23, minute=59, second=59, microsecond=999999)
                events_message = "مواعيدك للشهر القادم:"
            elif time_range == "upcoming":
                end_time = start_time + timedelta(days=30)
                events_message = "مواعيدك اللي جاية:"
            elif calendar_tool_groq_response.get("details", {}).get("specific_date"):
                try:
                    specific_date = cairo_tz.localize(datetime.strptime(
                        calendar_tool_groq_response["details"]["specific_date"], "%Y-%m-%d"))
                    start_time = specific_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    end_time = specific_date.replace(hour=23, minute=59, second=59, microsecond=999999)
                    events_message = f"مواعيدك ليوم {specific_date.strftime('%Y-%m-%d')}:"
                except ValueError:
                    return "صيغة التاريخ غير صحيحة في طلبك. استخدم YYYY-MM-DD."

            events = await list_upcoming_events(service, start_time=start_time, end_time=end_time, max_results=max_results)

            if events:
                events_list = [
                    f"- {event['summary']} (من {event['start'].get('dateTime', event['start'].get('date'))} إلى {event['end'].get('dateTime', event['end'].get('date'))})"
                    for event in events
                ]
                return f"{events_message}\n" + "\n".join(events_list)
            else:
                return f"معنديش مواعيد جاية في التقويم {events_message.replace('مواعيدك اللي جاية:', '').strip()}."

        # === CREATE EVENT ===
        elif action == "create_event":
            details = calendar_tool_groq_response.get("details", {})
            summary = details.get("summary")
            start_datetime_str = details.get("start_time")
            end_datetime_str = details.get("end_time")
            description = details.get("description")
            location = details.get("location")

            if not all([summary, start_datetime_str, end_datetime_str]):
                return "من فضلك، أحتاج عنوانًا وتاريخ ووقت بدء وانتهاء لإنشاء الحدث."

            try:
                start_datetime = cairo_tz.localize(datetime.fromisoformat(start_datetime_str.replace('Z', '+00:00')))
                end_datetime = cairo_tz.localize(datetime.fromisoformat(end_datetime_str.replace('Z', '+00:00')))
            except ValueError:
                return "صيغة التاريخ والوقت غير صحيحة. استخدم YYYY-MM-DDTHH:MM:SS+HH:MM."

            service = await refresh_and_get_service(user_id)
            if not service:
                return "تقويم جوجل غير متصل. يرجى توصيله أولاً."

            event_details = {
                'summary': summary,
                'start': {'dateTime': start_datetime.isoformat(), 'timeZone': 'Africa/Cairo'},
                'end': {'dateTime': end_datetime.isoformat(), 'timeZone': 'Africa/Cairo'},
                'description': description,
                'location': location
            }

            created_event = await create_calendar_event(service, event_details)
            if created_event:
                return f"تم إنشاء حدث '{created_event.get('summary')}' بنجاح يوم {start_datetime.strftime('%A, %B %d')} الساعة {start_datetime.strftime('%H:%M')}."
            else:
                return "لم أتمكن من إنشاء الحدث. ربما توجد مشكلة في تفاصيل الحدث أو الاتصال."

        # === UNKNOWN INTENT ===
        elif action == "unknown_calendar_intent":
            return "عذراً، لم أستطع فهم طلبك المتعلق بالتقويم. هل يمكنك أن توضح أكثر؟"

        else:
            return "عذراً، حدث خطأ غير متوقع في معالجة طلب التقويم."

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"🔥 An unexpected error occurred in calendar parsing: {e}")
        return "عذراً، حدثت مشكلة أثناء محاولة التعامل مع التقويم الخاص بك."


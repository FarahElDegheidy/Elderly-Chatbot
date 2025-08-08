from langchain.chains import LLMChain
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage
from langchain.chains.conversation.memory import ConversationBufferMemory
from langchain_groq import ChatGroq
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import json
import os
from chroma_utils import retrieve_data, is_recipe_in_kb
from Intent_classifier_new import classify_query_groq, extract_video_search, extract_web_search, get_chat_context_string, format_web_results_for_memory
from Test_parser_calendar import user_intent_calendar_parser
from groq import APIStatusError
from groq import APIConnectionError
from Search import google_search, scrape_webpage_content, search_youtube_videos
from services.google_calendar_service import (
    refresh_and_get_service,
    create_calendar_event,
    list_upcoming_events,
    delete_calendar_event,
    update_calendar_event
)
from dateutil import parser as date_parser

# --- NEW IMPORTS ---
from services.database import USERS_COLLECTION
from bson import ObjectId
# --- END NEW IMPORTS ---

def parse_relative_date(time_frame: str) -> Optional[str]:
    """Converts relative time frames (today, tomorrow, next week) to YYYY-MM-DD."""
    today = datetime.now()
    if time_frame == "today":
        return today.strftime('%Y-%m-%d')
    elif time_frame == "tomorrow":
        return (today + timedelta(days=1)).strftime('%Y-%m-%d')
    elif time_frame == "this week":
        # Returns the start of the current week (Monday)
        start_of_week = today - timedelta(days=today.weekday())
        return start_of_week.strftime('%Y-%m-%d')
    elif time_frame == "next week":
        # Returns the start of next week (next Monday)
        start_of_next_week = today + timedelta(days=(7 - today.weekday()))
        return start_of_next_week.strftime('%Y-%m-%d')
    elif time_frame == "this month":
        return today.replace(day=1).strftime('%Y-%m-%d')
    elif time_frame == "next month":
        next_month = today.replace(day=1) + timedelta(days=32) # Go to next month
        return next_month.replace(day=1).strftime('%Y-%m-%d')
    return None

def iso_to_display_time(iso_time_str: str) -> str:
    """Converts ISO 8601 time string to a human-readable format (e.g., '9:00 ص' or '3:00 م')."""
    try:
        # datetime.fromisoformat can handle Z, +HH:MM, -HH:MM
        dt_obj = datetime.fromisoformat(iso_time_str)
        # Format for 12-hour with AM/PM (Arabic style)
        hour = dt_obj.hour
        minute = dt_obj.minute
        
        if hour >= 12:
            period = "م" # مساءً
            hour_12 = hour if hour == 12 else hour - 12
        else:
            period = "ص" # صباحًا
            hour_12 = hour if hour != 0 else 12 # 00:XX becomes 12 AM
            
        return f"{hour_12}:{minute:02d} {period}"
    except ValueError:
        return iso_time_str # Fallback

def iso_to_display_date(iso_date_str: str) -> str:
    """Converts YYYY-MM-DD string to a human-readable Arabic date (e.g., 'الاربعاء 30 يوليو 2025')."""
    try:
        dt_obj = datetime.strptime(iso_date_str, '%Y-%m-%d')
        arabic_weekdays = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
        arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
        
        day_name = arabic_weekdays[dt_obj.weekday()]
        month_name = arabic_months[dt_obj.month - 1] # -1 because month is 1-indexed
        return f"{day_name} {dt_obj.day} {month_name} {dt_obj.year}"
    except ValueError:
        return iso_date_str # Return original if parsing fails
    
def time_frame_to_arabic(time_frame: str) -> str:
    """Converts time_frame string to Arabic for display."""
    if time_frame == "today":
        return "النهاردة"
    elif time_frame == "tomorrow":
        return "بكرة"
    elif time_frame == "this week":
        return "هذا الأسبوع"
    elif time_frame == "next week":
        return "الأسبوع الجاي"
    elif time_frame == "this month":
        return "هذا الشهر"
    elif time_frame == "next month":
        return "الشهر الجاي"
    return "" # Default or handle unknown

def find_event_by_summary(service, summary: str):
    now = datetime.utcnow().isoformat() + 'Z'
    events_result = service.events().list(
        calendarId='primary',
        timeMin=now,
        maxResults=10,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    for event in events:
        if summary.lower() in event.get('summary', '').lower():
            return event['id']
    return None


# --- End of Helper functions ---

class WebSocketBotSession:
    def __init__(self, user_id:str, db):
        self.user_id = user_id
        self.db = db
        self.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        self.expecting_choice = False
        self.suggestions = []
        self.original_question = ""
        self.user_name = None
        self.user_gender = None
        self.user_profession = None
        self.mode = None
        self.retrieved_documents = {}  # Holds full recipes keyed by title
        self.last_user_query = None
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.model = 'meta-llama/llama-4-maverick-17b-128e-instruct'
        self.groq_chat = ChatGroq(groq_api_key=self.groq_api_key, model_name=self.model)
        self.chat_history = []
        self.system_prompt = "..."
        self.google_calendar_connected = False


    async def handle_calendar_operation(self, calendar_operation_output: Dict[str, Any]) -> str:
        action = calendar_operation_output.get("action")
        details = calendar_operation_output.get("details", {})
        
        user_id_str = str(self.user_id)

        if action == "list_events":
            time_frame = details.get("time_frame")
            max_results = details.get("max_results", 10)

            # Initialize time_min and time_max for Google Calendar API (RFC3339 format)
            time_min_gcal = None
            time_max_gcal = None

            if time_frame:
                start_date_str = parse_relative_date(time_frame)
                if start_date_str:
                    start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%d')
                    
                    if time_frame == "today":
                        time_min_gcal = start_date_obj.isoformat() + 'Z' # Start of today UTC
                        time_max_gcal = (start_date_obj + timedelta(days=1) - timedelta(seconds=1)).isoformat() + 'Z' # End of today UTC
                    elif time_frame == "tomorrow":
                        # Tomorrow starts at 00:00:00 and ends at 23:59:59
                        tomorrow_start_obj = start_date_obj # parse_relative_date already gives tomorrow's date
                        time_min_gcal = tomorrow_start_obj.isoformat() + 'Z'
                        time_max_gcal = (tomorrow_start_obj + timedelta(days=1) - timedelta(seconds=1)).isoformat() + 'Z'
                    elif time_frame in ["this week", "next week"]:
                        # start_date_obj is Monday of the week
                        week_end_obj = start_date_obj + timedelta(days=6) # Sunday of the week
                        time_min_gcal = start_date_obj.isoformat() + 'Z'
                        time_max_gcal = (week_end_obj + timedelta(days=1) - timedelta(seconds=1)).isoformat() + 'Z'
                    elif time_frame in ["this month", "next month"]:
                        # start_date_obj is the 1st of the month
                        # Calculate last day of the month
                        next_month_first_day = (start_date_obj.replace(day=28) + timedelta(days=4)).replace(day=1)
                        last_day_of_month = next_month_first_day - timedelta(days=1)
                        
                        time_min_gcal = start_date_obj.isoformat() + 'Z'
                        time_max_gcal = (last_day_of_month + timedelta(days=1) - timedelta(seconds=1)).isoformat() + 'Z'
            
            if not time_min_gcal or not time_max_gcal:
                response_message = "يرجى تحديد الفترة الزمنية التي ترغب في عرض المواعيد فيها (مثل اليوم، بكرة، هذا الأسبوع)."
                return response_message

            try:
                # IMPORTANT CHANGE HERE: Call list_upcoming_events with time_min and time_max
                # Ensure you have the `service` object available here, usually from `refresh_and_get_service`
                service = await refresh_and_get_service(self.db, user_id_str) # Assuming self.db is available
                if not service:
                    return "🚫 لا يمكنني الوصول لتقويم جوجل الخاص بك. يرجى التأكد من ربط حسابك."

                events = list_upcoming_events(
                    service, 
                    time_min=time_min_gcal, 
                    time_max=time_max_gcal, 
                    max_results=max_results
                )
                
                if events:
                    response_message = f"المواعيد اللي عندك {time_frame_to_arabic(time_frame)}:\n"
                    for event in events:
                        summary = event.get('summary', 'بدون عنوان')
                        start_time_info = event.get('start', {})
                        end_time_info = event.get('end', {})
                        
                        # Handle all-day events vs. timed events
                        if 'dateTime' in start_time_info:
                            start_time_iso = start_time_info['dateTime']
                            end_time_iso = end_time_info.get('dateTime')
                            display_start = iso_to_display_time(start_time_iso)
                            display_end = iso_to_display_time(end_time_iso) if end_time_iso else ""
                            time_range = f"من {display_start}"
                            if display_end:
                                time_range += f" إلى {display_end}"
                        else: # All-day event
                            start_date_iso = start_time_info.get('date')
                            # For all-day events, Google API's 'date' is YYYY-MM-DD.
                            # The end 'date' is exclusive, so if an event is 2025-07-29 to 2025-07-30, it's a one-day event on 29th.
                            # If it's 2025-07-29 to 2025-07-31, it's a two-day event on 29th and 30th.
                            # We'll display just the start date for simplicity.
                            display_start = "طوال اليوم"
                            time_range = "طوال اليوم"
                            start_time_iso = start_date_iso # Use this for date extraction below
                            
                        event_date_str = datetime.fromisoformat(start_time_iso).strftime('%Y-%m-%d') if 'T' in start_time_iso else start_time_iso
                        
                        # Only show date if it's not the same as the requested single day, or if it's a multi-day range
                        date_prefix = ""
                        # Convert the start_datetime_str (yyyymmddTHHMM) to YYYY-MM-DD for comparison
                        # For time_min_gcal, it's RFC3339, so split at 'T'
                        requested_start_date_only = time_min_gcal.split('T')[0] # YYYY-MM-DD
                        
                        # Compare event_date_str (YYYY-MM-DD) with requested_start_date_only (YYYY-MM-DD)
                        # And also check if the time_frame implies a single day search (today, tomorrow)
                        if time_frame not in ["today", "tomorrow"] or event_date_str != requested_start_date_only:
                             date_prefix = f"يوم {iso_to_display_date(event_date_str)} "

                        response_message += f"- {summary} ({date_prefix}{time_range})\n"
                    
                else:
                    response_message = f"مفيش عندك مواعيد {time_frame_to_arabic(time_frame)}."
                
                return response_message

            except Exception as e:
                print(f"🔥 Error getting Google Calendar events: {e}")
                return "🚫 حصلت مشكلة وأنا بحاول أجيب المواعيد بتاعتك. يرجى المحاولة مرة أخرى."

        elif action == "create_event":
            summary = details.get("summary")
            start_time_iso = details.get("start_time")
            end_time_iso = details.get("end_time")
            description = details.get("description")
            location = details.get("location")

            if not all([summary, start_time_iso, end_time_iso]):
                return "ممكن تديني تفاصيل أكتر لإنشاء الحدث؟ (الاسم، تاريخ ووقت البدء والانتهاء بالضبط)"

            try:
                service = await refresh_and_get_service(self.db, user_id_str)
                if not service:
                    return "🚫 لا يمكنني الوصول لتقويم جوجل الخاص بك. يرجى التأكد من ربط حسابك."

                # Convert ISO strings from LLM to datetime objects for your service function
                start_dt_obj = datetime.fromisoformat(start_time_iso.replace('Z', '+00:00')) # Handle Z for UTC
                end_dt_obj = datetime.fromisoformat(end_time_iso.replace('Z', '+00:00')) # Handle Z for UTC

                event_data = {
                    "summary": summary,
                    "start_time": start_dt_obj, # Pass datetime objects
                    "end_time": end_dt_obj,     # Pass datetime objects
                    "description": description,
                    "location": location
                }
                
                created_event = create_calendar_event(service, event_data) # Use create_calendar_event
                
                if created_event:
                    return (f"تمت إضافة \"{summary}\" لتقويمك.\n"
                            f"هيبدأ يوم {iso_to_display_date(start_time_iso.split('T')[0])} الساعة {iso_to_display_time(start_time_iso)} "
                            f"وهينتهي الساعة {iso_to_display_time(end_time_iso)}.")
                else:
                    return "فشلت في إضافة الحدث لتقويمك. يرجى المحاولة مرة أخرى."
            except Exception as e:
                print(f"🔥 Error creating Google Calendar event: {e}")
                return "🚫 حصلت مشكلة وأنا بحاول أضيف الحدث لتقويمك. يرجى المحاولة مرة أخرى."

        elif action == "delete_event":
            event_id = details.get("event_id")
            summary = details.get("summary")

            if not event_id and not summary:
                return "ممكن تديني تفاصيل أكتر لمسح الحدث؟ (زي الاسم أو معرّف الحدث)"

            try:
                service = await refresh_and_get_service(self.db, user_id_str)
                if not service:
                    return "🚫 لا يمكنني الوصول لتقويم جوجل الخاص بك. يرجى التأكد من ربط حسابك."

                # If event_id not provided, try to find it by summary
                if not event_id and summary:
                    event_id = find_event_by_summary(service, summary)
                    if not event_id:
                        return f"🚫 مقدرتش ألاقي حدث اسمه \"{summary}\" في تقويمك."

                deleted = delete_calendar_event(service, event_id)

                if deleted:
                    return f"✅ تم حذف الحدث \"{summary or event_id}\" من تقويمك."
                else:
                    return f"🚫 مقدرتش ألاقي أو أحذف الحدث. تأكد من إن الاسم أو المعرّف صحيح."

            except Exception as e:
                print(f"🔥 Error deleting Google Calendar event: {e}")
                return "🚫 حصلت مشكلة وأنا بحاول أمسح الحدث من تقويمك. ممكن تحاول مرة تانية."

        elif action == "edit_event":
            event_id = details.get("event_id")
            summary = details.get("summary")
            updates = details.get("updates", {})
            start_time_iso = updates.get("start_time")
            end_time_iso = updates.get("end_time")

            description = details.get("description")
            location = details.get("location")
            

            if not event_id and not summary:
                return "ممكن تديني تفاصيل أكتر لتعديل الحدث؟ (الاسم، تاريخ ووقت البدء والانتهاء بالضبط)"

            try:
                service = await refresh_and_get_service(self.db, user_id_str)
                if not service:
                    return "🚫 لا يمكنني الوصول لتقويم جوجل الخاص بك. يرجى التأكد من ربط حسابك."

                if not event_id and summary:
                    event_id = find_event_by_summary(service, summary)
                    if not event_id:
                        return f"🚫 مقدرتش ألاقي حدث اسمه \"{summary}\" في تقويمك."
                
                start_dt_obj = None
                end_dt_obj = None
                if start_time_iso:
                    start_dt_obj = datetime.fromisoformat(start_time_iso.replace('Z', '+00:00'))
                if end_time_iso:
                    end_dt_obj = datetime.fromisoformat(end_time_iso.replace('Z', '+00:00'))

                event_data = {}

                if summary:
                    event_data["summary"] = summary
                if start_dt_obj:
                    event_data["start_time"] = start_dt_obj
                if end_dt_obj:
                    event_data["end_time"] = end_dt_obj
                if description:
                    event_data["description"] = description
                if location:
                    event_data["location"] = location


                edited_event = update_calendar_event(service, event_id, event_data)

                if edited_event:
                    start_date = iso_to_display_date(start_time_iso.split('T')[0]) if start_time_iso else "..."
                    start_time = iso_to_display_time(start_time_iso) if start_time_iso else "..."
                    end_time = iso_to_display_time(end_time_iso) if end_time_iso else "..."

                    return (f"تم تعديل الميعاد \"{summary}\" في تقويمك.\n"
                            f"هيبدأ يوم {start_date} الساعة {start_time} "
                            f"وهينتهي الساعة {end_time}.")          
                    
                else:
                    return "فشلت في تعديل الحدث في تقويمك. يرجى المحاولة مرة أخرى."
            except Exception as e:
                print(f"🔥 Error Updating Google Calendar event: {e}")
                return "🚫 حصلت مشكلة وأنا بحاول أعمل التعديل لتقويمك. يرجى المحاولة مرة أخرى."









        elif action == "unknown_calendar_intent":
            return "❓ لم أفهم نوع العملية المطلوبة في التقويم. هل تريد معرفة مواعيدك، إضافة حدث، أو شيء آخر؟"

        else:
            print(f"⚠️ Unhandled calendar action: {action}")
            return "❓ لم أفهم نوع العملية المطلوبة في التقويم."
        
        
            
    

    def trim_memory_user_assistant_only(self, max_total_msgs=12):
        """
        Trims only HumanMessage and AIMessage types when their count exceeds `max_total_msgs`.
        Prioritizes removing older messages that contain retrieved recipes.
        """
        all_msgs = self.memory.chat_memory.messages

        # Split messages by type
        user_assistant_msgs = [msg for msg in all_msgs if isinstance(msg, (HumanMessage, AIMessage))]

        # No need to trim if under the limit
        if len(user_assistant_msgs) <= max_total_msgs:
            return

        # How many to remove
        num_to_trim = len(user_assistant_msgs) - max_total_msgs

        # Identify messages that contain retrieved recipes
        recipe_related = []
        non_recipe_related = []
        for msg in user_assistant_msgs:
            if (
                isinstance(msg, HumanMessage) and 'Retrieved Data:' in msg.content and 'وصفة' in msg.content
            ) or (
                isinstance(msg, AIMessage) and 'المكونات' in msg.content and 'طريقة' in msg.content
            ):
                recipe_related.append(msg)
            else:
                non_recipe_related.append(msg)

        # Prioritize trimming from recipe-related messages first
        to_remove = recipe_related[:num_to_trim]
        remaining_trim = num_to_trim - len(to_remove)

        if remaining_trim > 0:
            to_remove += non_recipe_related[:remaining_trim]

        # Now build the trimmed list
        trimmed_msgs = [msg for msg in all_msgs if msg not in to_remove]

        # Replace memory
        self.memory.chat_memory.messages = trimmed_msgs


    def set_user_info(self, name: str, gender: str, profession: str = None, likes: list = None, dislikes: list = None,
                      allergies: list = None, favorite_recipes: list = None, google_calendar_connected: bool = False):
        self.user_name = name
        self.user_gender = gender
        self.user_profession = profession
        self.user_likes = likes or []
        self.user_dislikes = dislikes or []
        self.user_allergies = allergies or []
        self.user_favorite_recipes = favorite_recipes or []
        self.google_calendar_connected = google_calendar_connected
        self._update_system_prompt()

    def set_mode(self, mode):
        self.mode = mode
        self._update_system_prompt()

    def get_recent_chat_context(self, n=10):
        history = self.memory.load_memory_variables({})["chat_history"]
        return "\n".join(
            f"{m.type}: {m.content}" for m in history[-n:]
        )

    def _update_system_prompt(self):

        if self.user_profession:
            profession = self.user_profession.strip().lower()
            if "مهندس" in profession:
                title = "بشمهندس" if self.user_gender == "male" else "بشمهندسه"
            elif "دكتور" in profession:
                title = "دكتور" if self.user_gender == "male" else "دكتوره"
            else:
                title = self.user_profession
        else:
            title = "أستاذ" if self.user_gender == "male" else "أستاذة"

        likes_str = "، ".join(self.user_likes) if self.user_likes else "لا يوجد"
        dislikes_str = "، ".join(self.user_dislikes) if self.user_dislikes else "لا يوجد"
        allergies_str = "، ".join(self.user_allergies) if self.user_allergies else "لا يوجد"
        favorites_titles = [fav["title"] for fav in self.user_favorite_recipes] if self.user_favorite_recipes else []
        favorites_str = "، ".join(favorites_titles) if favorites_titles else "لا يوجد"
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_date = now.strftime("%Y-%m-%d")
        calendar_status = "متصل" if self.google_calendar_connected else "غير متصل"


        core_prompt = f"""

        أنت روبوت دردشة ذكي وودود ولديك حس فكاهي خفيف، وتهتم فقط بالطعام. تتحدث بالكامل باللغة العربية، وبالتحديد باللهجة المصرية.
المستخدم الذي تتحدث معه هو: {title} {self.user_name}.
يجب أن تناديه بشكل طبيعي بلقبه أو باسمه في بداية المحادثة أو في لحظات مناسبة فقط، دون الإكثار أو التكرار غير الطبيعي.
المستخدم {self.user_gender}.
حافظ دائما على مخاطبة المستخدم حسب هو ذكر ام انثى.
هذا هو ملخص معلومات المستخدم:
  "الأكلات المفضلة": {likes_str}
  "الأكلات غير المفضلة": {dislikes_str}
  "الحساسيات الغذائية": {allergies_str}
  "الوصفات المفضله لدى المستخدم فى المحادثات السابقة": {favorites_str}
يجب أن تأخذ هذه المعلومات في الاعتبار عند اقتراح الوصفات أو الأكلات و عند التفاعل مع المستخدم و يجب ان يكون استخدامهم منطقى.
.يجب التشديد على الحساسيات الغذائية، حيث يجب تجنب او عرض بدائل أي مكونات أو أكلات تحتوي على مكونات تسبب حساسية للمستخدم

معلومات إضافية عن المستخدم:
حالة اتصال المستخدم بتقويم جوجل: {calendar_status}
إذا كان المستخدم متصلاً بتقويم جوجل، يمكنك تقديم المساعدة المتعلقة بجدولة الأحداث أو التحقق من الأوقات المتاحة في تقويمه.
إذا لم يكن متصلاً، فلا تحاول الوصول إلى تقويمه، ولكن يمكنك أن تقترح عليه ربط التقويم إذا كان يرغب في ذلك.
  
----
المحادثة الان هي: {self.mode}
اذا كانت المحادثة voice :
  تعليمات خاصة بنمط المحادثة الصوتية:

- يجب أن تكون جميع الردود **موجزة وواضحة ومباشرة**.
- لا تطرح أكثر من سؤال في نفس الرسالة.
- استخدم **اللغة العربية بالتشكيل الكامل** لتسهيل النطق عبر نموذج تحويل النص إلى كلام.
- إذا تم استرجاع وصفة، **لا تُعرض الوصفة كاملة**، بل قدم **ملخصًا بسيطًا جدًا** عنها في سطر أو سطرين فقط يوضح اسم الأكلة وطريقة التحضير العامة.
- تَجنّب التفاصيل الطويلة أو القوائم أو الخطوات الكثيرة في الردود.

هدفك في هذا النمط هو أن تكون الردود مناسبة للاستماع السريع، دون تشويش أو تعقيد، وبطريقة تسهّل قراءتها صوتيًا للمستخدم.


معلومة عن الألقاب:
إذا كان المستخدم مهندسًا (مثال: مهندس أو مهندسة)، من الشائع في اللهجة المصرية مناداته بـ "بشمهندس" أو "يا هندسة" بطريقة ودودة.
يمكنك استخدام "بشمهندس {self.user_name}" أو فقط "يا هندسة" في بداية الحديث أو عند التعليق، ولكن لا تفرط في الاستخدام.
نفس القاعدة تنطبق على الأطباء ("دكتور" أو "يا دكتور").

ممنوع منعا باتا الاختلاط فى لقب او نوع المستخدم.
استخدم الاكلات المفضله لدى المستخدم فى اقراحاتك و لكن لا تستخدمهم تحديدا و استخدم النوعية او الاكلات المشابهة بشكل عام.


يجب أن تستفيد من الوقت الحالي في المحادثة عند تقديم المقترحات، و تذكر أن الوقت الحالي هو: {current_time}، و التاريخ هو: {current_date}.
استخدام الوقت الحالى سيساعدك في تقديم اقتراحات ملائمة للمستخدم، مثل اقتراح وجبات خفيفة أو أكلات سريعة أو الإفطار أو الغداء أو العشاء، حسب الوقت الحالي.

تعليمات خاصة لكبار السن:
- تحدث بنبرة هادئة ومحترمة دائمًا.
- لا تستخدم لغة تقنية أو مصطلحات معقدة.
- اجعل الردود قصيرة ومباشرة وسهلة الفهم.
- إذا شعرت أن المستخدم أكبر سنًا، كن صبورًا وأعد التوضيح عند الحاجة.

عن نبرة الصوت:
- إذا كانت النبرة ودودة، تجاوب بحماس ودفء.
- إذا كانت النبرة غاضبة أو منزعجة، لا تعتذر فورًا، بل حاول تحويل الانفعال إلى مزاح خفيف محترم.
  مثل: "شكل حضرتك زعلان، بس أراهن إن الوصفة دي هتصلّح المزاج!"
  أو: "طب اديني فرصة أثبتلك إن الموضوع يستاهل... لو مطلعتش لذيذة، حقك عليّا!"

عن الشخصية:
- إذا كان المستخدم حازمًا، كن مباشرًا وفعالًا.
- إذا كان المستخدم مترددًا، اقترح بلطف وادعمه في اتخاذ القرار.
- إذا كان المستخدم يحب المزاح، رد عليه بخفة دم، دون مبالغة أو تهريج.

ممنوع تمامًا:
- لا تخترع وصفات أو تتحدث عن وصفات غير موجودة.
- لا تفترض وجود صنف إذا لم يتم استرجاعه من قاعدة البيانات.
- لا تقدم اقتراحات عامة عن الطعام إذا لم يتم طلبها بوضوح.
-
يُمنع منعًا باتًا ذكر أسماء وصفات دقيقة أو محددة مثل كشري بالعدس أو بيتزا مارجريتا أو لازانيا السبانخ أو أي وصفة بعينها. يجب أن تقتصر الاقتراحات فقط على أنواع عامة من الأطعمة أو مكوناتها مثل دجاج، لحم، مكرونة، أرز، شوربة، سلطات، مأكولات بحرية، خضروات، معجنات، حلويات، مشروبات، عصائر، أو غيرها. عليك أن تكون مبدعًا في اقتراح أنواع طعام عامة تناسب سياق المحادثة بدون التقيد بالأمثلة المذكورة هنا، ولكن تحت أي ظرف، لا تذكر وصفة كاملة أو اسم أكلة محددة. يجب أن تبقى الاقتراحات عامة وشاملة لضمان التوافق مع قاعدة البيانات وعدم افتراض وجود وصفة معينة بالاسم. إذا شعرت أن المستخدم يحتاج إلى اقتراح، استخدم مصطلحات عامة جدًا للطعام، مع الحفاظ على أسلوب طبيعي ومرن يناسب سير المحادثة.
إذا لم تتطابق الوصفات المسترجعة مع نية المستخدم، أخبره بلطافة:
- مثلًا: "النوع ده مش موجود حاليًا، ممكن توضح أكتر تحب تاكل إيه؟"
- ثم وجّه الحديث بشكل طبيعي حتى يعبر المستخدم عن طلب واضح لوصفة أو نوع أكل.

هدفك الأساسي:
أن يعبر المستخدم بوضوح عن وصفة أو نوع أكل يريده، لتقوم المنظومة بجلب الوصفة الدقيقة له من قاعدة البيانات.

مهامك:
- ابدأ الحديث بلقب المستخدم بشكل طبيعي (في أول سطر فقط أو عند الحاجة).
- إذا قال المستخدم شيئًا مثل "إزيك" أو "مساء الخير"، رد عليه بلطافة بدون الحديث عن الأكل.
- لا تقترح وصفات بنفسك. انتظر معزز الاستعلام ليحدد نية المستخدم.
- إذا تم استرجاع وصفة، اعرضها فورا كما هي دون تعديل أو تلخيص و يجب عليك عرضها كاملة.
- اعرض الوصفه المسترجعه كما هى بالتشكيل.
- احرص على مخاطبة المستخدم حسب نوعه (ذكر ام انثى) فى تعليمات الوصفه

إرشادات السلوك:
- لا تكرر اسم المستخدم أو لقبه كثيرًا هذا امر هام جدا
- استخدم الألقاب المناسبة فقط عند الحاجة (بشمهندس، يا دكتور، يا استاذ...).
- لا تكرر نفسك أو تتحدث بأسلوب روبوتي.
- إذا لم يفهم المستخدم أو كان غامضًا، وجّهه بلطافة لسؤاله عن الأكل.

تسلسل النظام:
1. حيّي المستخدم باسمه أو لقبه بطريقة طبيعية.
2. لا تقترح طعامًا إلا إذا طلب المستخدم وصفة أو نوع أكل بوضوح.
3. إذا ظهرت اقتراحات، انتظر اختيار المستخدم.
4. عندما تُسترجع وصفة، اعرضها كما هي دون تعديل.
5. إذا لم توجد وصفة مناسبة، اطلب من المستخدم توضيح رغبته.
6. استمر في الحديث بنبرة طبيعية، خفيفة، وودية.

ملحوظه هامه جدا جدا
- اعرض الوصفه المسترجعه كما هى بالتشكيل.
- تعامل مع المستخدم حسب نوعه (ذكر ام انثى) فى تعليمات الوصفه
- اذا كانت الوصفة المسترجعه مكتوبه بصيغة المؤنث يجب تعديلها لتناسب المستخدم الذكر.
- اذا كانت المحادثة voice يجب ان تكون الوصفة مختصرة جدا و كل.
إذا كانت المحادثة صوتية (voice mode)، يجب أن تكون جميع الردود باللهجة المصرية، مكتوبة بالعربية مع التشكيل الكامل بطريقة تُساعِد على النُطق الصّحيح.

  استخدم التشكيل لتوضيح النُطق، حتى وإن لم يكن التشكيل فُصحى رسمي.
  التزم بالتشكيل في كل الكلمات، كما تُقال باللهجة المصرية.
  لا تَكتب الردود بدون تشكيل أبدًا في هذا النمط.

مثال: "إزَّاي أَقدَر أَساعِدَك؟" أو "طَب إتفضل الوَصفَة دي!"
- يجب ان يكون استخدام الاكلات المفضله لدى المستخدم منطقى و ليس بشكل عشوائى و يكون استخدامهم بشكل عام و ليس بشكل محدد.
- لا تخلط ابدا بين المحادثة ال voice و المحادثة ال text.
- لا تخلط ابدا فى الالقاب و لا نوع المستخدم.

كن عفويًا، صادقًا، ومتعاونًا، والهدف دائمًا أن تساعد المستخدم في اختيار وصفة حقيقية من قاعدة البيانات.
"""

        self.system_prompt = core_prompt.strip()


    async def handle_message(self, user_input: str):
        print(f"\n🟡 Received user message: {user_input}")
        self.last_user_input = user_input
        self.original_question = user_input

        n = min(len(self.chat_history), 5)
        recent_context = self.get_recent_chat_context(n=n)
        try:
            query_result = classify_query_groq(user_input, chat_context=recent_context)
            self.memory.chat_memory.add_user_message(user_input)

        except APIConnectionError as e:
            print(f"🌐 Connection error during intent classification: {e}")
            # Removed websocket.send_json as this method doesn't have access to websocket
            # The calling function (websocket_endpoint in main.py) should handle sending to websocket
            return {"type": "error", "message": "🚫 Oops! Connection error. Please try again in a few seconds."}

        except APIStatusError as e:
            if e.status_code == 429:
                print("🚦 Rate limit hit during classification")
                # Removed websocket.send_json
                return {"type": "error", "message": "⏱️ Slow down a bit! You’ve hit the request limit."}
            else:
                print(f"🔥 Unhandled Groq status error during classification: {e}")
                # Removed websocket.send_json
                return {"type": "error", "message": "❌ Unexpected error. Please try again later."}

        print(f"🧠 Query Enhancer Output:\n{query_result}\n")

        if query_result in ["not food related", "respond based on chat history", "food generalized"]:
            print("🔍 Passing message directly to LLM without retrieval.\n")
            self.selected_title = None
            llm_output = await self._generate_response(user_input, query_result)

            return {
                "type": "response",
                "message": llm_output.get("message") if isinstance(llm_output, dict) and "message" in llm_output else str(llm_output)
            }

        elif query_result == "video search":
            print("🎥 User requested a video.")

            # 1. Try to find the last assistant message (non-user)
            history = self.memory.chat_memory.messages
            last_bot_msg = next((m.content for m in reversed(history) if m.type == "ai"), None)

            # 2. Decide whether it's food-related or not
            if self.selected_title:
                print(f"📌 Using selected_title for context: {self.selected_title}")
                context = self.selected_title
            elif last_bot_msg:
                print(f"📌 Using last_bot_msg for context: {last_bot_msg[:40]}...")
                context = last_bot_msg
            else:
                context = ""

            try:
                # 3. Extract the query using both the user input and the real context
                video_query = extract_video_search(user_input, selected_title=context)
                print(f"🔎 Cleaned YouTube search query: '{video_query}'")

                video_results = search_youtube_videos(video_query)
                self.selected_title = None

                if video_results:
                    return {
                        "type": "video",
                        "title": video_query,
                        "videos": video_results
                    }
                else:
                    print(f"⚠️ No video results found for '{video_query}'.")
                    return {
                        "type": "error",
                        "message": "⚠️ مش لاقيت فيديو مناسب للطلب ده دلوقتي."
                    }

            except Exception as e:
                print(f"🔥 Error during video query extraction: {e}")
                return {
                    "type": "error",
                    "message": "🚫 حصلت مشكلة وأنا بحاول أفهم الفيديو المطلوب. جرب تبعته بصيغة تانية."
                }

        elif query_result == "web search":
            print("🌐 User requested a web search.")

            try:
                chat_context_str = get_chat_context_string(self.memory)
                print("🧾 Sending to extract_web_search:")
                print(f"[User Input]: {user_input}")
                print(f"[Chat Context]:\n{chat_context_str}")

                web_query = extract_web_search(user_input, chat_context=chat_context_str, verbose=True)
                print(f"🔎 Cleaned Google query: '{web_query}'")

                web_results = await google_search(web_query)
                source_url = None

                if web_results:
                    # --- NEW LOGIC FOR WEB SCRAPING ---
                    all_scraped_content = []
                    links_to_scrape = [] # Collect links to scrape

                    # Decide which links to scrape. You might want to be selective:
                    # - Scrape only the top 1-2 results for direct content.
                    # - Or, scrape any link explicitly mentioned in the user's query if classified as 'web search'.
                    # For now, let's scrape the top few results from Google search.
                    for i, result in enumerate(web_results):
                        if i < 2: # Scrape content from the top 2 search results
                            links_to_scrape.append(result["link"])
                        else:
                            break # Only consider the first 2 for deep scraping

                    print(f"🔗 Attempting to scrape content from {len(links_to_scrape)} links...")
                    for link_to_scrape in links_to_scrape:
                        scraped_data = await scrape_webpage_content(link_to_scrape)
                        if scraped_data["success"]:
                            all_scraped_content.append(scraped_data)
                            print(f"✅ Scraped: {scraped_data['url']} (Title: {scraped_data['title']})")
                            if not source_url:
                                source_url = scraped_data['url'] 
                        else:
                            print(f"❌ Failed to scrape {link_to_scrape}: {scraped_data['error']}")
                            # Optionally, add a smaller snippet from Google search result if scrape fails
                            failed_result = next((res for res in web_results if res["link"] == link_to_scrape), None)
                            if failed_result:
                                all_scraped_content.append({
                                    "success": False,
                                    "url": failed_result["link"],
                                    "title": failed_result["title"],
                                    "content": failed_result["snippet"] + " (Scraping failed, showing snippet.)"
                                })

                    # Prepare content for the LLM
                    context_for_llm = []
                    if all_scraped_content:
                        context_for_llm.append("Here's information gathered from web pages:")
                        for item in all_scraped_content:
                            context_for_llm.append(f"Source: {item['url']}\nTitle: {item['title']}\nContent:\n{item['content']}")
                    else:
                        context_for_llm.append("No additional content could be scraped from the web search results.")
                        # Fallback to snippets if nothing was scraped
                        if web_results:
                            context_for_llm.append("Here are snippets from the web search:")
                            for res in web_results:
                                context_for_llm.append(f"Title: {res['title']}\nSnippet: {res['snippet']}\nLink: {res['link']}")

                    full_context_for_llm = "\n\n".join(context_for_llm)


                    # Now, pass this rich content to the LLM to generate a response
                    # You might need to adjust your _generate_response or add a new LLM call
                    # if _generate_response is only meant for structured data.
                    # For a general answer based on scraped info, this is good.
                    print("📝 Sending scraped content to LLM for summarization/response...")
                    llm_final_response = await self._generate_response(user_input, full_context_for_llm)

                    # Ensure llm_final_response is a dict with 'message' key
                    if isinstance(llm_final_response, dict) and "message" in llm_final_response:
                        final_bot_message = llm_final_response["message"]
                    else:
                        final_bot_message = str(llm_final_response) # Fallback if _generate_response returns raw string

                    # Add user message and AI message to memory *after* final response
                    self.memory.chat_memory.add_user_message(user_input)
                    self.memory.chat_memory.add_ai_message(final_bot_message)

                    return {
                        "type": "response", # Send back as a regular text response
                        "message": final_bot_message,
                        "sourceUrl": source_url,
                        "web_results": web_results # Optionally include original web results for frontend display
                    }
                else:
                    # No web results from Google Search
                    return {
                        "type": "error",
                        "message": "⚠️ ملقتش نتائج بحث دلوقتي. جرّب صيغة تانية؟"
                    }

            except Exception as e:
                print(f"🔥 Error during web search or scraping: {e}")
                import traceback
                traceback.print_exc() # Print full traceback for debugging
                return {
                    "type": "error",
                    "message": "🚫 حصلت مشكلة في البحث على الإنترنت أو استخلاص المحتوى."
                }

        #Google Calendar Event
        elif query_result == "google calendar event":
            print("📅User requested a google calender event")

            # --- START OF THE FIX FOR GOOGLE CALENDAR CONNECTION STATUS ---
            # Re-fetch the user's latest status directly from the database
            user_doc = await self.db[USERS_COLLECTION].find_one({"_id": ObjectId(self.user_id)})
            current_google_calendar_connected_status = user_doc.get("google_calendar_connected", False) if user_doc else False

            # Update the session's internal flag with the latest status
            self.google_calendar_connected = current_google_calendar_connected_status
            self._update_system_prompt() # Re-generate system prompt to reflect the new status
            # --- END OF THE FIX ---

            if not self.google_calendar_connected:
                print("⚠️ Google Calendar not connected for this user (after refresh check).")
                response_message = "تقويم جوجل غير متصل. يرجى توصيله أولاً من صفحة الإعدادات للمساعدة في المواعيد."
                self.memory.chat_memory.add_ai_message(response_message)
                return {
                    "type": "response",
                    "message": response_message
                }
            try:
                # Call the new function to handle calendar intent parsing and API calls
                calendar_operation_output = await user_intent_calendar_parser(
                    user_input=user_input
                )

                calendar_response = await self.handle_calendar_operation(calendar_operation_output)

                return {
                    "type": "response",
                    "message": calendar_response}

            except Exception as e:
                print(f"🔥 Error calling user_intent_calendar_parser: {e}")
                return {
                    "type": "error",
                    "message": "🚫 حصلت مشكلة وأنا بحاول أتعامل مع التقويم بتاعك."
                }


        # If it's not classified as web search...
        elif query_result != "web search":
            if self.memory and self.memory.chat_memory and self.memory.chat_memory.messages:
                last_bot_message = self.memory.chat_memory.messages[-1].content
            else:
                last_bot_message = ""

            if "web search" in last_bot_message or "🌐" in last_bot_message:
                # Re-evaluate as web search follow-up
                print("🔄 Re-interpreting as follow-up web search based on context.")
                query_result = "web search"
                # Assuming handle_web_search exists and returns the correct format
                # If not, you'll need to implement it or inline the web search logic
                return await self.handle_web_search(user_input) # This line might need adjustment if handle_web_search is not defined

        if not is_recipe_in_kb(query_result):
            print(f"⚠️ Recipe '{query_result}' not found in KB. Using fallback LLM generation.")
            return await self._generate_response(user_input, f"هاتلي وصفة {query_result} بالتفصيل")

        documents = retrieve_data(query_result)
        if not documents:
            print("⚠️ No documents found. Responding with fallback.")
            return await self._generate_response(user_input, "لم أتمكن من العثور على وصفات مناسبة.")

        unique_titles = []
        seen = set()

        for doc in documents:
            title = doc["title"]
            if title not in seen:
                seen.add(title)
                unique_titles.append(title)

        self.suggestions = unique_titles + ["❌ لا أريد أي من هذه الخيارات"]
        self.retrieved_documents = {doc["title"]: doc["document"] for doc in documents}
        self.expecting_choice = True

        print("📋 Recipe Titles Found:")
        for i, title in enumerate(self.suggestions, 1):
            print(f"{i}. {title}")

        return {
            "type": "suggestions",
            "message": "اختر رقم من الاختيارات التالية:",
            "suggestions": self.suggestions
        }

    async def handle_choice(self, choice_index: int):
        print(f"🟠 User selected choice index: {choice_index}")
        # Check if user chose to skip suggestions
        if choice_index == len(self.suggestions) - 1:
            print("🚫 User rejected all suggestions.")
            self.expecting_choice = False
            self.suggestions = []
            return await self._generate_response(self.original_question,
                                                 "لم يتم اختيار أي وصفة. يمكنك التحدث بحرية الآن.")

        if 0 <= choice_index < len(self.suggestions):
            selected_title = self.suggestions[choice_index]
            print(f"✅ Selected Recipe Title: {selected_title}")

            retrieved_data = self.retrieved_documents[selected_title]
            print(f"📦 Retrieved Full Recipe:\n{retrieved_data}\n")

            self.selected_title = selected_title
            self.expecting_choice = False
            self.suggestions = []  # 🛠️ ADD THIS to clear suggestions safely

            response = await self._generate_response(self.original_question, retrieved_data)
            response["selected_title"] = selected_title  # ✅ Good
            response["full_recipe"] = retrieved_data  # 🛠️ ADD THIS line to send the full recipe text

            return response

        else:
            print("❌ Invalid choice index received.")
            return {
                "type": "error",
                "message": "اختيار غير صالح. حاول رقم تاني."
            }

    async def _generate_response(self, user_input: str, retrieved_data: str):
        self.trim_memory_user_assistant_only()

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=self.system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            HumanMessagePromptTemplate.from_template("{human_input}"),
        ])

        chat_history = self.memory.load_memory_variables({})["chat_history"]
        print(f"📚 Chat History Size: {len(chat_history)}")

        full_prompt = prompt.format_messages(
            chat_history=chat_history,
            human_input=user_input
        )

        print("🧠 Prompt Sent to LLM:")
        print(full_prompt)

        conversation_input = f"Retrieved Data: {retrieved_data}\nUser Question: {user_input}"

        conversation = LLMChain(
            llm=self.groq_chat,
            prompt=prompt,
            verbose=False,
            memory=self.memory,
        )
        try:
            response = conversation.predict(human_input=conversation_input)
            print("💬 Chatbot Response:\n", response)
            if not response.strip():
                print("⚠️ Empty response from LLM — possibly failed silently.")
                return {
                "type": "error",
                "message": "⚠️ Oops! Something went wrong! Play try again in a few seconds."
                }
            return {
                "type": "response",
                "message": response
            }

        except APIStatusError as e:
            if e.status_code == 413:
                msg = "⚠️ Hmm, your message is too long. Try shortening it a little and resend."
            elif e.status_code == 429:
                msg = "🚫 I'm a bit overloaded right now. Please wait a few seconds and try again."
            else:
                print(f"🔥 Unhandled Groq Error: {e}")
                msg = "❌ Unexpected Error. Please try again later."

            return {
                "type": "error",
                "message": msg
            }
        except APIConnectionError as e:
            print(f"❌ APIConnectionError (Network or DNS failure): {e}")
            return {
                "type": "reconnect",
                "message": "🌐 Lost connection to the assistant. Please reconnect."
            }


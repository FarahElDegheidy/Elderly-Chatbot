import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi import Request, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse, RedirectResponse
from utils import create_user, get_user_by_email, verify_password, add_recipe_to_favourites, \
    get_user_favourites_by_email, save_chat_log, get_user_chats, update_user_field
from fastapi.middleware.cors import CORSMiddleware
from myChatBot import WebSocketBotSession
from services.schemas import CalendarEventCreate, FreeBusyRequest, CalendarEventUpdate
from groq import Groq
from datetime import datetime, timedelta, timezone
from services.google_calendar_service import update_calendar_event, delete_calendar_event
from elevenlabs import ElevenLabs
import io
import os
import traceback


# ADD THIS IMPORT:
from contextlib import asynccontextmanager

# --- MongoDB Imports and Setup (Your existing code) ---
import motor.motor_asyncio
from dotenv import load_dotenv
from bson import ObjectId # For handling MongoDB's _id

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME")

client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
db = client[DB_NAME]
# --------------------------------------------------

# Import database specific definitions (including the Pydantic models and collection names)
from services.database import (
    USERS_COLLECTION, GOOGLE_CREDS_COLLECTION, UserInDB
)

# Import the Google Calendar service functions
from services.google_calendar_service import (
    get_flow,
    refresh_and_get_service,
    save_credentials_to_db,
    create_calendar_event,
    list_upcoming_events,
    check_free_busy
)

# --- Configuration for Google OAuth ---
# This must match what you configured in Google Cloud Console
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8001/auth/google/callback")
if not GOOGLE_REDIRECT_URI:
    raise ValueError("GOOGLE_REDIRECT_URI environment variable not set. Please set it in .env file.")

# --- FastAPI App Setup ---

# Define the lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Connecting to MongoDB and ensuring indexes...")
    # Ensure indexes for user_id and username
    await db[GOOGLE_CREDS_COLLECTION].create_index("user_id", unique=True)
    await db[USERS_COLLECTION].create_index("username", unique=True, sparse=True)
    print("MongoDB indexes ensured.")
    print("FastAPI application started.")
    yield # This yields control to the application, the code above runs on startup.
          # The code below will run on shutdown.
    print("Closing MongoDB connection...")
    client.close()
    print("MongoDB connection closed. FastAPI application stopped.")

# Pass the lifespan context manager to the FastAPI app instance
app = FastAPI(lifespan=lifespan) # IMPORTANT: MODIFY THIS LINE


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, set your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions = {}
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY")) # Renamed 'client' to 'groq_client' to avoid conflict with MongoDB client

# --- REMOVE THE OLD @app.on_event FUNCTIONS BELOW ---
# @app.on_event("startup")
# async def startup_db_client_and_indexes():
#     print("Connecting to MongoDB and ensuring indexes...")
#     # Ensure indexes for user_id and username
#     await db[GOOGLE_CREDS_COLLECTION].create_index("user_id", unique=True)
#     await db[USERS_COLLECTION].create_index("username", unique=True, sparse=True)
#     print("MongoDB indexes ensured.")
#     print("FastAPI application started.")

# @app.on_event("shutdown")
# async def shutdown_db_client():
#     print("Closing MongoDB connection...")
#     client.close()
#     print("MongoDB connection closed. FastAPI application stopped.")
# --- END OF REMOVED CODE ---


# --- Helper to get current user ID from request (for protected endpoints) ---
async def get_current_user_id(request: Request):
    """
    Dependency to retrieve the current user's ID.
    For this demo, we're using an 'X-User-ID' header.
    In production, this would be from a JWT token, session, etc.
    """
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: Please provide 'X-User-ID' header."
        )
    
    # Validate if the user_id exists in your database
    try:
        # MongoDB _id is an ObjectId, convert the string ID to ObjectId
        object_id = ObjectId(user_id)
        user_exists = await db[USERS_COLLECTION].find_one({"_id": object_id})
        if not user_exists:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user ID provided."
            )
    except Exception: # Catches InvalidId and other potential errors during ObjectId conversion
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID format."
        )
    
    return user_id # Return the string representation of ObjectId


# --- Existing Endpoints (No change unless specified) ---

@app.get("/get-chat-logs")
async def get_chat_logs_endpoint(email: str): # Renamed to avoid conflict if get_user_chats used globally
    chats = await get_user_chats(email)
    return {"chats": chats}


@app.get("/get-profile")
async def get_profile_endpoint(email: str): # Renamed
    user = await get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    return {
        "name": user.get("name", ""),
        "likes": user.get("likes", []),
        "dislikes": user.get("dislikes", []),
        "allergies": user.get("allergies", []),
        "google_calendar_connected": user.get("google_calendar_connected", False) # Added this field
    }


@app.post("/update-profile")
async def update_profile_endpoint(request: Request): # Renamed
    data = await request.json()
    email = data.get("email")
    field = data.get("field")  # likes, dislikes, allergies
    updated_list = data.get("updatedList")

    try:
        await update_user_field(email, field, updated_list)
        return {"status": "success"}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@app.post("/signup")
async def signup_endpoint(request: Request): # Renamed
    data = await request.json()

    # Check required fields only
    required_fields = ["email", "password", "gender"]
    for field in required_fields:
        if not data.get(field):
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    # Optional fields with defaults (from your UserInDB model now)
    # Using UserInDB model for creation
    try:
        user_data = UserInDB(
            username=data["email"], # Assuming email is the username
            passkey=data["password"], # HASH THIS IN PRODUCTION
            gender=data["gender"],
            name=data.get("name", ""),
            profession=data.get("profession", ""),
            allergies=data.get("allergies", []),
            likes=data.get("likes", []),
            dislikes=data.get("dislikes", []),
            favorite_recipes=data.get("favorite_recipes", []),
            google_calendar_connected=False # Default to false on signup
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid user data: {e}")

    existing_user = await get_user_by_email(user_data.username) # Use username field for email
    if existing_user:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Insert into MongoDB using motor client directly (assuming create_user handles this)
    # If create_user directly uses the 'db' object from this file, then it's fine.
    # Otherwise, ensure 'utils.py' gets the 'db' object passed to it.
    # For now, I'm assuming 'utils.create_user' internally uses 'db'
    user_id_obj = await create_user(user_data.model_dump(by_alias=True)) # Pass dict, not Pydantic object
    user_id_str = str(user_id_obj) if user_id_obj else None # Convert ObjectId to string

    if not user_id_str:
        raise HTTPException(status_code=500, detail="Failed to create user.")
        
    return {"message": "User created successfully", "user_id": user_id_str}


@app.post("/login")
async def login_endpoint(request: Request): # Renamed
    data = await request.json()

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")

    user = await get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not verify_password(password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    # Return user's MongoDB _id as a string for subsequent requests
    return {
        "message": "Login successful",
        "email": user["email"],
        "user_id": str(user["_id"]) # Provide the user_id
    }


@app.post("/add-favourite")
async def add_favourite_endpoint(request: Request): # Renamed
    data = await request.json()
    email = data.get("email")
    title = data.get("title")
    recipe = data.get("recipe")

    if not all([email, title, recipe]):
        raise HTTPException(status_code=400, detail="Missing data.")

    result = await add_recipe_to_favourites(email, title, recipe)
    return result


@app.post("/transcribe-audio")
async def transcribe_audio_endpoint(file: UploadFile = File(...)): # Renamed
    try:
        contents = await file.read()
        wav_buffer = io.BytesIO(contents)
        wav_buffer.name = "audio.wav"

        transcription = groq_client.audio.transcriptions.create( # Use groq_client
            file=wav_buffer,
            model="whisper-large-v3",
            language="ar",
            response_format="verbose_json"
        )

        return {"text": transcription.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@app.get("/get-favourites")
async def get_favourites_endpoint(email: str): # Renamed
    favourites = await get_user_favourites_by_email(email)
    if favourites is None:
        raise HTTPException(status_code=404, detail="User not found or no favorites.")
    return {"favourites": favourites}

@app.post("/speak-text")
async def speak_text_endpoint(request: Request): # Renamed
    try:
        data = await request.json()
        text = data.get("text", "").strip()

        if not text:
            raise HTTPException(status_code=400, detail="Text is required.")

        
        elevenlabs_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

        audio = elevenlabs_client.text_to_speech.convert(
            voice_id="IES4nrmZdUBHByLBde0P",
            output_format="mp3_44100_128",
            text=text,
            model_id="eleven_multilingual_v2"
        )

        import io
        audio_bytes = b"".join(audio)  # convert generator to bytes
        audio_stream = io.BytesIO(audio_bytes)

        audio_stream.seek(0)

        return StreamingResponse(audio_stream, media_type="audio/mpeg")

    except Exception as e:
        import traceback
        traceback.print_exc()  # 👈 prints full error in console
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")


# --- New Google Calendar OAuth Endpoints ---

@app.get("/auth/google/initiate")
async def initiate_google_auth(user_id: str = Depends(get_current_user_id)):
    """
    Initiates the Google OAuth 2.0 flow for a given user.
    The user_id is passed as the 'state' parameter to be received by the callback.
    """
    state_param = user_id 

    flow = await get_flow(GOOGLE_REDIRECT_URI)
    
    authorization_url, _ = flow.authorization_url(
        access_type='offline', # Crucial for getting a refresh token
        include_granted_scopes='true',
        state=state_param # Pass the user_id in state
    )
    
    return {"authorization_url": authorization_url}

@app.get("/auth/google/callback")
async def google_auth_callback(request: Request):
    """
    Handles the redirect from Google's OAuth 2.0 server after user consent.
    This endpoint directly receives the `code` and `state` from Google.
    """
    code = request.query_params.get("code")
    error = request.query_params.get("error")
    received_state = request.query_params.get("state") # This is our user_id

    if not received_state:
        # State parameter is missing, potential CSRF or misconfiguration
        print("Error: User ID (from state) missing in OAuth callback.")
        return RedirectResponse(
            url=f"http://localhost:3000/calendar-connected?status=error&message=Authentication+failed%3A+User+ID+missing+in+callback."
        )
    
    # Use the received_state as the user_id for saving credentials
    user_id = received_state 

    if error:
        print(f"Google OAuth error for user {user_id}: {error}")
        return RedirectResponse(
            url=f"http://localhost:3000/calendar-connected?status=error&message=Google+OAuth+error%3A+{error}.+User+may+have+denied+access."
        )

    if not code:
        print(f"Authorization code missing for user {user_id} in Google redirect.")
        return RedirectResponse(
            url=f"http://localhost:3000/calendar-connected?status=error&message=Authorization+code+missing+from+Google+redirect."
        )

    try:
        # Re-create the flow with the exact redirect_uri Google used
        flow = await get_flow(GOOGLE_REDIRECT_URI)
        
        # Exchange the authorization code for tokens
        flow.fetch_token(code=code)
        
        creds = flow.credentials

        # Save the credentials to MongoDB using your 'db' object
        await save_credentials_to_db(db, user_id, creds)
        
        # Update user's status in the users collection
        await db[USERS_COLLECTION].update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"google_calendar_connected": True}}
        )

        # Redirect the user back to your React frontend, indicating success
        return RedirectResponse(url=f"http://localhost:3000/calendar-connected?status=success&user_id={user_id}")

    except Exception as e:
        print(f"Error during OAuth callback processing for user {user_id}: {e}")
        # Redirect to a frontend error page
        return RedirectResponse(
            url=f"http://localhost:3000/calendar-connected?status=error&message=Failed+to+process+Google+Calendar+connection."
        )


# --- New Google Calendar API Endpoints (Protected by user_id) ---

@app.get("/api/google-calendar-events")
async def get_google_calendar_events(
    max_results: int = 10,
    user_id: str = Depends(get_current_user_id)
):
    """
    Lists upcoming Google Calendar events for the authenticated user.
    Requires X-User-ID header.
    """
    try:
        service = await refresh_and_get_service(db, user_id)

        if not service:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google Calendar not connected for this user. Please initiate OAuth again."
            )

        # Define time range for "upcoming events"
        now = datetime.now(timezone.utc) # Get current time in UTC with timezone info
        time_min_gcal = now.isoformat().replace('+00:00', 'Z') # RFC3339 format for Google API

        # Fetch events for the next 7 days, for example
        seven_days_from_now = now + timedelta(days=7)
        time_max_gcal = seven_days_from_now.isoformat().replace('+00:00', 'Z')

        loop = asyncio.get_event_loop()
        events = await loop.run_in_executor(
            None, # Use default executor (thread pool)
            list_upcoming_events, # Your synchronous function
            service,
            time_min_gcal, # Pass time_min
            time_max_gcal, # Pass time_max
            max_results
        )

        if not events:
            return {"message": "No upcoming events found.", "events": []}

        formatted_events = []
        for event in events:
            start_time = event['start'].get('dateTime', event['start'].get('date'))
            end_time = event['end'].get('dateTime', event['end'].get('date'))

            formatted_events.append({
                "id": event.get("id"),
                "summary": event.get("summary", "No Summary"),
                "start_time": start_time,
                "end_time": end_time,
                "location": event.get("location"),
                "description": event.get("description"),
                "html_link": event.get("htmlLink")
            })

        return formatted_events

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error retrieving Google Calendar events for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve Google Calendar events: {e}"
        )

@app.post("/calendar/freebusy")
async def get_free_busy_slots_endpoint(
    request_data: FreeBusyRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Checks free/busy slots for specified calendars and time range.
    Requires X-User-ID header.
    """
    try:
        service = await refresh_and_get_service(db, user_id)
        if not service:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google Calendar not connected for this user. Please initiate OAuth."
            )
        
        loop = asyncio.get_event_loop()
        free_busy_info = await loop.run_in_executor(
            None,
            check_free_busy,
            service,
            request_data.time_min,
            request_data.time_max,
            request_data.calendar_ids
        )
        return {"message": "Free/Busy information retrieved", "free_busy": free_busy_info}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get free/busy information: {e}"
        )
    

@app.post("/api/google-calendar-events/create")
async def create_google_calendar_event(
    event_data: CalendarEventCreate, # Use the Pydantic model for request body
    user_id: str = Depends(get_current_user_id)
):
    """
    Creates a new Google Calendar event for the authenticated user.
    Requires X-User-ID header and event details in the request body.
    """
    try:
        service = await refresh_and_get_service(db, user_id)
        
        if not service:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google Calendar not connected or credentials invalid. Please initiate OAuth again."
            )
        
        # Run the synchronous create_calendar_event in a thread pool
        loop = asyncio.get_event_loop()
        created_event = await loop.run_in_executor(
            None, # Use default executor
            create_calendar_event,
            service,
            event_data.dict() # Pass event_data as a dictionary
        )
        
        if created_event:
            return {"message": "Event created successfully", "event": created_event}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create event on Google Calendar."
            )

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error creating Google Calendar event for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )
    
@app.put("/api/google-calendar-events/{event_id}")
async def update_google_calendar_event(
    event_id: str, # Event ID from the URL path
    event_data: CalendarEventUpdate, # Use the Pydantic model for request body
    user_id: str = Depends(get_current_user_id) # Use the dependency for user_id
):
    """
    Updates an existing Google Calendar event for the authenticated user.
    Requires X-User-ID header and event details in the request body.
    """
    if not event_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Event ID is required for update.")

    try:
        service = await refresh_and_get_service(db, user_id)
        if not service:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google Calendar not connected or credentials invalid. Please initiate OAuth again."
            )

        # Run the synchronous update_calendar_event in a thread pool
        loop = asyncio.get_event_loop()
        updated_event = await loop.run_in_executor(
            None, # Use default executor
            update_calendar_event,
            service,
            event_id,
            event_data.dict() # Pass event_data as a dictionary
        )

        if updated_event:
            return {"message": "Event updated successfully", "event_id": updated_event['id'], "event": updated_event}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update event in Google Calendar. Event might not exist or data is invalid."
            )

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error updating Google Calendar event {event_id} for user {user_id}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )

# --- REWRITTEN: Delete Event Endpoint ---
@app.delete("/api/google-calendar-events/{event_id}", status_code=status.HTTP_200_OK)
async def delete_google_calendar_event(
    event_id: str, # Event ID from the URL path
    user_id: str = Depends(get_current_user_id) # Use the dependency for user_id
):
    """
    Deletes a Google Calendar event for the authenticated user.
    Requires X-User-ID header.
    """
    if not event_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Event ID is required for deletion.")

    try:
        service = await refresh_and_get_service(db, user_id)
        if not service:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google Calendar not connected or credentials invalid. Please initiate OAuth again."
            )

        # Run the synchronous delete_calendar_event in a thread pool
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None, # Use default executor
            delete_calendar_event,
            service,
            event_id
        )

        if success:
            return {"message": f"Event {event_id} deleted successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, # Can be 404 if event not found
                detail="Failed to delete event from Google Calendar. Event might not exist or an error occurred."
            )

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error deleting Google Calendar event {event_id} for user {user_id}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )


# --- Original WebSocket Endpoint (No functional change, only slight formatting) ---

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    print("🟢 WebSocket connection established.")
    # Initial session creation, will fetch user_data later
    session = None # Initialize session to None or a placeholder

    try:
        # Step 1: Wait for email (identifier)
        await websocket.send_json({
            "type": "auth_request",
            "message": "من فضلك ادخل البريد الإلكتروني لتسجيل الدخول."
        })

        login_info = await websocket.receive_json()
        user_email = login_info.get("email", "").strip()
        mode = login_info.get("mode", "text")

        user_data = await get_user_by_email(user_email) # Fetch user data initially
        if not user_data:
            await websocket.send_json({
                "type": "error",
                "message": "المستخدم غير موجود. من فضلك سجل أولاً."
            })
            await websocket.close()
            return

        # Create the session AFTER fetching user_data
        session = WebSocketBotSession(user_id=user_id, db=db)

        # Step 2: Use user data from DB to set session
        session.set_user_info(
            name=user_data.get("name", ""),
            gender=user_data.get("gender", "male"),
            profession=user_data.get("profession", None),
            likes=user_data.get("likes", []),
            dislikes=user_data.get("dislikes", []),
            allergies=user_data.get("allergies", []),
            favorite_recipes=user_data.get("favorite_recipes", []),
            google_calendar_connected=user_data.get("google_calendar_connected", False)
        )

        session.user_email = user_email
        session.set_mode(mode)
        session._update_system_prompt() # Update prompt with new info

        # Step 3: Start the chat loop
        while True:
            user_message = await websocket.receive_text()
            print(f"\n📨 Incoming WebSocket message: {user_message}")

            # Check for reset command
            if user_message.strip() == "/new":
                # RE-FETCH user data to get the latest status, including google_calendar_connected
                user_data = await get_user_by_email(user_email)
                if not user_data:
                    await websocket.send_json({
                        "type": "error",
                        "message": "المستخدم غير موجود بعد إعادة الضبط. من فضلك سجل دخولك مرة أخرى."
                    })
                    await websocket.close()
                    return

                # Create a NEW session instance with the UPDATED user_data
                session = WebSocketBotSession(user_id=user_id, db=db)
                session.set_user_info(
                    name=user_data.get("name", ""),
                    gender=user_data.get("gender", "male"),
                    profession=user_data.get("profession", None),
                    likes=user_data.get("likes", []),
                    dislikes=user_data.get("dislikes", []),
                    allergies=user_data.get("allergies", []),
                    favorite_recipes=user_data.get("favorite_recipes", []),
                    google_calendar_connected=user_data.get("google_calendar_connected", False)
                )
                session.user_email = user_email
                session.set_mode(mode) # Re-set the mode for the new session
                session._update_system_prompt() # Re-update system prompt

                await websocket.send_json({
                    "type": "reset",
                    "message": "✅ تم بدء محادثة جديدة تمامًا."
                })
                continue

            if session.expecting_choice:
                try:
                    selected_index = int(user_message.strip()) - 1

                    # ✅ Append the original query only if stored
                    if session.last_user_query:
                        session.chat_history.append({"sender": "user", "text": session.last_user_query})
                        session.last_user_query = None  # reset after logging

                    # ✅ Append the user's choice
                    session.chat_history.append({"sender": "user", "text": user_message})

                    result = await session.handle_choice(selected_index)

                    if result["type"] == "response":
                        session.chat_history.append({"sender": "bot", "text": result["message"]})

                except (ValueError, IndexError):
                    result = {
                        "type": "error",
                        "message": "من فضلك اختر رقم من الاختيارات الموجودة."
                    }

            else:
                result = await session.handle_message(user_message)

                if result["type"] == "suggestions":
                    session.last_user_query = user_message

                else:
                    session.chat_history.append({"sender": "user", "text": user_message})

                    if result["type"] == "response":
                        session.chat_history.append({"sender": "bot", "text": result["message"]})

                    elif result["type"] == "video":
                        video_title = result.get("title", "الفيديو المطلوب")
                        video_links = "\n".join([f"{v['title']}: {v['url']}" for v in result.get("videos", [])])
                        session.chat_history.append({
                            "sender": "bot",
                            "text": f"📹 تم العثور على فيديوهات لـ **{video_title}**:\n{video_links}"
                        })
                    
                    elif result["type"] == "web":
                        print("🌐 Sending web search results to frontend.")
                        await websocket.send_json({
                            "type": "web",
                            "title": result.get("title", ""),
                            "results": result.get("results", [])
                        })
                    
                    elif result["type"] == "error":
                        session.chat_history.append({"sender": "bot", "text": result["message"]})

            if result["type"] != "web":
                await websocket.send_json(result)

            print("📤 Response sent to frontend.\n")

    except WebSocketDisconnect:
        print("🔴 WebSocket disconnected.")
        if session.chat_history:
            await save_chat_log(user_email, session.chat_history)

# --- End of Original main.py with Integrations ---
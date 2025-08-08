# services/google_calendar_service.py

import os
import datetime
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError 
from dotenv import load_dotenv

# Import database specific definitions
from services.database import GOOGLE_CREDS_COLLECTION

load_dotenv() # Load environment variables

# Define your scopes
SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.freebusy'
]

# --- CORRECTED CREDENTIAL LOADING ---
# Get the path to the client_secrets.json file from the environment variable
CLIENT_SECRETS_FILE_PATH = os.getenv("GOOGLE_CLIENT_SECRETS_FILE") # This is the correct way to get the path

if not CLIENT_SECRETS_FILE_PATH:
    raise ValueError("GOOGLE_CLIENT_SECRETS_FILE environment variable not set. Please set it to the path of your client_secrets.json file.")

# Verify that the file exists at the specified path
if not os.path.exists(CLIENT_SECRETS_FILE_PATH):
    raise FileNotFoundError(f"Client secrets file not found at: {CLIENT_SECRETS_FILE_PATH}. Please check the path in your .env.")

# --- Credential Management with MongoDB ---
async def load_credentials_from_db(db, user_id: str) -> Credentials | None:
    """Loads Google credentials for a user from MongoDB."""
    creds_data = await db[GOOGLE_CREDS_COLLECTION].find_one({"user_id": user_id})

    if creds_data:
        try:
            creds = Credentials(
                token=creds_data['token'],
                refresh_token=creds_data.get('refresh_token'),
                token_uri=creds_data['token_uri'],
                client_id=creds_data['client_id'],
                client_secret=creds_data['client_secret'],
                scopes=creds_data['scopes'],
                expiry=datetime.datetime.fromisoformat(creds_data['expiry']) if 'expiry' in creds_data and creds_data['expiry'] else None
            )
            return creds
        except Exception as e:
            print(f"Error reconstructing credentials for user {user_id}: {e}")
            return None
    return None

async def save_credentials_to_db(db, user_id: str, creds: Credentials):
    """Saves or updates Google credentials for a user in MongoDB."""
    creds_data = {
        "user_id": user_id,
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret, # Encrypt this in production!
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None
    }
    await db[GOOGLE_CREDS_COLLECTION].update_one(
        {"user_id": user_id},
        {"$set": creds_data},
        upsert=True
    )
    print(f"Credentials saved/updated for user: {user_id}")

# --- Authentication Flow for Backend ---
async def get_flow(redirect_uri: str):
    """Initializes the InstalledAppFlow."""
    # This now correctly uses the path loaded from the environment variable
    return InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRETS_FILE_PATH, SCOPES, redirect_uri=redirect_uri
    )

async def refresh_and_get_service(db, user_id: str):
    """
    Attempts to load, refresh, and return a Google Calendar service for a user.
    Returns None if credentials are not available or cannot be refreshed.
    """
    creds = await load_credentials_from_db(db, user_id)

    if not creds:
        print(f"No credentials found for user {user_id}.")
        return None

    if not creds.valid:
        if creds.refresh_token:
            print(f"Refreshing token for user {user_id}...")
            try:
                creds.refresh(GoogleRequest())
                await save_credentials_to_db(db, user_id, creds)
                print(f"Token refreshed and saved for user {user_id}.")
            except Exception as e:
                print(f"Error refreshing token for user {user_id}: {e}")
                # Clear invalid creds to force re-authentication
                await db[GOOGLE_CREDS_COLLECTION].delete_one({"user_id": user_id})
                return None
        else:
            print(f"Credentials invalid and no refresh token for user {user_id}.")
            # Clear invalid creds to force re-authentication
            await db[GOOGLE_CREDS_COLLECTION].delete_one({"user_id": user_id})
            return None
            
    try:
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        print(f"Error building calendar service for user {user_id}: {e}")
        return None

# --- New create_calendar_event function ---
def create_calendar_event(service, event_data: dict, calendar_id: str = 'primary'):
    """
    Creates a new event on the specified Google Calendar.

    Args:
        service: An authorized Google Calendar API service instance.
        event_data (dict): Dictionary containing event details.
                            Expected keys: 'summary', 'start_time', 'end_time' (as datetime objects),
                            optional 'description', 'location'.
        calendar_id (str): The ID of the calendar to create the event on. Defaults to 'primary'.

    Returns:
        dict: The created event resource from Google API, or None on failure.
    """
    # Convert datetime objects to RFC3339 format required by Google API
    # event_data['start_time'] and ['end_time'] should already be datetime objects here
    # coming from the Pydantic model in main.py
    start_time_iso = event_data['start_time'].isoformat()
    end_time_iso = event_data['end_time'].isoformat()

    event = {
        'summary': event_data.get('summary', 'New Event'),
        'location': event_data.get('location'),
        'description': event_data.get('description'),
        'start': {
            'dateTime': start_time_iso,
            'timeZone': 'Africa/Cairo', # Changed from 'UTC' to 'Africa/Cairo'
        },
        'end': {
            'dateTime': end_time_iso,
            'timeZone': 'Africa/Cairo', # Changed from 'UTC' to 'Africa/Cairo'
        },
        # You can add attendees here if you want to support them via the frontend form later
        # 'attendees': [{'email': email} for email in event_data.get('attendees', [])],
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 10},
            ],
        },
    }

    try:
        created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"Event created: {created_event.get('htmlLink')}")
        return created_event
    except HttpError as error:
        print(f"An error occurred while creating event: {error}")
        return None

def update_calendar_event(service, event_id: str, event_data: dict, calendar_id: str = 'primary'):
    
    # Convert datetime objects to RFC3339 format required by Google API
    start_time_iso = event_data['start_time'].isoformat()
    end_time_iso = event_data['end_time'].isoformat()

    event_body = {
        'summary': event_data.get('summary', 'Updated Event'),
        'location': event_data.get('location'),
        'description': event_data.get('description'),
        'start': {
            'dateTime': start_time_iso,
            'timeZone': 'Africa/Cairo', # Changed from 'UTC' to 'Africa/Cairo'
        },
        'end': {
            'dateTime': end_time_iso,
            'timeZone': 'Africa/Cairo', # Changed from 'UTC' to 'Africa/Cairo'
        },
        # Reminders can be updated too, or left as is
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 10},
            ],
        },
    }

    try:
        updated_event = service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event_body
        ).execute()
        print(f"Event updated: {updated_event.get('htmlLink')}")
        return updated_event
    except HttpError as error:
        print(f"An error occurred while updating event {event_id}: {error}")
        return None

# --- NEW: delete_calendar_event function ---
def delete_calendar_event(service, event_id: str, calendar_id: str = 'primary'):
    """
    Deletes an event from the specified Google Calendar.

    Args:
        service: An authorized Google Calendar API service instance.
        event_id (str): The ID of the event to delete.
        calendar_id (str): The ID of the calendar where the event resides. Defaults to 'primary'.

    Returns:
        bool: True if deletion was successful, False otherwise.
    """
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        print(f"Event {event_id} deleted successfully.")
        return True
    except HttpError as error:
        if error.resp.status == 404:
            print(f"Event {event_id} not found: {error}")
        else:
            print(f"An error occurred while deleting event {event_id}: {error}")
        return False

# --- MODIFIED: list_upcoming_events to list events within a specific range ---
def list_upcoming_events(service, time_min: str, time_max: str, max_results: int = 10, calendar_id: str = 'primary'):
    """
    Lists events from Google Calendar within a specified time range.

    Args:
        service: An authorized Google Calendar API service instance.
        time_min (str): The start of the time range (RFC3339 format, e.g., "2025-07-29T00:00:00Z").
        time_max (str): The end of the time range (RFC3339 format, e.g., "2025-07-30T23:59:59Z").
        max_results (int): Maximum number of events to return.
        calendar_id (str): The ID of the calendar to query. Defaults to 'primary'.

    Returns:
        list: A list of event resources from Google API.
    """
    try:
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min, # Now uses the provided time_min
            timeMax=time_max, # Now uses the provided time_max
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        return events
    except Exception as e:
        raise Exception(f"Failed to list events: {e}")

def check_free_busy(service, time_min: str, time_max: str, calendar_ids: list[str]):
    """
    Checks free/busy information for given calendars and time range.
    time_min and time_max should be ISO 8601 strings (e.g., "2025-07-25T09:00:00Z").
    """
    items = [{'id': cal_id} for cal_id in calendar_ids]
    body = {
        "timeMin": time_min,
        "timeMax": time_max,
        "items": items
    }
    
    try:
        response = service.freebusy().query(body=body).execute()
        return response.get('calendars', {})
    except Exception as e:
        raise Exception(f"Failed to check free/busy: {e}")
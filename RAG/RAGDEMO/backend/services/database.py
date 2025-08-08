# services/database.py

import os
from dotenv import load_dotenv

# Assuming your existing client and db are set up in main.py
# If you prefer to define them here and import, you can, but for now
# we'll assume they are defined globally or managed in main.py.
# We will get them via get_database() from main.py
# from main import client, db # This is generally bad practice due to circular imports.
# Better to pass db object or use FastAPI dependency injection for db connection.

# Collection names
USERS_COLLECTION = "users"
GOOGLE_CREDS_COLLECTION = "google_calendar_credentials"

# Pydantic models (can be moved to a separate models.py if desired)
from pydantic import BaseModel
from typing import Optional, List

class UserInDB(BaseModel):
    # For MongoDB, _id is usually an ObjectId, but Pydantic can handle str for now
    # when converting from dict. In FastAPI, using str for input is fine.
    id: Optional[str] = None # Will be set by MongoDB as _id
    username: str
    passkey: str # In production, this should be a hashed password, not plaintext!
    google_calendar_connected: bool = False # Flag to indicate if Google Calendar is linked

    class Config:
        populate_by_name = True # Allows field name aliasing
        json_schema_extra = {
            "example": {
                "username": "testuser",
                "passkey": "testpass123"
            }
        }

class GoogleCalendarCredsInDB(BaseModel):
    # This model represents how credentials will be stored in MongoDB
    user_id: str # This should be the _id (as string) of the user from your users collection
    token: str
    refresh_token: Optional[str]
    token_uri: str
    client_id: str
    client_secret: str # Remember to encrypt this in production!
    scopes: List[str]
    expiry: str # ISO format datetime string

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "user_id": "60c7b0d9f2e3a4b5c6d7e8f0",
                "token": "ya29.a0AR...token",
                "refresh_token": "1//0ge...refresh_token",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "your_client_id.apps.googleusercontent.com",
                "client_secret": "your_client_secret",
                "scopes": ["https://www.googleapis.com/auth/calendar.events"],
                "expiry": "2025-07-25T18:00:00Z"
            }
        }
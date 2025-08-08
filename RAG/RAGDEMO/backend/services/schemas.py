# services/schemas.py
from pydantic import BaseModel, Field # Import Field for default_factory (good practice)
from datetime import datetime
from typing import Optional, List

# Base model for common event fields
class CalendarEventBase(BaseModel):
    summary: str
    start_time: datetime
    end_time: datetime
    description: Optional[str] = None
    location: Optional[str] = None
    # Add other common fields if needed, e.g., attendees: Optional[List[str]] = None

# Model for creating a new event
class CalendarEventCreate(CalendarEventBase):
    pass
    # No additional fields needed here, inherits from base

# Model for updating an event
class CalendarEventUpdate(CalendarEventBase):
    # For a PUT request, typically all fields are expected in the body
    # If you wanted to support partial updates (PATCH method),
    # you would make all fields Optional here:
    # summary: Optional[str] = None
    # start_time: Optional[datetime] = None
    # ...
    pass


class FreeBusyRequest(BaseModel):
    time_min: str # ISO format, e.g., "2025-07-25T09:00:00Z"
    time_max: str # ISO format, e.g., "2025-07-26T00:00:00Z"
    calendar_ids: List[str] = Field(default_factory=lambda: ['primary']) # List of calendar IDs to check
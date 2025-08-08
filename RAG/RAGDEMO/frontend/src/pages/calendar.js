import React, { useState, useEffect } from "react";
import { RefreshCcw } from 'lucide-react';

function UserCalendar() {
    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [isConnected, setIsConnected] = useState(false);

    const [areEventsListOpen, setAreEventsListOpen] = useState(true);

    const userId = localStorage.getItem('user_id');
    const [showAddEventForm, setShowAddEventForm] = useState(false);

    // --- NEW STATE FOR EDIT FUNCTIONALITY ---
    const [showEditEventForm, setShowEditEventForm] = useState(false);
    const [currentEventToEdit, setCurrentEventToEdit] = useState(null); // Stores the event object being edited

    const [newEvent, setNewEvent] = useState({
        summary: '',
        start_time: '',
        end_time: '',
        description: '',
        location: ''
    });

    const API_BASE_URL = 'http://localhost:8001'; // Define your API base URL

    // Function to initiate the Google Calendar connection (OAuth flow)
    const handleConnectGoogleCalendar = async () => {
        if (!userId) {
            setError("User ID not found. Please log in.");
            return;
        }
        setLoading(true);
        setError(null);

        try {
            const response = await fetch(`${API_BASE_URL}/auth/google/initiate`, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'X-User-ID': userId,
                },
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to initiate Google authentication.');
            }

            const data = await response.json();
            const authorizationUrl = data.authorization_url;

            window.location.href = authorizationUrl;

        } catch (err) {
            console.error("Error initiating Google Calendar connection:", err);
            setError(err.message || "Could not initiate Google Calendar connection.");
            setLoading(false);
        }
    };

    // Function to fetch actual calendar events from your backend
    const fetchCalendarEvents = async () => {
        setLoading(true);
        setError(null);

        if (!userId) {
            setError("User ID not found. Please log in.");
            setLoading(false);
            return;
        }

        const calendarConnectedFlag = localStorage.getItem(`google_calendar_connected_${userId}`);
        setIsConnected(calendarConnectedFlag === 'true');

        if (calendarConnectedFlag !== 'true') {
            setError("Google Calendar not connected. Please click 'Connect'.");
            setLoading(false);
            return;
        }

        try {
            const response = await fetch(`${API_BASE_URL}/api/google-calendar-events`, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'X-User-ID': userId,
                },
            });

            if (!response.ok) {
                const errorData = await response.json();
                if (response.status === 401 || errorData.detail === "Google Calendar not connected for this user") {
                    setIsConnected(false);
                    setError("Google Calendar not connected. Please click 'Connect' to re-authenticate.");
                    localStorage.removeItem(`google_calendar_connected_${userId}`);
                    return;
                }
                throw new Error(errorData.detail || 'Failed to fetch events');
            }

            const data = await response.json();

            let fetchedEvents = [];
            if (Array.isArray(data)) {
                fetchedEvents = data;
            } else if (data && data.events && Array.isArray(data.events)) {
                fetchedEvents = data.events;
            } else if (data && data.message && !data.events) {
                setEvents([]);
                setError(null); // No error, just no events
                setLoading(false);
                return;
            }
            
            // Map to a format suitable for your current list rendering
            // Important: Preserve the original event object in `resource` to use its `id` for edit/delete
            const formattedEvents = fetchedEvents.map(event => ({
                title: event.summary,
                start: new Date(event.start_time),
                end: new Date(event.end_time),
                allDay: false, // Assuming events are not all-day by default
                resource: event // Store the original event object for access to its ID and other details
            }));

            setEvents(formattedEvents);

        } catch (err) {
            console.error("Error fetching calendar events:", err);
            setError(err.message || "Could not load calendar events.");
        } finally {
            setLoading(false);
        }
    };

    const handleNewEventChange = (e) => {
        const { name, value } = e.target;
        setNewEvent(prev => ({ ...prev, [name]: value }));
    };

    const handleAddEventSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError(null);

        if (!userId) {
            setError("User ID not found. Please log in.");
            setLoading(false);
            return;
        }

        try {
            const startDateTime = new Date(newEvent.start_time).toISOString();
            const endDateTime = new Date(newEvent.end_time).toISOString();

            const eventToSend = {
                ...newEvent,
                start_time: startDateTime,
                end_time: endDateTime
            };

            const response = await fetch(`${API_BASE_URL}/api/google-calendar-events/create`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-User-ID': userId,
                },
                body: JSON.stringify(eventToSend),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to create event.');
            }

            const data = await response.json();
            console.log("Event created successfully:", data);

            await fetchCalendarEvents(); // Re-fetch all events to include the new one
            setShowAddEventForm(false);
            // Reset form
            setNewEvent({
                summary: '',
                start_time: '',
                end_time: '',
                description: '',
                location: ''
            });

        } catch (err) {
            console.error("Error creating event:", err);
            setError(err.message || "Could not create event.");
        } finally {
            setLoading(false);
        }
    };

    // --- NEW: Handle Edit Click ---
    const handleEditClick = (eventData) => {
        // `eventData` here is the `resource` from your mapped event, which is the original backend event object
        setCurrentEventToEdit(eventData);
        setShowEditEventForm(true);
    };

    // --- NEW: Handle Edit Event Success ---
    const handleEditEventSuccess = () => {
        setShowEditEventForm(false);
        setCurrentEventToEdit(null); // Clear the event being edited
        fetchCalendarEvents(); // Re-fetch events to show the updated one
    };

    // --- NEW: Handle Delete Event ---
    const handleDeleteEvent = async (eventId) => {
        if (!userId) {
            alert("User not authenticated. Please log in.");
            return;
        }
        if (window.confirm("Are you sure you want to delete this event?")) {
            setLoading(true);
            setError(null);
            try {
                const response = await fetch(`${API_BASE_URL}/api/google-calendar-events/${eventId}`, {
                    method: 'DELETE',
                    headers: {
                        'X-User-ID': userId,
                        'Accept': 'application/json',
                    },
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || 'Failed to delete event.');
                }

                alert("Event deleted successfully!");
                fetchCalendarEvents(); // Re-fetch events to update the list
            } catch (err) {
                console.error("Error deleting event:", err);
                setError(err.message || "Failed to delete event.");
            } finally {
                setLoading(false);
            }
        }
    };

    useEffect(() => {
        if (userId) {
            const initialConnectedState = localStorage.getItem(`google_calendar_connected_${userId}`) === 'true';
            setIsConnected(initialConnectedState);
            fetchCalendarEvents();
        } else {
            setLoading(false);
            setError("Please log in to view your calendar.");
        }
    }, [userId]);


    // Render logic based on state
    if (loading) {
        return <div className="calendar-status">Loading calendar events...</div>;
    }

    if (!isConnected || error) {
        return (
            <div className="calendar-not-connected">
                {error && <p className="calendar-error-message">{error}</p>}
                <p>Please connect your Google Calendar to view and manage events.</p>
                <button onClick={handleConnectGoogleCalendar} className="connect-calendar-button">
                    Connect
                </button>
            </div>
        );
    }

    return (
        <div className="user-calendar-container">
            {/* "Add New Event" button */}
            <button
                onClick={() => setShowAddEventForm(!showAddEventForm)}
                className="add-event-button"
            >
                {showAddEventForm ? 'Hide Add Event Form' : 'Add New Event'}
            </button>

            {/* Add Event Form */}
            {showAddEventForm && (
                <form onSubmit={handleAddEventSubmit} className="add-event-form" style={{
                    border: '1px solid #ddd',
                    padding: '15px',
                    borderRadius: '8px',
                    marginTop: '15px',
                    backgroundColor: '#f9f9f9'
                }}>
                    <div style={{ marginBottom: '10px' }}>
                        <label>Summary:</label>
                        <input type="text" name="summary" value={newEvent.summary} onChange={handleNewEventChange} required style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }} />
                    </div>
                    <div style={{ marginBottom: '10px' }}>
                        <label>Start Time:</label>
                        <input type="datetime-local" name="start_time" value={newEvent.start_time} onChange={handleNewEventChange} required style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }} />
                    </div>
                    <div style={{ marginBottom: '10px' }}>
                        <label>End Time:</label>
                        <input type="datetime-local" name="end_time" value={newEvent.end_time} onChange={handleNewEventChange} required style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }} />
                    </div>
                    <div style={{ marginBottom: '10px' }}>
                        <label>Description:</label>
                        <textarea name="description" value={newEvent.description} onChange={handleNewEventChange} style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }}></textarea>
                    </div>
                    <div style={{ marginBottom: '10px' }}>
                        <label>Location:</label>
                        <input type="text" name="location" value={newEvent.location} onChange={handleNewEventChange} style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }} />
                    </div>
                    <button type="submit" style={{ padding: '10px 20px', backgroundColor: '#28a745', color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer' }}>Create Event</button>
                    <button type="button" onClick={() => setShowAddEventForm(false)} style={{ padding: '10px 20px', backgroundColor: '#dc3545', color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer', marginLeft: '10px' }}>Cancel</button>
                </form>
            )}

            {/* --- NEW: Edit Event Form/Modal --- */}
            {showEditEventForm && currentEventToEdit && (
                <EditEventForm
                    event={currentEventToEdit}
                    onClose={() => {setShowEditEventForm(false); setCurrentEventToEdit(null);}}
                    onSuccess={handleEditEventSuccess}
                    userId={userId}
                    API_BASE_URL={API_BASE_URL}
                />
            )}

            <div
                className="calendar-events-collapsible-header"
                onClick={() => setAreEventsListOpen(!areEventsListOpen)}
            >
                <span>Upcoming Events</span>
                <div className="header-icons-group">
                    {areEventsListOpen && (
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                fetchCalendarEvents();
                            }}
                            className="refresh-icon-button"
                            aria-label="Refresh events"
                        >
                            <RefreshCcw size={18} />
                        </button>
                    )}
                    <span className="dropdown-arrow">{areEventsListOpen ? "▲" : "▼"}</span>
                </div>
            </div>

            {areEventsListOpen && (
                <div className="calendar-display-area" style={{ margin: '10px 0', border: '1px solid #ccc', borderRadius: '8px' }}>
                    {events.length > 0 ? (
                        <ul className="event-list">
                            {events.map((event, index) => (
                                // Crucially, use event.resource.id for the key if available, otherwise fallback to index
                                <li key={event.resource?.id || index} className="event-item" style={{
                                    borderBottom: '1px solid #eee',
                                    padding: '10px 0',
                                    display: 'flex',
                                    flexDirection: 'column',
                                    gap: '5px'
                                }}>
                                    <strong>{event.title}</strong>
                                    <p style={{ margin: 0, fontSize: '0.9em', color: '#555' }}>
                                        {new Date(event.start).toLocaleString(undefined, {
                                            year: 'numeric',
                                            month: 'short',
                                            day: 'numeric',
                                            hour: 'numeric',
                                            minute: 'numeric',
                                            hour12: true
                                        })} - {new Date(event.end).toLocaleString(undefined, {
                                            hour: 'numeric',
                                            minute: 'numeric',
                                            hour12: true
                                        })}
                                    </p>
                                    {event.resource?.location && <p style={{ margin: 0, fontSize: '0.9em', color: '#777' }}>Location: {event.resource.location}</p>}
                                    {event.resource?.description && <p style={{ margin: 0, fontSize: '0.9em', color: '#777' }}>Description: {event.resource.description}</p>}
                                    {event.resource?.html_link && <p style={{ margin: 0, fontSize: '0.9em' }}><a href={event.resource.html_link} target="_blank" rel="noopener noreferrer">View on Google Calendar</a></p>}
                                    
                                    {/* --- NEW: Edit and Delete Buttons --- */}
                                    <div style={{ marginTop: '10px' }}>
                                        <button
                                            onClick={() => handleEditClick(event.resource)}
                                            style={{
                                                padding: '8px 15px',
                                                backgroundColor: '#007bff',
                                                color: 'white',
                                                border: 'none',
                                                borderRadius: '5px',
                                                cursor: 'pointer',
                                                marginRight: '10px'
                                            }}
                                        >
                                            Edit
                                        </button>
                                        <button
                                            onClick={() => handleDeleteEvent(event.resource.id)}
                                            style={{
                                                padding: '8px 15px',
                                                backgroundColor: '#dc3545',
                                                color: 'white',
                                                border: 'none',
                                                borderRadius: '5px',
                                                cursor: 'pointer'
                                            }}
                                        >
                                            Delete
                                        </button>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className="no-events-message">No upcoming events found for your connected calendar.</p>
                    )}
                </div>
            )}
        </div>
    );
}

export default UserCalendar;



function EditEventForm({ event, onClose, onSuccess, userId, API_BASE_URL }) {
    // Initialize form states with current event data
    const [summary, setSummary] = useState(event.summary || '');
    // Format dates for datetime-local input (YYYY-MM-DDTHH:mm)
    const [startTime, setStartTime] = useState(event.start_time ? new Date(event.start_time).toISOString().slice(0, 16) : '');
    const [endTime, setEndTime] = useState(event.end_time ? new Date(event.end_time).toISOString().slice(0, 16) : '');
    const [description, setDescription] = useState(event.description || '');
    const [location, setLocation] = useState(event.location || '');
    const [formError, setFormError] = useState(null);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError(null);

        // Basic validation
        if (!summary || !startTime || !endTime) {
            setFormError("Summary, Start Time, and End Time are required.");
            return;
        }

        try {
            const startDateTime = new Date(startTime).toISOString();
            const endDateTime = new Date(endTime).toISOString();

            const eventToUpdate = {
                summary,
                start_time: startDateTime,
                end_time: endDateTime,
                description,
                location,
            };

            const response = await fetch(`${API_BASE_URL}/api/google-calendar-events/${event.id}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-User-ID': userId,
                },
                body: JSON.stringify(eventToUpdate),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to update event.');
            }

            const data = await response.json();
            console.log("Event updated successfully:", data);
            alert('Event updated successfully!');
            onSuccess(); // Call the parent's success handler to re-fetch events
        } catch (err) {
            console.error("Error updating event:", err);
            setFormError(err.message || "Could not update event.");
        }
    };

    return (
        <div className="edit-event-form" style={{
            border: '1px solid #ddd',
            padding: '15px',
            borderRadius: '8px',
            marginTop: '15px',
            backgroundColor: '#f9f9f9',
            position: 'relative', // For close button positioning
            marginBottom: '20px'
        }}>
            <h2>Edit Event</h2>
            {formError && <p style={{ color: 'red' }}>{formError}</p>}
            <form onSubmit={handleSubmit}>
                <div style={{ marginBottom: '10px' }}>
                    <label>Summary:</label>
                    <input type="text" value={summary} onChange={(e) => setSummary(e.target.value)} required style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }} />
                </div>
                <div style={{ marginBottom: '10px' }}>
                    <label>Start Time:</label>
                    <input type="datetime-local" value={startTime} onChange={(e) => setStartTime(e.target.value)} required style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }} />
                </div>
                <div style={{ marginBottom: '10px' }}>
                    <label>End Time:</label>
                    <input type="datetime-local" value={endTime} onChange={(e) => setEndTime(e.target.value)} required style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }} />
                </div>
                <div style={{ marginBottom: '10px' }}>
                    <label>Description:</label>
                    <textarea value={description} onChange={(e) => setDescription(e.target.value)} style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }}></textarea>
                </div>
                <div style={{ marginBottom: '10px' }}>
                    <label>Location:</label>
                    <input type="text" value={location} onChange={(e) => setLocation(e.target.value)} style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }} />
                </div>
                <button type="submit" style={{ padding: '10px 20px', backgroundColor: '#007bff', color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer' }}>Update Event</button>
                <button type="button" onClick={onClose} style={{ padding: '10px 20px', backgroundColor: '#6c757d', color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer', marginLeft: '10px' }}>Cancel</button>
            </form>
        </div>
    );
}


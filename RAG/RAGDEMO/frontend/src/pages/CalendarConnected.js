// src/components/CalendarConnected.js (or similar path)
import React, { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

function CalendarConnected() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();

    useEffect(() => {
        const status = searchParams.get('status');
        const userId = searchParams.get('user_id');
        const message = searchParams.get('message'); // For error messages

        if (userId) {
            if (status === 'success') {
                localStorage.setItem(`google_calendar_connected_${userId}`, 'true');
                console.log(`Google Calendar connected successfully for user ${userId}.`);
                // Optionally, display a success message briefly before redirecting
            } else { // status === 'error'
                localStorage.setItem(`google_calendar_connected_${userId}`, 'false');
                console.error(`Google Calendar connection failed for user ${userId}: ${message || 'Unknown error'}`);
                // Optionally, display an error message
            }
        } else {
            console.error("User ID not found in callback URL.");
        }

        // Redirect back to the main chat page (or dashboard) after a short delay
        // This gives the localStorage time to update and the user a brief moment to see any messages.
        const redirectTimeout = setTimeout(() => {
            navigate('/chat'); // Or wherever your main chat/dashboard page is
        }, 1000); // Redirect after 1 second

        return () => clearTimeout(redirectTimeout); // Clean up the timeout
    }, [navigate, searchParams]);

    return (
        <div style={{ padding: '50px', textAlign: 'center' }}>
            <h2>Processing Google Calendar Connection...</h2>
            <p>You will be redirected shortly.</p>
            {searchParams.get('status') === 'success' && <p style={{color: 'green'}}>Connection successful!</p>}
            {searchParams.get('status') === 'error' && <p style={{color: 'red'}}>Connection failed: {searchParams.get('message')}</p>}
        </div>
    );
}

export default CalendarConnected;
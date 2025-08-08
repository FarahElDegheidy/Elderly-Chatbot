import React, { useState, useEffect } from 'react';
import { Clock } from 'react-feather';

// Helper function to convert 24-hour time to AM/PM format
const formatToAmPm = (timeString) => {
  if (!timeString) return '';
  
  const [hours, minutes] = timeString.split(':').map(Number);
  const ampm = hours >= 12 ? 'م' : 'ص'; // 'م' for PM, 'ص' for AM
  const formattedHours = hours % 12 || 12; // The hour '0' becomes '12' for midnight
  
  return `${formattedHours}:${String(minutes).padStart(2, '0')} ${ampm}`;
};

const PrayerTimesViewer = ({ compact = false }) => {
  const [prayerTimes, setPrayerTimes] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [nextPrayer, setNextPrayer] = useState(null);
  const [timeToNext, setTimeToNext] = useState(null);

  useEffect(() => {
    const fetchPrayerTimes = async () => {
      try {
        // Fetch prayer times for Cairo, Egypt
        const response = await fetch('https://api.aladhan.com/v1/timingsByCity?city=Cairo&country=Egypt&method=5');
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        const timings = data.data.timings;

        // Create a new object with the times formatted in AM/PM
        const formattedTimes = {};
        for (const prayer in timings) {
          formattedTimes[prayer] = formatToAmPm(timings[prayer]);
        }
        setPrayerTimes(formattedTimes);

        // Logic to find the next prayer and time remaining
        // NOTE: We must use the original 24-hour times for calculations
        const now = new Date();
        const prayerNames = ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha'];
        let next = null;

        for (const name of prayerNames) {
          const [hours, minutes] = timings[name].split(':').map(Number);
          const prayerTime = new Date(now.getFullYear(), now.getMonth(), now.getDate(), hours, minutes);
          
          if (prayerTime > now) {
            // Set the next prayer name and its formatted time
            next = { name, time: formattedTimes[name] }; 
            const diff = prayerTime.getTime() - now.getTime();
            const minutesLeft = Math.floor(diff / (1000 * 60));
            setTimeToNext(`${minutesLeft} min`);
            break;
          }
        }
        setNextPrayer(next);

      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    fetchPrayerTimes();
  }, []);

  if (loading) {
    return <div className="prayer-times-loading">Loading prayer times...</div>;
  }

  if (error) {
    return <div className="prayer-times-error">Error: {error}</div>;
  }

  // If in compact mode, show only the next prayer
  if (compact) {
    return (
      <div className="compact-prayer-times">
        {nextPrayer ? (
          <div>
            Next: {nextPrayer.name} ({timeToNext})
          </div>
        ) : (
          <div>No prayer times found.</div>
        )}
      </div>
    );
  }

  // If not in compact mode, show the full list
  return (
    <div className="full-prayer-times-viewer">
      <h2>مواعيد الصلاة في القاهرة</h2>
      {prayerTimes ? (
        <ul className="prayer-times-list">
          <li><strong>الفجر:</strong> {prayerTimes.Fajr}</li>
          <li><strong>الشروق:</strong> {prayerTimes.Sunrise}</li>
          <li><strong>الظهر:</strong> {prayerTimes.Dhuhr}</li>
          <li><strong>العصر:</strong> {prayerTimes.Asr}</li>
          <li><strong>المغرب:</strong> {prayerTimes.Maghrib}</li>
          <li><strong>العشاء:</strong> {prayerTimes.Isha}</li>
        </ul>
      ) : (
        <div>No prayer times available.</div>
      )}
    </div>
  );
};

export default PrayerTimesViewer;
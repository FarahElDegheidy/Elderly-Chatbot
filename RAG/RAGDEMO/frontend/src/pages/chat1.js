import React, { useState, useEffect, useRef } from "react";
import "./chat1.css";
import "./calendar.css";
import { FontSizeSelector, ComfortModeToggle } from "./font";
import { BookOpen,Bot, ThumbsUp, User } from "lucide-react";
import { Heart, ThumbsDown, AlertTriangle, Trash2, Plus, Edit3, UserCircle2, Menu, Info, Copy, ChevronDown, ChevronUp}  from "lucide-react";
import { Clock, X } from "react-feather";
import UserCalendar from "./calendar";
import { FcGoogle } from "react-icons/fc";
import QuranViewer from "./Quran";
import PrayerTimesViewer from "./prayertime";

function ParsedMessage({ text, sourceUrl }) {
    console.log("Source URL:", sourceUrl);

    // Regex to find bold text, markdown links, and plain URLs in parentheses
    const boldRegex = /\*\*(.*?)\*\*/g;
    const markdownLinkRegex = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
    const plainUrlInParensRegex = /\((https?:\/\/[^\s)]+)\)/g;

    const containsHTML = /<a\s|<div\s|<br\s*\/?>|<strong>/i.test(text);

    if (containsHTML) {
        return <div dangerouslySetInnerHTML={{ __html: text }} />;
    }

    // Helper function to split a string by a regex and map the parts
    const splitByRegex = (input, regex, callback) => {
        let parts = [];
        let lastIndex = 0;
        let match;
        while ((match = regex.exec(input)) !== null) {
            const [fullMatch, ...captures] = match;
            const index = match.index;
            if (index > lastIndex) {
                parts.push(input.substring(lastIndex, index));
            }
            parts.push(callback(fullMatch, ...captures, index));
            lastIndex = index + fullMatch.length;
        }
        if (lastIndex < input.length) {
            parts.push(input.substring(lastIndex));
        }
        return parts;
    };

    let result = [text];

    // First pass: Parse bold text
    result = result.flatMap(part => {
        if (typeof part !== 'string') return part;
        return splitByRegex(part, boldRegex, (fullMatch, boldText, index) => <strong key={`bld-${index}`}>{boldText}</strong>);
    });

    // Second pass: Parse markdown links
    result = result.flatMap(part => {
        if (typeof part !== 'string') return part;
        return splitByRegex(part, markdownLinkRegex, (fullMatch, title, url, index) => {
            const displayTitle = title.replace(/\|/g, " - ");
            return (
                <a
                    key={`md-${index}`}
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: "#007bff", textDecoration: "underline" }}
                >
                    {displayTitle}
                </a>
            );
        });
    });

    // Third pass: Parse plain URLs in parentheses
    result = result.flatMap(part => {
        if (typeof part !== 'string') return part;
        return splitByRegex(part, plainUrlInParensRegex, (fullMatch, url, index) => (
            <a
                key={`plain-${index}`}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: "#007bff", textDecoration: "underline" }}
            >
                {url}
            </a>
        ));
    });

    return (
        <div style={{ position: 'relative' }}>
            <span>{result}</span>
            {sourceUrl && (
                <a
                    href={sourceUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="source-icon-container"
                >
                    <img
                        src={`https://www.google.com/s2/favicons?domain=${new URL(sourceUrl).hostname}`}
                        alt="Source"
                        className="source-icon"
                    />
                </a>
            )}
        </div>
    );
}
function Chat() {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState("");
    const [suggestions, setSuggestions] = useState([]);
    const [expectingChoice, setExpectingChoice] = useState(false);
    const [ws, setWs] = useState(null);
    const [currentRecipeTitle, setCurrentRecipeTitle] = useState(null);
    const [favourites, setFavourites] = useState([]);
    const [fullRecipeContent, setFullRecipeContent] = useState({});
    const [isRecording, setIsRecording] = useState(false);
    const [mode, setMode] = useState(null); // 'text' or 'voice'
    const [botSpeaking, setBotSpeaking] = useState(false);
    const [showThinking, setShowThinking] = useState(false);
    const [typingText, setTypingText] = useState(null);
    const [selectedFavourite, setSelectedFavourite] = useState(null);
    const [chatLogs, setChatLogs] = useState([]);
    const [selectedChatLog, setSelectedChatLog] = useState(null);
    const [userPrefs, setUserPrefs] = useState({ name: "", likes: [], dislikes: [], allergies: [] });
    const [profileLoaded, setProfileLoaded] = useState(false);
    const [showStarters, setShowStarters] = useState(true);
    const [isHistoryCollapsed, setIsHistoryCollapsed] = useState(false);
    const [awaitingResponse, setAwaitingResponse] = useState(false);
    const [wsConnected, setWsConnected] = useState(false);
    const [suppressUserMessage, setSuppressUserMessage] = useState(false);
    const [copyFeedback, setCopyFeedback] = useState("");
    const [isRecipeCollapsed, setIsRecipeCollapsed] = useState(false);
    const [copiedMessageId, setCopiedMessageId] = useState(null); // New state variable


    // New states for mobile off-canvas panels
    const [isHistoryOpenMobile, setIsHistoryOpenMobile] = useState(false);
    const [isInfoOpenMobile, setIsInfoOpenMobile] = useState(false);

    // NEW STATE FOR GOOGLE CALENDAR CONNECTION STATUS
    const [googleCalendarConnected, setGoogleCalendarConnected] = useState(false);
    const [showFullQuranViewer, setShowFullQuranViewer] = useState(false);
    const [showFullPrayerTimes, setShowFullPrayerTimes] = useState(false);


    const mediaRecorderRef = useRef(null);
    const recordedChunksRef = useRef([]);
    const messageListRef = useRef(null);

    // Effect for WebSocket auto-reconnect
    useEffect(() => {
        if (!wsConnected && mode) {
            const reconnectTimeout = setTimeout(() => {
                console.log("🔄 Attempting auto-reconnect...");
                connectWebSocket();
            }, 0); //  delay

            return () => clearTimeout(reconnectTimeout);
        }
    }, [wsConnected, mode]);

    // Effect for initial data fetching
    useEffect(() => {
        const email = localStorage.getItem("userEmail");
        const userId = localStorage.getItem("user_id"); // Get user_id

        if (!email) return;

        fetchFavourites();
        fetchChatLogs();
        fetchUserProfile();

        // Check Google Calendar connection status on load
        if (userId) {
            const isConnectedFlag = localStorage.getItem(`google_calendar_connected_${userId}`) === 'true';
            setGoogleCalendarConnected(isConnectedFlag);
        }
    }, []);

    // Effect to manage body overflow for mobile off-canvas panels
    useEffect(() => {
        const isMobile = window.innerWidth < 768;
        if (isMobile && (isHistoryOpenMobile || isInfoOpenMobile)) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = 'hidden'; // Keep hidden to allow #chatbot-container to manage its own overflow
        }
    }, [isHistoryOpenMobile, isInfoOpenMobile]);

    // Effect to handle layout changes on resize
    useEffect(() => {
        const handleResize = () => {
            if (window.innerWidth >= 768) {
                // On desktop, ensure mobile panels are closed and history is not collapsed by mobile state
                setIsHistoryOpenMobile(false);
                setIsInfoOpenMobile(false);
                // isHistoryCollapsed will be managed by its own toggle on desktop
            } else {
                // On mobile, ensure desktop collapse state doesn't interfere with off-canvas
                setIsHistoryCollapsed(false);
            }
        };

        window.addEventListener('resize', handleResize);
        handleResize(); // Call on mount to set initial state
        return () => window.removeEventListener('resize', handleResize);
    }, []);


    const connectWebSocket = () => {
        const userId = localStorage.getItem("user_id"); // Ensure userId is available here
        if (!userId) {
            console.error("User ID not found in localStorage. Cannot establish WebSocket connection.");
            // Optionally, handle this error more gracefully, e.g., redirect to login
            return;
        }
        const socket = new WebSocket(`ws://localhost:8001/ws/${userId}`);

        socket.onopen = () => {
            const email = localStorage.getItem("userEmail");
            const userId = localStorage.getItem("user_id"); // Get user_id for calendar status check
            const isCalendarConnected = localStorage.getItem(`google_calendar_connected_${userId}`) === 'true'; // Check the flag

            // Send email, mode, and google_calendar_connected status to backend
            socket.send(JSON.stringify({ email, mode, google_calendar_connected: isCalendarConnected }));
            setWsConnected(true);
        };

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                if (data.type === "error") {
                    setShowThinking(false);
                    setAwaitingResponse(false);
                    setTypingText(null);
                    setMessages((prev) => [
                        ...prev,
                        { sender: "system", text: data.message }
                    ]);
                    return;
                }

                if (data.type === "reconnect") {
                    setShowThinking(false);
                    setAwaitingResponse(false);
                    setTypingText(null);
                    setWsConnected(false); // shows the reconnect UI
                    setMessages((prev) => [
                        ...prev,
                        { sender: "system", text: data.message }
                    ]);
                    return;
                }

                if (data.type === "suggestions") {
                    setSuggestions(data.suggestions);
                    setExpectingChoice(true);
                    setShowThinking(true);
                    setMessages((prev) => [
                        ...prev,
                        { sender: "bot", text: data.message || "اختر وصفة من الخيارات التالية:" }
                    ])
                    return;

                } else if (data.type === "response") {
                    setShowThinking(false);
                    const fullMessage = {
                        id: Date.now(), // Unique ID for keying in React
                        sender: 'bot',
                        text: data.message,
                        sourceUrl: data.sourceUrl // <-- Add this line to capture the URL
                    };
                    animateTyping(fullMessage);
                    setAwaitingResponse(false);
                    // just in case there's no TTS
                    if (mode === "voice") {
                        setBotSpeaking(true);
                        playBotSpeech(data.message);
                    }
                    setExpectingChoice(false);
                    setSuggestions([]);
                    if (data.selected_title && data.full_recipe) {
                        setCurrentRecipeTitle(data.selected_title);
                        setFullRecipeContent(prev => ({ ...prev, [data.selected_title]: data.full_recipe }));
                    }
                    return;
                }

                if (data.type === "video") {
                    setShowThinking(false);
                    setAwaitingResponse(false);

                    const videos = data.videos || [];

                    const videoText = `
                        <div class="video-wrapper">
                          <div class="video-grid">
                            ${videos.map((v) => {
                        const videoId = v.url.split("v=")[1]?.split("&")[0];
                        const thumbnail = `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;

                        return `
                              <div class="video-card">
                                <a href="${v.url}" target="_blank" class="video-thumb-link">
                                  <img src="${thumbnail}" alt="Thumbnail" class="video-thumb"/>
                                  <div class="video-caption">${v.title}</div>
                                </a>
                              </div>
                            `;
                    }).join("")}
                          </div>
                        </div>
                    `;

                    setMessages((prev) => [
                        ...prev,
                        { sender: "bot", text: videoText }
                    ])


                    // 🧼 Reset suppression flag
                    setSuppressUserMessage(false);
                    return;
                }

                if (data.type === "web") {
                    console.log("Web results received:", data.results);
                    setShowThinking(false);
                    setAwaitingResponse(false);

                    const seen = new Set();
                    const filtered = (data.results || []).filter((res) => {
                        const title = res?.title?.trim();
                        const snippet = res?.snippet?.trim();
                        const link = res?.link?.trim();
                        const isValid = title && snippet && link && !seen.has(title);
                        if (isValid) {
                            seen.add(title);
                            return true;
                        }
                        return false;
                    });


                    const links = filtered.map((result) => {
                        return `
                            <div style="background-color:#374151;padding:16px;border-radius:16px;margin-bottom:12px;box-shadow:0 4px 6px rgba(146, 190, 234, 0.1);direction: rtl;text-align: right;">
                                <a href="${result.link}"
                                  style="
                                    display: block;
                                    text-align: right;
                                    direction: rtl;
                                    width = 100%;
                                    color: #60a5fa;
                                    font-weight: 600;
                                    font-size: 16px;
                                    text-decoration: none;
                                    transition: all 0.2s ease-in-out;
                                    border-bottom: 1px dashed #60a5fa;
                                  "
                                  onmouseover="this.style.color='#93c5fd'; this.style.borderBottomColor='#93c5fd'"
                                  onmouseout="this.style.color='#60a5fa'; this.style.borderBottomColor='#60a5fa'"
                                >
                                    ${result.title}
                                </a>
                                <p style="color:#d1d5db;font-size:14px;margin-top:4px;">${result.snippet}</p>
                            </div>
                        `;
                    }).join("").trim();

                    const webSearchText = `
                        <div style="margin-top:3px;">
                            ${links.length > 0 ? links : "<p>لم يتم العثور على نتائج مناسبة.</p>"}
                        </div>
                    `;

                    setMessages((prev) => [
                        ...prev,
                        { sender: "bot", text: webSearchText }
                    ]);
                    return;
                }

                if (data.selected_title && data.full_recipe) {
                    setCurrentRecipeTitle(data.selected_title);
                    setFullRecipeContent(prev => ({ ...prev, [data.selected_title]: data.full_recipe }));
                    setIsRecipeCollapsed(false); // <--- IMPORTANT: Expand recipe when a new one arrives
                }

            } catch (e) {
                console.error("WebSocket message parsing error:", e);
                handleCriticalError("An unexpected error occurred. You will be redirected to the homepage.");
            }
        };


        socket.onclose = () => {
            console.warn("WebSocket connection closed.");
            setWsConnected(false);
            setShowThinking(false);
            setAwaitingResponse(false);

        };

        setWs(socket);
    };


    useEffect(() => {
        messageListRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, suggestions, typingText]);

    const handleCriticalError = (message = "You're out of chats for today, please come back later! You will be logged out and returned to the homepage.") => {
        // Using a custom modal/message box would be better than alert in a real app
        // For this example, we'll keep the alert as per original, but note the best practice.
        alert(message);
        localStorage.removeItem("userEmail");
        window.location.href = "/";
    };

    // Effect to load selected chat log into current messages
    useEffect(() => {
    // Check if selectedChatLog exists and is an array
    if (selectedChatLog && Array.isArray(selectedChatLog)) {
        setMessages(selectedChatLog); // <--- CHANGE IS HERE!
        setShowStarters(false); // Hide starters when a past chat is loaded
    } else {
        // Optionally clear messages if no chat is selected (e.g., on new chat)
        setMessages([]);
        }
    }, [selectedChatLog]); // This effect runs whenever selectedChatLog changes

    const timeoutRef = useRef(null);
    const sendMessage = (messageText = input) => {
        setShowStarters(false);
        if (!messageText.trim() || !ws) return;
        setMessages((prev) => [...prev, { sender: "user", text: messageText }]);
        setShowThinking(true);
        setAwaitingResponse(true);
        ws.send(messageText);

        if (timeoutRef.current) {
            clearTimeout(timeoutRef.current);
        }
        setInput("");
        timeoutRef.current = setTimeout(() => {
            if (showThinking || awaitingResponse) {
                setShowThinking(false);
                setAwaitingResponse(false);
                setTypingText(null);

                setMessages((prev) => [
                    ...prev,
                    {
                        sender: "system",
                        text: "⚠️ Oops! Something went wrong! Please try again.",
                    },
                ]);
                timeoutRef.current = null;
            }
        }, 60000); // 120 seconds
    };

    const handleAddToFavourites = async () => {
        if (!currentRecipeTitle || !ws) return;

        const email = localStorage.getItem("userEmail");
        if (!email) {
            setMessages((prev) => [
                ...prev,
                { sender: "bot", text: "❗ You must be logged in to add to favourites." },
            ]);
            return;
        }

        try {
            const response = await fetch("http://172.20.10.3:8001/add-favourite", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    email,
                    title: currentRecipeTitle,
                    recipe: fullRecipeContent[currentRecipeTitle] || "",
                }),
            });

            const result = await response.json();

            if (result.status === "success") {
                setFavourites((prev) => [...prev, currentRecipeTitle]);
                setMessages((prev) => [
                    ...prev,
                    { sender: "bot", text: `✅ "${currentRecipeTitle}" has been added to your favourites.` },
                ]);
            } else if (result.status === "exists") {
                setMessages((prev) => [
                    ...prev,
                    { sender: "bot", text: `🔔 "${currentRecipeTitle}" is already in your favourites.` },
                ]);
            } else {
                setMessages((prev) => [
                    ...prev,
                    { sender: "bot", text: `❗ Failed to add to favourites.` },
                ]);
            }
        } catch (error) {
            console.error("Error adding to favourites:", error);
            setMessages((prev) => [
                ...prev,
                { sender: "bot", text: `❗ Server error while adding to favourites.` },
            ]);
        }

        setCurrentRecipeTitle(null); // clear after saving
    };

    const updatePreference = async (field, updatedList) => {
        const email = localStorage.getItem("userEmail");
        if (!email) return;

        try {
            await fetch(`http://172.20.10.3:8001/update-profile`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, field, updatedList })
            });

            setUserPrefs(prev => ({ ...prev, [field]: updatedList }));
        } catch (err) {
            console.error("Error updating preference:", err);
        }
    };


    const fetchChatLogs = async () => {
        const email = localStorage.getItem("userEmail");
        if (!email) return;

        try {
            const response = await fetch(`http://172.20.10.3:8001/get-chat-logs?email=${email}`);
            const data = await response.json();
            if (Array.isArray(data.chats)) {
                setChatLogs(data.chats);
            }
        } catch (err) {
            console.error("Error fetching chats:", err);
        }
    };

    const fetchUserProfile = async () => {
        const email = localStorage.getItem("userEmail");
        if (!email) return;

        try {
            const response = await fetch(`http://172.20.10.3:8001/get-profile?email=${email}`);
            const data = await response.json();
            setUserPrefs({
                name: data.name || "",
                likes: data.likes || [],
                dislikes: data.dislikes || [],
                allergies: data.allergies || []
            });
            setProfileLoaded(true);
        } catch (err) {
            console.error("Error fetching user profile:", err);
        }
    };


    const fetchFavourites = async () => {
        const email = localStorage.getItem("userEmail");
        if (!email) return;

        try {
            const response = await fetch(`http://172.20.10.3:8001/get-favourites?email=${email}`);
            const data = await response.json();
            if (Array.isArray(data.favourites)) {
                setFavourites(data.favourites.map(f => f.title)); // get titles
                const fullContent = {};
                data.favourites.forEach(f => {
                    fullContent[f.title] = f.recipe;
                });
                setFullRecipeContent(fullContent); // store full recipes
            }
        } catch (err) {
            console.error("Error fetching favourites:", err);
        }
    };


    // This function now accepts the full message object
    const animateTyping = (fullMessage) => {
        let i = 0;
        // Add a new message object to the state with placeholder text
        setMessages((prev) => [...prev, { ...fullMessage, text: '' }]);

        const typingInterval = setInterval(() => {
            setMessages((prev) => {
                const lastMessage = prev[prev.length - 1];

                // Check if we're typing the correct message and if it's not finished
                if (lastMessage && lastMessage.id === fullMessage.id && i < fullMessage.text.length) {
                    i++;
                    const newText = fullMessage.text.substring(0, i);
                    return [
                        ...prev.slice(0, -1),
                        {
                            ...lastMessage,
                            text: newText,
                        },
                    ];
                } else {
                    clearInterval(typingInterval);
                    // Ensure the final message object is saved completely
                    return [
                        ...prev.slice(0, -1),
                        {
                            ...fullMessage,
                            text: fullMessage.text,
                        },
                    ];
                }
            });
        }, 30); // Adjust typing speed here
    };


    const playBotSpeech = async (text) => {
        try {
            const response = await fetch("http://172.20.10.3:8001/speak-text", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text }),
            });
            if (!response.ok) throw new Error("TTS failed");
            const arrayBuffer = await response.arrayBuffer();
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
            const source = audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(audioContext.destination);
            source.onended = () => {
                setBotSpeaking(false);
                setAwaitingResponse(false);
            };
            setBotSpeaking(true);
            source.start(0);
        } catch (e) {
            console.error("TTS Error", e);
            handleCriticalError("Failed to play the bot's voice. You will be redirected to the homepage.");
        }
    };

    const toggleRecording = async () => {
        if (!navigator.mediaDevices || !window.MediaRecorder) return alert("🎙️ غير مدعوم");

        if (!isRecording) {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mediaRecorder = new MediaRecorder(stream);
            recordedChunksRef.current = [];

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) recordedChunksRef.current.push(event.data);
            };

            mediaRecorder.onstop = async () => {
                setIsRecording(false); // ✅ Move this here

                const blob = new Blob(recordedChunksRef.current, { type: "audio/webm" });
                const formData = new FormData();
                formData.append("file", blob, "voice.webm");

                try {
                    const res = await fetch("http://172.20.10.3:8001/transcribe-audio", {
                        method: "POST",
                        body: formData,
                    });

                    const data = await res.json();
                    if (data.text) {
                        setAwaitingResponse(true); // ✅ Set waiting immediately after send
                        sendMessage(data.text);
                    }
                } catch (err) {
                    console.error("Transcription failed", err);
                    handleCriticalError("Failed to convert your voice to text. You will be redirected to the homepage.");
                }
            };

            mediaRecorderRef.current = mediaRecorder;
            mediaRecorder.start();
            setIsRecording(true);
        } else {
            mediaRecorderRef.current?.stop(); // ⚠️ async stop — don't reset state here
        }
    };


    const DropdownSection = ({ title, items, icon: Icon }) => {
        const [open, setOpen] = useState(false);

        return (
        // The main container for each dropdown section (e.g., Likes, Dislikes, Favourite Recipes)
        <div className="dropdown-section">
            {/* The clickable header that acts as the "baby blue box" */}
            <div className="dropdown-header" onClick={() => setOpen(!open)}>
                {/* This is the new group for the icon and the text.
                    It will be the FIRST direct child of .dropdown-header. */}
                <div className="dropdown-icon-text-group"> {/* Using a new classname for this group */}
                    {/* The Icon component is rendered here.
                        It will be a direct child of 'dropdown-icon-text-group'.
                        Remove the inline style 'marginRight:"8px"' as we'll handle spacing with CSS 'gap'. */}
                    {Icon && <Icon size={18} />} {/* Conditionally render the icon if 'Icon' prop is provided */}

                    {/* The title text (e.g., "Favourite Recipes") */}
                    <span>{title}</span>
                </div>

                {/* The dropdown arrow.
                    This will be the SECOND direct child of .dropdown-header,
                    allowing 'justify-content: space-between' to push it to the right. */}
                <span className="dropdown-arrow">{open ? "▲" : "▼"}</span>
            </div>

            {/* The list of items that appears when the dropdown is open */}
            {open && (
                <ul className="dropdown-list">
                    {items.length === 0 ? (
                        <li className="empty-item">None</li>
                    ) : (
                        items.map((item, i) => <li key={`${title}-${i}`}>{item}</li>)
                    )}
                </ul>
            )}
        </div>
    );
};

    const EditableListSection = ({ title, items, icon: Icon, onAdd, onDelete }) => {
        const [open, setOpen] = useState(false);
        const [newItem, setNewItem] = useState("");

        return (
            <div className="editable-section">
                <div className="section-header" onClick={() => setOpen(!open)}>
                    <div className="section-title">
                        <Icon size={18} style={{ marginRight: "8px" }} />
                        {title}
                    </div>
                    <span className="dropdown-arrow">{open ? "▲" : "▼"}</span>
                </div>

                {open && (
                    <div className="section-body">
                        <ul>
                            {items.map((item, i) => (
                                <li key={`${title}-${i}`}>
                                    {item}
                                    <Trash2 size={16} className="delete-icon" onClick={() => onDelete(i)} />
                                </li>
                            ))}
                        </ul>
                        <div className="add-input">
                            <input
                                type="text"
                                placeholder={`Add to ${title}`}
                                value={newItem}
                                onChange={(e) => setNewItem(e.target.value)}
                            />
                            <button onClick={() => {
                                if (newItem.trim()) {
                                    onAdd(newItem.trim());
                                    setNewItem("");
                                }
                            }}>
                                <Plus size={16} />
                            </button>
                        </div>
                    </div>
                )}
            </div>
        );
    };


    const handleModeSelect = (selectedMode) => setMode(selectedMode);
    const handleCopyRecipe = async () => {
        if (currentRecipeTitle && fullRecipeContent[currentRecipeTitle]) {
            try {
                await navigator.clipboard.writeText(fullRecipeContent[currentRecipeTitle]);
                setCopyFeedback("Copied!");
                setTimeout(() => setCopyFeedback(""), 2000); // Clear feedback after 2 seconds
            } catch (err) {
                console.error("Failed to copy recipe text: ", err);
                setCopyFeedback("Failed to copy.");
                setTimeout(() => setCopyFeedback(""), 2000);
            }
        }
    };

    const handleCopyMessage = async (textToCopy, messageId) => {
        try {
            // Create a temporary div to strip HTML tags if the message contains them
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = textToCopy;
            const plainText = tempDiv.textContent || tempDiv.innerText || "";

            await navigator.clipboard.writeText(plainText);
            setCopiedMessageId(messageId);
            setTimeout(() => {
                setCopiedMessageId(null);
            }, 1500);
        } catch (err) {
            console.error("Failed to copy message: ", err);
            // Optionally, alert the user or show a temporary error message
            alert("Failed to copy message. Please try again or copy manually.");
        }
    };

    return (
        <div className="chat-page">
            {/* Mobile Header with Toggle Buttons */}
            {window.innerWidth < 768 && (
                <div className="mobile-header">
                    <button
                        id="mobile-toggle-history"
                        className="mobile-toggle-btn mobile-history-toggle"
                        onClick={() => setIsHistoryOpenMobile(!isHistoryOpenMobile)}
                        aria-label="Toggle chat history"
                    >
                        <Menu size={24} />
                    </button>
                    <h2 className="mobile-header-title">Chatterly</h2> {/* Central title for mobile header */}
                    <button
                        id="mobile-toggle-info"
                        className="mobile-toggle-btn mobile-info-toggle"
                        onClick={() => setIsInfoOpenMobile(!isInfoOpenMobile)}
                        aria-label="Toggle info panel"
                    >
                        <Info size={24} />
                    </button>
                </div>
            )}

            {/* Overlay for mobile panels */}
            {(isHistoryOpenMobile || isInfoOpenMobile) && window.innerWidth < 768 && (
                <div className="overlay" onClick={() => {
                    setIsHistoryOpenMobile(false);
                    setIsInfoOpenMobile(false);
                }}></div>
            )}

            {/* Chat History Bar */}
            <div className={`chat-history-bar ${isHistoryOpenMobile ? "open-mobile" : ""} ${window.innerWidth >= 768 && isHistoryCollapsed ? "collapsed" : ""}`}>
                {/* Controls for desktop and mobile history bar */}
                {(!isHistoryCollapsed || isHistoryOpenMobile) && (
                    <div className="history-controls"> {/* New container for these controls */}
                        <button className="collapse-btn" onClick={() => setIsHistoryCollapsed(prev => !prev)} aria-label={isHistoryCollapsed ? "Expand chat history" : "Collapse chat history"}>
                            {isHistoryCollapsed ? "»" : "«"}
                        </button>
                        <div className="history-control-item"> {/* New class here */}
                            <ComfortModeToggle />
                        </div>
                        <div className="history-control-item font-size-control-item"> {/* New class here for specific styling */}
                            <FontSizeSelector />
                        </div>
                        <button className="new-chat-btn new-chat-history-btn" onClick={() => window.location.reload()}>
                            <span className="plus-icon">+</span> New Chat
                        </button>
                    </div>
                )}

                <div className="chat-history-header">
                    <h3>Past Chats</h3>
                    {window.innerWidth < 768 ? ( // Mobile close button
                        <button className="close-panel-btn" onClick={() => setIsHistoryOpenMobile(false)} aria-label="Close chat history">✖</button>
                    ) : ( // Desktop collapse button
                        <button className="collapse-btn" onClick={() => setIsHistoryCollapsed(prev => !prev)} aria-label={isHistoryCollapsed ? "Expand chat history" : "Collapse chat history"}>
                            {isHistoryCollapsed ? "»" : "«"}
                        </button>
                    )}
                </div>

                {/* Only show chat logs if not collapsed on desktop OR open on mobile */}
                {(!isHistoryCollapsed || isHistoryOpenMobile) && (
                    <div className="chat-log-list">
                        {chatLogs.map((log, i) => (
                            <div key={i} className="chat-log-item" onClick={() => {
                                console.log("Clicked chat log item:", log);
                                console.log("Content of log.chat:", log.chat);
                                console.log("Messages property in log.chat:", log.chat?.messages); 
                                setSelectedChatLog(log.chat);
                                if (window.innerWidth < 768) {
                                    setIsHistoryOpenMobile(false);
                                }
                            }}
                        >
                            {log.title || `Chat #${i + 1}`}
                        </div>
                    ))}
                </div>
                )}

            </div>

            {/* Main Chat Window */}
            {!mode ? (
                <div className="chat-window mode-selection-window">
                    <div className="mode-selection">
                        <h2>How would you like to chat?</h2>
                        <button onClick={() => handleModeSelect("text")}>Text</button>
                        <button onClick={() => handleModeSelect("voice")}>Voice</button>
                    </div>
                </div>
            ) : mode === "text" ? (
                <div className="chat-window">
                    <div className="chat-header">
                        {/* "Chatterly" title remains here for desktop, but is hidden on mobile */}
                        <div className="header-controls">
                            <button onClick={() => setShowFullQuranViewer(!showFullQuranViewer)}>
                                <BookOpen size={16} style={{ marginRight: '8px' }} />
                                الْقُرْآن الْكَرِيْم
                            </button>
                            <button onClick={() => {
                                setShowFullPrayerTimes(!showFullPrayerTimes);
                                // Ensure only one viewer is open at a time
                                setShowFullQuranViewer(false); 
                            }}>
                                {showFullPrayerTimes ? <X size={16} /> : <Clock size={16}  />}
                                مواقيت الصلاة
                            </button>

                        </div>
                    </div>
                    {showFullQuranViewer ? (
                        <QuranViewer compact={false} />
                    ) : showFullPrayerTimes ? (
                        <PrayerTimesViewer compact={false} />
                    ) : (
                    <>
                        {!wsConnected && (
                            <div className="reconnect-notice">
                                <p className="reconnect-text">🚫 Lost connection to the assistant.</p>
                                <button 
                                    className="reconnect-button" 
                                    onClick={connectWebSocket}>
                                    🔄 Reconnect
                                </button>
                            </div>
                        )}
                        {showStarters && (
                            <div className="starter-options">
                                <p className="starter-title">Need help getting started?</p>
                                <div className="starter-buttons">
                                    {[
                                        "السلام عليكم",
                                        "أزيك؟ عامل إيه؟",
                                        "مساء الفل ",
                                        "صباح الخير ",
                                        "أنا زهقان شوية ",
                                        "احكيلي حاجة حلوة",
                                        "إيه الأخبار؟"
                                    ]
                                        .map((text, i) => (
                                            <button
                                                key={i}
                                                onClick={() => {
                                                    sendMessage(text);
                                                    setShowStarters(false);
                                                }}
                                            >
                                                {text}
                                            </button>
                                        ))}
                                </div>
                            </div>
                        )}

                        <div className="chat-messages">
                            {messages.map((msg, idx) => { // This is where the mapping starts
                                // Define a unique ID for each message.
                                // This 'messageId' is crucial for tracking which specific message has been copied.
                                // Using `idx` is generally fine if messages are not reordered or deleted.
                                // If your 'msg' object already has a unique 'id' property, use that instead:
                                // const messageId = msg.id;
                                const messageId = `msg-${idx}`; // Simple unique ID using index

                                return ( // Each mapped item must return a single element (the message-row div)
                                    <div key={idx} className={`message-row ${msg.sender}`}>
                                        <div className={`avatar ${msg.sender === "bot" ? "bot-avatar" : "user-avatar"}`}>
                                            {msg.sender === "bot" ? <Bot size={22} strokeWidth={2} /> : <User size={22} strokeWidth={2} />}
                                        </div>

                                        {msg.sender === "bot" ? (
                                            // This is the 'bot-message-wrapper' div for bot messages
                                            <div className="bot-message-wrapper message" style={{
                                                whiteSpace: "pre-wrap",
                                                direction: "rtl",
                                                textAlign: "right",
                                                fontFamily: "Inter, Helvetica, Arial, sans-serif",
                                                fontWeight: "500",
                                                fontSize: "1.08rem",
                                                backgroundColor: "#f9fcffff"
                                            }}>
                                                <ParsedMessage text={msg.text} sourceUrl={msg.sourceUrl} />
                                                <button
                                                    className="copy-message-btn"
                                                    // Pass the messageId to handleCopyMessage
                                                    onClick={() => handleCopyMessage(msg.text, messageId)}
                                                    title="Copy message"
                                                >
                                                    {/* Conditional rendering for the copy button/feedback */}
                                                    {copiedMessageId === messageId ? (
                                                        // Show "Copied!" feedback if this message's ID matches the copiedMessageId state
                                                        <span className="copied-feedback">!Copied</span>
                                                    ) : (
                                                        // Otherwise, show the Copy icon
                                                        <Copy size={16} />
                                                    )}
                                                </button>
                                            </div>
                                        ) : (
                                            // This is the standard 'message' div for user messages
                                            <div className="message" style={{
                                                whiteSpace: "pre-wrap",
                                                direction: "rtl",
                                                textAlign: "right",
                                                fontFamily:"Inter, Helvetica, Arial, sans-serif",
                                                fontWeight: "500",
                                                fontSize: "1.08rem",
                                                backgroundColor: "#e0eeffff",
                                            }}>
                                                {msg.text}
                                            </div>
                                        )}
                                    </div>
                                ); // End of the return for each mapped message


                                
                            })} 
                            {typingText && (
                                <div className="message-row bot" style={{
                                    whiteSpace: "pre-wrap",
                                    direction: "rtl",
                                    textAlign: "right",
                                    fontFamily: "Tahoma, Arial, sans-serif"
                                }}>
                                    <div className="avatar bot-avatar">
                                        <Bot size={22} strokeWidth={2} />
                                    </div>

                                    <div className="message bot">{typingText}</div>
                                </div>
                            )}


                            {showThinking && (
                                <div className="message-row bot">
                                    <div className="avatar bot-avatar">
                                        <Bot size={22} strokeWidth={2} />
                                    </div>
                                    <div className="message bot typing-indicator">
                                        <span className="dot"></span>
                                        <span className="dot"></span>
                                        <span className="dot"></span>
                                    </div>
                                </div>
                            )}


                            {expectingChoice && (
                                <>
                                    <div className="choice-hint">Choose from the following suggestions ⬇</div>
                                        <div className="suggestions">
                                            {suggestions.map((s, i) => (
                                                <button
                                                    className="suggestion-button"
                                                    key={i}
                                                    onClick={() => {
                                                        const selectedTitle = s;
                                                        setMessages((prev) => [...prev, { sender: "user", text: selectedTitle }]);
                                                        sendMessage(`${i + 1}`);
                                                        setExpectingChoice(false);
                                                        setSuggestions([]);
                                                    }}
                                                >
                                                    {s}
                                                </button>
                                            ))}

                                        </div>
                                </>
                            )}
                            <div ref={messageListRef}></div>
                        </div>


                        <div className="input-container">
                            <input
                                type="text"
                                placeholder={
                                    !wsConnected
                                        ? "Connecting..."
                                        : showThinking
                                            ? "Please wait..."
                                            : expectingChoice
                                                ? "Waiting for your choice..."
                                                : "Type here..."
                                }
                                value={input}
                                onChange={(e) => e.target.value === "" ? setInput("") : setInput(e.target.value)} // Ensure input is cleared properly
                                onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                                disabled={!wsConnected || expectingChoice || showThinking}
                            />


                            <button
                                onClick={() => {
                                    if (!expectingChoice) sendMessage();
                                }}
                                disabled={!wsConnected || expectingChoice || showThinking || input.trim() === ""}
                            >   
                                send
                            </button>

                            {expectingChoice && (
                                <div className="suggestion-hint">Choose from suggestions</div>
                            )}
                        </div>  
                    </>
                )}
            </div> 
                
        ) : (
                <div className="chat-window">
                    <div className="chat-header">
                        <h2>Recipe Assistant</h2>
                        {/* Removed new-chat-btn from here */}
                    </div>

                    {!wsConnected && (
                        <div className="reconnect-notice">
                            <p className="reconnect-text">🚫 Lost connection to the assistant.</p>
                            <button className="reconnect-button" onClick={connectWebSocket}>
                                🔄 Try Reconnecting
                            </button>
                        </div>
                    )}

                    <div
                        className={`voice-circle ${isRecording ? "listening" : botSpeaking ? "speaking" : awaitingResponse ? "thinking" : ""
                            }`}
                        onClick={() => {
                            // Allow toggleRecording during recording, but block during thinking/speaking
                            if (!botSpeaking && !awaitingResponse) toggleRecording();
                        }}
                    >

                        {isRecording
                            ? "Listening..."
                            : botSpeaking
                                ? "Speaking..."
                                : awaitingResponse
                                    ? "Thinking..."
                                    : "Click to Speak"}
                    </div>

                    {expectingChoice && (
                        <>
                            <div className="choice-hint">Choose from the following suggestions ⬇</div>
                            <div className="suggestions">
                                {suggestions.map((s, i) => (
                                    <button
                                        className="suggestion-button"
                                        key={i}
                                        onClick={() => {
                                            const selectedTitle = s;
                                            setMessages((prev) => [...prev, { sender: "user", text: selectedTitle }]);
                                            sendMessage(`${i + 1}`);
                                            setExpectingChoice(false);
                                            setSuggestions([]);
                                        }}
                                    >
                                        {s}
                                    </button>
                                ))}

                            </div>
                        </>
                    )}
                    <div ref={messageListRef}></div>
                    <div className="input-container">
                        <input
                            type="text"
                            placeholder={
                                !wsConnected
                                    ? "Connecting..."
                                    : showThinking
                                        ? "Please wait..."
                                        : expectingChoice
                                            ? "Waiting for your choice..."
                                            : "Type here..."
                            }
                            value={input}
                            onChange={(e) => e.target.value === "" ? setInput("") : setInput(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                            disabled={!wsConnected || expectingChoice || showThinking}
                            style={{ display: 'none' }} // Hide input for voice mode
                        />
                        <button
                            onClick={() => {
                                if (!expectingChoice) sendMessage();
                            }}
                            disabled={!wsConnected || expectingChoice || showThinking || input.trim() === ""}
                            style={{ display: 'none' }} // Hide send button for voice mode
                        >
                            send
                        </button>
                    </div>
                </div>
            )}

            <div className={`info-panel-bar ${isInfoOpenMobile ? "open-mobile" : ""}`}>
    <div className="info-panel-header">
        <h3>Chatterly</h3>
        {window.innerWidth < 768 && (
            <button className="close-panel-btn" onClick={() => setIsInfoOpenMobile(false)} aria-label="Close info panel">✖</button>
        )}
        {currentRecipeTitle && (
            <div className="current-recipe-box">
                {/* Flex container for title and copy button */}
                {/* THIS IS WHERE THE CORRECTION IS: <h3>Current Recipe</h3> is moved inside this flex container */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <h3>Current Recipe</h3> {/* MOVED HERE */}
                    <div style={{ position: 'relative' }}> {/* Wrapper for button and feedback */}
                        <button
                            onClick={handleCopyRecipe}
                            className="copy-button" // Add a class for styling
                            title="Copy recipe to clipboard"
                            style={{
                                background: 'none',
                                border: 'none',
                                cursor: 'pointer',
                                color: '#0966d0',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '4px',
                                padding: '4px 8px',
                                borderRadius: '4px',
                                transition: 'background-color 0.2s',
                            }}
                            
                        >
                            <Copy size={16} />
                            {copyFeedback && <span style={{ fontSize: '12px' }}>{copyFeedback}</span>}
                        </button>
                    </div>

                    <button
                        onClick={() => setIsRecipeCollapsed(!isRecipeCollapsed)}
                        className="collapse-recipe-button" // Add a class for specific styling
                        title={isRecipeCollapsed ? "Expand recipe" : "Collapse recipe"}
                        style={{
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            color: '#0966d0',
                            padding: '4px',
                            borderRadius: '4px',
                            transition: 'background-color 0.2s',
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(0, 123, 255, 0.2)'}
                        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                    >
                        {isRecipeCollapsed ? <ChevronDown size={20} /> : <ChevronUp size={20} />}
                    </button>
                </div>
                {/* The h4 and p for the recipe content should be outside the flex container
                    if they are meant to flow below the header/button line. */}

                {/* Conditionally render recipe content */}
                {!isRecipeCollapsed && (
                                <>
                                    <h4 style={{
                                        direction: "rtl",
                                        textAlign: "right",
                                        whiteSpace: "pre-wrap",
                                        fontFamily: "Tahoma, Arial, sans-serif",
                                    }}>{currentRecipeTitle}</h4>
                                    <p
                                        style={{
                                            direction: "rtl",
                                            textAlign: "right",
                                            whiteSpace: "pre-wrap",
                                            fontFamily: "Tahoma, Arial, sans-serif",
                                        }}
                                    >
                                        {fullRecipeContent[currentRecipeTitle]}
                                    </p>
                                    <div style={{ display: "flex", justifyContent: "center", marginTop: "1rem" }}>
                                        <button className="new-chat-btn" onClick={handleAddToFavourites}>
                                            <span className="plus-icon">+</span>Add to favorites
                                        </button>
                                    </div>
                                </>
                            )}
            </div>
        )}
    </div>
                <div className="info-panel-content">
                    {profileLoaded ? (
                        <>
                            <div className="user-profile-section">
                                <UserCircle2 size={20} style={{ marginRight: "6px" }} />
                                <h4>{userPrefs.name || "User Profile"}</h4>
                            </div>
                            <EditableListSection
                                title="Likes"
                                items={userPrefs.likes}
                                icon={ThumbsUp}
                                onAdd={(item) => updatePreference("likes", [...userPrefs.likes, item])}
                                onDelete={(index) => updatePreference("likes", userPrefs.likes.filter((_, i) => i !== index))}
                            />
                            <EditableListSection
                                title="Dislikes"
                                items={userPrefs.dislikes}
                                icon={ThumbsDown}
                                onAdd={(item) => updatePreference("dislikes", [...userPrefs.dislikes, item])}
                                onDelete={(index) => updatePreference("dislikes", userPrefs.dislikes.filter((_, i) => i !== index))}
                            />
                            <EditableListSection
                                title="Allergies"
                                items={userPrefs.allergies}
                                icon={AlertTriangle}
                                onAdd={(item) => updatePreference("allergies", [...userPrefs.allergies, item])}
                                onDelete={(index) => updatePreference("allergies", userPrefs.allergies.filter((_, i) => i !== index))}
                            />
                            <DropdownSection 
                                title="Favourite Recipes" 
                                items={favourites} 
                                icon={Heart} 
                            />

                            <div className="calendar-section" style={{ marginTop: '2rem', borderTop: '1px solid #ccc', paddingTop: '10px' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
                                <FcGoogle size={24} style={{ marginRight: "8px" }} />
                                <h3>Your Google Calendar</h3>
                                
                              </div>
                              <UserCalendar />
                            </div>

                        </>
                    ) : (
                        <p>Loading profile...</p>
                    )}
                </div>
            </div>
        </div>
    );
}

export default Chat;
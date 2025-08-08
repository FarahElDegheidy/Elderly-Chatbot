// src/QuranViewer.js
import React, { useState, useEffect, useRef } from 'react';
import './Quranviewer.css';
import { Play, Square, ChevronLeft, ChevronRight } from 'lucide-react';

const QuranViewer = ({ compact = false }) => {
  const [surahNumber, setSurahNumber] = useState(1);
  const [surahData, setSurahData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [allSurahs, setAllSurahs] = useState([]);
  
  const audioPlayerRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentAyahAudioIndex, setCurrentAyahAudioIndex] = useState(0);
  const [currentSurahAudioUrls, setCurrentSurahAudioUrls] = useState([]);

  const ayahRefs = useRef([]);

  // Effect to fetch the list of all Surahs once on component mount
  useEffect(() => {
    const fetchAllSurahs = async () => {
      try {
        const surahsResponse = await fetch('http://api.alquran.cloud/v1/surah');
        if (!surahsResponse.ok) {
          throw new Error(`HTTP error! status: ${surahsResponse.status} for surah list`);
        }
        const surahsData = await surahsResponse.json();
        setAllSurahs(surahsData.data);

      } catch (err) {
        console.error("Failed to fetch initial data:", err);
        setError("Failed to load necessary Quran data. Please try again.");
      }
    };

    fetchAllSurahs();
  }, []);

  // Effect to fetch data for the selected Surah (text)
  useEffect(() => {
    if (!compact) {
      const fetchData = async () => {
        setIsLoading(true);
        setError(null);

        try {
          const url = `http://api.alquran.cloud/v1/surah/${surahNumber}/quran-uthmani`; 
          const response = await fetch(url);
          
          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }

          const data = await response.json();
          setSurahData(data.data);
          ayahRefs.current = data.data.ayahs.map(() => React.createRef());
        } catch (error) {
          console.error("Fetching error: ", error);
          setError("Failed to fetch surah. Please try again.");
        } finally {
          setIsLoading(false);
        }
      };
      fetchData();
    } else {
        setIsLoading(false);
        setError(null);
        setSurahData(null);
        if (audioPlayerRef.current) {
            audioPlayerRef.current.pause();
            setIsPlaying(false);
            setCurrentAyahAudioIndex(0);
        }
    }
  }, [surahNumber, compact]);

  // Effect for auto-scrolling
  useEffect(() => {
    if (!compact && isPlaying && surahData && ayahRefs.current[currentAyahAudioIndex]) {
      ayahRefs.current[currentAyahAudioIndex].current?.scrollIntoView({
        behavior: 'smooth',
        block: 'center'
      });
    }
  }, [currentAyahAudioIndex, isPlaying, compact, surahData]);

  // Function to play the current ayah's audio
  const playCurrentAyah = () => {
    if (!audioPlayerRef.current) {
        audioPlayerRef.current = new Audio();
        audioPlayerRef.current.onended = () => {
            if (currentAyahAudioIndex + 1 < currentSurahAudioUrls.length) {
                setCurrentAyahAudioIndex(prevIndex => prevIndex + 1);
            } else {
                setIsPlaying(false);
                setCurrentAyahAudioIndex(0);
            }
        };
        audioPlayerRef.current.onerror = (e) => {
            console.error("Audio playback error:", e);
            setError("Failed to play audio. Please try again.");
            setIsPlaying(false);
            setCurrentAyahAudioIndex(0);
        };
    }

    if (currentSurahAudioUrls.length > 0 && currentAyahAudioIndex < currentSurahAudioUrls.length) {
      const audioUrl = currentSurahAudioUrls[currentAyahAudioIndex];
      audioPlayerRef.current.src = audioUrl;
      audioPlayerRef.current.play().catch(e => {
        console.error("Audio play failed:", e);
        setError("Failed to play audio. (Autoplay blocked?)");
        setIsPlaying(false);
      });
      setIsPlaying(true);
      setError(null);
    } else if (currentSurahAudioUrls.length > 0 && currentAyahAudioIndex >= currentSurahAudioUrls.length) {
        setIsPlaying(false);
        setCurrentAyahAudioIndex(0);
    } else {
      setError("Audio URLs not found for this Surah.");
      setIsPlaying(false);
    }
  };

  // Effect to play the next ayah when currentAyahAudioIndex changes,
  // or when currentSurahAudioUrls is populated for the first time.
  useEffect(() => {
    if (isPlaying && currentSurahAudioUrls.length > 0) {
      playCurrentAyah();
    }
  }, [currentAyahAudioIndex, currentSurahAudioUrls, isPlaying]);

  // Handle audio playback toggle (initial click)
  const handleAudioToggle = async () => {
    if (isPlaying) {
      audioPlayerRef.current.pause();
      setIsPlaying(false);
    } else {
      setIsLoading(true);
      setError(null);

      try {
        const audioFetchUrl = `http://api.alquran.cloud/v1/surah/${surahNumber}/ar.alafasy`;
        const response = await fetch(audioFetchUrl);

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status} for audio`);
        }
        const data = await response.json();
        
        const ayahsWithAudio = data.data?.ayahs;

        if (ayahsWithAudio && ayahsWithAudio.length > 0) {
            const allAudioUrls = ayahsWithAudio.map(ayah => ayah.audio).filter(url => url);
            setCurrentSurahAudioUrls(allAudioUrls);
            
            if (!isPlaying && currentAyahAudioIndex === 0) { 
                setCurrentAyahAudioIndex(0);
            }

            setIsPlaying(true); 

        } else {
            setError("Audio URLs not found for this Surah (or no ayahs with audio).");
            setIsPlaying(false);
        }
      } catch (err) {
        console.error("Audio fetch error:", err);
        setError("Failed to fetch audio for this Surah. Please try again.");
        setIsPlaying(false);
      } finally {
        setIsLoading(false);
      }
    }
  };

  // Function to go to the previous ayah
  const goToPreviousAyah = () => {
    if (currentAyahAudioIndex > 0) {
      const newIndex = currentAyahAudioIndex - 1;
      setCurrentAyahAudioIndex(newIndex);
      if (isPlaying) {
        // The useEffect will handle playing the new ayah due to index change
      }
    } else {
        if (isPlaying) {
            audioPlayerRef.current.pause();
            setIsPlaying(false);
        }
        setCurrentAyahAudioIndex(0);
    }
  };

  // Function to go to the next ayah
  const goToNextAyah = () => {
    if (currentAyahAudioIndex < currentSurahAudioUrls.length - 1) {
      const newIndex = currentAyahAudioIndex + 1;
      setCurrentAyahAudioIndex(newIndex);
      if (isPlaying) {
        // The useEffect will handle playing the new ayah due to index change
      }
    } else {
        if (isPlaying) {
            audioPlayerRef.current.pause();
            setIsPlaying(false);
        }
        setCurrentAyahAudioIndex(currentSurahAudioUrls.length - 1);
    }
  };


  return (
    <div className="quran-viewer-container">
      {!compact && (
        // NEW: Fixed header section
        <div className='quran-viewer-fixed-header'>
            <div className='controls'> {/* Existing controls div */}
              <label htmlFor="surah-select">Select a Surah:</label>
              <select 
                id="surah-select" 
                value={surahNumber} 
                onChange={(e) => {
                    setSurahNumber(e.target.value);
                    if (audioPlayerRef.current) {
                        audioPlayerRef.current.pause();
                        setIsPlaying(false);
                        setCurrentAyahAudioIndex(0);
                    }
                }}
              >
                {allSurahs.map(surah => (
                  <option key={surah.number} value={surah.number}>
                    Surah {surah.number} - {surah.englishName} ({surah.name})
                  </option>
                ))}
              </select>
              
              <div className="audio-controls-group">
                <button onClick={goToPreviousAyah} disabled={isLoading || currentAyahAudioIndex === 0}>
                    <ChevronLeft size={18} />
                </button>

                <button onClick={handleAudioToggle} disabled={isLoading}>
                    {isPlaying ? (
                        <>
                            <Square size={18} style={{ marginRight: '8px' }} /> Pause Audio
                        </>
                    ) : (
                        <>
                            <Play size={18} style={{ marginRight: '8px' }} /> Play Audio
                        </>
                    )}
                </button>

                <button onClick={goToNextAyah} disabled={isLoading || currentAyahAudioIndex === currentSurahAudioUrls.length - 1}>
                    <ChevronRight size={18} />
                </button>
              </div>
            </div> {/* End of controls div */}
        </div> 
      )}

      {/* NEW: Scrollable content section */}
      {!compact && (isLoading || error || surahData) && ( /* Only render if there's content to show/load */
        <div className="quran-viewer-scrollable-content">
          {isLoading && <p>Loading Surah...</p>}
          {error && <p className="error-message">{error}</p>}
          {surahData && (
            <article>
              <header>
                <h2 lang="ar" dir="rtl">{surahData.name}</h2>
                <p>{surahData.englishName} ({surahData.englishNameTranslation})</p>
              </header>
              
              <div className="ayahs-container">
                {surahData.ayahs.map((ayah, idx) => {
                  const basmalaText = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ";
                  
                  const shouldShowAyahNumber = 
                    (surahData.number === 1) || 
                    (surahData.number === 9) || 
                    !(idx === 0 && ayah.text === basmalaText);

                  return (
                    <p 
                      key={ayah.number} 
                      className={`ayah ${currentAyahAudioIndex === idx && isPlaying ? 'highlight-ayah' : ''}`}
                      ref={ayahRefs.current[idx]}
                    >
                      {shouldShowAyahNumber && <span className="ayah-number">{ayah.numberInSurah}. </span>} 
                      <span className="arabic-text" lang="ar" dir="rtl">{ayah.text}</span>
                    </p>
                  );
                })}
              </div>
            </article>
          )}
        </div> /* End of quran-viewer-scrollable-content */
      )}
    </div>
  );
};

export default QuranViewer;

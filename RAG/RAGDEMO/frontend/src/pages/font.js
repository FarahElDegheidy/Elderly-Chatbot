import React, { useState, useEffect } from "react";
import "./font.css";
import { ZoomIn } from "lucide-react";

// Font size selector component
export const FontSizeSelector = () => {
  const [fontSize, setFontSize] = useState(() => localStorage.getItem("fontSize") || "100%");

  useEffect(() => {
    document.documentElement.style.fontSize = fontSize;
    localStorage.setItem("fontSize", fontSize);
  }, [fontSize]);

  return (
    <div className="font-size-selector">
      <ZoomIn size={16} />
      <select value={fontSize} onChange={(e) => setFontSize(e.target.value)}>
        <option value="90%">Small</option>
        <option value="100%">Default</option>
        <option value="110%">Large</option>
        <option value="120%">Extra Large</option>
      </select>
    </div>
  );
};

// Visual comfort mode toggle component
export const ComfortModeToggle = () => {
  const [isComfortMode, setIsComfortMode] = useState(() => localStorage.getItem("comfortMode") === "true");

  useEffect(() => {
    document.body.classList.toggle("comfort-mode", isComfortMode);
    localStorage.setItem("comfortMode", isComfortMode);
  }, [isComfortMode]);

  return (
    <div className="accessibility-toggle">
      <input
        type="checkbox"
        id="comfortMode"
        onChange={() => setIsComfortMode(prev => !prev)}
        checked={isComfortMode}
      />
      <label htmlFor="comfortMode" className="toggle-label">Mode</label>
    </div>
  );
};

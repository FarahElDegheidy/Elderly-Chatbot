import React, { useState } from "react";
import "./CustomDropdown.css";

const CustomDropdown = ({ label = "Choose", options = [], value, onSelect }) => {
  const [open, setOpen] = useState(false);

  const handleSelect = (option) => {
    onSelect(option);
    setOpen(false);
  };

  return (
    <div className="custom-dropdown">
      <div className="dropdown-header" onClick={() => setOpen((prev) => !prev)}>
        <span className={`dropdown-selected ${!value ? 'placeholder' : ''}`}>
          {value || label}
        </span>
        <span className="material-symbols-outlined arrow-icon">keyboard_arrow_down</span>
      </div>

      {open && (
        <ul className="dropdown-options">
          {options.map((opt, idx) => (
            <li key={idx} onClick={() => handleSelect(opt)}>
              {opt}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default CustomDropdown;

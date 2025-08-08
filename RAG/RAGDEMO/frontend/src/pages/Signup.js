// Signup.jsx
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./Signup.css";
import CustomDropdown from "./CustomDropdown";
import "./CustomDropdown.css"

const categories = {
  likes: [
  "فول مدمس", "طعمية", "كشري", "محشي", "ملوخية", "شاورما", "كباب", "كفتة",
  "حمام محشي", "فسيخ", "كبدة إسكندراني", "مكرونة بشاميل", "فتة", "حواوشي",
  "دجاج مشوي", "صدور دجاج", "لحم ضاني", "بانيه", "سمك بلطي", "جمبري",
  "بطاطس محمرة", "بامية", "كوسة", "سبانخ", "بسلة بالجزر", "ورق عنب"
],
  dislikes: [
  "فسيخ", "كوارع", "ممبار", "كبدة", "كوارع", "محشي ورق عنب", "بامية", "كوسة",
  "بصل", "ثوم", "فلفل حار", "كزبرة", "كراوية", "يانسون", "قرفة", "زنجبيل"
],
  allergies: [
  "لبن", "بيض", "فول سوداني", "قمح", "سمك", "جمبري", "كابوريا", "فراولة",
  "طماطم", "فلفل", "سمسم", "موز", "مانجو", "مكسرات"
]
,
  professions: ["طالب", "طبيب", "مهندس", "مدرس", "فنان", "أخرى"]
};

function Signup() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    email: "",
    password: "",
    name: "",
    gender: "",
    profession: "",
    otherProfession: "",
    likes: [],
    otherLike: "",
    dislikes: [],
    otherDislike: "",
    allergies: [],
    otherAllergy: ""
  });

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

const [showLikes, setShowLikes] = useState(false);
const [showDislikes, setShowDislikes] = useState(false);
const [showAllergies, setShowAllergies] = useState(false);


  const handleCheckboxChange = (e, field) => {
    const value = e.target.value;
    const isChecked = e.target.checked;
    setForm((prev) => {
      const updated = isChecked
        ? [...prev[field], value]
        : prev[field].filter((item) => item !== value);
      return { ...prev, [field]: updated };
    });
  };

  const handleSignup = async () => {
    const payload = {
      ...form,
      likes: [...new Set([...form.likes, ...form.otherLike.split(",").map((v) => v.trim())])].filter(Boolean),
      dislikes: [...new Set([...form.dislikes, ...form.otherDislike.split(",").map((v) => v.trim())])].filter(Boolean),
      allergies: [...new Set([...form.allergies, ...form.otherAllergy.split(",").map((v) => v.trim())])].filter(Boolean),
      profession: form.profession === "أخرى" ? form.otherProfession.trim() : form.profession
    };

    const res = await fetch("http://172.20.10.3:8001/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      alert("Registration successful! Please log in.");
      navigate("/login");
    } else {
      const err = await res.json();
      alert("Registration FAILED!" + err.detail);
    }
  };

  return (
  <div className="signup-wrapper">
    <div className="signup-form">
      <h2 className="signin-header">
          <img src="/logo5.png" alt="Logo" className="signin-logo" />
        Create Account
      </h2>
      <input name="email" type="email" placeholder="Email" onChange={handleChange} />
      <input name="password" type="password" placeholder="Password" onChange={handleChange} />
      <input name="name" placeholder="First name" onChange={handleChange} />
      <CustomDropdown
        label="Gender"
        options={["Male", "Female"]}
        value={form.gender}
        onSelect={(val) => setForm({ ...form, gender: val })}
      />
      <CustomDropdown
        label="Profession"
        options={categories.professions}
        value={form.profession}
        onSelect={(val) => setForm({ ...form, profession: val })}
      />
      {form.profession === "أخرى" && (
        <input name="otherProfession" placeholder="Other" onChange={handleChange} />
      )}

      {/* Likes Section */}
      <div className="toggle-checkbox-block">
        <div className="toggle-header" onClick={() => setShowLikes(!showLikes)}>
          <div className="fav-wrapper" >
            <img src="/fav.png" alt="Logo" className="fav-wrapper" />
          </div>
          <span>Set Your Favorites</span>
          <span className="plus-icon">{showLikes ? "×" : "+"}</span>
        </div>
        {showLikes && (
          <>
            <div className="checkbox-group">
              {categories.likes.map((item, i) => (
                <label key={i} className="custom-checkbox">
                <input
                  type="checkbox"
                  value={item}
                  onChange={(e) => handleCheckboxChange(e, "likes")}
                />
            <div className="checkbox-box">{item}</div>
              </label>

              ))}
            </div>
            <input name="otherLike" placeholder="Other" onChange={handleChange} />
          </>
        )}
      </div>

      {/* Dislikes Section */}
      <div className="toggle-checkbox-block">
        <div className="toggle-header" onClick={() => setShowDislikes(!showDislikes)}>
          <div className="fav-wrapper" >
            <img src="/thumb.png" alt="Logo" className="fav-wrapper" />
          </div>
          <span>Any Dislikes?</span>
          <span className="plus-icon">{showDislikes ? "×" : "+"}</span>
        </div>
        {showDislikes && (
          <>
            <div className="checkbox-group">
              {categories.dislikes.map((item, i) => (
                <label key={i} className="custom-checkbox">
                  <input type="checkbox" value={item} onChange={(e) => handleCheckboxChange(e, "dislikes")} />
                  <div className="checkbox-box">{item}</div>
                </label>
              ))}
            </div>
            <input name="otherDislike" placeholder="Other" onChange={handleChange} />
          </>
        )}
      </div>

      {/* Allergies Section */}
      <div className="toggle-checkbox-block">
        <div className="toggle-header" onClick={() => setShowAllergies(!showAllergies)}>
          <div className="fav-wrapper" >
            <img src="/allergy.png" alt="Logo" className="fav-wrapper" />
          </div>
          <span>Allergic to Something? Safety First.</span>
          <span className="plus-icon">{showAllergies ? "×" : "+"}</span>
        </div>
        {showAllergies && (
          <>
            <div className="checkbox-group">
              {categories.allergies.map((item, i) => (
                <label key={i} className="custom-checkbox">
                  <input type="checkbox" value={item} onChange={(e) => handleCheckboxChange(e, "allergies")} />
                  <div className="checkbox-box">{item}</div>
                </label>
              ))}
            </div>
            <input name="otherAllergy" placeholder="Other" onChange={handleChange} />
          </>
        )}
      </div>

      <button
        onClick={handleSignup}
        disabled={!form.email || !form.password || !form.name || !form.gender}
      >
        Register
      </button>

    </div>
  </div>
);

}

export default Signup;

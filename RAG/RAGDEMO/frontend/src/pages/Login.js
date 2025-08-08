import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import "./Login.css";


function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const savedEmail = localStorage.getItem("rememberedEmail");
    const savedPassword = localStorage.getItem("rememberedPassword");

    if (savedEmail && savedPassword) {
      setEmail(savedEmail);
      setPassword(savedPassword);
      setRememberMe(true);
    }
  }, []);

  useEffect(() => {
    if (errorMessage) {
      setErrorMessage("");
    }
  }, [email, password, rememberMe]);

  const handleLogin = async (e) => {
    e.preventDefault();

    setIsLoading(true);
    setErrorMessage("");

    try {
      const res = await fetch("http://172.20.10.3:8001/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (res.ok) {
        const data = await res.json(); // <--- Parse the JSON response here

        // --- ADD THIS LINE HERE ---
        // Assuming your backend's /login endpoint returns a 'user_id' in the response body
        if (data.user_id) {
            localStorage.setItem("user_id", data.user_id);
            console.log("User ID saved to localStorage:", data.user_id); // For debugging
        } else {
            console.warn("Login successful, but no 'user_id' found in the response from the backend.");
            // You might want to handle this case, e.g., display a specific message
        }
        // --- END OF ADDITION ---

        if (rememberMe) {
          localStorage.setItem("rememberedEmail", email);
          localStorage.setItem("rememberedPassword", password);
        } else {
          localStorage.removeItem("rememberedEmail");
          localStorage.removeItem("rememberedPassword");
        }

        localStorage.setItem("userEmail", email);
        navigate("/chat");
      } else {
        const err = await res.json();
        setErrorMessage("Login failed: " + (err.detail || "Unknown error."));
      }
    } catch (error) {
      setErrorMessage("Network error. Please try again.");
      console.error("Login fetch error:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="signin-wrapper">
      <div className="signin-form">
        <h2 className="signin-header">
          <img img src="/logo5.png" alt="Logo" className="signin-logo" />
          Sign In
        </h2>
        <form onSubmit={handleLogin}>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={isLoading}
          />

          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={isLoading}
          />

          <div className="remember-me-wrapper">
            <div className="remember-me">
              <input
                type="checkbox"
                id="remember"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                disabled={isLoading}
              />
              <label htmlFor="remember">Remember Me</label>
            </div>
          </div>

          {errorMessage && <p style={{ color: 'red', textAlign: 'center', margin: '10px 0' }}>{errorMessage}</p>}

          <button type="submit" disabled={isLoading}>
            {isLoading ? "Logging In..." : "Let's Go!"}
          </button>
        </form>
        <p className="form-switch-text">
          Don't Have an Account Yet?{" "}
          <span className="form-link" onClick={() => navigate("/signup")}>
            Register Now
          </span>
        </p>
      </div>
    </div>
  );
}

export default Login;
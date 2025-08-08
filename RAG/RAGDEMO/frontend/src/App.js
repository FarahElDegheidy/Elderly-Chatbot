import {
  BrowserRouter as Router,
  Routes,
  Route,
  useLocation,
} from "react-router-dom";
import Signup from "./pages/Signup";
import Login from "./pages/Login";
import Chat from "./pages/chat1";
import Home from "./pages/Home";
import "./App.css";
import CalendarConnected from './pages/CalendarConnected';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/login" element={<Login />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/calendar-connected" element={<CalendarConnected />} /> 
      </Routes>
    </Router>
  );
}


export default App;

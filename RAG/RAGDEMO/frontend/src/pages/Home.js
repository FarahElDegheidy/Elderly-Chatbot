import { Link } from "react-router-dom";
import "./Home.css";
import { Utensils, MessageCircle, Clock, Bookmark, HeartHandshake } from 'lucide-react';

function Home() {
  return (
    <div className="homepage-wrapper">
      {/* The homepage-content typically sets up the main content's position/width on the page */}
      <main className="homepage-content">
        {/* The content-box now wraps all the specific elements you want to be inside the "nice box" */}
        <div className="content-box">
          <div className="main-header-block">
            {/* Note: Ensure /logo.png is correctly accessible from your public folder or assets setup */}
            <img src="/logo5.png" alt="App Logo" className="app-logo" />
            <h1 className="animated-blue-heading">Chatterly</h1>


          </div>
          <p className="subtitle">
            From Kitchen Dips to The World at Your Tips.
          </p>

          <ul className="feature-list">
            <li><Utensils size={18} /> Suggests recipes based on your preferences</li>
            <li><MessageCircle size={18} /> Converses with you in Egyptian Arabic</li>
            <li><Clock size={18} /> Recommends meals based on time of day</li>
            <li><Bookmark size={18} /> Save your favorites & access them anytime</li>
            <li><HeartHandshake size={18} /> Optimized experience for elderly users</li>
          </ul>

          <div className="button-group">
            <Link to="/signup">
              <button className="btn primary-btn">New to Chatterly? Sign Up Here!</button>
            </Link>
            <Link to="/login">
              <button className="btn secondary-btn">Sign In</button>
            </Link>
          </div>
        </div> {/* End of content-box */}
      </main>
    </div> 
  );
}

export default Home;